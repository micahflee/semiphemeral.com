import os
import requests
from datetime import datetime, timedelta

import tweepy

from peony import PeonyClient
from peony.oauth_dance import get_oauth_token, get_access_token

from db import Tweet, Thread, Nag, Job, Tip


async def log(job_details, s):
    if job_details:
        print(f"[{datetime.now().strftime('%c')}] job_details={job_details.id} {s}")
    else:
        print(f"[{datetime.now().strftime('%c')}] {s}")


async def peony_oauth_step1(
    twitter_consumer_token, twitter_consumer_key, callback_path
):
    token = await get_oauth_token(
        twitter_consumer_token,
        twitter_consumer_key,
        callback_uri=f"https://{os.environ.get('DOMAIN')}{callback_path}",
    )
    redirect_url = (
        f"https://api.twitter.com/oauth/authorize?oauth_token={token['oauth_token']}"
    )
    return redirect_url, token


async def peony_oauth_step3(
    twitter_consumer_token,
    twitter_consumer_key,
    oauth_token,
    oauth_token_secret,
    oauth_verifier,
):
    token = await get_access_token(
        twitter_consumer_token,
        twitter_consumer_key,
        oauth_token,
        oauth_token_secret,
        oauth_verifier,
    )
    return token


def tweepy_client(user, dms=False):
    if dms:
        consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
        consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
        access_token = user.twitter_dms_access_token
        access_token_secret = user.twitter_dms_access_token_secret
    else:
        consumer_key = os.environ.get("TWITTER_CONSUMER_TOKEN")
        consumer_secret = os.environ.get("TWITTER_CONSUMER_KEY")
        access_token = user.twitter_access_token
        access_token_secret = user.twitter_access_token_secret

    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        return_type=dict,
        wait_on_rate_limit=True,
    )


def tweepy_semiphemeral_client():
    consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
    access_token = os.environ.get("TWITTER_DM_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_DM_ACCESS_KEY")
    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        return_type=dict,
        wait_on_rate_limit=True,
    )


class SemiphemeralPeonyClient:
    def __init__(self, user, dms=False):
        if dms:
            self.consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
            self.consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
            self.access_token = user.twitter_dms_access_token
            self.access_token_secret = user.twitter_dms_access_token_secret
        else:
            self.consumer_key = os.environ.get("TWITTER_CONSUMER_TOKEN")
            self.consumer_secret = os.environ.get("TWITTER_CONSUMER_KEY")
            self.access_token = user.twitter_access_token
            self.access_token_secret = user.twitter_access_token_secret

    async def __aenter__(self):
        self.client = PeonyClient(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
        )
        return self.client

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        await self.client.close()
        if exc_type:
            print(f"Exception: {exc_type}, {exc_value}, {exc_tb}")


# For sending DMs from the @semiphemeral account
class SemiphemeralAppPeonyClient:
    def __init__(self):
        self.consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
        self.consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
        self.access_token = os.environ.get("TWITTER_DM_ACCESS_TOKEN")
        self.access_token_secret = os.environ.get("TWITTER_DM_ACCESS_KEY")

    async def __aenter__(self):
        self.client = PeonyClient(
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            access_token=self.access_token,
            access_token_secret=self.access_token_secret,
        )
        return self.client

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        await self.client.close()
        if exc_type:
            print(f"Exception: {exc_type}, {exc_value}, {exc_tb}")


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


async def send_admin_notification(message):
    # Webhook
    webhook_url = os.environ.get("ADMIN_WEBHOOK")
    try:
        requests.post(webhook_url, data=message)
    except:
        pass


async def delete_user(user):
    await Tip.delete.where(Tip.user_id == user.id).gino.status()
    await Nag.delete.where(Nag.user_id == user.id).gino.status()
    await Job.delete.where(Job.user_id == user.id).gino.status()
    await Tweet.delete.where(Tweet.user_id == user.id).gino.status()
    await Thread.delete.where(Thread.user_id == user.id).gino.status()
    await user.delete()
