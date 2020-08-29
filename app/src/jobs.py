import asyncio
import json
import os
import shutil
import csv
from datetime import datetime, timedelta
import time
import zipfile

import tweepy
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from common import (
    twitter_api,
    twitter_api_call,
    twitter_dm_api,
    tweets_to_delete,
    send_admin_dm,
)
from db import (
    Job,
    DirectMessageJob,
    BlockJob,
    UnblockJob,
    ExportJob,
    User,
    Tip,
    Nag,
    Tweet,
    Thread,
    Fascist,
)


class JobRescheduled(Exception):
    pass


class UserBlocked(Exception):
    pass


async def log(job, s):
    print(f"[{datetime.now().strftime('%c')}] job_id={job.id} {s}")


def test_api_creds(func):
    async def wrapper(job):
        """
        Make sure the API creds work, and if not pause semiphemeral for the user
        """
        user = await User.query.where(User.id == job.user_id).gino.first()
        api = await twitter_api(user)
        try:
            # Make an API request
            await twitter_api_call(api, "me")
        except tweepy.error.TweepError as e:
            print(
                f"user_id={user.id} API creds failed ({e}), canceling job and pausing user"
            )
            await user.update(paused=True).apply()
            await job.update(status="canceled").apply()
            return False

        return await func(job)

    return wrapper


def ensure_user_follows_us(func):
    async def wrapper(job):
        user = await User.query.where(User.id == job.user_id).gino.first()

        # Make an exception for semiphemeral user, because semiphemeral can't follow semiphemeral
        if user.twitter_screen_name == "semiphemeral":
            return await func(job)

        api = await twitter_api(user)

        # Is the user following us?
        friendship = (
            await twitter_api_call(
                api,
                "show_friendship",
                source_id=user.twitter_id,
                target_screen_name="semiphemeral",
            )
        )[0]

        if friendship.blocked_by:
            # The semiphemeral user has blocked this user, so they're not allowed
            # to use this service
            print(f"user_id={user.id} is blocked, canceling job and updating user")
            await job.update(status="canceled").apply()
            await user.update(paused=True, blocked=True).apply()
            return False

        elif not friendship.following:
            # Make follow request
            print(f"user_id={user.id} not following, making follow request")
            await twitter_api_call(
                api, "create_friendship", screen_name="semiphemeral", follow=True
            )

        return await func(job)

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


async def update_progress(job, progress):
    await job.update(progress=json.dumps(progress)).apply()


async def update_progress_rate_limit(job, progress, minutes):
    await log(job, f"Hit twitter rate limit, waiting {minutes} minutes")

    old_status = progress["status"]

    # Change status message
    progress[
        "status"
    ] = f"Not so fast... I hit Twitter's rate limit, waiting {minutes} minutes"
    await update_progress(job, progress)

    # Wait
    await asyncio.sleep(minutes * 60)

    # Change status message back
    progress["status"] = old_status
    await update_progress(job, progress)

    await log(job, "Finished waiting, resuming")


async def save_tweet(user, status):
    # Mark any new fascist tweets as fascist
    fascist = await Fascist.query.where(
        Fascist.username == status.author.screen_name
    ).gino.first()
    if fascist:
        is_fascist = True
    else:
        is_fascist = False

    return await Tweet.create(
        user_id=user.id,
        created_at=status.created_at,
        twitter_user_id=status.author.id,
        twitter_user_screen_name=status.author.screen_name,
        status_id=status.id,
        text=status.full_text,
        in_reply_to_screen_name=status.in_reply_to_screen_name,
        in_reply_to_status_id=status.in_reply_to_status_id,
        in_reply_to_user_id=status.in_reply_to_user_id,
        retweet_count=status.retweet_count,
        favorite_count=status.favorite_count,
        retweeted=status.retweeted,
        favorited=status.favorited,
        is_retweet=hasattr(status, "retweeted_status"),
        is_deleted=False,
        is_unliked=False,
        exclude_from_delete=False,
        is_fascist=is_fascist,
    )


async def import_tweet_and_thread(user, api, job, progress, status):
    """
    This imports a tweet, and recursively imports all tweets that it's in reply to,
    and returns the number of tweets fetched
    """
    # Is the tweet already saved?
    tweet = await (
        Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.status_id == status.id)
        .gino.first()
    )
    if not tweet:
        # Save the tweet
        await log(job, f"Saving tweet: {status.id}")
        tweet = await save_tweet(user, status)
    else:
        await log(
            job,
            f"Tweet of {status.id} already imported",
        )

    # Is this tweet a reply?
    if tweet.in_reply_to_status_id:
        # Do we already have the parent tweet?
        parent_tweet = await (
            Tweet.query.where(Tweet.user_id == user.id)
            .where(Tweet.status_id == tweet.in_reply_to_status_id)
            .gino.first()
        )
        if not parent_tweet:
            # If we don't have the parent tweet, import it
            while True:  # loop in case we get rate-limited
                try:
                    parent_status = await twitter_api_call(
                        api,
                        "get_status",
                        id=tweet.in_reply_to_status_id,
                        tweet_mode="extended",
                    )
                    await import_tweet_and_thread(
                        user, api, job, progress, parent_status
                    )
                    break
                except tweepy.error.TweepError as e:
                    try:
                        error_code = e.args[0][0]["code"]
                    except:
                        error_code = e.api_code

                    # On rate limit, try again
                    if error_code == 88:  # 88 = Rate limit exceeded
                        await update_progress_rate_limit(job, progress, 5)
                    else:
                        # Otherwise (it's been deleted, the user is suspended, unauthorized, blocked), ignore
                        await log(job, f"Error importing parent tweet: {e}")
                        break


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
async def fetch(job):
    user = await User.query.where(User.id == job.user_id).gino.first()
    api = await twitter_api(user)

    since_id = user.since_id

    await log(job, "Fetch started")

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

    # Fetch tweets from timeline a page at a time
    pages = await loop.run_in_executor(
        None,
        tweepy.Cursor(
            api.user_timeline,
            id=user.twitter_screen_name,
            since_id=since_id,
            tweet_mode="extended",
        ).pages,
    )
    while True:
        try:
            # Sadly, I can't figure out a good way of making the cursor's next() function
            # happen in the executor, so it will be a blocking call. If I try running it
            # with loop.run_in_executor, the StopIteration exception gets lost, and the code
            # simply freezes when the loop is done, and never continues.

            # page = await loop.run_in_executor(None, pages.next)
            page = pages.next()
            await log(job, f"Fetch tweets loop: got page with {len(page)} tweets")
        except StopIteration:
            await log(job, f"Hit the end of fetch tweets loop, breaking")
            break
        except tweepy.TweepError as e:
            if str(e) == "Twitter error response: status code = 404":
                # Twitter responded with a 404 error, which could mean the user has deleted their account
                await log(
                    job,
                    f"404 error from twitter (account does not exist), so pausing user",
                )
                await user.update(paused=True).apply()
                # await reschedule_job(job, timedelta(minutes=15))
                return

            await update_progress_rate_limit(job, progress, 15)
            continue

        # Import these tweets, and all their threads
        for status in page:
            await import_tweet_and_thread(user, api, job, progress, status)
            progress["tweets_fetched"] += 1

        await update_progress(job, progress)

        # Now hunt for threads. This is a dict that maps the root status_id
        # to a list of status_ids in the thread
        threads = {}
        for status in page:
            if status.in_reply_to_status_id:
                status_ids = await calculate_thread(user, status.id)
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
                    user_id=user.id, root_status_id=root_status_id, should_exclude=False
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

        await log(job, f"Fetch tweets loop progress: {progress}")
        await update_progress(job, progress)

    # Update progress
    progress["status"] = "Downloading tweets that you liked"
    await update_progress(job, progress)

    # Fetch tweets that are liked
    pages = await loop.run_in_executor(
        None,
        tweepy.Cursor(
            api.favorites,
            id=user.twitter_screen_name,
            since_id=since_id,
            tweet_mode="extended",
        ).pages,
    )
    while True:
        try:
            page = pages.next()
            await log(job, f"Fetch likes loop: got page with {len(page)} tweets")
        except StopIteration:
            await log(job, f"Hit the end of fetch likes loop, breaking")
            break
        except tweepy.TweepError as e:
            if str(e) == "Twitter error response: status code = 404":
                # Twitter responded with a 404 error, which could mean the user has deleted their account
                await log(
                    job,
                    f"404 error from twitter (account does not exist), so pausing user",
                )
                await user.update(paused=True).apply()
                # await reschedule_job(job, timedelta(minutes=15))
                return

            await update_progress_rate_limit(job, progress, 15)
            continue

        # Import these tweets
        for status in page:

            # Is the tweet already saved?
            tweet = await (
                Tweet.query.where(Tweet.user_id == user.id)
                .where(Tweet.status_id == status.id)
                .gino.first()
            )
            if not tweet:
                # Save the tweet
                await log(job, f"Saving tweet: {status.id}")
                await save_tweet(user, status)

            progress["likes_fetched"] += 1

        await log(job, f"Fetch likes loop progress: {progress}")
        await update_progress(job, progress)

    # All done, update the since_id
    tweet = await (
        Tweet.query.where(Tweet.user_id == user.id)
        .order_by(Tweet.status_id.desc())
        .gino.first()
    )
    if tweet:
        await user.update(since_id=tweet.status_id).apply()

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
    if len(fascist_tweets) > 0:
        # Create a block job
        await BlockJob.create(
            user_id=user.id,
            twitter_username=user.twitter_screen_name,
            status="pending",
            scheduled_timestamp=datetime.now(),
        )
        # Don't send any DMs
        await log(job, "Blocking user")
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
        )

    await log(job, f"Fetch complete")


@test_api_creds
@ensure_user_follows_us
async def delete(job):
    user = await User.query.where(User.id == job.user_id).gino.first()
    api = await twitter_api(user)

    loop = asyncio.get_running_loop()

    await log(job, "Delete started")

    # Start the progress
    progress = json.loads(job.progress)
    progress["tweets_deleted"] = 0
    progress["retweets_deleted"] = 0
    progress["likes_deleted"] = 0

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
                # Try deleting the tweet, in a while loop in case it gets rate limited and
                # needs to try again
                while True:
                    try:
                        await loop.run_in_executor(
                            None, api.destroy_status, tweet.status_id
                        )
                        await tweet.update(is_deleted=True).apply()
                        break
                    except tweepy.error.TweepError as e:
                        if e.api_code == 144:
                            # Already deleted
                            await tweet.update(is_deleted=True).apply()
                            break
                        elif e.api_code == 429:  # 429 = Too Many Requests
                            await update_progress_rate_limit(job, progress, 15)
                            # Don't break, so it tries again
                        else:
                            # Unknown error
                            print(f"job_id={job.id} Error deleting retweet {e}")
                            break

                progress["retweets_deleted"] += 1
                await update_progress(job, progress)

            await log(job, f"Delete retweets progress: {progress}")

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
                # Try unliking the tweet, in a while loop in case it gets rate limited and
                # needs to try again
                while True:
                    try:
                        await loop.run_in_executor(
                            None, api.destroy_favorite, tweet.status_id
                        )
                        await tweet.update(is_unliked=True).apply()
                        break
                    except tweepy.error.TweepError as e:
                        if e.api_code == 144:  # 144 = No status found with that ID
                            # Already unliked
                            await tweet.update(is_unliked=True).apply()
                            break
                        elif e.api_code == 429:  # 429 = Too Many Requests
                            await update_progress_rate_limit(job, progress, 15)
                            # Don't break, so it tries again
                        else:
                            # Unknown error
                            print(f"job_id={job.id} Error unliking tweet {e}")
                            break

                progress["likes_deleted"] += 1
                await update_progress(job, progress)

            await log(job, f"Delete likes progress: {progress}")

    # Deleting tweets
    if user.delete_tweets:
        tweets = tweets = await tweets_to_delete(user)

        progress[
            "status"
        ] = f"Deleting {len(tweets)} tweets, starting with the earliest"
        await update_progress(job, progress)

        for tweet in tweets:
            # Try deleting the tweet, in a while loop in case it gets rate limited and
            # needs to try again
            while True:
                try:
                    await loop.run_in_executor(
                        None, api.destroy_status, tweet.status_id
                    )
                    await tweet.update(is_deleted=True, text=None).apply()
                    break
                except tweepy.error.TweepError as e:
                    if e.api_code == 144:  # No status found with that ID
                        # Already deleted
                        await tweet.update(is_deleted=True, text=None).apply()
                        break
                    elif e.api_code == 429:  # 429 = Too Many Requests
                        await update_progress_rate_limit(job, progress, 15)
                        # Don't break, so it tries again
                    else:
                        # Unknown error
                        print(f"job_id={job.id} Error deleting tweet {e}")
                        break

            progress["tweets_deleted"] += 1
            await update_progress(job, progress)

        await log(job, f"Delete tweets progress: {progress}")

    progress["status"] = "Finished"
    await update_progress(job, progress)

    await log(job, "Delete finished")

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
        )

        message = f"Semiphemeral is free, but running this service costs money. Care to chip in?\n\nIf you tip any amount, even just $1, I will stop nagging you for a year. Otherwise, I'll gently remind you once a month.\n\n(It's fine if you want to ignore these DMs. I won't care. I'm a bot, so I don't have feelings).\n\nVisit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"

        await DirectMessageJob.create(
            dest_twitter_id=user.twitter_id,
            message=message,
            status="pending",
            scheduled_timestamp=datetime.now(),
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
            )


async def start_job(job):
    await log(job, "Starting job")
    await job.update(status="active", started_timestamp=datetime.now()).apply()

    if job.job_type == "fetch":
        try:
            await fetch(job)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()
        except UserBlocked:
            await job.update(
                status="blocked", finished_timestamp=datetime.now()
            ).apply()
        except JobRescheduled:
            pass

    elif job.job_type == "delete":
        try:
            await fetch(job)
            await delete(job)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()
        except UserBlocked:
            await job.update(
                status="blocked", finished_timestamp=datetime.now()
            ).apply()
        except JobRescheduled:
            pass

    await log(job, "Finished job")


async def start_dm_job(dm_job):
    api = await twitter_dm_api()

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
            error_code = e.api_code

        # 150: You cannot send messages to users who are not following you.
        # 349: You cannot send messages to this user.
        # 108: Cannot find specified user.
        if error_code == 150 or error_code == 349 or error_code == 108:
            print(
                f"[{datetime.now().strftime('%c')}] dm_job_id={dm_job.id} failed to send DM ({e}), marking as failure"
            )
            await dm_job.update(status="failed").apply()
        else:
            # If sending the DM failed, try again in 5 minutes
            await dm_job.update(
                status="pending",
                scheduled_timestamp=datetime.now() + timedelta(minutes=5),
            ).apply()

            print(
                f"[{datetime.now().strftime('%c')}] dm_job_id={dm_job.id} failed to send DM ({e}), delaying 5 minutes"
            )


async def start_block_job(block_job):
    api = await twitter_dm_api()

    try:
        # Are they already blocked?
        friendship = (
            await twitter_api_call(
                api,
                "show_friendship",
                source_screen_name="semiphemeral",
                target_screen_name=block_job.twitter_username,
            )
        )[0]

        if friendship.blocking:
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
                message = f"You have liked at least one tweet from a fascist or fascist sympathizer within the last 6 months, so you have been blocked and your Semiphemeral account is deactivated. See https://{os.environ.get('DOMAIN')}/dashboard for more information.\n\nYou will get automatically unblocked on {unblock_timestamp_formatted}. You can try logging in to reactivate your account then, so long as you stop liking tweets from fascists."

                await twitter_api_call(
                    api,
                    "send_direct_message",
                    recipient_id=user.twitter_id,
                    text=message,
                )
                print(
                    f"[{datetime.now().strftime('%c')}] block_job_id={block_job.id} sent DM to {block_job.twitter_username}"
                )

                # Update the user
                await user.update(paused=True, blocked=True).apply()

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
        await twitter_api_call(
            api, "create_block", screen_name=block_job.twitter_username
        )

        # Success, update block_job
        await block_job.update(
            status="blocked", blocked_timestamp=datetime.now()
        ).apply()

        print(
            f"[{datetime.now().strftime('%c')}] block_job_id={block_job.id} blocked user {block_job.twitter_username}"
        )
    except Exception as e:
        # Try again in 5 minutes
        await block_job.update(
            status="pending", scheduled_timestamp=datetime.now() + timedelta(minutes=5)
        ).apply()

        print(
            f"[{datetime.now().strftime('%c')}] block_job_id={block_job.id} failed ({e}), delaying 5 minutes"
        )


async def start_unblock_job(unblock_job):
    api = await twitter_dm_api()

    try:
        # Are they already unblocked?
        friendship = (
            await twitter_api_call(
                api,
                "show_friendship",
                source_screen_name="semiphemeral",
                target_screen_name=unblock_job.twitter_username,
            )
        )[0]

        if not friendship.blocking:
            # Already unblocked, so our work here is done
            await unblock_job.update(
                status="unblocked", unblocked_timestamp=datetime.now()
            ).apply()
            print(
                f"[{datetime.now().strftime('%c')}] unblock_job_id={unblock_job.id} already unblocked {unblock_job.twitter_username}"
            )
            return

        # Unblock them
        await twitter_api_call(
            api, "destroy_block", screen_name=unblock_job.twitter_username
        )

        # If we're unblocking a semiphemeral user
        if unblock_job.user_id:
            user = await User.query.where(id=unblock_job.user_id).gino.first()
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
    except Exception as e:
        # Try again in 5 minutes
        await unblock_job.update(
            status="pending", scheduled_timestamp=datetime.now() + timedelta(minutes=5)
        ).apply()

        print(
            f"[{datetime.now().strftime('%c')}] unblock_job_id={unblock_job.id} failed ({e}), delaying 5 minutes"
        )


async def start_export_job(export_job):
    await export_job.update(status="active", started_timestamp=datetime.now()).apply()

    user = await User.query.where(User.id == export_job.user_id).gino.first()
    api = await twitter_api(user)

    export_date = datetime.now()

    # Prepare export directory
    export_dir = os.path.join("/export", str(user.twitter_screen_name))
    if os.path.exists(export_dir):
        shutil.rmtree(export_dir, ignore_errors=True)
    os.makedirs(export_dir)
    os.makedirs(os.path.join(export_dir, "screenshots"))
    await log(export_job, f"Export started, export_dir={export_dir}")

    # Start the selenium web driver
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    d = webdriver.Chrome(options=options)
    d.set_window_size(700, 900)

    # Start the CSV
    csv_filename = os.path.join(export_dir, "tweets.csv")
    screenshot_filenames = []
    with open(csv_filename, "w") as f:
        fieldnames = [
            "Date",  # created_at
            "Username",  # twitter_user_screen_name
            "Tweet ID",  # status_id
            "Text",  # text
            "Replying to Username",  # in_reply_to_screen_name
            "Replying to Tweet ID",  # in_reply_to_status_id
            "Retweets",  # retweet_count
            "Likes",  # favorite_count
            "Retweeted",  # is_retweet
            "Liked",  # favorited
            "Screenshot",
            "URL",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, dialect="unix")
        writer.writeheader()

        tweets = (
            await Tweet.query.where(Tweet.user_id == export_job.user_id)
            .where(Tweet.twitter_user_id == user.twitter_id)
            .where(Tweet.is_deleted == False)
            .where(Tweet.is_unliked == False)
            .order_by(Tweet.created_at.desc())
            .gino.all()
        )
        for tweet in tweets:
            url = f"https://twitter.com/{user.twitter_screen_name}/status/{tweet.status_id}"
            screenshot_filename = (
                f"{tweet.created_at.strftime('%Y-%m-%d_%H%M%S')}_{tweet.status_id}.png"
            )
            screenshot_filenames.append(screenshot_filename)

            # Write the row
            writer.writerow(
                {
                    "Date": tweet.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "Username": tweet.twitter_user_screen_name,
                    "Tweet ID": str(tweet.status_id),
                    "Text": tweet.text,
                    "Replying to Username": tweet.in_reply_to_screen_name,
                    "Replying to Tweet ID": str(tweet.in_reply_to_status_id),
                    "Retweets": str(tweet.retweet_count),
                    "Likes": str(tweet.favorite_count),
                    "Retweeted": str(tweet.is_retweet),
                    "Liked": str(tweet.favorited),
                    "Screenshot": screenshot_filename,
                    "URL": url,
                }
            )

            # Take screenshot
            await log(export_job, f"Screenshoting {url}")
            d.get(url)
            await asyncio.sleep(1)
            d.save_screenshot(
                os.path.join(export_dir, "screenshots", screenshot_filename)
            )

    await log(export_job, f"CSV written: {csv_filename}")

    # Write readme.txt
    with open(os.path.join(export_dir, "readme.txt"), "w") as f:
        f.write("Semiphemeral export of tweets\n")
        f.write(f"Export started: {export_date.strftime('%Y-%m-%d at %H:%M')}\n\n")
        f.write(
            "The text from all of your tweets are saved in the spreadsheet tweets.csv. Open it in spreadsheet software like LibreOffice Calc, Microsoft Excel, or Google Docs.\n\n"
        )
        f.write(
            "Screenshots of all your tweets are in the screenshots folder. To find a screenshot of a specific tweet, search the spreadsheet for it and then find its filename in the 'Screenshot' column.\n"
        )

    # Zip it all up
    zip_filename = os.path.join(export_dir, f"export.zip")
    with zipfile.ZipFile(zip_filename, "w") as z:
        z.write(os.path.join(export_dir, "readme.txt"), arcname="readme.txt")
        z.write(os.path.join(export_dir, "tweets.csv"), arcname="tweets.csv")
        z.write(os.path.join(export_dir, "screenshots"), arcname="screenshots")

    # Now that it's compressed, delete the uncompressed stuff to save disk space
    os.remove(os.path.join(export_dir, "readme.txt"))
    os.remove(os.path.join(export_dir, "tweets.csv"))
    shutil.rmtree(os.path.join(export_dir, "screenshots"))

    # All finished! Update the job
    await export_job.update(
        status="finished", finished_timestamp=datetime.now()
    ).apply()

    # Send a DM
    message = f"The export of your tweets is ready to download! Get it from here: https://{os.environ.get('DOMAIN')}/export"
    await DirectMessageJob.create(
        dest_twitter_id=user.twitter_id,
        message=message,
        status="pending",
        scheduled_timestamp=datetime.now(),
    )


async def start_jobs():
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        await asyncio.sleep(5)
    await send_admin_dm(
        f"jobs container started ({os.environ.get('DEPLOY_ENVIRONMENT')})"
    )

    seconds_to_sleep = int(os.environ.get("SECONDS_TO_SLEEP"))
    print(f"Sleeping {seconds_to_sleep} seconds")
    await asyncio.sleep(seconds_to_sleep)

    # Infinitely loop looking for pending jobs
    while True:
        tasks = []

        # Run the next 10 fetch and delete jobs
        ids = []
        for job in (
            await Job.query.where(Job.status == "pending")
            .where(Job.scheduled_timestamp <= datetime.now())
            .order_by(Job.scheduled_timestamp)
            .limit(10)
            .gino.all()
        ):
            ids.append(job.id)
            tasks.append(start_job(job))

        if len(tasks) > 0:
            print(f"Running {len(tasks)} fetch/delete jobs {ids}")
            await asyncio.gather(*tasks)
        else:
            print(f"No fetch/delete jobs, waiting 60 seconds")
            await asyncio.sleep(60)


async def start_dm_jobs():
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        await asyncio.sleep(5)
    await send_admin_dm(
        f"DM jobs container started ({os.environ.get('DEPLOY_ENVIRONMENT')})"
    )

    minutes = 0

    while True:
        tasks = []

        # Run the first direct message job (only send one per minute)
        dm_job = (
            await DirectMessageJob.query.where(DirectMessageJob.status == "pending")
            .where(DirectMessageJob.scheduled_timestamp <= datetime.now())
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

        print(f"Waiting 1 minute")
        await asyncio.sleep(60)

        # Only run this once a day
        if minutes == 0:
            # Do we need to send reminders?
            print("Checking if we need to send reminders")

            message = f"Hello! Just in case you forgot about me, your Semiphemeral account has been paused for several months. You can login at https://{os.environ.get('DOMAIN')}/ to unpause your account and start automatically deleting your old tweets and likes, except for the ones you want to keep."

            three_months_ago = datetime.now() - timedelta(days=90)
            reminded_users = []

            # Find all the paused users
            users = (
                await User.query.where(User.blocked == False)
                .where(User.paused == True)
                .gino.all()
            )
            for user in users:
                # Get the last job they finished
                last_job = (
                    await Job.query.where(Job.user_id == user.id)
                    .where(Job.status == "finished")
                    .order_by(Job.finished_timestamp.desc())
                    .gino.first()
                )
                if last_job:
                    # Was it it more than 3 months ago?
                    if last_job.finished_timestamp < three_months_ago:
                        remind = False

                        # Let's make sure we also haven't sent them a DM in the last 3 months
                        last_dm_job = (
                            await DirectMessageJob.query.where(
                                DirectMessageJob.dest_twitter_id == user.twitter_id
                            )
                            .order_by(DirectMessageJob.sent_timestamp.desc())
                            .gino.first()
                        )
                        if last_dm_job:
                            if last_dm_job.scheduled_timestamp < three_months_ago:
                                remind = True
                        else:
                            remind = True

                        if remind:
                            reminded_users.append(user.twitter_screen_name)
                            await DirectMessageJob.create(
                                dest_twitter_id=user.twitter_id,
                                message=message,
                                status="pending",
                                scheduled_timestamp=datetime.now(),
                            )

            if len(reminded_users) > 0:
                admin_message = (
                    f"Sent semiphemeral reminders to {len(reminded_users)} users:\n\n"
                    + "\n".join(reminded_users)
                )
                await send_admin_dm(admin_message)

            minutes += 1
            if minutes == 1440:
                minutes = 0


async def start_export_jobs():
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        await asyncio.sleep(5)
    await send_admin_dm(
        f"Export jobs container started ({os.environ.get('DEPLOY_ENVIRONMENT')})"
    )

    # Infinitely loop looking for pending export jobs
    while True:
        tasks = []

        # Run the next 3 export jobs
        ids = []
        for export_job in (
            await ExportJob.query.where(ExportJob.status == "pending")
            .where(ExportJob.scheduled_timestamp <= datetime.now())
            .order_by(ExportJob.scheduled_timestamp)
            .limit(3)
            .gino.all()
        ):
            ids.append(export_job.id)
            tasks.append(start_export_job(export_job))

        if len(tasks) > 0:
            print(f"Running {len(tasks)} export jobs {ids}")
            await asyncio.gather(*tasks)
        else:
            print(f"No export jobs, waiting 60 seconds")
            await asyncio.sleep(60)
