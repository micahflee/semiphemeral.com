import asyncio
import json
import os
import queue
from datetime import datetime, timedelta, timezone

import peony

from common import (
    log,
    update_progress,
    update_progress_rate_limit,
    peony_client,
    peony_dms_client,
    peony_semiphemeral_dm_client,
    tweets_to_delete,
    send_admin_notification,
)
from db import (
    Job,
    DirectMessageJob,
    BlockJob,
    UnblockJob,
    User,
    Tip,
    Nag,
    Tweet,
    Thread,
    Fascist,
)
from sqlalchemy.sql import text
from gino.exceptions import NoSuchRowError
from asyncpg.exceptions import ForeignKeyViolationError


# A queue of pending jobs
job_q = queue.Queue()
job_q_lock = False
job_q_last_refresh = None


class JobRescheduled(Exception):
    pass


class JobCanceled(Exception):
    pass


class UserBlocked(Exception):
    pass


def test_api_creds(func):
    async def wrapper(gino_db, job, job_runner_id):
        """
        Make sure the API creds work, and if not pause semiphemeral for the user
        """
        user = await User.query.where(User.id == job.user_id).gino.first()
        client = await peony_client(user)
        try:
            twitter_user = await client.user
        except peony.exceptions.InvalidOrExpiredToken:
            print(f"user_id={user.id} API creds failed, canceling job and pausing user")
            await user.update(paused=True).apply()
            await job.update(status="canceled").apply()
            return False

        return await func(gino_db, job, job_runner_id)

    return wrapper


def ensure_user_follows_us(func):
    async def wrapper(gino_db, job, job_runner_id):
        user = await User.query.where(User.id == job.user_id).gino.first()

        # Make an exception for semiphemeral user, because semiphemeral can't follow semiphemeral
        if user.twitter_screen_name == "semiphemeral":
            return await func(gino_db, job, job_runner_id)

        client = await peony_client(user)

        # Is the user following us?
        friendship = await client.api.friendships.show.get(
            source_screen_name=user.twitter_screen_name,
            target_screen_name="semiphemeral",
            _data=(job, None, job_runner_id),
        )

        if friendship["relationship"]["source"]["blocked_by"]:
            # The semiphemeral user has blocked this user, so they're not allowed
            # to use this service
            print(f"user_id={user.id} is blocked, canceling job and updating user")
            await job.update(status="canceled").apply()
            await user.update(paused=True, blocked=True).apply()
            return False

        elif not friendship["relationship"]["source"]["following"]:
            # Make follow request
            print(f"user_id={user.id} not following, making follow request")
            try:
                await client.api.friendships.create.post(
                    screen_name="semiphemeral",
                    follow=True,
                    _data=(job, None, job_runner_id),
                )
            except:
                print(
                    f"user_id={user.id} failed to make follow request, pause the user"
                )
                await user.update(paused=True).apply()
                return

        return await func(gino_db, job, job_runner_id)

    return wrapper


async def create_job(user, job_type, scheduled_timestamp):
    # If this user does not already have a pending job of this type, then schedule it
    existing_job = (
        await Job.query.where(Job.user_id == user.id)
        .where(Job.job_type == job_type)
        .where(Job.status == "pending")
        .gino.first()
    )
    if not existing_job:
        print(
            f"Scheduling {job_type} for user_id={user.id} at at {scheduled_timestamp}"
        )
        await Job.create(
            user_id=user.id,
            job_type=job_type,
            status="pending",
            scheduled_timestamp=scheduled_timestamp,
        )
    else:
        print(
            f"Pending job already exists (existing_job_id={existing_job.id}), skipping scheduling {job_type} for user_id={user.id} at at {scheduled_timestamp}"
        )


async def reschedule_job(job, timedelta_in_the_future):
    await log(job, f"rescheduling to +{timedelta_in_the_future}")
    await job.update(
        status="pending", scheduled_timestamp=datetime.now() + timedelta_in_the_future
    ).apply()
    raise JobRescheduled


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


async def import_tweet_and_thread(user, client, job, progress, status, job_runner_id):
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
                    _data=(job, progress, job_runner_id),
                )
                if len(parent_statuses) > 0:
                    await import_tweet_and_thread(
                        user,
                        client,
                        job,
                        progress,
                        parent_statuses[0],
                        job_runner_id,
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


@test_api_creds
@ensure_user_follows_us
async def fetch(gino_db, job, job_runner_id):
    user = await User.query.where(User.id == job.user_id).gino.first()
    client = await peony_client(user)

    since_id = user.since_id

    await log(job, f"#{job_runner_id} Fetch started")

    loop = asyncio.get_running_loop()

    # Start the progress
    progress = {"tweets_fetched": 0, "likes_fetched": 0}
    if since_id:
        progress["status"] = "Downloading all recent tweets"
    else:
        progress[
            "status"
        ] = "Downloading all tweets, this first run may take a long time"
    await update_progress(job, progress)

    # Fetch tweets
    params = {
        "screen_name": user.twitter_screen_name,
        "tweet_mode": "extended",
        "count": 200,
        "_data": (job, progress, job_runner_id),
    }
    if since_id:
        params["since_id"] = since_id

    # Fetch 200 at a time until we run out
    while True:
        try:
            statuses = await client.api.statuses.user_timeline.get(**params)
        except peony.exceptions.DoesNotExist:
            await log(
                job,
                f"#{job_runner_id} DoesNotExist, account seems deleted, canceling job and pausing user",
            )
            await user.update(paused=True).apply()
            await job.update(status="canceled").apply()
            raise JobCanceled()
        except peony.exceptions.HTTPUnauthorized:
            await log(
                job,
                f"#{job_runner_id} HTTPUnauthorized, account seems broken, canceling job and pausing user",
            )
            await user.update(paused=True).apply()
            await job.update(status="canceled").apply()
            raise JobCanceled()

        if len(statuses) == 0:
            break
        await log(job, f"#{job_runner_id} Importing {len(statuses)} tweets")

        # Next loop, set max_id to one less than the oldest status batch
        params["max_id"] = statuses[-1].id - 1

        # Import these tweets
        for status in statuses:
            await import_tweet_and_thread(
                user, client, job, progress, status, job_runner_id
            )
            progress["tweets_fetched"] += 1

        await update_progress(job, progress)

        # Hunt for threads. This is a dict that maps the root status_id to a list
        # of status_ids in the thread
        threads = {}
        for status in statuses:
            if status.in_reply_to_status_id:
                status_ids = await calculate_thread(user, status.id_str)
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

        await update_progress(job, progress)

    # Update progress
    progress["status"] = "Downloading tweets that you liked"
    await update_progress(job, progress)

    # Fetch likes
    params = {
        "screen_name": user.twitter_screen_name,
        "tweet_mode": "extended",
        "count": 200,
        "_data": (job, progress, job_runner_id),
    }
    if since_id:
        params["since_id"] = since_id

    # Fetch 200 at a time until we run out
    while True:
        try:
            statuses = await client.api.favorites.list.get(**params)
        except peony.exceptions.HTTPUnauthorized:
            await log(
                job,
                f"#{job_runner_id} HTTPUnauthorized, account seems broken, canceling job and pausing user",
            )
            await user.update(paused=True).apply()
            await job.update(status="canceled").apply()
            raise JobCanceled()

        if len(statuses) == 0:
            break
        await log(job, f"#{job_runner_id} Importing {len(statuses)} likes")

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
                progress["likes_fetched"] += 1

        await update_progress(job, progress)

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
    progress["status"] = "Calculating which threads to exclude from deletion"
    await update_progress(job, progress)

    await calculate_excluded_threads(user)

    progress["status"] = "Finished"
    await update_progress(job, progress)

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
        await BlockJob.create(
            user_id=user.id,
            twitter_username=user.twitter_screen_name,
            status="pending",
            scheduled_timestamp=datetime.now(),
        )
        # Don't send any DMs
        await log(job, f"#{job_runner_id} Blocking user")
        raise UserBlocked

    # Fetch is done! If semiphemeral is paused, send a DM
    # (If it's not paused, then this should actually be a delete job, and delete will run next)
    if user.paused:
        if not since_id:
            message = f"Good news! Semiphemeral finished downloading a copy of all {progress['tweets_fetched']} of your tweets and all {progress['likes_fetched']} of your likes.\n\n"
        else:
            message = f"Semiphemeral finished downloading {progress['tweets_fetched']} new tweets and {progress['likes_fetched']} new likes.\n\n"

        message += f"The next step is look through your tweets and manually mark which ones you want to make sure never get deleted. Visit https://{os.environ.get('DOMAIN')}/tweets to finish.\n\nWhen you're done, you can start deleting your tweets from the dashboard."

        await DirectMessageJob.create(
            dest_twitter_id=user.twitter_id,
            message=message,
            status="pending",
            scheduled_timestamp=datetime.now(),
            priority=0,
        )

    await log(job, f"#{job_runner_id} Fetch complete")


@test_api_creds
@ensure_user_follows_us
async def delete(gino_db, job, job_runner_id):
    if job.status == "canceled":
        return

    user = await User.query.where(User.id == job.user_id).gino.first()
    client = await peony_client(user)

    await log(job, f"#{job_runner_id} Delete started")

    # Start the progress
    progress = json.loads(job.progress)
    progress["tweets_deleted"] = 0
    progress["retweets_deleted"] = 0
    progress["likes_deleted"] = 0
    progress["dms_deleted"] = 0

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

            progress[
                "status"
            ] = f"Deleting {len(tweets)} retweets, starting with the earliest"
            await update_progress(job, progress)

            for tweet in tweets:
                # Delete retweet
                try:
                    await client.api.statuses.unretweet[tweet.status_id].post(
                        _data=(job, progress, job_runner_id),
                    )
                    # await log(
                    #     job, f"#{job_runner_id} Deleted retweet {tweet.status_id}"
                    # )
                    await tweet.update(is_deleted=True).apply()
                except peony.exceptions.StatusNotFound:
                    await log(
                        job,
                        f"#{job_runner_id} Skipped deleting retweet, StatusNotFound {tweet.status_id}",
                    )
                    await tweet.update(is_deleted=True).apply()
                except peony.exceptions.UserSuspended:
                    await log(
                        job,
                        f"#{job_runner_id} Skipped deleting retweet, UserSuspended {tweet.status_id}",
                    )
                    await tweet.update(is_deleted=True).apply()
                except peony.exceptions.DoesNotExist:
                    await log(
                        job,
                        f"#{job_runner_id} Skipped deleting retweet, DoesNotExist {tweet.status_id}",
                    )
                    await tweet.update(is_deleted=True).apply()
                except peony.exceptions.ProtectedTweet:
                    await log(
                        job,
                        f"#{job_runner_id} Skipped deleting retweet, ProtectedTweet {tweet.status_id}",
                    )
                    await tweet.update(is_deleted=True).apply()
                except peony.exceptions.HTTPForbidden:
                    await log(
                        job,
                        f"#{job_runner_id} Skipped deleting retweet, HTTPForbidden {tweet.status_id}",
                    )
                    await tweet.update(is_deleted=True).apply()

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

            progress[
                "status"
            ] = f"Unliking {len(tweets)} tweets, starting with the earliest"
            await update_progress(job, progress)

            for tweet in tweets:
                # Delete like

                try:
                    await client.api.favorites.destroy.post(
                        id=tweet.status_id,
                        _data=(job, progress, job_runner_id),
                    )
                    await tweet.update(is_unliked=True).apply()
                    await log(job, f"#{job_runner_id} Deleted like {tweet.status_id}")
                except peony.exceptions.StatusNotFound:
                    await log(
                        job,
                        f"#{job_runner_id} Skipped deleting like, StatusNotFound {tweet.status_id}",
                    )
                    await tweet.update(is_unliked=True).apply()

                progress["likes_deleted"] += 1
                await update_progress(job, progress)

    # Deleting tweets
    if user.delete_tweets:
        tweets = tweets = await tweets_to_delete(user)

        progress[
            "status"
        ] = f"Deleting {len(tweets)} tweets, starting with the earliest"
        await update_progress(job, progress)

        for tweet in tweets:
            # Delete tweet
            try:
                await client.api.statuses.destroy.post(
                    id=tweet.status_id,
                    _data=(job, progress, job_runner_id),
                )
                await tweet.update(is_deleted=True).apply()
            except peony.exceptions.StatusNotFound:
                await log(
                    job,
                    f"#{job_runner_id} Skipped deleting retweet, StatusNotFound {tweet.status_id}",
                )
                await tweet.update(is_deleted=True).apply()

            progress["tweets_deleted"] += 1
            await update_progress(job, progress)

    # Deleting direct messages
    if user.direct_messages:
        # Make sure the DMs API authenticates successfully
        proceed = False
        dms_client = await peony_dms_client(user)
        try:
            twitter_user = await dms_client.user
            proceed = True
        except peony.exceptions.InvalidOrExpiredToken:
            # It doesn't, so disable deleting direct messages
            await user.update(
                direct_messages=False,
                twitter_dms_access_token="",
                twitter_dms_access_token_secret="",
            ).apply()

        if proceed:
            progress["status"] = f"Deleting direct messages"
            await update_progress(job, progress)

            # Delete DMs
            datetime_threshold = datetime.utcnow() - timedelta(
                days=user.direct_messages_threshold
            )

            # TODO: Work on making DMs work later

            # # Fetch DMs
            # dms_request = dms_client.api.direct_messages.events.list.get(count=50)
            # dm_ids = dms_request.iterator.with_cursor()

            # pages = await loop.run_in_executor(
            #     None,
            #     tweepy.Cursor(dms_api.list_direct_messages).pages,
            # )
            # while True:
            #     try:
            #         page = pages.next()
            #         await log(
            #             job,
            #             f"#{job_runner_id} Fetch DMs loop: got page with {len(page)} DMs",
            #         )
            #     except StopIteration:
            #         await log(
            #             job, f"#{job_runner_id} Hit the end of fetch DMs loop, breaking"
            #         )
            #         break
            #     except tweepy.errors.TweepyException as e:
            #         await update_progress_rate_limit(job, progress, job_runner_id)
            #         continue

            #     for dm in page:
            #         created_timestamp = datetime.fromtimestamp(
            #             int(dm.created_timestamp) / 1000
            #         )
            #         if created_timestamp <= datetime_threshold:
            #             # Try deleting the DM in a loop, in case it gets rate-limited
            #             while True:
            #                 try:
            #                     await loop.run_in_executor(
            #                         None, dms_api.destroy_direct_message, dm.id
            #                     )
            #                     await log(job, f"#{job_runner_id} Deleted DM {dm.id}")
            #                     break
            #                 except tweepy.errors.TweepyException as e:
            #                     if e.api_code == 429:  # 429 = Too Many Requests
            #                         await update_progress_rate_limit(
            #                             job, progress, job_runner_id
            #                         )
            #                         # Don't break, so it tries again
            #                     else:
            #                         if (
            #                             e.api_code == 89
            #                         ):  # 89 = Invalid or expired token.
            #                             pass
            #                         else:
            #                             # Unknown error
            #                             print(f"job_id={job.id} Error deleting DM {e}")
            #                             break

            #             progress["dms_deleted"] += 1
            #             await update_progress(job, progress)

            #         else:
            #             await log(job, f"Skipping DM {dm.id}")

    progress["status"] = "Finished"
    await update_progress(job, progress)

    await log(job, f"#{job_runner_id} Delete finished")

    # Delete is done!

    # Schedule the next delete job
    await create_job(user, "delete", datetime.now() + timedelta(days=1))

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
        # Create a nag
        await Nag.create(
            user_id=user.id,
            timestamp=datetime.now(),
        )

        # The user has never been nagged, so this is the first delete
        message = f"Congratulations! Semiphemeral has deleted {progress['tweets_deleted']} tweets, unretweeted {progress['retweets_deleted']} tweets, and unliked {progress['likes_deleted']} tweets. Doesn't that feel nice?\n\nEach day, I will download your latest tweets and likes and then delete the old ones based on your settings. You can sit back, relax, and enjoy the privacy.\n\nYou can always change your settings, mark new tweets to never delete, and pause Semiphemeral from the website https://{os.environ.get('DOMAIN')}/dashboard."

        await DirectMessageJob.create(
            dest_twitter_id=user.twitter_id,
            message=message,
            status="pending",
            scheduled_timestamp=datetime.now(),
            priority=0,
        )

        message = f"Semiphemeral is free, but running this service costs money. Care to chip in?\n\nIf you tip any amount, even just $1, I will stop nagging you for a year. Otherwise, I'll gently remind you once a month.\n\n(It's fine if you want to ignore these DMs. I won't care. I'm a bot, so I don't have feelings).\n\nVisit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"

        await DirectMessageJob.create(
            dest_twitter_id=user.twitter_id,
            message=message,
            status="pending",
            scheduled_timestamp=datetime.now(),
            priority=0,
        )

    else:
        if should_nag:
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
            jobs = (
                await Job.query.where(Job.user_id == user.id)
                .where(Job.job_type == "delete")
                .where(Job.status == "finished")
                .gino.all()
            )
            for job in jobs:
                if job.progress:
                    p = json.loads(job.progress)

                    if "tweets_deleted" in p:
                        total_progress["tweets_deleted"] += p["tweets_deleted"]
                    if "retweets_deleted" in p:
                        total_progress["retweets_deleted"] += p["retweets_deleted"]
                    if "likes_deleted" in p:
                        total_progress["likes_deleted"] += p["likes_deleted"]

                    if job.finished_timestamp > last_nag.timestamp:
                        if "tweets_deleted" in p:
                            total_progress_since_last_nag["tweets_deleted"] += p[
                                "tweets_deleted"
                            ]
                        if "retweets_deleted" in p:
                            total_progress_since_last_nag["retweets_deleted"] += p[
                                "retweets_deleted"
                            ]
                        if "likes_deleted" in p:
                            total_progress_since_last_nag["likes_deleted"] += p[
                                "likes_deleted"
                            ]

            message = f"Since you've been using Semiphemeral, I have deleted {total_progress['tweets_deleted']} tweets, unretweeted {total_progress['retweets_deleted']} tweets, and unliked {total_progress['likes_deleted']} tweets for you.\n\nJust since last month, I've deleted {total_progress_since_last_nag['tweets_deleted']} tweets, unretweeted {total_progress_since_last_nag['retweets_deleted']} tweets, and unliked {total_progress_since_last_nag['likes_deleted']} tweets.\n\nSemiphemeral is free, but running this service costs money. Care to chip in? Visit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"

            await DirectMessageJob.create(
                dest_twitter_id=user.twitter_id,
                message=message,
                status="pending",
                scheduled_timestamp=datetime.now(),
                priority=0,
            )


@test_api_creds
@ensure_user_follows_us
async def delete_dms(gino_db, job, job_runner_id):
    await delete_dms_job(job, "dms", job_runner_id)


@test_api_creds
@ensure_user_follows_us
async def delete_dm_groups(gino_db, job, job_runner_id):
    await delete_dms_job(job, "groups", job_runner_id)


async def delete_dms_job(job, dm_type, job_runner_id):
    user = await User.query.where(User.id == job.user_id).gino.first()

    dms_client = await peony_dms_client(user)
    try:
        twitter_user = await dms_client.user
    except peony.exceptions.InvalidOrExpiredToken:
        await log(
            job, f"#{job_runner_id} DMs Twitter API creds don't work, canceling job"
        )
        await job.update(status="canceled", started_timestamp=datetime.now()).apply()
        raise JobCanceled()

    if dm_type == "dms":
        await log(job, f"#{job_runner_id} Delete DMs started")
    elif dm_type == "groups":
        await log(job, f"#{job_runner_id} Delete group DMs started")

    # Start the progress
    progress = {"dms_deleted": 0, "dms_skipped": 0, "status": "Verifying permissions"}
    await update_progress(job, progress)

    # Make sure deleting DMs is enabled
    if not user.direct_messages:
        await log(job, f"#{job_runner_id} Deleting DMs is not enabled, canceling job")
        await job.update(status="canceled", started_timestamp=datetime.now()).apply()
        raise JobCanceled()

    # Load the DM metadata
    if dm_type == "dms":
        filename = os.path.join("/var/bulk_dms", f"dms-{user.id}.json")
    elif dm_type == "groups":
        filename = os.path.join("/var/bulk_dms", f"groups-{user.id}.json")
    if not os.path.exists(filename):
        await log(
            job, f"#{job_runner_id} Filename {filename} does not exist, canceling job"
        )
        await job.update(status="canceled", started_timestamp=datetime.now()).apply()
        raise JobCanceled()
    with open(filename) as f:
        try:
            conversations = json.loads(f.read())
        except:
            await log(job, f"#{job_runner_id} Cannot decode JSON, canceling job")
            await job.update(
                status="canceled", started_timestamp=datetime.now()
            ).apply()
            raise JobCanceled()

    # Delete DMs
    progress["status"] = "Deleting old direct messages"
    await update_progress(job, progress)

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

                    await dms_client.api.direct_messages.events.destroy.delete(id=dm_id)

                    # TODO: handle exceptions, but I'm not sure which exceptions yet
                    # Here's some exception code:

                    # await log(
                    #     job,
                    #     f"#{job_runner_id} Error deleting DM {dm_id}: {e}",
                    # )

                    # progress["dms_skipped"] += 1
                    # await update_progress(job, progress)
                    # break

    # Delete the DM metadata file
    try:
        os.remove(filename)
    except:
        pass

    progress["status"] = "Finished"
    await update_progress(job, progress)

    await log(job, f"#{job_runner_id} Delete DMs finished")

    # Send a DM to the user
    if dm_type == "dms":
        message = f"Congratulations, Semiphemeral just finished deleting {progress['dms_deleted']} of your old direct messages."
    elif dm_type == "groups":
        message = f"Congratulations, Semiphemeral just finished deleting {progress['dms_deleted']} of your old group direct messages."

    await DirectMessageJob.create(
        dest_twitter_id=user.twitter_id,
        message=message,
        status="pending",
        scheduled_timestamp=datetime.now(),
        priority=0,
    )


async def start_job(gino_db, job, job_runner_id):
    # Stagger job starting times a bit, to stagger database locking
    await asyncio.sleep(0.2 * job_runner_id)

    await log(job, f"#{job_runner_id} Starting job")
    await job.update(
        status="active",
        started_timestamp=datetime.now(),
        container_name=f"{job_runner_id}",
    ).apply()

    try:
        if job.job_type == "fetch":
            await fetch(gino_db, job, job_runner_id)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()

        elif job.job_type == "delete":
            await fetch(gino_db, job, job_runner_id)
            await delete(gino_db, job, job_runner_id)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()

        elif job.job_type == "delete_dms":
            await delete_dms(gino_db, job, job_runner_id)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()

        elif job.job_type == "delete_dm_groups":
            await delete_dm_groups(gino_db, job, job_runner_id)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()

    except UserBlocked:
        await job.update(status="blocked", finished_timestamp=datetime.now()).apply()

    except JobRescheduled:
        pass

    except JobCanceled:
        pass

    await log(job, f"#{job_runner_id} Finished job")


async def start_dm_job(dm_job):
    client = await peony_semiphemeral_dm_client()

    try:
        # Send the DM
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, api.send_direct_message, dm_job.dest_twitter_id, dm_job.message
        )

        # Success, update dm_job as sent
        await dm_job.update(status="sent", sent_timestamp=datetime.now()).apply()

        print(
            f"[{datetime.now().strftime('%c')}] dm_job_id={dm_job.id} sent DM to twitter_id={dm_job.dest_twitter_id}"
        )
    except Exception as e:
        try:
            error_code = e.args[0][0]["code"]
        except:
            if (
                hasattr(e, "reason")
                and e.reason == "Twitter error response: status code = 420"
            ):
                error_code = 420
            else:
                error_code = e.api_code

        # 150: You cannot send messages to users who are not following you.
        # 349: You cannot send messages to this user.
        # 108: Cannot find specified user.
        # 89: Invalid or expired token.
        # 389: You cannot send messages to users you have blocked.
        if (
            error_code == 150
            or error_code == 349
            or error_code == 108
            or error_code == 89
            or error_code == 389
        ):
            print(
                f"[{datetime.now().strftime('%c')}] dm_job_id={dm_job.id} failed to send DM ({e}) error code {error_code}, marking as failure"
            )
            await dm_job.update(status="failed").apply()
        elif error_code == 226 or error_code == 420:
            # 226: This request looks like it might be automated. To protect our users from spam and
            # other malicious activity, we can't complete this action right now. Please try again later.
            # 420: Enhance Your Calm
            await dm_job.update(
                status="pending",
                scheduled_timestamp=datetime.now() + timedelta(minutes=10),
            ).apply()
            print(
                f"[{datetime.now().strftime('%c')}] dm_job_id={dm_job.id} sending DMs too fast, rescheduling and cooling off on DM sending for 10 minutes"
            )
            await asyncio.sleep(10 * 60)
        else:
            # If sending the DM failed, try again in 5 minutes
            await dm_job.update(
                status="pending",
                scheduled_timestamp=datetime.now() + timedelta(minutes=5),
            ).apply()
            print(f"{type(e)}, {dir(e)}")
            print(f"api_code={e.api_code}, reason={e.reason}")
            print(
                f"[{datetime.now().strftime('%c')}] dm_job_id={dm_job.id} failed to send DM ({e}), delaying 5 minutes"
            )


async def start_block_job(block_job):
    client = await peony_semiphemeral_dm_client()

    # Are they already blocked?
    friendship = await client.api.friendships.show.get(
        source_screen_name="semiphemeral",
        target_screen_name=block_job.twitter_username,
        _data=(block_job, None, None),
    )
    if friendship["relationship"]["source"]["blocking"]:
        # Already blocked, so our work here is done
        await block_job.update(
            status="blocked", blocked_timestamp=datetime.now()
        ).apply()
        print(
            f"[{datetime.now().strftime('%c')}] block_job_id={block_job.id} already blocked {block_job.twitter_username}"
        )
        return

    # If we're blocking a semiphemeral user, and not just a fascist influencer
    if block_job.user_id:
        user = await User.query.where(User.id == block_job.user_id).gino.first()
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
                unblock_timestamp = last_fascist_tweet.created_at + timedelta(days=180)
            else:
                unblock_timestamp = datetime.now() + timedelta(days=180)
            unblock_timestamp_formatted = unblock_timestamp.strftime("%B %-d, %Y")

            # Send the DM
            message_text = f"You have liked {len(fascist_tweets)} tweets from a prominent fascist or fascist sympathizer within the last 6 months, so you have been blocked and your Semiphemeral account is deactivated.\n\nTo see which tweets you liked and learn how to get yourself unblocked, see https://{os.environ.get('DOMAIN')}/dashboard.\n\nOr you can wait until {unblock_timestamp_formatted} when you will get automatically unblocked, at which point you can login to reactivate your account so long as you've stop liking tweets from fascists."

            message = {
                "event": {
                    "type": "message_create",
                    "message_create": {
                        "target": {"recipient_id": int(user.twitter_id)},
                        "message_data": {"text": message_text},
                    },
                }
            }
            await client.api.direct_messages.events.new.post(
                _json=message, _data=(block_job, None, None)
            )
            print(
                f"[{datetime.now().strftime('%c')}] block_job_id={block_job.id} sent DM to {block_job.twitter_username}"
            )

            # Create the unblock job
            await UnblockJob.create(
                user_id=block_job.user_id,
                twitter_username=block_job.twitter_username,
                status="pending",
                scheduled_timestamp=unblock_timestamp,
            )

            # Wait 10 seconds before blocking, to ensure they receive the DM
            await asyncio.sleep(10)

    # Block the user
    await client.api.blocks.create.post(
        screen_name=block_job.twitter_username, _data=(block_job, None, None)
    )

    # Success, update block_job
    await block_job.update(status="blocked", blocked_timestamp=datetime.now()).apply()

    print(
        f"[{datetime.now().strftime('%c')}] block_job_id={block_job.id} blocked user {block_job.twitter_username}"
    )


async def start_unblock_job(unblock_job):
    client = await peony_semiphemeral_dm_client()

    # Are they already unblocked?
    friendship = await client.api.friendships.show.get(
        source_screen_name="semiphemeral",
        target_screen_name=unblock_job.twitter_username,
        _data=(unblock_job, None, None),
    )
    if not friendship["relationship"]["source"]["blocking"]:
        # Update the user
        user = await User.query.where(User.id == unblock_job.user_id).gino.first()
        if user and user.blocked:
            await user.update(paused=True, blocked=False).apply()

        # Already unblocked, so our work here is done
        await unblock_job.update(
            status="unblocked", unblocked_timestamp=datetime.now()
        ).apply()
        print(
            f"[{datetime.now().strftime('%c')}] unblock_job_id={unblock_job.id} already unblocked {unblock_job.twitter_username}"
        )
        return

    # Unblock them
    await client.api.blocks.create.destroy(
        screen_name=unblock_job.twitter_username, _data=(unblock_job, None, None)
    )

    # If we're unblocking a semiphemeral user
    if unblock_job.user_id:
        user = await User.query.where(User.id == unblock_job.user_id).gino.first()
        if user and user.blocked:
            # Update the user
            await user.update(paused=True, blocked=False).apply()

    # Success, update block_job
    await unblock_job.update(
        status="unblocked", unblocked_timestamp=datetime.now()
    ).apply()

    print(
        f"[{datetime.now().strftime('%c')}] unblock_job_id={unblock_job.id} unblocked user {unblock_job.twitter_username}"
    )


async def job_runner(gino_db, job_runner_id):
    global job_q, job_q_lock, job_q_last_refresh

    while True:
        # Wait until the job queue isn't locked
        while job_q_lock:
            await asyncio.sleep(1)

        # If there are no jobs in the queue and it hasn't been refreshed recently
        recently = datetime.now() - timedelta(minutes=2)
        if job_q.qsize() == 0 and (
            (not job_q_last_refresh or job_q_last_refresh < recently)
            or os.environ.get("DEPLOY_ENVIRONMENT") == "staging"
        ):
            job_q_lock = True

            if os.environ.get("DEPLOY_ENVIRONMENT") != "staging":
                print(
                    f"#{job_runner_id} Job queue is empty, replenishing from the database"
                )

            # Add all pending job_ids to the queue
            async with gino_db.acquire() as conn:
                now = datetime.now()

                await conn.all("BEGIN")
                r = await conn.all(
                    text(
                        "SELECT id FROM jobs WHERE status='pending' AND scheduled_timestamp <= :scheduled_timestamp ORDER BY scheduled_timestamp FOR UPDATE SKIP LOCKED"
                    ),
                    scheduled_timestamp=now,
                )

                for row in r:
                    job_id = row[0]
                    job_q.put(job_id)

                await conn.all(
                    text(
                        "UPDATE jobs SET status='queued' WHERE status='pending' AND scheduled_timestamp <= :scheduled_timestamp"
                    ),
                    scheduled_timestamp=now,
                )
                await conn.all("COMMIT")

            if os.environ.get("DEPLOY_ENVIRONMENT") != "staging":
                print(
                    f"#{job_runner_id} There are {job_q.qsize()} pending jobs in the queue"
                )

            job_q_lock = False
            job_q_last_refresh = datetime.now()

        try:
            job_id = job_q.get(block=False)
            job = await Job.query.where(Job.id == job_id).gino.first()
            if job:
                try:
                    await start_job(gino_db, job, job_runner_id)
                except NoSuchRowError:
                    print(
                        f"#{job_runner_id} gino.exceptions.NoSuchRowError, moving on to the next job"
                    )

        except queue.Empty:
            if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(60 * 5)


async def start_jobs(gino_db):
    # In case the app crashed in the middle of any previous jobs, change all "active"
    # jobs to "pending" so they'll start over
    await Job.update.values(status="pending").where(
        Job.status == "active"
    ).gino.status()
    await Job.update.values(status="pending").where(
        Job.status == "queued"
    ).gino.status()

    # If staging, start by pausing all users and cancel all pending jobs
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        print("Staging environment, so pausing all users and canceling all jobs")
        await User.update.values(paused=True).gino.status()
        await Job.update.values(status="canceled").where(
            Job.status == "pending"
        ).gino.status()
        await DirectMessageJob.update.values(status="canceled").where(
            DirectMessageJob.status == "pending"
        ).gino.status()
        await BlockJob.update.values(status="canceled").where(
            BlockJob.status == "pending"
        ).gino.status()
        await UnblockJob.update.values(status="canceled").where(
            UnblockJob.status == "pending"
        ).gino.status()

    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        job_runner_count = 2
    else:
        job_runner_count = 10

    await asyncio.gather(
        *[
            job_runner(gino_db, job_runner_id)
            for job_runner_id in range(job_runner_count)
        ]
    )


async def start_dm_jobs():
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        await asyncio.sleep(5)
    await send_admin_notification(
        f"DM jobs container started ({os.environ.get('DEPLOY_ENVIRONMENT')})"
    )

    while True:
        tasks = []

        # Run the first direct message job (only send one per minute)
        dm_job = (
            await DirectMessageJob.query.where(DirectMessageJob.status == "pending")
            .where(DirectMessageJob.scheduled_timestamp <= datetime.now())
            .order_by(DirectMessageJob.priority)
            .order_by(DirectMessageJob.scheduled_timestamp)
            .gino.first()
        )
        if dm_job:
            tasks.append(start_dm_job(dm_job))

        # Run all block jobs
        for block_job in (
            await BlockJob.query.where(BlockJob.status == "pending")
            .where(BlockJob.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
            tasks.append(start_block_job(block_job))

        # Run all unblock jobs
        for unblock_job in (
            await UnblockJob.query.where(UnblockJob.status == "pending")
            .where(UnblockJob.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
            tasks.append(start_unblock_job(unblock_job))

        if len(tasks) > 0:
            print(f"Running {len(tasks)} DM/block/unblock jobs")
            await asyncio.gather(*tasks)

        print(f"Waiting 60s")
        await asyncio.sleep(60)
