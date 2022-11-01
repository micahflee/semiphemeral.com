import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import tweepy
import peony

from common import (
    log,
    tweets_to_delete,
    tweepy_client,
    tweepy_semiphemeral_client,
    tweepy_dms_api_v1_1,
)
from db import (
    connect_db,
    JobDetails,
    User,
    Tip,
    Nag,
    Tweet,
    Thread,
    Fascist,
    Like,
)
from sqlalchemy.sql import text

import redis
from rq import Queue, Retry

conn = redis.from_url(os.environ.get("REDIS_URL"))
jobs_q = Queue("jobs", connection=conn)
dm_jobs_high_q = Queue("dm_jobs_high", connection=conn)
dm_jobs_low_q = Queue("dm_jobs_low", connection=conn)


class JobCanceled(Exception):
    pass


# Global variables

gino_db = None

# Decorators


def init_db(func):
    async def wrapper(job_details_id, funcs):
        """
        Initialize the database
        """
        global gino_db
        gino_db = await connect_db()
        return await func(job_details_id, funcs)

    return wrapper


def test_api_creds(func):
    async def wrapper(job_details_id, funcs):
        """
        Make sure the API creds work, and if not pause semiphemeral for the user
        """
        job_details = await JobDetails.query.where(
            JobDetails.id == job_details_id
        ).gino.first()
        user = await User.query.where(User.id == job_details.user_id).gino.first()
        if user:
            client = tweepy_client(user)
            try:
                client.get_me()
            except Exception as e:
                print(
                    f"user_id={user.id} API creds failed, canceling job and pausing user"
                )
                await user.update(paused=True).apply()
                await job_details.update(
                    status="canceled", finished_timestamp=datetime.now()
                ).apply()
                return False

        return await func(job_details_id, funcs)

    return wrapper


def ensure_user_follows_us(func):
    async def wrapper(job_details_id, funcs):
        job_details = await JobDetails.query.where(
            JobDetails.id == job_details_id
        ).gino.first()
        user = await User.query.where(User.id == job_details.user_id).gino.first()

        if user:
            # Make an exception for semiphemeral user, because semiphemeral can't follow semiphemeral
            if user.twitter_screen_name == "semiphemeral":
                return await func(job_details_id, funcs)

            # Try following
            client = tweepy_client(user)
            try:
                client.follow_user(
                    target_user_id=1209344563589992448  # @semiphemeral twitter ID
                )

            except tweepy.errors.BadRequest as e:
                if "You cannot follow an account that is blocking you" in e.args[0]:
                    # The semiphemeral user has blocked this user, so they're not allowed to use this service
                    print(
                        f"user_id={user.id} is blocked, canceling job and updating user"
                    )
                    await job_details.update(
                        status="canceled", finished_timestamp=datetime.now()
                    ).apply()
                    await user.update(paused=True, blocked=True).apply()
                    return False

        return await func(job_details_id, funcs)

    return wrapper


# Helper functions


async def calculate_thread(user, status_id):
    """
    Given a tweet, recursively add its parents to a thread. In this end, the first
    element of the list should be the root of the thread
    """
    tweet = (
        await Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.status_id == status_id)
        .gino.first()
    )
    if not tweet:
        return []
    if not tweet.in_reply_to_status_id:
        return [status_id]
    return await calculate_thread(user, tweet.in_reply_to_status_id) + [status_id]


async def calculate_excluded_threads(user):
    """
    Based on the user's settings, figure out which threads should be excluded from
    deletion, and which threads should have their tweets deleted
    """
    # Reset the should_exclude flag for all threads
    await Thread.update.values(should_exclude=False).where(
        Thread.user_id == user.id
    ).gino.status()

    # Set should_exclude for all threads based on the settings
    if user.tweets_threads_threshold:
        threads = (
            await Thread.query.select_from(Thread.join(Tweet))
            .where(Thread.id == Tweet.thread_id)
            .where(Thread.user_id == user.id)
            .where(Tweet.user_id == user.id)
            .where(Tweet.is_deleted == False)
            .where(Tweet.is_retweet == False)
            .where(Tweet.retweet_count >= user.tweets_retweet_threshold)
            .where(Tweet.like_count >= user.tweets_like_threshold)
            .gino.all()
        )
        for thread in threads:
            await thread.update(should_exclude=True).apply()


async def broken_and_cancel(user, job_details):
    await log(
        job_details,
        f"Account seems broken, canceling job and pausing user",
    )
    await user.update(paused=True).apply()
    await job_details.update(
        status="canceled", finished_timestamp=datetime.now()
    ).apply()


# Fetch job


@init_db
@test_api_creds
@ensure_user_follows_us
async def fetch(job_details_id, funcs):
    job_details = await JobDetails.query.where(
        JobDetails.id == job_details_id
    ).gino.first()
    await job_details.update(status="active", started_timestamp=datetime.now()).apply()
    await log(job_details, str(job_details))

    user = await User.query.where(User.id == job_details.user_id).gino.first()
    if not user:
        await log(job_details, "User not found, canceling job")
        await job_details.update(
            status="canceled", finished_timestamp=datetime.now()
        ).apply()
        return

    client = tweepy_client(user)
    since_id = user.since_id

    await log(job_details, f"Fetch started")

    # Start the data
    data = {"progress": {"tweets_fetched": 0, "likes_fetched": 0}}
    if since_id:
        data["progress"]["status"] = "Downloading all recent tweets"
    else:
        data["progress"][
            "status"
        ] = "Downloading all tweets, this first run may take a long time"

    await job_details.update(data=json.dumps(data)).apply()

    # Fetch tweets
    pagination_token = None
    while True:
        response = client.get_users_tweets(
            id=user.twitter_id,
            max_results=100,
            since_id=since_id,
            tweet_fields=[
                "author_id",
                "conversation_id",
                "created_at",
                "in_reply_to_user_id",
                "public_metrics",
                "referenced_tweets",
            ],
            pagination_token=pagination_token,
            user_auth=True,
        )
        if response["meta"]["result_count"] == 0:
            await log(job_details, f"No new tweets")
            break

        await log(job_details, f"Importing {len(response['data'])} tweets")

        # Import these tweets
        for api_tweet in response["data"]:
            # Is the tweet already saved?
            tweet = await (
                Tweet.query.where(Tweet.user_id == user.id)
                .where(Tweet.twitter_id == api_tweet["id"])
                .gino.first()
            )
            if not tweet:
                # Make sure we have a thread for this tweet
                thread = await (
                    Thread.query.where(Thread.user_id == user.id)
                    .where(Thread.conversation_id == api_tweet["conversation_id"])
                    .gino.first()
                )
                if not thread:
                    thread = await Thread.create(
                        user_id=user.id,
                        conversation_id=api_tweet["conversation_id"],
                        should_exclude=False,
                    )

                # Save the tweet
                is_retweet = False
                retweet_id = None
                if "referenced_tweets" in api_tweet:
                    for referenced_tweet in api_tweet["referenced_tweets"]:
                        if referenced_tweet["type"] == "retweet":
                            is_retweet = True
                            retweet_id = referenced_tweet["id"]
                            break

                is_reply = "in_reply_to_user_id" in api_tweet

                await Tweet.create(
                    user_id=user.id,
                    twitter_id=api_tweet["id"],
                    created_at=datetime.fromisoformat(api_tweet["created_at"][0:19]),
                    text=api_tweet["text"],
                    is_retweet=is_retweet,
                    retweet_id=retweet_id,
                    is_reply=is_reply,
                    retweet_count=api_tweet["public_metrics"]["retweet_count"],
                    like_count=api_tweet["public_metrics"]["like_count"],
                    exclude_from_delete=False,
                    is_deleted=False,
                    thread_id=thread.id,
                )

            data["progress"]["tweets_fetched"] += 1

        await job_details.update(data=json.dumps(data)).apply()

        if "next_token" in response["meta"]:
            pagination_token = response["meta"]["next_token"]
        else:
            # all done
            break

    # Update progress
    data["progress"]["status"] = "Downloading tweets that you liked"
    await job_details.update(data=json.dumps(data)).apply()

    # Fetch likes
    pagination_token = None
    while True:
        response = client.get_liked_tweets(
            id=user.twitter_id,
            max_results=100,
            pagination_token=pagination_token,
            tweet_fields=[
                "author_id",
                "created_at",
            ],
            user_auth=True,
        )
        if response["meta"]["result_count"] == 0:
            await log(job_details, f"No new likes")
            break

        await log(job_details, f"Importing {len(response['data'])} likes")

        # Import these likes
        for api_like in response["data"]:
            # Is the like already saved?
            like = await (
                Like.query.where(Like.user_id == user.id)
                .where(Like.twitter_id == api_like["id"])
                .gino.first()
            )
            if not like:
                fascist = await Fascist.query.where(
                    Fascist.twitter_id == api_like["author_id"]
                ).gino.first()
                is_fascist = fascist is not None

                # Save the like
                await Like.create(
                    user_id=user.id,
                    twitter_id=api_like["id"],
                    created_at=datetime.fromisoformat(api_like["created_at"][0:19]),
                    author_id=api_like["author_id"],
                    is_deleted=False,
                    is_fascist=is_fascist,
                )

            data["progress"]["likes_fetched"] += 1

        await job_details.update(data=json.dumps(data)).apply()

        if "next_token" in response["meta"]:
            pagination_token = response["meta"]["next_token"]
        else:
            # all done
            break

    # All done, update the since_id
    async with gino_db.acquire() as conn:
        await conn.all("BEGIN")
        r = await conn.all(
            text(
                "SELECT twitter_id FROM tweets WHERE user_id=:user_id ORDER BY CAST(twitter_id AS bigint) DESC LIMIT 1"
            ),
            user_id=user.id,
            twitter_user_id=user.twitter_id,
        )
        await conn.all("COMMIT")

    if len(r) > 0:
        new_since_id = r[0][0]
        await user.update(since_id=new_since_id).apply()

    # Calculate which threads should be excluded from deletion
    data["progress"]["status"] = "Calculating which threads to exclude from deletion"
    await job_details.update(data=json.dumps(data)).apply()

    await calculate_excluded_threads(user)

    data["progress"]["status"] = "Finished"
    await job_details.update(data=json.dumps(data)).apply()

    # Has this user liked any fascist tweets?
    six_months_ago = datetime.now() - timedelta(days=180)
    fascist_likes = (
        await Like.query.where(Like.user_id == user.id)
        .where(Like.is_fascist == True)
        .where(Like.created_at > six_months_ago)
        .gino.all()
    )
    if len(fascist_likes) > 4:
        # Create a block job
        new_job_details = await JobDetails.create(
            job_type="block",
            data=json.dumps(
                {"twitter_username": user.twitter_screen_name, "user_id": user.id}
            ),
        )
        redis_job = jobs_q.enqueue(
            funcs["block"],
            new_job_details.id,
            retry=Retry(max=3, interval=[60, 120, 240]),
        )
        await new_job_details.update(redis_id=redis_job.id).apply()

        # Don't send any DMs
        await log(job_details, f"Blocking user")
        await job_details.update(
            status="finished", finished_timestamp=datetime.now()
        ).apply()
        return

    # Fetch is done! If semiphemeral is paused, send a DM
    # (If it's not paused, then this should actually be a delete job, and delete will run next)
    if user.paused:
        if not since_id:
            message = f"Good news! Semiphemeral finished downloading a copy of all {data['progress']['tweets_fetched']} of your tweets and all {data['progress']['likes_fetched']} of your likes.\n\n"
        else:
            message = f"Semiphemeral finished downloading {data['progress']['tweets_fetched']} new tweets and {data['progress']['likes_fetched']} new likes.\n\n"

        message += f"The next step is look through your tweets and manually mark which ones you want to make sure never get deleted. Visit https://{os.environ.get('DOMAIN')}/tweets to finish.\n\nWhen you're done, you can start deleting your tweets from the dashboard."

        # Create DM job
        new_job_details = await JobDetails.create(
            job_type="dm",
            data=json.dumps(
                {
                    "dest_twitter_id": user.twitter_id,
                    "message": message,
                }
            ),
        )
        redis_job = dm_jobs_high_q.enqueue(
            funcs["dm"], new_job_details.id, retry=Retry(max=3, interval=[60, 120, 240])
        )
        await new_job_details.update(redis_id=redis_job.id).apply()

    await job_details.update(
        status="finished", finished_timestamp=datetime.now()
    ).apply()
    await log(job_details, f"Fetch finished")


# Delete job


@init_db
@test_api_creds
@ensure_user_follows_us
async def delete(job_details_id, funcs):
    job_details = await JobDetails.query.where(
        JobDetails.id == job_details_id
    ).gino.first()
    if job_details.status == "canceled":
        await log(job_details, str(job_details))
        await log(job_details, "canceled job, so quitting early")
        return
    await job_details.update(status="active", started_timestamp=datetime.now()).apply()
    await log(job_details, str(job_details))

    user = await User.query.where(User.id == job_details.user_id).gino.first()
    if not user:
        await log(job_details, "User not found, canceling job")
        await job_details.update(
            status="canceled", finished_timestamp=datetime.now()
        ).apply()
        return

    client = tweepy_client(user)
    await log(job_details, "Delete started")

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
            tweets = (
                await Tweet.query.where(Tweet.user_id == user.id)
                .where(Tweet.is_deleted == False)
                .where(Tweet.is_retweet == True)
                .where(Tweet.created_at < datetime_threshold)
                .order_by(Tweet.created_at)
                .gino.all()
            )

            data["progress"][
                "status"
            ] = f"Deleting {len(tweets):,} retweets, starting with the earliest"
            await job_details.update(data=json.dumps(data)).apply()

            for tweet in tweets:
                # Delete retweet
                try:
                    client.delete_tweet(tweet.twitter_id, user_auth=True)
                except Exception as e:
                    await log(job_details, f"Error deleting retweet: {e}")

                await tweet.update(is_deleted=True).apply()

                data["progress"]["retweets_deleted"] += 1
                await job_details.update(data=json.dumps(data)).apply()

        # Unlike
        if user.retweets_likes_delete_likes:
            days = user.retweets_likes_likes_threshold
            if days > 99999:
                days = 99999
            datetime_threshold = datetime.utcnow() - timedelta(days=days)
            likes = (
                await Like.query.where(Like.user_id == user.id)
                .where(Like.is_deleted == False)
                .where(Like.created_at < datetime_threshold)
                .order_by(Like.created_at)
                .gino.all()
            )

            data["progress"][
                "status"
            ] = f"Unliking {len(likes):,} tweets, starting with the earliest"
            await job_details.update(data=json.dumps(data)).apply()

            for like in likes:
                # Delete like

                try:
                    client.unlike(like.twitter_id, user_auth=True)
                except Exception as e:
                    await log(job_details, f"Error deleting like: {e}")

                await like.update(is_deleted=True).apply()

                data["progress"]["likes_deleted"] += 1
                await job_details.update(data=json.dumps(data)).apply()

    # Deleting tweets
    if user.delete_tweets:
        tweets = tweets = await tweets_to_delete(user)

        data["progress"][
            "status"
        ] = f"Deleting {len(tweets):,} tweets, starting with the earliest"
        await job_details.update(data=json.dumps(data)).apply()

        for tweet in tweets:
            # Delete tweet
            try:
                client.delete_tweet(tweet.twitter_id, user_auth=True)
            except Exception as e:
                await log(job_details, f"Error deleting retweet: {e}")

            await tweet.update(is_deleted=True).apply()

            data["progress"]["tweets_deleted"] += 1
            await job_details.update(data=json.dumps(data)).apply()

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
            await user.update(
                direct_messages=False,
                twitter_dms_access_token="",
                twitter_dms_access_token_secret="",
            ).apply()

        if proceed:
            data["progress"]["status"] = f"Deleting direct messages"
            await job_details.update(data=json.dumps(data)).apply()

            datetime_threshold = datetime.utcnow() - timedelta(
                days=user.direct_messages_threshold
            )

            # Fetch DMs
            dms = []
            pagination_token = None
            while True:
                response = client.get_direct_message_events(
                    dm_event_fields=["created_at"],
                    event_types="MessageCreate",
                    max_results=100,
                    pagination_token=pagination_token,
                    user_auth=True,
                )
                if response["meta"]["result_count"] == 0:
                    await log(job_details, f"No new DMs")
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
                        await log(job_details, f"Skipping DM {dm.id}, {e}")
                        pass

                    data["progress"]["dms_deleted"] += 1
                    await job_details.update(data=json.dumps(data)).apply()

    data["progress"]["status"] = "Finished"
    await job_details.update(data=json.dumps(data)).apply()

    await job_details.update(
        status="finished", finished_timestamp=datetime.now()
    ).apply()
    await log(job_details, f"Delete finished")

    # Delete is done!

    # Schedule the next delete job
    scheduled_timestamp = datetime.now() + timedelta(days=1)
    new_job_details = await JobDetails.create(
        job_type="delete", user_id=user.id, scheduled_timestamp=scheduled_timestamp
    )
    redis_job = jobs_q.enqueue_at(
        scheduled_timestamp, funcs["delete"], new_job_details.id, job_timeout="24h"
    )
    with open("/tmp/debug.log", "w") as f:
        f.write(str(redis_job))
        f.write("\n")
    await new_job_details.update(redis_id=redis_job.id).apply()

    # Has the user tipped in the last year?
    one_year = timedelta(days=365)
    tipped_in_the_last_year = (
        await Tip.query.where(Tip.user_id == user.id)
        .where(Tip.paid == True)
        .where(Tip.refunded == False)
        .where(Tip.timestamp > datetime.now() - one_year)
        .order_by(Tip.timestamp.desc())
        .gino.first()
    )

    # Should we nag the user?
    one_month_ago = datetime.now() - timedelta(days=30)
    last_nag = (
        await Nag.query.where(Nag.user_id == user.id)
        .order_by(Nag.timestamp.desc())
        .gino.first()
    )

    should_nag = False
    if not tipped_in_the_last_year:
        if not last_nag:
            should_nag = True
        elif last_nag.timestamp < one_month_ago and not tipped_in_the_last_year:
            should_nag = True

    if not last_nag:
        await log(job_details, f"Nagging the user for the first time")

        # Create a nag
        await Nag.create(
            user_id=user.id,
            timestamp=datetime.now(),
        )

        # The user has never been nagged, so this is the first delete
        message = f"Congratulations! Semiphemeral has deleted {data['progress']['tweets_deleted']:,} tweets, unretweeted {data['progress']['retweets_deleted']:,} tweets, and unliked {data['progress']['likes_deleted']:,} tweets. Doesn't that feel nice?\n\nEach day, I will download your latest tweets and likes and then delete the old ones based on your settings. You can sit back, relax, and enjoy the privacy.\n\nYou can always change your settings, mark new tweets to never delete, and pause Semiphemeral from the website https://{os.environ.get('DOMAIN')}/dashboard."

        new_job_details = await JobDetails.create(
            job_type="dm",
            data=json.dumps(
                {
                    "dest_twitter_id": user.twitter_id,
                    "message": message,
                }
            ),
        )
        redis_job = dm_jobs_high_q.enqueue(
            funcs["dm"], new_job_details.id, retry=Retry(max=3, interval=[60, 120, 240])
        )
        await new_job_details.update(redis_id=redis_job.id).apply()

        message = f"Semiphemeral is free, but running this service costs money. Care to chip in?\n\nIf you tip any amount, even just $1, I will stop nagging you for a year. Otherwise, I'll gently remind you once a month.\n\n(It's fine if you want to ignore these DMs. I won't care. I'm a bot, so I don't have feelings).\n\nVisit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"

        new_job_details = await JobDetails.create(
            job_type="dm",
            data=json.dumps(
                {
                    "dest_twitter_id": user.twitter_id,
                    "message": message,
                }
            ),
        )
        redis_job = dm_jobs_high_q.enqueue(
            funcs["dm"], new_job_details.id, retry=Retry(max=3, interval=[60, 120, 240])
        )
        await new_job_details.update(redis_id=redis_job.id).apply()

    else:
        if should_nag:
            await log(job_details, f"Nagging the user again")

            # Create a nag
            await Nag.create(
                user_id=user.id,
                timestamp=datetime.now(),
            )

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
            job_details = (
                await JobDetails.query.where(JobDetails.user_id == user.id)
                .where(JobDetails.job_type == "delete")
                .where(JobDetails.status == "finished")
                .gino.all()
            )
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

            new_job_details = await JobDetails.create(
                job_type="dm",
                data=json.dumps(
                    {
                        "dest_twitter_id": user.twitter_id,
                        "message": message,
                    }
                ),
            )
            redis_job = dm_jobs_high_q.enqueue(
                funcs["dm"],
                new_job_details.id,
                retry=Retry(max=3, interval=[60, 120, 240]),
            )
            await new_job_details.update(redis_id=redis_job.id).apply()


# Delete DMs and DM Groups jobs


@init_db
@test_api_creds
@ensure_user_follows_us
async def delete_dms(job_details_id, funcs):
    await delete_dms_job(job_details_id, "dms", funcs)


@init_db
@test_api_creds
@ensure_user_follows_us
async def delete_dm_groups(job_details_id, funcs):
    await delete_dms_job(job_details_id, "groups", funcs)


async def delete_dms_job(job_details_id, dm_type, funcs):
    job_details = await JobDetails.query.where(
        JobDetails.id == job_details_id
    ).gino.first()
    await job_details.update(status="active", started_timestamp=datetime.now()).apply()
    await log(job_details, str(job_details))

    user = await User.query.where(User.id == job_details.user_id).gino.first()
    if not user:
        await log(job_details, "User not found, canceling job")
        await job_details.update(
            status="canceled", finished_timestamp=datetime.now()
        ).apply()
        return

    dm_client = tweepy_client(user, dms=True)
    dm_api = tweepy_dms_api_v1_1(user)

    # Make sure the DMs API authenticates successfully
    try:
        dm_client.get_me()
    except Exception as e:
        # It doesn't, so disable deleting direct messages
        await log(job_details, f"DMs Twitter API creds don't work, canceling job")
        await job_details.update(
            status="canceled", started_timestamp=datetime.now()
        ).apply()
        return

    if dm_type == "dms":
        await log(job_details, f"Delete DMs started")
    elif dm_type == "groups":
        await log(job_details, f"Delete group DMs started")

    # Start the progress
    data = {
        "progress": {
            "dms_deleted": 0,
            "dms_skipped": 0,
            "status": "Verifying permissions",
        }
    }
    await job_details.update(data=json.dumps(data)).apply()

    # Make sure deleting DMs is enabled
    if not user.direct_messages:
        await log(job_details, f"Deleting DMs is not enabled, canceling job")
        await job_details.update(
            status="canceled", started_timestamp=datetime.now()
        ).apply()
        return

    # Load the DM metadata
    if dm_type == "dms":
        filename = os.path.join("/var/bulk_dms", f"dms-{user.id}.json")
    elif dm_type == "groups":
        filename = os.path.join("/var/bulk_dms", f"groups-{user.id}.json")
    if not os.path.exists(filename):
        await log(
            job_details,
            f"Filename {filename} does not exist, canceling job",
        )
        await job_details.update(
            status="canceled", started_timestamp=datetime.now()
        ).apply()
        return
    with open(filename) as f:
        try:
            conversations = json.loads(f.read())
        except:
            await job_details(job_details, f"Cannot decode JSON, canceling job")
            await job_details.update(
                status="canceled", started_timestamp=datetime.now()
            ).apply()
            return

    # Delete DMs
    data["progress"]["status"] = "Deleting old direct messages"
    await job_details.update(data=json.dumps(data)).apply()

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
                        await job_details.update(data=json.dumps(data)).apply()
                    except Exception as e:
                        await log(job_details, f"Error deleting DM {dm_id}, {e}")
                        data["progress"]["dms_skipped"] += 1
                        await job_details.update(data=json.dumps(data)).apply()

    # Delete the DM metadata file
    try:
        os.remove(filename)
    except:
        pass

    data["progress"]["status"] = "Finished"
    await job_details.update(data=json.dumps(data)).apply()

    await job_details.update(
        status="finished", finished_timestamp=datetime.now()
    ).apply()
    await log(job_details, f"Delete DMs finished")

    # Send a DM to the user
    if dm_type == "dms":
        message = f"Congratulations, Semiphemeral just finished deleting {data['progress']['dms_deleted']:,} of your old direct messages."
    elif dm_type == "groups":
        message = f"Congratulations, Semiphemeral just finished deleting {data['progress']['dms_deleted']:,} of your old group direct messages."

    new_job_details = await JobDetails.create(
        job_type="dm",
        data=json.dumps(
            {
                "dest_twitter_id": user.twitter_id,
                "message": message,
            }
        ),
    )
    redis_job = dm_jobs_high_q.enqueue(
        funcs["dm"], new_job_details.id, retry=Retry(max=3, interval=[60, 120, 240])
    )
    await new_job_details.update(redis_id=redis_job.id).apply()

    await job_details.update(
        status="finished", finished_timestamp=datetime.now()
    ).apply()
    await log(job_details, f"Delete DMs ({dm_type}) finished")


# Block job


@init_db
async def block(job_details_id, funcs):
    job_details = await JobDetails.query.where(
        JobDetails.id == job_details_id
    ).gino.first()
    await job_details.update(status="active", started_timestamp=datetime.now()).apply()
    await log(job_details, str(job_details))

    data = json.loads(job_details.data)

    semiphemeral_client = tweepy_semiphemeral_client()

    # Look up user to block
    twitter_user = semiphemeral_client.get_user(
        username=data["twitter_username"], user_auth=True
    )
    if "data" not in twitter_user and "id" not in twitter_user["data"]:
        await job_details.update(
            status="finished", finished_timestamp=datetime.now()
        ).apply()
        await log(job_details, f"invalid user @{data['twitter_username']}")
        return

    twitter_id = twitter_user["data"]["id"]

    # If we're blocking a semiphemeral user, and not just a fascist influencer
    if "user_id" in data:
        user = await User.query.where(User.id == data["user_id"]).gino.first()
        if user and not user.blocked:
            # Update the user
            await user.update(paused=True, blocked=True).apply()

            # Get all the recent fascist likes
            six_months_ago = datetime.now() - timedelta(days=180)
            fascist_likes = (
                await Like.query.where(Like.user_id == user.id)
                .where(Like.is_fascist == True)
                .where(Like.created_at > six_months_ago)
                .gino.all()
            )

            # When do we unblock them?
            last_fascist_like = (
                await Like.query.where(Like.user_id == user.id)
                .where(Like.is_fascist == True)
                .order_by(Like.created_at.desc())
                .gino.first()
            )
            if last_fascist_like:
                unblock_timestamp = last_fascist_like.created_at + timedelta(days=180)
            else:
                unblock_timestamp = datetime.now() + timedelta(days=180)
            unblock_timestamp_formatted = unblock_timestamp.strftime("%B %-d, %Y")

            # Send the DM
            message = f"You have liked {len(fascist_likes):,} tweets from a prominent fascist or fascist sympathizer within the last 6 months, so you have been blocked and your Semiphemeral account is deactivated.\n\nTo see which tweets you liked and learn how to get yourself unblocked, see https://{os.environ.get('DOMAIN')}/dashboard.\n\nOr you can wait until {unblock_timestamp_formatted} when you will get automatically unblocked, at which point you can login to reactivate your account so long as you've stop liking tweets from fascists."

            new_job_details = await JobDetails.create(
                job_type="dm",
                data=json.dumps(
                    {
                        "dest_twitter_id": user.twitter_id,
                        "message": message,
                    }
                ),
            )
            redis_job = dm_jobs_high_q.enqueue(
                funcs["dm"],
                new_job_details.id,
                retry=Retry(max=3, interval=[60, 120, 240]),
            )
            await new_job_details.update(redis_id=redis_job.id).apply()

            # Wait 65 seconds before blocking, to ensure they receive the DM
            await asyncio.sleep(65)

            # Create the unblock job
            new_job_details = await JobDetails.create(
                job_type="unblock",
                data=json.dumps(
                    {
                        "user_id": user.id,
                        "twitter_username": user.twitter_screen_name,
                    }
                ),
            )
            redis_job = jobs_q.enqueue_at(
                unblock_timestamp, funcs["unblock"], new_job_details.id
            )
            await new_job_details.update(redis_id=redis_job.id).apply()

        # Block the user
        try:
            semiphemeral_client.block(twitter_id, user_auth=True)
        except Exception as e:
            await log(
                job_details, f"Error blocking user @{data['twitter_username']}, {e}"
            )

    # Finished
    await job_details.update(
        status="finished", finished_timestamp=datetime.now()
    ).apply()
    await log(job_details, f"Block finished")


# Unblock job


@init_db
async def unblock(job_details_id, funcs):
    job_details = await JobDetails.query.where(
        JobDetails.id == job_details_id
    ).gino.first()
    await job_details.update(status="active", started_timestamp=datetime.now()).apply()
    await log(job_details, str(job_details))

    data = json.loads(job_details.data)

    semiphemeral_client = tweepy_semiphemeral_client()

    # Look up user to block
    twitter_user = semiphemeral_client.get_user(
        username=data["twitter_username"], user_auth=True
    )
    if "data" not in twitter_user and "id" not in twitter_user["data"]:
        await job_details.update(
            status="finished", finished_timestamp=datetime.now()
        ).apply()
        await log(job_details, f"invalid user @{data['twitter_username']}")
        return

    twitter_id = twitter_user["data"]["id"]

    # Unblock the user
    try:
        semiphemeral_client.unblock(twitter_id, user_auth=True)
    except Exception as e:
        await log(
            job_details, f"Error unblocking user @{data['twitter_username']}, {e}"
        )

    # If we're unblocking a semiphemeral user
    if "user_id" in data:
        user = await User.query.where(User.id == data["user_id"]).gino.first()
        if user and user.blocked:
            # Update the user
            await user.update(paused=True, blocked=False).apply()
            await log(
                job_details,
                f"User @{data['twitter_username']} unblocked in semiphemeral db",
            )

    # Finished
    await job_details.update(
        status="finished", finished_timestamp=datetime.now()
    ).apply()
    await log(job_details, f"Unblock finished")


# DM job


@init_db
async def dm(job_details_id, funcs):
    job_details = await JobDetails.query.where(
        JobDetails.id == job_details_id
    ).gino.first()
    await job_details.update(status="active", started_timestamp=datetime.now()).apply()
    await log(job_details, str(job_details))

    data = json.loads(job_details.data)

    async with SemiphemeralAppPeonyClient() as client:
        message = {
            "event": {
                "type": "message_create",
                "message_create": {
                    "target": {"recipient_id": int(data["dest_twitter_id"])},
                    "message_data": {"text": data["message"]},
                },
            }
        }

        try:
            await client.api.direct_messages.events.new.post(_json=message)

            await job_details.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()
            await log(job_details, f"DM sent")
        except Exception as e:
            await job_details.update(
                status="canceled", finished_timestamp=datetime.now()
            ).apply()
            await log(job_details, f"Failed to send DM")

    # Sleep a minute between sending each DM
    await log(job_details, f"Sleeping 60s")
    await asyncio.sleep(60)
