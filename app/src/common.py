import os
import sys
import requests
from datetime import datetime, timedelta

import tweepy

from db import Tweet, Like, Thread, Nag, JobDetails, Tip


async def log(job_details, s):
    # Print to stderr, so we can immediately see output in docker logs
    if job_details:
        print(
            f"[{datetime.now().strftime('%c')}] job_details={job_details.id} {s}",
            file=sys.stderr,
        )
    else:
        print(f"[{datetime.now().strftime('%c')}] {s}", file=sys.stderr)


# Twitter API v2


def create_tweepy_client(
    consumer_key,
    consumer_secret,
    access_token,
    access_token_secret,
    wait_on_rate_limit=True,
):
    return tweepy.Client(
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        return_type=dict,
        wait_on_rate_limit=wait_on_rate_limit,
    )


def tweepy_client(user, dms=False, wait_on_rate_limit=True):
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
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret,
        wait_on_rate_limit=True,
    )


def tweepy_semiphemeral_client():
    consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
    access_token = os.environ.get("TWITTER_SEMIPHEMERAL_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_SEMIPHEMERAL_ACCESS_KEY_KEY")
    return create_tweepy_client(
        consumer_key, consumer_secret, access_token, access_token_secret
    )


# Twitter API v1.1


def create_tweepy_api_1_1(
    consumer_key, consumer_secret, access_token, access_token_secret
):
    auth = tweepy.OAuth1UserHandler(
        consumer_key, consumer_secret, access_token, access_token_secret
    )
    return tweepy.API(auth, wait_on_rate_limit=True)


def tweepy_semiphemeral_api_1_1():
    consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
    access_token = os.environ.get("TWITTER_SEMIPHEMERAL_ACCESS_TOKEN")
    access_token_secret = os.environ.get("TWITTER_SEMIPHEMERAL_ACCESS_KEY_KEY")
    return create_tweepy_api_1_1(
        consumer_key, consumer_secret, access_token, access_token_secret
    )


def tweepy_api_v1_1(user):
    consumer_key = os.environ.get("TWITTER_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_CONSUMER_KEY")
    access_token = user.twitter_access_token
    access_token_secret = user.twitter_access_token_secret
    return create_tweepy_api_1_1(
        consumer_key, consumer_secret, access_token, access_token_secret
    )


def tweepy_dms_api_v1_1(user):
    consumer_key = os.environ.get("TWITTER_DM_CONSUMER_TOKEN")
    consumer_secret = os.environ.get("TWITTER_DM_CONSUMER_KEY")
    access_token = user.twitter_dms_access_token
    access_token_secret = user.twitter_dms_access_token_secret
    return create_tweepy_api_1_1(
        consumer_key, consumer_secret, access_token, access_token_secret
    )


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
    await JobDetails.delete.where(JobDetails.user_id == user.id).gino.status()
    await Tweet.delete.where(Tweet.user_id == user.id).gino.status()
    await Like.delete.where(Like.user_id == user.id).gino.status()
    await Thread.delete.where(Thread.user_id == user.id).gino.status()
    await user.delete()
