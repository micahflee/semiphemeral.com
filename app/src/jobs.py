import asyncio
import json
import os
from datetime import datetime, timedelta

import tweepy

from common import twitter_api, twitter_api_call, twitter_dm_api, tweets_to_delete
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
        tweet = await save_tweet(user, status)

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
                        print(f"job_id={job.id} Error importing parent tweet: {e}")
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
        except StopIteration:
            break
        except tweepy.TweepError as e:
            if str(e) == "Twitter error response: status code = 404":
                # Twitter responded with a 404 error, which could mean the user has deleted their account
                await log(job, f"404 error from twitter, rescheduling job for 15 minutes from now")
                await reschedule_job(job, timedelta(minutes=15))
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
        except tweepy.TweepError as e:
            if str(e) == "Twitter error response: status code = 404":
                # Twitter responded with a 404 error, which could mean the user has deleted their account
                await log(job, f"404 error from twitter, rescheduling job for 15 minutes from now")
                await reschedule_job(job, timedelta(minutes=15))
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
                await save_tweet(user, status)

            progress["likes_fetched"] += 1

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

    # Go ahead and create the nag early
    # In case the following code crashes, I don't want to accidentally trigger tons of nags
    if should_nag:
        await Nag.create(
            user_id=user.id, timestamp=datetime.now(),
        )

    if not last_nag:
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
        # If sending the DM failed, try again in 5 minutes
        await dm_job.update(
            status="pending", scheduled_timestamp=datetime.now() + timedelta(minutes=5)
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


async def start_jobs():
    # Start by sleeping, to stagger the start times of job containers
    seconds_to_sleep = int(os.environ.get("SECONDS_TO_SLEEP"))
    print(f"Sleeping {seconds_to_sleep} seconds")
    await asyncio.sleep(seconds_to_sleep)

    # Infinitely loop looking for pending jobs
    while True:
        tasks = []

        # Run all direct message jobs
        for dm_job in (
            await DirectMessageJob.query.where(DirectMessageJob.status == "pending")
            .where(DirectMessageJob.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
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

        # Run the next fetch and delete job
        job = (
            await Job.query.where(Job.status == "pending")
            .where(Job.scheduled_timestamp <= datetime.now())
            .order_by(Job.scheduled_timestamp)
            .gino.first()
        )
        tasks.append(start_job(job))

        await asyncio.gather(*tasks)
        await asyncio.sleep(10)
