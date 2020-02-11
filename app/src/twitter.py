import asyncio
import json
import os
from datetime import datetime, timedelta

import tweepy

from common import twitter_api, twitter_api_call, twitter_dm_api, tweets_to_delete
from db import Job, DirectMessageJob, User, Tip, Nag, Tweet, Thread


class JobRescheduled(Exception):
    pass


async def log(job, s):
    print(f"[{datetime.now().strftime('%c')}] job_id={job.id} {s}")
    # logging.info(s)


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
    progress["status"] = "Not so fast... I hit Twitter's rate limit, waiting 15 minutes"
    await update_progress(job, progress)

    # Wait 15 minutes
    await asyncio.sleep(15 * 60)

    # Change status message back
    progress["status"] = old_status
    await update_progress(job, progress)

    await log(job, "Finished waiting, resuming")


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
    since_id = user.since_id

    loop = asyncio.get_running_loop()

    # Start the progress
    progress = {
        "tweets": 0,
        "likes": 0,
        "threads": 0,
    }
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
            since_id=since_id,
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

    # Fetch is done! If semiphemeral is paused, send a DM
    if user.paused:
        if not since_id:
            message = f"Good news! Semiphemeral finished downloading a copy of all {progress['tweets']} of your tweets and all {progress['likes']} of your likes.\n\n"
        else:
            message = f"Semiphemeral finished downloading {progress['tweets']} new tweets and {progress['likes']} new likes.\n\n"

        message += f"The next step is look through your tweets and manually mark which ones you want to make sure never get deleted. Visit https://{os.environ.get('DOMAIN')}/tweets to finish.\n\nWhen you're done, you can start deleting your tweets from the dashboard."

        await DirectMessageJob.create(
            dest_twitter_id=user.twitter_id,
            message=message,
            status="pending",
            scheduled_timestamp=datetime.now(),
        )
    else:
        # If it's not paused, then schedule a delete job

        # Create a new delete job
        await Job.create(
            user_id=user.id,
            job_type="delete",
            status="pending",
            scheduled_timestamp=datetime.now(),
        )


@ensure_user_follows_us
async def delete(job):
    await log(job, "Delete started")

    user = await User.query.where(User.id == job.user_id).gino.first()
    api = await twitter_api(user)

    loop = asyncio.get_running_loop()

    # Start the progress
    progress = {"tweets": 0, "retweets": 0, "likes": 0}

    # Unretweet and unlike tweets
    if user.retweets_likes:

        # Unretweet
        if user.retweets_likes_delete_retweets:
            datetime_threshold = datetime.utcnow() - timedelta(
                days=user.retweets_likes_retweets_threshold
            )
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
                        # await loop.run_in_executor(
                        #     None, api.destroy_status, tweet.status_id
                        # )
                        # await tweet.update(is_delete=True).apply()
                        print(f"deleting retweet {tweet.status_id}")
                        break
                    except tweepy.error.TweepError as e:
                        if e.api_code == 144:
                            # Already deleted
                            await tweet.update(is_deleted=True).apply()
                            break
                        elif e.api_code == 429:
                            await update_progress_rate_limit(job, progress)
                            # Don't break -- this will wait 15 minutes and try again
                        else:
                            # Unknown error
                            break

            progress["retweets"] += 1
            await update_progress(job, progress)

        # Unlike
        if user.retweets_likes_delete_likes:
            datetime_threshold = datetime.utcnow() - timedelta(
                days=user.retweets_likes_likes_threshold
            )
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
                        # await loop.run_in_executor(
                        #     None, api.destroy_favorite, tweet.status_id
                        # )
                        print(f"unliking tweet {tweet.status_id}")
                        await tweet.update(is_unliked=True).apply()
                        break
                    except tweepy.error.TweepError as e:
                        if e.api_code == 144:
                            # Already unliked
                            await tweet.update(is_unliked=True).apply()
                            break
                        elif e.api_code == 429:
                            await update_progress_rate_limit(job, progress)
                            # Don't break -- this will wait 15 minutes and try again
                        else:
                            # Unknown error
                            break

            progress["likes"] += 1
            await update_progress(job, progress)

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
                # await loop.run_in_executor(None, api.destroy_status, tweet.status_id)
                print(f"deleting tweet {tweet.status_id}")
                await tweet.update(is_deleted=True).apply()
                break
            except tweepy.error.TweepError as e:
                if e.api_code == 144:
                    # Already deleted
                    await tweet.update(is_deleted=True).apply()
                    break
                elif e.api_code == 429:
                    await update_progress_rate_limit(job, progress)
                    # Don't break -- this will wait 15 minutes and try again
                else:
                    # Unknown error
                    break

        progress["tweets"] += 1
        await update_progress(job, progress)

    progress["status"] = "Finished"
    await update_progress(job, progress)

    await log(job, "Delete finished")

    # Delete is done!

    # Schedule the next fetch job
    tomorrow = datetime.now() + timedelta(days=1)
    await Job.create(
        user_id=user.id,
        job_type="fetch",
        status="pending",
        scheduled_timestamp=tomorrow,
    )

    # When was the last time?
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
    one_month_ago = datetime.now() + timedelta(days=30)
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

    # Go ahead and create the nag early
    # In case the following code crashes, I don't want to accidentally trigger tons of nags
    if should_nag:
        await Nag.create(
            user_id=user.id, timestamp=datetime.now(),
        )

    if not last_nag:
        # The user has never been nagged, so this is the first delete
        message = f"Congratulations! Semiphemeral has deleted {progress['tweets']} tweets, unretweeted {progress['retweets']} tweets, and unliked  {progress['likes']} tweets. Doesn't that feel nice?\n\nEach day, I will download your latest tweets and likes and then delete the old ones based on your settings. You can sit back, relax, and enjoy the privacy.\n\nYou can always change your settings, mark new tweets to never delete, and pause Semiphemeral from the website https://{os.environ.get('DOMAIN')}/dashboard."

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
            # The user has been nagged before -- do some math to get the totals

            # Get all the delete jobs
            total_progress = {"tweets": 0, "retweets": 0, "likes": 0}
            total_progress_since_last_nag = {"tweets": 0, "retweets": 0, "likes": 0}
            jobs = (
                await Job.query.where(Job.user_id == user.id)
                .where(Job.job_type == "delete")
                .where(Job.status == "finished")
                .gino.all()
            )
            for job in jobs:
                p = json.loads(job.progress)

                if "tweets" in p:
                    total_progress["tweets"] += p["tweets"]
                if "retweets" in p:
                    total_progress["retweets"] += p["retweets"]
                if "likes" in p:
                    total_progress["likes"] += p["likes"]

                if job.finished_timestamp > last_nag.timestamp:
                    if "tweets" in p:
                        total_progress_since_last_nag["tweets"] += p["tweets"]
                    if "retweets" in p:
                        total_progress_since_last_nag["retweets"] += p["retweets"]
                    if "likes" in p:
                        total_progress_since_last_nag["likes"] += p["likes"]

            message = f"Since you've been using Semiphemeral, I have deleted {total_progress['tweets']} tweets, unretweeted {total_progress['retweets']} tweets, and unliked {total_progress['likes']} tweets for you.\n\nJust since last month, I've deleted {total_progress_since_last_nag['tweets']} tweets, unretweeted {total_progress_since_last_nag['retweets']} tweets, and unliked {total_progress_since_last_nag['likes']} tweets.\n\nSemiphemeral is free, but running this service costs money. Care to chip in? Visit here if you'd like to give a tip: https://{os.environ.get('DOMAIN')}/tip"

            await DirectMessageJob.create(
                dest_twitter_id=user.twitter_id,
                message=message,
                status="pending",
                scheduled_timestamp=datetime.now(),
            )


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
    except:
        # If sending the DM failed, try again in 5 minutes
        await dm_job.update(
            status="pending", scheduled_timestamp=datetime.now() + timedelta(minutes=5)
        ).apply()

        print(
            f"[{datetime.now().strftime('%c')}] dm_job_id={dm_job.id} failed to send DM, delaying 5 minutes"
        )


async def start_jobs():
    # Initialize logging -- commented out because I don't want to have to deal with figuring out how to
    # restart logging in logrotate, especially since I may never need these logs
    # logging.basicConfig(filename="/var/jobs/jobs.log", level=logging.INFO, force=True)

    # In case the app crashed in the middle of any previous jobs, change all "active"
    # jobs to "pending" so they'll start over
    await Job.update.values(status="pending").where(
        Job.status == "active"
    ).gino.status()

    # Infinitely loop looking for pending jobs
    while True:
        # Fetch and delete jobs
        for job in (
            await Job.query.where(Job.status == "pending")
            .where(Job.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
            await start_job(job)

        # Direct message jobs
        for dm_job in (
            await DirectMessageJob.query.where(DirectMessageJob.status == "pending")
            .where(DirectMessageJob.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
            await start_dm_job(dm_job)

        await asyncio.sleep(60)
