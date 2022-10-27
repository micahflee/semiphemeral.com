import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import peony

from common import (
    log,
    tweets_to_delete,
    SemiphemeralPeonyClient,
    SemiphemeralAppPeonyClient,
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
)
from sqlalchemy.sql import text
from asyncpg.exceptions import ForeignKeyViolationError

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
            async with SemiphemeralPeonyClient(user) as client:
                try:
                    await client.user
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

            async with SemiphemeralPeonyClient(user) as client:
                # Is the user following us?
                try:
                    friendship = await client.api.friendships.show.get(
                        source_screen_name=user.twitter_screen_name,
                        target_screen_name="semiphemeral",
                    )

                    if friendship["relationship"]["source"]["blocked_by"]:
                        # The semiphemeral user has blocked this user, so they're not allowed
                        # to use this service
                        print(
                            f"user_id={user.id} is blocked, canceling job and updating user"
                        )
                        await job_details.update(
                            status="canceled", finished_timestamp=datetime.now()
                        ).apply()
                        await user.update(paused=True, blocked=True).apply()
                        return False

                    elif not friendship["relationship"]["source"]["following"]:
                        # Make follow request
                        print(f"user_id={user.id} not following, making follow request")
                        await client.api.friendships.create.post(
                            screen_name="semiphemeral",
                        )

                except Exception as e:
                    await log(job_details, f"Exception in ensure_user_follows_us: {e}")

        return await func(job_details_id, funcs)

    return wrapper


# Helper functions


async def save_tweet(user, status):
    # Mark any new fascist tweets as fascist
    fascist = await Fascist.query.where(
        Fascist.username == status.user.screen_name
    ).gino.first()
    if fascist:
        is_fascist = True
    else:
        is_fascist = False

    try:
        return await Tweet.create(
            user_id=user.id,
            created_at=datetime.strptime(
                status.created_at, "%a %b %d %H:%M:%S %z %Y"
            ).replace(tzinfo=None),
            twitter_user_id=status.user.id_str,
            twitter_user_screen_name=status.user.screen_name,
            status_id=status.id_str,
            text=status.full_text.replace(
                "\x00", ""
            ),  # For some reason this tweet has null bytes https://twitter.com/mehdirhasan/status/65015127132471296
            in_reply_to_screen_name=status.in_reply_to_screen_name,
            in_reply_to_status_id=status.in_reply_to_status_id_str,
            in_reply_to_user_id=status.in_reply_to_user_id_str,
            retweet_count=status.retweet_count,
            favorite_count=status.favorite_count,
            retweeted=status.retweeted,
            favorited=status.favorited,
            is_retweet="retweeted_status" in status,
            is_deleted=False,
            is_unliked=False,
            exclude_from_delete=False,
            is_fascist=is_fascist,
        )
    except ForeignKeyViolationError:
        # If the user isn't in the database (maybe the user deleted their account, but a
        # job is still running?) just ignore
        pass


async def import_tweet_and_thread(user, client, status):
    """
    This imports a tweet, and recursively imports all tweets that it's in reply to,
    and returns the number of tweets fetched
    """
    # Is the tweet already saved?
    tweet = await (
        Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.status_id == status.id_str)
        .gino.first()
    )
    if not tweet:
        # Save the tweet
        tweet = await save_tweet(user, status)
        if not tweet:
            return

    # Is this tweet a reply?
    if tweet.in_reply_to_status_id:
        # Do we already have the parent tweet?
        parent_tweet = await (
            Tweet.query.where(Tweet.user_id == user.id)
            .where(Tweet.status_id == tweet.in_reply_to_status_id)
            .gino.first()
        )
        if not parent_tweet:
            # If we don't have the parent tweet, try importing it
            try:
                parent_statuses = await client.api.statuses.lookup.get(
                    id=tweet["in_reply_to_status_id_str"],
                    tweet_mode="extended",
                )
                if len(parent_statuses) > 0:
                    await import_tweet_and_thread(
                        user,
                        client,
                        parent_statuses[0],
                    )
            except:
                pass


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
            .where(Tweet.favorite_count >= user.tweets_like_threshold)
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

    async with SemiphemeralPeonyClient(user) as client:
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
        params = {
            "screen_name": user.twitter_screen_name,
            "tweet_mode": "extended",
            "count": 200,
        }
        if since_id:
            params["since_id"] = since_id

        # Fetch 200 at a time until we run out
        while True:
            try:
                statuses = await client.api.statuses.user_timeline.get(**params)
            except (
                peony.exceptions.DoesNotExist,
                peony.exceptions.HTTPUnauthorized,
                peony.exceptions.InvalidOrExpiredToken,
                peony.exceptions.AccountLocked,
            ):
                await broken_and_cancel(user, job_details)
                return

            if len(statuses) == 0:
                break
            await log(job_details, f"Importing {len(statuses)} tweets")

            # Next loop, set max_id to one less than the oldest status batch
            params["max_id"] = statuses[-1].id - 1

            # Import these tweets
            for status in statuses:
                await import_tweet_and_thread(user, client, status)
                data["progress"]["tweets_fetched"] += 1

            await job_details.update(data=json.dumps(data)).apply()

            # Hunt for threads. This is a dict that maps the root status_id to a list
            # of status_ids in the thread
            threads = {}
            for status in statuses:
                if status.in_reply_to_status_id:
                    status_ids = await calculate_thread(user, status.id_str)
                    if len(status_ids) > 0:
                        root_status_id = status_ids[0]
                        if root_status_id in threads:
                            for status_id in status_ids:
                                if status_id not in threads[root_status_id]:
                                    threads[root_status_id].append(status_id)
                        else:
                            threads[root_status_id] = status_ids

            # For each thread, does this thread already exist, or do we create a new one?
            for root_status_id in threads:
                status_ids = threads[root_status_id]
                thread = (
                    await Thread.query.where(Thread.user_id == user.id)
                    .where(Thread.root_status_id == root_status_id)
                    .gino.first()
                )
                if not thread:
                    thread = await Thread.create(
                        user_id=user.id,
                        root_status_id=root_status_id,
                        should_exclude=False,
                    )

                # Add all of the thread's tweets to the thread
                for status_id in status_ids:
                    tweet = (
                        await Tweet.query.where(Tweet.user_id == user.id)
                        .where(Tweet.status_id == status_id)
                        .gino.first()
                    )
                    if tweet:
                        await tweet.update(thread_id=thread.id).apply()

        # Update progress
        data["progress"]["status"] = "Downloading tweets that you liked"
        await job_details.update(data=json.dumps(data)).apply()

        # Fetch likes
        params = {
            "screen_name": user.twitter_screen_name,
            "tweet_mode": "extended",
            "count": 200,
        }
        if since_id:
            params["since_id"] = since_id

        # Fetch 200 at a time until we run out
        while True:
            try:
                statuses = await client.api.favorites.list.get(**params)
            except (
                peony.exceptions.DoesNotExist,
                peony.exceptions.HTTPUnauthorized,
                peony.exceptions.InvalidOrExpiredToken,
                peony.exceptions.AccountLocked,
            ):
                await broken_and_cancel(user, job_details)
                return

            if len(statuses) == 0:
                break
            await log(job_details, f"Importing {len(statuses)} likes")

            # Next loop, set max_id to one less than the oldest status batch
            params["max_id"] = statuses[-1].id - 1

            # Import these likes
            for status in statuses:
                # Is the tweet already saved?
                tweet = await (
                    Tweet.query.where(Tweet.user_id == user.id)
                    .where(Tweet.status_id == status.id_str)
                    .gino.first()
                )
                if not tweet:
                    # Save the tweet
                    await save_tweet(user, status)
                    data["progress"]["likes_fetched"] += 1

            await job_details.update(data=json.dumps(data)).apply()

    # All done, update the since_id
    async with gino_db.acquire() as conn:
        await conn.all("BEGIN")
        r = await conn.all(
            text(
                "SELECT status_id FROM tweets WHERE user_id=:user_id AND twitter_user_id=:twitter_user_id ORDER BY CAST(status_id AS bigint) DESC LIMIT 1"
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
    fascist_tweets = (
        await Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.favorited == True)
        .where(Tweet.is_fascist == True)
        .where(Tweet.created_at > six_months_ago)
        .gino.all()
    )
    if len(fascist_tweets) > 4:
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

    async with SemiphemeralPeonyClient(user) as client:
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
                    .where(Tweet.twitter_user_id == user.twitter_id)
                    .where(Tweet.is_deleted == False)
                    .where(Tweet.is_retweet == True)
                    .where(Tweet.created_at < datetime_threshold)
                    .order_by(Tweet.created_at)
                    .gino.all()
                )

                data["progress"][
                    "status"
                ] = f"Deleting {len(tweets)} retweets, starting with the earliest"
                await job_details.update(data=json.dumps(data)).apply()

                for tweet in tweets:
                    # Delete retweet
                    try:
                        await client.api.statuses.unretweet[tweet.status_id].post()
                        await tweet.update(is_deleted=True).apply()
                    except Exception as e:
                        # await log(
                        #     job_details,
                        #     f"Skipped deleting retweet {tweet.status_id} {e}",
                        # )
                        await tweet.update(is_deleted=True).apply()

                    data["progress"]["retweets_deleted"] += 1
                    await job_details.update(data=json.dumps(data)).apply()

            # Unlike
            if user.retweets_likes_delete_likes:
                days = user.retweets_likes_likes_threshold
                if days > 99999:
                    days = 99999
                datetime_threshold = datetime.utcnow() - timedelta(days=days)
                tweets = (
                    await Tweet.query.where(Tweet.user_id == user.id)
                    .where(Tweet.twitter_user_id != user.twitter_id)
                    .where(Tweet.is_unliked == False)
                    .where(Tweet.favorited == True)
                    .where(Tweet.created_at < datetime_threshold)
                    .order_by(Tweet.created_at)
                    .gino.all()
                )

                data["progress"][
                    "status"
                ] = f"Unliking {len(tweets)} tweets, starting with the earliest"
                await job_details.update(data=json.dumps(data)).apply()

                for tweet in tweets:
                    # Delete like

                    try:
                        await client.api.favorites.destroy.post(id=tweet.status_id)
                        await tweet.update(is_unliked=True).apply()
                        # await log(job_details, f"Deleted like {tweet.status_id}")
                    except Exception as e:
                        # await log(
                        #     job_details,
                        #     f"Skipped deleting like {tweet.status_id} {e}",
                        # )
                        await tweet.update(is_unliked=True).apply()

                    data["progress"]["likes_deleted"] += 1
                    await job_details.update(data=json.dumps(data)).apply()

        # Deleting tweets
        if user.delete_tweets:
            tweets = tweets = await tweets_to_delete(user)

            data["progress"][
                "status"
            ] = f"Deleting {len(tweets)} tweets, starting with the earliest"
            await job_details.update(data=json.dumps(data)).apply()

            for tweet in tweets:
                # Delete tweet
                try:
                    await client.api.statuses.destroy.post(id=tweet.status_id)
                    await tweet.update(is_deleted=True).apply()
                except Exception as e:
                    # await log(
                    #     job_details,
                    #     f"Skipped deleting retweet {tweet.status_id} {e}",
                    # )
                    await tweet.update(is_deleted=True).apply()

                data["progress"]["tweets_deleted"] += 1
                await job_details.update(data=json.dumps(data)).apply()

    # Deleting direct messages
    if user.direct_messages:
        # Make sure the DMs API authenticates successfully
        proceed = False
        async with SemiphemeralPeonyClient(user, dms=True) as dms_client:
            try:
                await dms_client.user
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

                # Delete DMs
                datetime_threshold = datetime.utcnow() - timedelta(
                    days=user.direct_messages_threshold
                )

                # Fetch DMs
                dms = []
                cursor = None
                while True:
                    dms_request = await dms_client.api.direct_messages.events.list.get(
                        count=50, cursor=cursor
                    )
                    dms.extend(dms_request["events"])
                    if "next_cursor" in dms_request:
                        cursor = dms_request["next_cursor"]
                    else:
                        break

                for dm in dms:
                    created_timestamp = datetime.fromtimestamp(
                        int(dm.created_timestamp) / 1000
                    )
                    if created_timestamp <= datetime_threshold:
                        # Delete the DM
                        # await log(job_details, f"Deleted DM {dm.id}")
                        try:
                            await dms_client.api.direct_messages.events.destroy.delete(
                                id=dm.id
                            )
                        except Exception as e:
                            # await log(job_details, f"Skipping DM {dm.id}, {e}")
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
        message = f"Congratulations! Semiphemeral has deleted {data['progress']['tweets_deleted']} tweets, unretweeted {data['progress']['retweets_deleted']} tweets, and unliked {data['progress']['likes_deleted']} tweets. Doesn't that feel nice?\n\nEach day, I will download your latest tweets and likes and then delete the old ones based on your settings. You can sit back, relax, and enjoy the privacy.\n\nYou can always change your settings, mark new tweets to never delete, and pause Semiphemeral from the website https://{os.environ.get('DOMAIN')}/dashboard."

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

            message = f"Since you've been using Semiphemeral, I have deleted {total_progress['tweets_deleted']} tweets, unretweeted {total_progress['retweets_deleted']} tweets, and unliked {total_progress['likes_deleted']} tweets for you.\n\nJust since last month, I've deleted {total_progress_since_last_nag['tweets_deleted']} tweets, unretweeted {total_progress_since_last_nag['retweets_deleted']} tweets, and unliked {total_progress_since_last_nag['likes_deleted']} tweets.\n\nSemiphemeral is free, but running this service costs money. Care to chip in? Visit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"

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

    async with SemiphemeralPeonyClient(user, dms=True) as dms_client:
        try:
            twitter_user = await dms_client.user
        except Exception as e:
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
                            await dms_client.api.direct_messages.events.destroy.delete(
                                id=dm_id
                            )
                            data["progress"]["dms_deleted"] += 1
                            await job_details.update(data=json.dumps(data)).apply()
                        except peony.exceptions.DoesNotExist as e:
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
        message = f"Congratulations, Semiphemeral just finished deleting {data['progress']['dms_deleted']} of your old direct messages."
    elif dm_type == "groups":
        message = f"Congratulations, Semiphemeral just finished deleting {data['progress']['dms_deleted']} of your old group direct messages."

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

    async with SemiphemeralAppPeonyClient() as client:
        # Are they already blocked?
        friendship = await client.api.friendships.show.get(
            source_screen_name="semiphemeral",
            target_screen_name=data["twitter_username"],
        )
        if friendship["relationship"]["source"]["blocking"]:
            # Already blocked, so our work here is done
            await job_details.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()
            await log(job_details, f"already blocked @{data['twitter_username']}")
            return

        # If we're blocking a semiphemeral user, and not just a fascist influencer
        if "user_id" in data:
            user = await User.query.where(User.id == data["user_id"]).gino.first()
            if user and not user.blocked:
                # Update the user
                await user.update(paused=True, blocked=True).apply()

                # Get all the recent fascist tweets
                six_months_ago = datetime.now() - timedelta(days=180)
                fascist_tweets = (
                    await Tweet.query.where(Tweet.user_id == user.id)
                    .where(Tweet.favorited == True)
                    .where(Tweet.is_fascist == True)
                    .where(Tweet.created_at > six_months_ago)
                    .gino.all()
                )

                # When do we unblock them?
                last_fascist_tweet = (
                    await Tweet.query.where(Tweet.user_id == user.id)
                    .where(Tweet.is_fascist == True)
                    .order_by(Tweet.created_at.desc())
                    .gino.first()
                )
                if last_fascist_tweet:
                    unblock_timestamp = last_fascist_tweet.created_at + timedelta(
                        days=180
                    )
                else:
                    unblock_timestamp = datetime.now() + timedelta(days=180)
                unblock_timestamp_formatted = unblock_timestamp.strftime("%B %-d, %Y")

                # Send the DM
                message = f"You have liked {len(fascist_tweets)} tweets from a prominent fascist or fascist sympathizer within the last 6 months, so you have been blocked and your Semiphemeral account is deactivated.\n\nTo see which tweets you liked and learn how to get yourself unblocked, see https://{os.environ.get('DOMAIN')}/dashboard.\n\nOr you can wait until {unblock_timestamp_formatted} when you will get automatically unblocked, at which point you can login to reactivate your account so long as you've stop liking tweets from fascists."

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
        await client.api.blocks.create.post(screen_name=data["twitter_username"])

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

    async with SemiphemeralAppPeonyClient() as client:
        # Are they already unblocked?
        friendship = await client.api.friendships.show.get(
            source_screen_name="semiphemeral",
            target_screen_name=data["twitter_username"],
        )
        if not friendship["relationship"]["source"]["blocking"]:
            # Update the user
            user = await User.query.where(User.id == job_details.user_id).gino.first()
            if user and user.blocked:
                await user.update(paused=True, blocked=False).apply()

            # Already unblocked, so our work here is done
            await job_details.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()
            await log(job_details, f"already unblocked @{data['twitter_username']}")
            return

        # Unblock them
        try:
            await client.api.blocks.destroy.post(screen_name=data["twitter_username"])
        except peony.exceptions.DoesNotExist:
            pass

    # If we're unblocking a semiphemeral user
    if "user_id" in data:
        user = await User.query.where(User.id == data["user_id"]).gino.first()
        if user and user.blocked:
            # Update the user
            await user.update(paused=True, blocked=False).apply()

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
