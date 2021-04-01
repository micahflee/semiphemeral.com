import os
import asyncio
import functools
import requests
import json
from datetime import datetime, timedelta, timezone

import tweepy
import peony
from peony import PeonyClient

from db import Tweet, Thread, User, DirectMessageJob


async def log(job, s):
    if job:
        print(f"[{datetime.now().strftime('%c')}] job_id={job.id} {s}")
    else:
        print(f"[{datetime.now().strftime('%c')}] {s}")


async def update_progress(job, progress):
    await job.update(progress=json.dumps(progress)).apply()


async def update_progress_rate_limit(job, progress, job_runner_id=None, seconds=960):
    await log(
        job, f"#{job_runner_id} Hit twitter rate limit, pausing for {seconds}s ..."
    )

    old_status = progress["status"]

    # Change status message
    progress[
        "status"
    ] = f"I hit Twitter's rate limit, so I have to wait a bit before continuing ..."
    await update_progress(job, progress)

    # Sleep
    await asyncio.sleep(seconds)

    # Change status message back
    progress["status"] = old_status
    await update_progress(job, progress)

    await log(job, f"#{job_runner_id} Finished waiting, resuming")


class PoenyErrorHandler(peony.ErrorHandler):
    """
    https://peony-twitter.readthedocs.io/en/stable/adv_usage/error_handler.html
    """

    def __init__(self, request):
        super().__init__(request)

    @peony.ErrorHandler.handle(peony.exceptions.RateLimitExceeded)
    async def handle_rate_limits(self, exception):
        rate_limit_reset_ts = int(exception.response.headers.get("x-rate-limit-reset"))
        now_ts = datetime.now(timezone.utc).replace(tzinfo=timezone.utc).timestamp()
        seconds_to_wait = math.ceil(rate_limit_reset_ts - now_ts)
        if seconds_to_wait > 0:
            await update_progress_rate_limit(
                self.job, self.progress, self.job_runner_id, seconds=seconds_to_wait
            )
        return peony.ErrorHandler.RETRY

    @peony.ErrorHandler.handle(asyncio.TimeoutError, TimeoutError)
    async def handle_timeout_error(self):
        await log(self.job, f"#{self.job_runner_id} Timed out, retrying in 5s")
        await asyncio.sleep(5)
        return peony.ErrorHandler.RETRY

    @peony.ErrorHandler.handle(
        peony.exceptions.InternalError,
        peony.exceptions.HTTPServiceUnavailable,
        peony.exceptions.OverCapacity,
    )
    async def handle_delay_errors(self, exception):
        exception_str = str(exception).replace("\n", ", ")
        await log(self.job, f"#{self.job_runner_id} {exception_str}, retrying in 60s")
        await asyncio.sleep(60)
        return peony.ErrorHandler.RETRY

    @peony.ErrorHandler.handle(Exception)
    async def default_handler(self, exception):
        # exception_str = str(exception).replace("\n", ", ")
        # await log(
        #     self.job,
        #     f"#{self.job_runner_id} Hit exception: {exception_str}\n  Request info: {exception.response.request_info}\n  Response: status={exception.response.status} body={await exception.response.text()}",
        # )
        return peony.ErrorHandler.RAISE

    async def __call__(self, data=None, **kwargs):
        if data:
            self.job, self.progress, self.job_runner_id = data
        else:
            self.job = None
            self.progress = None
            self.job_runner_id = None
        return await super().__call__(**kwargs)


async def peony_client(user):
    client = PeonyClient(
        consumer_key=os.environ.get("TWITTER_CONSUMER_TOKEN"),
        consumer_secret=os.environ.get("TWITTER_CONSUMER_KEY"),
        access_token=user.twitter_access_token,
        access_token_secret=user.twitter_access_token_secret,
        error_handler=PoenyErrorHandler,
    )
    return client


async def peony_dms_client(user):
    client = PeonyClient(
        consumer_key=os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
        consumer_secret=os.environ.get("TWITTER_DM_CONSUMER_KEY"),
        access_token=user.twitter_dms_access_token,
        access_token_secret=user.twitter_dms_access_token_secret,
        error_handler=PoenyErrorHandler,
    )
    return client


async def tweepy_api_call(job, api, method, **kwargs):
    """
    Wrapper around Twitter API to support asyncio for all API calls. See:
    https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor
    https://docs.python.org/3/library/asyncio-eventloop.html#asyncio-pass-keywords
    """
    while True:
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, functools.partial(getattr(api, method), **kwargs)
            )
            return result
        except tweepy.error.TweepError as e:
            if e.api_code == 130:  # 130 = Over Capacity
                await log(job, f"tweepy_api_call, hit exception, retrying in 60s: {e}")
                await asyncio.sleep(60)
            # elif (
            #     e.api_code == 220
            # ):  # Your credentials do not allow access to this resource
            #     pass
            else:
                raise e


async def tweepy_api(user):
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
    )
    auth.set_access_token(user.twitter_access_token, user.twitter_access_token_secret)
    api = tweepy.API(auth)
    return api


async def tweepy_dms_api(user):
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_DM_CONSUMER_KEY"),
    )
    auth.set_access_token(
        user.twitter_dms_access_token, user.twitter_dms_access_token_secret
    )
    api = tweepy.API(auth)
    return api


# The API to send DMs from the @semiphemeral account
async def twitter_semiphemeral_dm_api():
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_DM_CONSUMER_KEY"),
    )
    auth.set_access_token(
        os.environ.get("TWITTER_DM_ACCESS_TOKEN"),
        os.environ.get("TWITTER_DM_ACCESS_KEY"),
    )
    api = tweepy.API(auth)
    return api


async def tweets_to_delete(user, include_manually_excluded=False):
    """
    Return the tweets that are staged for deletion for this user
    """
    try:
        datetime_threshold = datetime.utcnow() - timedelta(
            days=user.tweets_days_threshold
        )
    except OverflowError:
        # If we get "OverflowError: date value out of range", set the date to July 1, 2006,
        # shortly before Twitter was launched
        datetime_threshold = datetime(2006, 7, 1)

    # Get all the tweets to delete that have threads
    query = (
        Tweet.query.select_from(Tweet.join(Thread))
        .where(Tweet.user_id == user.id)
        .where(Tweet.twitter_user_id == user.twitter_id)
        .where(Tweet.is_deleted == False)
        .where(Tweet.is_retweet == False)
        .where(Tweet.created_at < datetime_threshold)
        .where(Thread.should_exclude == False)
    )
    if user.tweets_enable_retweet_threshold:
        query = query.where(Tweet.retweet_count < user.tweets_retweet_threshold)
    if user.tweets_enable_like_threshold:
        query = query.where(Tweet.favorite_count < user.tweets_like_threshold)
    if not include_manually_excluded:
        query = query.where(Tweet.exclude_from_delete == False)
    tweets_to_delete_with_threads = await query.gino.all()

    # Get all the tweets to delete that don't have threads
    query = (
        Tweet.query.where(Tweet.thread_id == None)
        .where(Tweet.user_id == user.id)
        .where(Tweet.twitter_user_id == user.twitter_id)
        .where(Tweet.is_deleted == False)
        .where(Tweet.is_retweet == False)
        .where(Tweet.created_at < datetime_threshold)
    )
    if user.tweets_enable_retweet_threshold:
        query = query.where(Tweet.retweet_count < user.tweets_retweet_threshold)
    if user.tweets_enable_like_threshold:
        query = query.where(Tweet.favorite_count < user.tweets_like_threshold)
    if not include_manually_excluded:
        query = query.where(Tweet.exclude_from_delete == False)
    tweets_to_delete_without_threads = await query.gino.all()

    # Merge them
    tweets_to_delete = sorted(
        tweets_to_delete_with_threads + tweets_to_delete_without_threads,
        key=lambda tweet: tweet.created_at,
    )

    return tweets_to_delete


async def send_admin_dm(message):
    # Webhook
    webhook_url = os.environ.get("ADMIN_WEBHOOK")
    try:
        requests.post(webhook_url, data=message)
    except:
        pass

    # Twitter DM
    # We don't need twitter DMs, the webhook is good enough
    # admin_user = await User.query.where(
    #     User.twitter_screen_name == os.environ.get("ADMIN_USERNAME")
    # ).gino.first()
    # if admin_user:
    #     await DirectMessageJob.create(
    #         dest_twitter_id=admin_user.twitter_id,
    #         message=message,
    #         status="pending",
    #         scheduled_timestamp=datetime.now(),
    #     )
