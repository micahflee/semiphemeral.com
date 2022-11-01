import os
import requests
from datetime import datetime, timedelta

import tweepy

from db import Tweet, Like, Thread, Nag, Job, Tip


async def log(job_details, s):
    if job_details:
        print(f"[{datetime.now().strftime('%c')}] job_details={job_details.id} {s}")
    else:
        print(f"[{datetime.now().strftime('%c')}] {s}")


def create_tweepy_client(
    consumer_key, consumer_secret, access_token, access_token_secret
):
    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        return_type=dict,
        wait_on_rate_limit=True,
    )


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

    return create_tweepy_client(
        consumer_key, consumer_secret, access_token, access_token_secret
    )


def tweepy_semiphemeral_client():
    consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
    access_token = os.environ.get("TWITTER_DM_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_DM_ACCESS_KEY")
    return create_tweepy_client(
        consumer_key, consumer_secret, access_token, access_token_secret
    )


def tweepy_semiphemeral_api():
    consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
    access_token = os.environ.get("TWITTER_DM_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_DM_ACCESS_KEY")

    auth = tweepy.OAuth1UserHandler(
        consumer_key, consumer_secret, access_token, access_token_secret
    )
    api = tweepy.API(auth)
    return api


# Twitter API v2 doesn't support getting likes with a since_id, so we have to use v1.1
def tweepy_api_v1_1(user):
    consumer_key = os.environ.get("TWITTER_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_CONSUMER_KEY")
    access_token = user.twitter_access_token
    access_token_secret = user.twitter_access_token_secret

    auth = tweepy.OAuth1UserHandler(
        consumer_key, consumer_secret, access_token, access_token_secret
    )
    api = tweepy.API(auth)
    return api


# Twitter API v2 doesn't support deleting DMs, so we have to use v1.1
def tweepy_dms_api_v1_1(user):
    consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
    access_token = user.twitter_dms_access_token
    access_token_secret = user.twitter_dms_access_token_secret

    auth = tweepy.OAuth1UserHandler(
        consumer_key, consumer_secret, access_token, access_token_secret
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

    query = (
        Tweet.query.select_from(Tweet.join(Thread))
        .where(Tweet.user_id == user.id)
        .where(Tweet.is_deleted == False)
        .where(Tweet.is_retweet == False)
        .where(Tweet.created_at < datetime_threshold)
        .where(Thread.should_exclude == False)
    )
    if user.tweets_enable_retweet_threshold:
        query = query.where(Tweet.retweet_count < user.tweets_retweet_threshold)
    if user.tweets_enable_like_threshold:
        query = query.where(Tweet.like_count < user.tweets_like_threshold)
    if not include_manually_excluded:
        query = query.where(Tweet.exclude_from_delete == False)
    tweets_to_delete = await query.gino.all()

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
    await Like.delete.where(Like.user_id == user.id).gino.status()
    await Thread.delete.where(Thread.user_id == user.id).gino.status()
    await user.delete()
