import json
import os
from datetime import datetime, timedelta
import time

import tweepy

from sqlalchemy import select, update
from sqlalchemy.sql import text
from db import (
    JobDetails,
    User,
    Tip,
    Nag,
    Tweet,
    Thread,
    Fascist,
    Like,
    session as db_session,
    engine as db_engine,
)

from common import (
    log,
    tweepy_client,
    tweepy_semiphemeral_client,
    tweepy_api_v1_1,
    tweepy_dms_api_v1_1,
    tweepy_semiphemeral_api_1_1,
    add_job,
    add_dm_job,
)


class JobCanceled(Exception):
    pass


# Exception helpers


def handle_tweepy_rate_limit(job_details, e, api_endpoint):
    reset_time = e.response.headers.get("x-rate-limit-reset")
    if reset_time is None:
        # wait 1 minute, if for some reason we don't get a x-rate-limit-reset header
        reset_time = int(time.time()) + 60
    else:
        reset_time = int(reset_time)
    sleep_time = reset_time - int(time.time())
    if sleep_time > 0:
        log(
            job_details,
            f"Rate limit on {api_endpoint}, sleeping {sleep_time}s",
        )
        time.sleep(sleep_time + 1)  # sleep for extra sec


def handle_tweepy_exception(job_details, e, api_endpoint):
    log(job_details, f"Error on {api_endpoint}, sleeping 120s: {e}")
    time.sleep(120)


# Decorators


def test_api_creds(func):
    def wrapper(job_details_id, funcs):
        """
        Make sure the API creds work, and if not pause semiphemeral for the user
        """
        job_details = db_session.scalar(
            select(JobDetails).where(JobDetails.id == job_details_id)
        )
        user = db_session.scalar(select(User).where(User.id == job_details.user_id))
        if user:
            api = tweepy_api_v1_1(user)
            try:
                api.verify_credentials()
            except tweepy.errors.Unauthorized:
                print(
                    f"user_id={user.id} API creds failed, canceling job and pausing user"
                )
                user.paused = True
                db_session.add(user)

                job_details.status = "canceled"
                job_details.finished_timestamp = datetime.now()
                db_session.add(job_details)

                db_session.commit()
                db_session.close()
                return False

        return func(job_details_id, funcs)

    return wrapper


# Fetch job


@test_api_creds
def fetch(job_details_id, funcs):
    job_details = db_session.scalar(
        select(JobDetails).where(JobDetails.id == job_details_id)
    )

    # Don't disconnect from the db if this is a delete job
    disconnect = job_details.job_type == "fetch"

    if job_details.status == "canceled":
        log(job_details, "Job already canceled, quitting early")
        if disconnect:
            db_session.close()
        return

    job_details.status = "active"
    job_details.started_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()

    log(job_details, str(job_details))

    user = db_session.scalar(select(User).where(User.id == job_details.user_id))
    if not user:
        log(job_details, "User not found, canceling job")
        job_details.status = "canceled"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        if disconnect:
            db_session.close()
        return

    api = tweepy_api_v1_1(user)
    since_id = user.since_id

    log(job_details, f"Fetch started")

    # Start the data
    data = {"progress": {"tweets_fetched": 0, "likes_fetched": 0}}
    if since_id:
        data["progress"]["status"] = "Downloading all recent tweets"
    else:
        data["progress"][
            "status"
        ] = "Downloading all tweets, this first run may take a long time"
        log(job_details, "since_id is None, so downloading everything")

    job_details.data = json.dumps(data)
    db_session.add(job_details)
    db_session.commit()

    # In API v1.1 we don't get conversation_id, so we have to make a zillion requests to figure it out ourselves.
    # This dict helps to cache that so we can avoid requests. Each item is a tuple (id, in_reply_to_id)
    cache = {}

    # Fetch tweets
    while True:
        try:
            for page in tweepy.Cursor(
                api.user_timeline, user_id=user.twitter_id, count=200, since_id=since_id
            ).pages():
                log(job_details, f"Importing {len(page)} tweets")
                for status in page:
                    # Get the conversation_id of this tweet
                    conversation_id = status.id_str
                    if status.in_reply_to_status_id_str is not None:
                        in_reply_to_id = status.in_reply_to_status_id_str
                        while True:
                            if in_reply_to_id in cache:
                                _id, _in_reply_to_id = cache[in_reply_to_id]
                            else:
                                try:
                                    response = api.get_status(in_reply_to_id)
                                    _id = response.id_str
                                    _in_reply_to_id = response.in_reply_to_status_id_str
                                    cache[in_reply_to_id] = (_id, _in_reply_to_id)
                                except:
                                    break

                            if _in_reply_to_id is None:
                                conversation_id = _id
                                break
                            else:
                                conversation_id = _id
                                in_reply_to_id = _in_reply_to_id

                    # Make sure we have a thread for this tweet
                    thread = db_session.scalar(
                        select(Thread)
                        .where(Thread.user_id == user.id)
                        .where(Thread.conversation_id == conversation_id)
                    )
                    if not thread:
                        thread = Thread(
                            user_id=user.id,
                            conversation_id=conversation_id,
                            should_exclude=False,
                        )
                        db_session.add(thread)
                        db_session.commit()

                    # Save or update the tweet
                    tweet = db_session.scalar(
                        select(Tweet)
                        .where(Tweet.user_id == user.id)
                        .where(Tweet.twitter_id == status.id_str)
                    )

                    is_retweet = hasattr(status, "retweeted_status")
                    if is_retweet:
                        retweet_id = status.retweeted_status.id_str
                    else:
                        retweet_id = None

                    is_reply = status.in_reply_to_status_id_str is not None

                    if not tweet:
                        tweet = Tweet(
                            user_id=user.id,
                            twitter_id=status.id_str,
                            created_at=status.created_at.replace(tzinfo=None),
                            text=status.text,
                            is_retweet=is_retweet,
                            retweet_id=retweet_id,
                            is_reply=is_reply,
                            retweet_count=status.retweet_count,
                            like_count=status.favorite_count,
                            exclude_from_delete=False,
                            is_deleted=False,
                            thread_id=thread.id,
                        )
                    else:
                        tweet.text = status.text
                        tweet.is_retweet = is_retweet
                        tweet.retweet_id = retweet_id
                        tweet.is_reply = is_reply
                        tweet.retweet_count = status.retweet_count
                        tweet.like_count = status.favorite_count
                        tweet.thread_id = thread.id

                    db_session.add(tweet)
                    data["progress"]["tweets_fetched"] += 1

                job_details.data = json.dumps(data)
                db_session.add(job_details)
                db_session.commit()
            break
        except tweepy.errors.TwitterServerError as e:
            handle_tweepy_exception(job_details, e, "api.user_timeline")

    # Update progress
    if since_id:
        data["progress"]["status"] = "Downloading all recent likes"
    else:
        data["progress"][
            "status"
        ] = "Downloading all likes, this first run may take a long time"
    job_details.data = json.dumps(data)
    db_session.add(job_details)
    db_session.commit()

    # Fetch likes
    while True:
        try:
            for page in tweepy.Cursor(
                api.get_favorites, user_id=user.twitter_id, count=200, since_id=since_id
            ).pages():
                log(job_details, f"Importing {len(page)} likes")
                for status in page:
                    # Is the like already saved?
                    like = db_session.scalar(
                        select(Like)
                        .where(Like.user_id == user.id)
                        .where(Like.twitter_id == status.id_str)
                    )
                    if not like:
                        fascist = db_session.scalar(
                            select(Fascist).where(
                                Fascist.twitter_id == status.user.id_str
                            )
                        )
                        is_fascist = fascist is not None

                        # Save the like
                        like = Like(
                            user_id=user.id,
                            twitter_id=status.id_str,
                            created_at=status.created_at.replace(tzinfo=None),
                            author_id=status.user.id_str,
                            is_deleted=False,
                            is_fascist=is_fascist,
                        )
                        db_session.add(like)

                    data["progress"]["likes_fetched"] += 1

                job_details.data = json.dumps(data)
                db_session.add(job_details)
                db_session.commit()

            break
        except tweepy.errors.TwitterServerError as e:
            handle_tweepy_exception(job_details, e, "api.user_timeline")

    # All done, update the since_id
    with db_engine.connect() as conn:
        new_since_id = conn.execute(
            text(
                "SELECT twitter_id FROM tweets WHERE user_id=:user_id ORDER BY CAST(twitter_id AS bigint) DESC LIMIT 1",
            ),
            {"user_id": user.id},
        ).scalar()

    user.since_id = new_since_id
    db_session.add(user)
    db_session.commit()

    # Based on the user's settings, figure out which threads should be excluded from deletion,
    # and which threads should have their tweets deleted

    # Calculate which threads should be excluded from deletion
    data["progress"]["status"] = "Calculating which threads to exclude from deletion"
    job_details.data = json.dumps(data)
    db_session.add(job_details)
    db_session.commit()

    # Reset the should_exclude flag for all threads
    db_session.execute(
        update(Thread)
        .values({"should_exclude": False})
        .where(Thread.user_id == user.id)
    )

    # Set should_exclude for all threads based on the settings
    if user.tweets_threads_threshold:
        threads = db_session.scalars(
            select(Thread)
            .join(Thread.tweets)
            .where(Thread.id == Tweet.thread_id)
            .where(Thread.user_id == user.id)
            .where(Tweet.user_id == user.id)
            .where(Tweet.is_deleted == False)
            .where(Tweet.is_retweet == False)
            .where(Tweet.retweet_count >= user.tweets_retweet_threshold)
            .where(Tweet.like_count >= user.tweets_like_threshold)
        ).fetchall()
        for thread in threads:
            thread.should_exclude = True
            db_session.add(thread)

        db_session.commit()

    data["progress"]["status"] = "Finished"
    job_details.data = json.dumps(data)
    db_session.add(job_details)
    db_session.commit()

    # Has this user liked any fascist tweets?
    six_months_ago = datetime.now() - timedelta(days=180)
    fascist_likes = db_session.scalars(
        select(Like)
        .where(Like.user_id == user.id)
        .where(Like.is_fascist == True)
        .where(Like.created_at > six_months_ago)
    ).fetchall()
    if len(fascist_likes) > 4:
        # Create a block job
        add_job(
            "block",
            None,
            funcs,
            data={
                "twitter_username": user.twitter_screen_name,
                "twitter_id": user.twitter_id,
                "user_id": user.id,
            },
            job_timeout="10m",
        )

        job_details.status = "finished"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()

        # Don't send any DMs
        log(job_details, f"Blocking user")
        if disconnect:
            db_session.close()
        return

    # Fetch is done! If semiphemeral is paused, send a DM
    # (If it's not paused, then this should actually be a delete job, and delete will run next)
    if user.paused:
        if not since_id:
            message = f"Good news! Semiphemeral finished downloading a copy of all {data['progress']['tweets_fetched']:,} of your tweets and all {data['progress']['likes_fetched']:,} of your likes.\n\n"
        else:
            message = f"Semiphemeral finished downloading {data['progress']['tweets_fetched']:,} new tweets and {data['progress']['likes_fetched']:,} new likes.\n\n"

        message += f"The next step is look through your tweets and manually mark which ones you want to make sure never get deleted. Visit https://{os.environ.get('DOMAIN')}/tweets to finish.\n\nWhen you're done, you can start deleting your tweets from the dashboard."

        # Create DM job
        add_dm_job(funcs, user.twitter_id, message)

    job_details.status = "finished"
    job_details.finished_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()

    log(job_details, f"Fetch finished")
    db_session.close()


# Delete job


@test_api_creds
def delete(job_details_id, funcs):
    job_details = db_session.scalar(
        select(JobDetails).where(JobDetails.id == job_details_id)
    )
    if job_details.status == "canceled":
        log(job_details, "Job already canceled, quitting early")
        db_session.close()
        return

    job_details.status = "active"
    job_details.started_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, str(job_details))

    user = db_session.scalar(select(User).where(User.id == job_details.user_id))
    if not user:
        log(job_details, "User not found, canceling job")
        job_details.status = "canceled"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        db_session.close()
        return

    api = tweepy_api_v1_1(user)
    log(job_details, "Delete started")

    # Start the progress
    data = json.loads(job_details.data)
    data["progress"]["tweets_deleted"] = 0
    data["progress"]["retweets_deleted"] = 0
    data["progress"]["likes_deleted"] = 0
    data["progress"]["dms_deleted"] = 0

    # Unretweet and unlike tweets
    if user.retweets_likes:

        # Unretweet
        if user.retweets_likes_delete_retweets:
            days = user.retweets_likes_retweets_threshold
            if days > 99999:
                days = 99999
            datetime_threshold = datetime.utcnow() - timedelta(days=days)

            tweets = db_session.scalars(
                select(Tweet)
                .where(Tweet.user_id == user.id)
                .where(Tweet.is_deleted == False)
                .where(Tweet.is_retweet == True)
                .where(Tweet.created_at < datetime_threshold)
                .order_by(Tweet.created_at)
            ).fetchall()

            data["progress"][
                "status"
            ] = f"Deleting {len(tweets):,} retweets, starting with the earliest"
            job_details.data = json.dumps(data)
            db_session.add(job_details)
            db_session.commit()

            for tweet in tweets:
                # Delete retweet
                try:
                    api.destroy_status(tweet.twitter_id)
                except Exception as e:
                    pass
                    # log(
                    #     job_details,
                    #     f"Error deleting retweet {tweet.twitter_id}: {e}",
                    # )

                tweet.is_deleted = True
                db_session.add(tweet)

                data["progress"]["retweets_deleted"] += 1
                job_details.data = json.dumps(data)
                db_session.add(job_details)

                db_session.commit()

        # Unlike
        if user.retweets_likes_delete_likes:
            days = user.retweets_likes_likes_threshold
            if days > 99999:
                days = 99999
            datetime_threshold = datetime.utcnow() - timedelta(days=days)
            likes = db_session.scalars(
                select(Like)
                .where(Like.user_id == user.id)
                .where(Like.is_deleted == False)
                .where(Like.created_at < datetime_threshold)
                .order_by(Like.created_at)
            ).fetchall()

            data["progress"][
                "status"
            ] = f"Unliking {len(likes):,} tweets, starting with the earliest"
            job_details.data = json.dumps(data)
            db_session.add(job_details)
            db_session.commit()

            for like in likes:
                # Delete like

                try:
                    api.destroy_favorite(like.twitter_id)
                except Exception as e:
                    pass
                    # log(
                    #     job_details, f"Error deleting like {like.twitter_id}: {e}"
                    # )

                like.is_deleted = True
                db_session.add(like)

                data["progress"]["likes_deleted"] += 1
                job_details.data = json.dumps(data)
                db_session.add(job_details)

                db_session.commit()

    # Deleting tweets
    if user.delete_tweets:
        # Figure out the tweets to delete
        try:
            datetime_threshold = datetime.utcnow() - timedelta(
                days=user.tweets_days_threshold
            )
        except OverflowError:
            # If we get "OverflowError: date value out of range", set the date to July 1, 2006,
            # shortly before Twitter was launched
            datetime_threshold = datetime(2006, 7, 1)

        statement = (
            select(Tweet)
            .join(Tweet.thread)
            .where(Tweet.user_id == user.id)
            .where(Tweet.is_deleted == False)
            .where(Tweet.is_retweet == False)
            .where(Tweet.created_at < datetime_threshold)
            .where(Tweet.exclude_from_delete == False)
            .where(Thread.should_exclude == False)
        )
        if user.tweets_enable_retweet_threshold:
            statement = statement.where(
                Tweet.retweet_count < user.tweets_retweet_threshold
            )
        if user.tweets_enable_like_threshold:
            statement = statement.where(Tweet.like_count < user.tweets_like_threshold)

        tweets = db_session.scalars(statement).fetchall()

        data["progress"][
            "status"
        ] = f"Deleting {len(tweets):,} tweets, starting with the earliest"
        job_details.data = json.dumps(data)
        db_session.add(job_details)
        db_session.commit()

        for tweet in tweets:
            # Delete tweet
            try:
                api.destroy_status(tweet.twitter_id)
            except Exception as e:
                pass
                # log(job_details, f"Error deleting tweet {tweet.twitter_id}: {e}")

            tweet.is_deleted = True
            db_session.add(tweet)

            data["progress"]["tweets_deleted"] += 1
            job_details.data = json.dumps(data)
            db_session.add(job_details)

            db_session.commit()

    # Deleting direct messages
    if user.direct_messages:
        dm_client = tweepy_client(user, dms=True)
        dm_api = tweepy_dms_api_v1_1(user)

        # Make sure the DMs API authenticates successfully
        proceed = False
        try:
            dm_client.get_me()
            proceed = True
        except Exception as e:
            # It doesn't, so disable deleting direct messages
            user.direct_messages = False
            user.twitter_dms_access_token = ""
            user.twitter_dms_access_token_secret = ""
            db_session.add(user)
            db_session.commit()

        if proceed:
            data["progress"]["status"] = f"Deleting direct messages"
            job_details.data = json.dumps(data)
            db_session.add(job_details)
            db_session.commit()

            datetime_threshold = datetime.utcnow() - timedelta(
                days=user.direct_messages_threshold
            )

            # Fetch DMs
            dms = []
            pagination_token = None
            while True:
                while True:
                    try:
                        response = dm_client.get_direct_message_events(
                            dm_event_fields=["created_at"],
                            event_types="MessageCreate",
                            max_results=100,
                            pagination_token=pagination_token,
                            user_auth=True,
                        )
                        break
                    except Exception as e:
                        handle_tweepy_exception(
                            job_details, e, "dm_client.get_direct_message_events"
                        )

                if response["meta"]["result_count"] == 0:
                    log(job_details, f"No new DMs")
                    break

                dms.extend(response["data"])

                if "next_token" in response["meta"]:
                    pagination_token = response["meta"]["next_token"]
                else:
                    # all done
                    break

            for dm in dms:
                created_timestamp = datetime.fromisoformat(dm["created_at"][0:19])
                if created_timestamp <= datetime_threshold:
                    # Delete the DM
                    try:
                        dm_api.delete_direct_message(dm["id"])
                    except Exception as e:
                        pass
                        # log(job_details, f"Skipping DM {dm['id']}, {e}")

                    data["progress"]["dms_deleted"] += 1
                    job_details.data = json.dumps(data)
                    db_session.add(job_details)
                    db_session.commit()

    data["progress"]["status"] = "Finished"
    job_details.data = json.dumps(data)
    job_details.status = "finished"
    job_details.finished_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, f"Delete finished")

    # Delete is done!

    # Schedule the next delete job
    scheduled_timestamp = datetime.now() + timedelta(days=1)
    add_job("delete", user.id, funcs, scheduled_timestamp=scheduled_timestamp)

    # Has the user tipped in the last year?
    one_year = timedelta(days=365)
    tipped_in_the_last_year = db_session.scalar(
        select(Tip)
        .where(Tip.user_id == user.id)
        .where(Tip.paid == True)
        .where(Tip.refunded == False)
        .where(Tip.timestamp > datetime.now() - one_year)
        .order_by(Tip.timestamp.desc())
    )

    # Should we nag the user?
    one_month_ago = datetime.now() - timedelta(days=30)
    last_nag = db_session.scalar(
        select(Nag).where(Nag.user_id == user.id).order_by(Nag.timestamp.desc())
    )

    should_nag = False
    if not tipped_in_the_last_year:
        if not last_nag:
            should_nag = True
        elif last_nag.timestamp < one_month_ago and not tipped_in_the_last_year:
            should_nag = True

    if not last_nag:
        log(job_details, f"Nagging the user for the first time")

        # Create a nag
        nag = Nag(
            user_id=user.id,
            timestamp=datetime.now(),
        )
        db_session.add(nag)
        db_session.commit()

        # The user has never been nagged, so this is the first delete
        message = f"Congratulations! Semiphemeral has deleted {data['progress']['tweets_deleted']:,} tweets, unretweeted {data['progress']['retweets_deleted']:,} tweets, and unliked {data['progress']['likes_deleted']:,} tweets. Doesn't that feel nice?\n\nEach day, I will download your latest tweets and likes and then delete the old ones based on your settings. You can sit back, relax, and enjoy the privacy.\n\nYou can always change your settings, mark new tweets to never delete, and pause Semiphemeral from the website https://{os.environ.get('DOMAIN')}/dashboard."
        add_dm_job(funcs, user.twitter_id, message)

        message = f"Semiphemeral is free, but running this service costs money. Care to chip in?\n\nIf you tip any amount, even just $1, I will stop nagging you for a year. Otherwise, I'll gently remind you once a month.\n\n(It's fine if you want to ignore these DMs. I won't care. I'm a bot, so I don't have feelings).\n\nVisit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"
        add_dm_job(funcs, user.twitter_id, message)

    else:
        if should_nag:
            log(job_details, f"Nagging the user again")

            # Create a nag
            nag = Nag(
                user_id=user.id,
                timestamp=datetime.now(),
            )
            db_session.add(nag)
            db_session.commit()

            # The user has been nagged before -- do some math to get the totals

            # Get all the delete jobs
            total_progress = {
                "tweets_deleted": 0,
                "retweets_deleted": 0,
                "likes_deleted": 0,
            }
            total_progress_since_last_nag = {
                "tweets_deleted": 0,
                "retweets_deleted": 0,
                "likes_deleted": 0,
            }
            job_details = db_session.scalars(
                select(JobDetails)
                .where(JobDetails.user_id == user.id)
                .where(JobDetails.job_type == "delete")
                .where(JobDetails.status == "finished")
            ).fetchall()
            for job_detail in job_details:
                if job_detail.data:
                    _data = json.loads(job_detail.data)

                    if "progress" in _data and "tweets_deleted" in _data["progress"]:
                        total_progress["tweets_deleted"] += _data["progress"][
                            "tweets_deleted"
                        ]
                    if "progress" in _data and "retweets_deleted" in _data["progress"]:
                        total_progress["retweets_deleted"] += _data["progress"][
                            "retweets_deleted"
                        ]
                    if "progress" in _data and "likes_deleted" in _data["progress"]:
                        total_progress["likes_deleted"] += _data["progress"][
                            "likes_deleted"
                        ]

                    if job_detail.finished_timestamp > last_nag.timestamp:
                        if (
                            "progress" in _data
                            and "tweets_deleted" in _data["progress"]
                        ):
                            total_progress_since_last_nag["tweets_deleted"] += _data[
                                "progress"
                            ]["tweets_deleted"]
                        if (
                            "progress" in _data
                            and "retweets_deleted" in _data["progress"]
                        ):
                            total_progress_since_last_nag["retweets_deleted"] += _data[
                                "progress"
                            ]["retweets_deleted"]
                        if "progress" in _data and "likes_deleted" in _data["progress"]:
                            total_progress_since_last_nag["likes_deleted"] += _data[
                                "progress"
                            ]["likes_deleted"]

            message = f"Since you've been using Semiphemeral, I have deleted {total_progress['tweets_deleted']:,} tweets, unretweeted {total_progress['retweets_deleted']:,} tweets, and unliked {total_progress['likes_deleted']:,} tweets for you.\n\nJust since last month, I've deleted {total_progress_since_last_nag['tweets_deleted']:,} tweets, unretweeted {total_progress_since_last_nag['retweets_deleted']:,} tweets, and unliked {total_progress_since_last_nag['likes_deleted']:,} tweets.\n\nSemiphemeral is free, but running this service costs money. Care to chip in? Visit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"
            add_dm_job(funcs, user.twitter_id, message)

    db_session.close()


# Delete DMs and DM Groups jobs


@test_api_creds
def delete_dms(job_details_id, funcs):
    delete_dms_job(job_details_id, "dms", funcs)
    db_session.close()


@test_api_creds
def delete_dm_groups(job_details_id, funcs):
    delete_dms_job(job_details_id, "groups", funcs)
    db_session.close()


def delete_dms_job(job_details_id, dm_type, funcs):
    job_details = db_session.scalar(
        select(JobDetails).where(JobDetails.id == job_details_id)
    )
    if job_details.status == "canceled":
        log(job_details, "Job already canceled, quitting early")
        db_session.close()
        return

    job_details.status = "active"
    job_details.started_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, str(job_details))

    user = db_session.scalar(select(User).where(User.id == job_details.user_id))
    if not user:
        log(job_details, "User not found, canceling job")
        job_details.statis = "canceled"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        return

    dm_client = tweepy_client(user, dms=True)
    dm_api = tweepy_dms_api_v1_1(user)

    # Make sure the DMs API authenticates successfully
    try:
        dm_client.get_me()
    except Exception as e:
        # It doesn't, so disable deleting direct messages
        log(job_details, f"DMs Twitter API creds don't work, canceling job")
        job_details.status = "canceled"
        job_details.started_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        return

    if dm_type == "dms":
        log(job_details, f"Delete DMs started")
    elif dm_type == "groups":
        log(job_details, f"Delete group DMs started")

    # Start the progress
    data = {
        "progress": {
            "dms_deleted": 0,
            "dms_skipped": 0,
            "status": "Verifying permissions",
        }
    }
    job_details.data = json.dumps(data)
    db_session.add(job_details)
    db_session.commit()

    # Make sure deleting DMs is enabled
    if not user.direct_messages:
        log(job_details, f"Deleting DMs is not enabled, canceling job")
        job_details.status = "canceled"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        return

    # Load the DM metadata
    if dm_type == "dms":
        filename = os.path.join("/var/bulk_dms", f"dms-{user.id}.json")
    elif dm_type == "groups":
        filename = os.path.join("/var/bulk_dms", f"groups-{user.id}.json")
    if not os.path.exists(filename):
        log(
            job_details,
            f"Filename {filename} does not exist, canceling job",
        )
        job_details.status = "canceled"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        return
    with open(filename) as f:
        try:
            conversations = json.loads(f.read())
        except:
            log(job_details, f"Cannot decode JSON, canceling job")
            job_details.status = "canceled"
            job_details.finished_timestamp = datetime.now()
            db_session.add(job_details)
            db_session.commit()
            return

    # Delete DMs
    data["progress"]["status"] = "Deleting old direct messages"
    job_details.data = json.dumps(data)
    db_session.add(job_details)
    db_session.commit()

    datetime_threshold = datetime.utcnow() - timedelta(
        days=user.direct_messages_threshold
    )
    for obj in conversations:
        conversation = obj["dmConversation"]
        for message in conversation["messages"]:
            if "messageCreate" in message:
                created_str = message["messageCreate"]["createdAt"]
                created_timestamp = datetime.strptime(
                    created_str, "%Y-%m-%dT%H:%M:%S.%fZ"
                )
                if created_timestamp <= datetime_threshold:
                    dm_id = message["messageCreate"]["id"]

                    # Delete the DM
                    try:
                        dm_api.delete_direct_message(dm_id)
                        data["progress"]["dms_deleted"] += 1
                    except Exception as e:
                        log(job_details, f"Error deleting DM {dm_id}, {e}")
                        data["progress"]["dms_skipped"] += 1

                    job_details.data = json.dumps(data)
                    db_session.add(job_details)
                    db_session.commit()

    # Delete the DM metadata file
    try:
        os.remove(filename)
    except:
        pass

    data["progress"]["status"] = "Finished"
    job_details.data = json.dumps(data)
    job_details.status = "finished"
    job_details.finished_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, f"Delete DMs finished")

    # Send a DM to the user
    if dm_type == "dms":
        message = f"Congratulations, Semiphemeral just finished deleting {data['progress']['dms_deleted']:,} of your old direct messages."
    elif dm_type == "groups":
        message = f"Congratulations, Semiphemeral just finished deleting {data['progress']['dms_deleted']:,} of your old group direct messages."
    add_dm_job(funcs, user.twitter_id, message)

    log(job_details, f"Delete DMs ({dm_type}) finished")


# Block job


def block(job_details_id, funcs):
    job_details = db_session.scalar(
        select(JobDetails).where(JobDetails.id == job_details_id)
    )
    if job_details.status == "canceled":
        log(job_details, "Job already canceled, quitting early")
        db_session.close()
        return

    job_details.status = "active"
    job_details.started_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, str(job_details))

    data = json.loads(job_details.data)

    semiphemeral_client = tweepy_semiphemeral_client()

    # If we're blocking a semiphemeral user, and not just a fascist influencer
    if "user_id" in data:
        user = db_session.scalar(select(User).where(User.id == data["user_id"]))
        if user and not user.blocked:
            # Update the user
            user.paused = True
            user.blocked = True
            db_session.add(user)
            db_session.commit()

            # Get all the recent fascist likes
            six_months_ago = datetime.now() - timedelta(days=180)
            fascist_likes = db_session.scalars(
                select(Like)
                .where(Like.user_id == user.id)
                .where(Like.is_fascist == True)
                .where(Like.created_at > six_months_ago)
            ).fetchall()

            # When do we unblock them?
            last_fascist_like = db_session.scalar(
                select(Like)
                .where(Like.user_id == user.id)
                .where(Like.is_fascist == True)
                .order_by(Like.created_at.desc())
            )
            if last_fascist_like:
                unblock_timestamp = last_fascist_like.created_at + timedelta(days=180)
            else:
                unblock_timestamp = datetime.now() + timedelta(days=180)
            unblock_timestamp_formatted = unblock_timestamp.strftime("%B %-d, %Y")

            # Send the DM
            message = f"You have liked {len(fascist_likes):,} tweets from a prominent fascist or fascist sympathizer within the last 6 months, so you have been blocked and your Semiphemeral account is deactivated.\n\nTo see which tweets you liked and learn how to get yourself unblocked, see https://{os.environ.get('DOMAIN')}/dashboard.\n\nOr you can wait until {unblock_timestamp_formatted} when you will get automatically unblocked, at which point you can login to reactivate your account so long as you've stop liking tweets from fascists."
            add_dm_job(funcs, user.twitter_id, message)

            # Wait 65 seconds before blocking, to ensure they receive the DM
            time.sleep(65)

            # Create the unblock job
            add_job(
                "unblock",
                None,
                funcs,
                data={
                    "user_id": user.id,
                    "twitter_username": user.twitter_screen_name,
                    "twitter_id": user.twitter_id,
                },
                job_timeout="10m",
                scheduled_timestamp=unblock_timestamp,
            )

        # Block the user
        try:
            semiphemeral_client.block(data["twitter_id"], user_auth=True)
        except Exception as e:
            log(job_details, f"Error blocking user @{data['twitter_username']}, {e}")

    # Finished
    job_details.status = "finished"
    job_details.finished_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, f"Block finished")
    db_session.close()


# Unblock job


def unblock(job_details_id, funcs):
    job_details = db_session.scalar(
        select(JobDetails).where(JobDetails.id == job_details_id)
    )
    if job_details.status == "canceled":
        log(job_details, "Job already canceled, quitting early")
        db_session.close()
        return

    job_details.status = "active"
    job_details.started_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, str(job_details))

    data = json.loads(job_details.data)

    semiphemeral_client = tweepy_semiphemeral_client()

    # Unblock the user
    try:
        semiphemeral_client.unblock(data["twitter_id"], user_auth=True)
    except Exception as e:
        log(job_details, f"Error unblocking user @{data['twitter_username']}, {e}")

    # If we're unblocking a semiphemeral user
    if "user_id" in data:
        user = db_session.scalar(select(User).where(User.id == data["user_id"]))
        if user and user.blocked:
            # Update the user
            user.paused = True
            user.blocked = False
            db_session.add(user)
            db_session.commit()
            log(
                job_details,
                f"User @{data['twitter_username']} unblocked in semiphemeral db",
            )

    # Finished
    job_details.status = "finished"
    job_details.finished_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, f"Unblock finished")
    db_session.close()


# DM job


def dm(job_details_id, funcs):
    job_details = db_session.scalar(
        select(JobDetails).where(JobDetails.id == job_details_id)
    )
    if job_details.status == "canceled":
        log(job_details, "Job already canceled, quitting early")
        db_session.close()
        return

    job_details.status = "active"
    job_details.started_timestamp = datetime.now()
    db_session.add(job_details)
    db_session.commit()
    log(job_details, str(job_details))

    data = json.loads(job_details.data)

    # Make sure the user follows us
    user = db_session.scalar(select(User).where(User.id == job_details.user_id))
    if user:
        # Make an exception for semiphemeral user, because semiphemeral can't follow semiphemeral
        if user.twitter_screen_name != "semiphemeral":
            api = tweepy_api_v1_1(user)

            # Is this user following us?
            try:
                res = api.lookup_friendships(user_id=["1209344563589992448"])
            except tweepy.errors.Forbidden as e:
                # User is suspended, canceling job and pausing using
                log(
                    job_details,
                    f"User is suspended, pausing user and canceling job: {e}",
                )
                user.paused = True
                db_session.add(user)

                job_details.status = "canceled"
                job_details.finished_timestamp = datetime.now()
                db_session.add(job_details)

                db_session.commit()
                db_session.close()
                return

            if len(res) > 0:
                relationship = res[0]
                if not relationship.is_following:
                    # Try following
                    try:
                        api.create_friendship(
                            user_id="1209344563589992448"  # @semiphemeral twitter ID
                        )
                        log(
                            job_details,
                            f"@{user.twitter_screen_name} followed @semiphemeral",
                        )
                    except Exception as e:
                        log(
                            job_details,
                            f"Error on api.create_friendship with v1.1 API, try again in an hour: {e}",
                        )
                        scheduled_timestamp = datetime.now() + timedelta(hours=1)
                        add_dm_job(
                            funcs,
                            data["dest_twitter_id"],
                            data["message"],
                            scheduled_timestamp=scheduled_timestamp,
                        )

                        job_details.status = "canceled"
                        job_details.finished_timestamp = datetime.now()
                        db_session.add(job_details)
                        db_session.commit()
                        db_session.close()
                        return

    # Send the DM
    semiphemeral_api = tweepy_semiphemeral_api_1_1()
    try:
        semiphemeral_api.send_direct_message(
            recipient_id=data["dest_twitter_id"], text=data["message"]
        )
        job_details.status = "finished"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        log(job_details, f"DM sent")
    except Exception as e:
        job_details.status = "canceled"
        job_details.finished_timestamp = datetime.now()
        db_session.add(job_details)
        db_session.commit()
        log(job_details, f"Failed to send DM: {e}")

    db_session.close()

    # Sleep a minute between sending each DM
    log(job_details, f"Sleeping 60s")
    time.sleep(60)
