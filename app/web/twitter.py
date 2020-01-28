import asyncio
import json
from datetime import datetime, timedelta

import tweepy

from common import twitter_api, twitter_api_call
from db import Job, User, Tweet, Thread


class JobRescheduled(Exception):
    pass


async def log(job, s):
    print(f"[{datetime.now().strftime('%c')}] job_id={job.id} {s}")


def ensure_user_follows_us(func):
    async def wrapper(job):
        user = await User.query.where(User.id == job.user_id).gino.first()
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

        if not friendship.following:
            reschedule_timedelta_in_the_future = timedelta(minutes=30)

            # If we've already sent a follow request but it still hasn't been accepted
            if friendship.following_requested:
                await reschedule_job(job, reschedule_timedelta_in_the_future)

            # Follow
            followed_user = await twitter_api_call(
                api, "create_friendship", screen_name="semiphemeral", follow=True
            )

            # If we're still not following but have now sent a follow request
            if not followed_user.following and followed_user.follow_request_sent:
                await reschedule_job(job, reschedule_timedelta_in_the_future)

        return await func(job)

    return wrapper


async def reschedule_job(job, timedelta_in_the_future):
    await job.update(
        status="pending", scheduled_timestamp=datetime.now() + timedelta_in_the_future
    ).apply()
    raise JobRescheduled()


async def update_progress(job, progress):
    await job.update(progress=json.dumps(progress)).apply()


async def update_progress_rate_limit(job, progress):
    await log(job, "Hit twitter rate limit, waiting 15 minutes")

    old_status = progress["status"]

    # Change status message
    progress[
        "status"
    ] = "Not so fast... I hit Twitter's rate limit, so I need to wait awhile before continuing"
    await update_progress(job, progress)

    # Wait 15 minutes
    await asyncio.sleep(15 * 60)

    # Change status message back
    progress["status"] = old_status
    await update_progress(job, progress)


async def save_tweet(user, status):
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
    )


async def import_tweet_and_thread(user, api, status):
    """
    This imports a tweet, and recursively imports all tweets that it's in reply to,
    and returns the number of tweets fetched
    """
    fetched_count = 0

    # Is the tweet already saved?
    tweet = await (
        Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.status_id == status.id)
        .gino.first()
    )
    if not tweet:
        # Save the tweet
        tweet = await save_tweet(user, status)
        fetched_count += 1

    # Is this tweet a reply?
    if tweet.in_reply_to_status_id:
        # Do we already have the parent tweet?
        parent_tweet = await (
            Tweet.query.where(Tweet.user_id == user.id)
            .where(Tweet.status_id == tweet.in_reply_to_status_id)
            .gino.first()
        )
        if not parent_tweet:
            # If not, import it
            try:
                parent_status = await twitter_api_call(
                    api,
                    "get_status",
                    id=tweet.in_reply_to_status_id,
                    tweet_mode="extended",
                )
                fetched_count += await import_tweet_and_thread(user, api, parent_status)
            except tweepy.error.TweepError:
                # If it's been deleted, ignore
                pass

    return fetched_count


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
        for thread in (
            await Thread.join(Tweet, Thread.id == Tweet.thread_id)
            .select()
            .where(Thread.user_id == user.id)
            .where(Tweet.user_id == user.id)
            .where(Tweet.is_deleted == False)
            .where(Tweet.is_retweet == False)
            .where(Tweet.retweet_count >= user.tweets_retweet_threshold)
            .where(Tweet.favorite_count >= user.tweets_like_threshold)
            .gino.all()
        ):
            await thread.update(should_exclude=True).apply()


@ensure_user_follows_us
async def fetch(job):
    await log(job, "Fetch started")

    user = await User.query.where(User.id == job.user_id).gino.first()
    api = await twitter_api(user)

    loop = asyncio.get_running_loop()

    # Load info about the user
    twitter_user = await twitter_api_call(api, "me")

    # Start the progress
    progress = {
        "tweets": 0,
        "total_tweets": twitter_user.statuses_count,
        "likes": 0,
        "total_likes": twitter_user.favourites_count,
        "threads": 0,
    }
    if user.since_id:
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
            since_id=user.since_id,
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
        except StopIteration:
            break
        except tweepy.TweepError:
            await update_progress_rate_limit(job, progress)

        fetched_count = 0

        # Import these tweets, and all their threads
        for status in page:
            fetched_count += await import_tweet_and_thread(user, api, status)
            progress["tweets"] += 1

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
                progress["threads"] += 1

            # Add all of the thread's tweets to the thread
            for status_id in status_ids:
                tweet = (
                    await Tweet.query.where(Tweet.user_id == user.id)
                    .where(Tweet.status_id == status_id)
                    .where(Tweet.thread_id != thread.id)
                    .gino.first()
                )
                if tweet:
                    await Tweet.update(thread_id=thread.id).apply()

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
            since_id=user.since_id,
            tweet_mode="extended",
        ).pages,
    )
    while True:
        try:
            page = pages.next()
        except StopIteration:
            break
        except tweepy.TweepError:
            await update_progress_rate_limit(job, progress)

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
                await save_tweet(user, status)
                progress["likes"] += 1

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

    await log(job, "Fetch finished")


@ensure_user_follows_us
async def delete(job):
    pass


async def start_job(job):
    await job.update(status="active", started_timestamp=datetime.now()).apply()

    if job.job_type == "fetch":
        try:
            await fetch(job)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
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
        except JobRescheduled:
            pass


async def start_jobs():
    # In case the app crashed in the middle of any previous jobs, change all "active"
    # jobs to "pending" so they'll start over
    await Job.update.values(status="pending").where(
        Job.status == "active"
    ).gino.status()

    # Infinitely loop looking for pending jobs
    while True:
        for job in (
            await Job.query.where(Job.status == "pending")
            .where(Job.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
            await start_job(job)

        await asyncio.sleep(60)
