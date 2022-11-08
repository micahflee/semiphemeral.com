import os
import sys
import requests
import json
from datetime import datetime, timedelta

import tweepy

from db import Tweet, Like, Thread, Nag, JobDetails, Tip

import redis
from rq import Queue
from rq.job import Retry

conn = redis.from_url(os.environ.get("REDIS_URL"))
jobs_q = Queue("jobs", connection=conn)
dm_jobs_high_q = Queue("dm_jobs_high", connection=conn)
dm_jobs_low_q = Queue("dm_jobs_low", connection=conn)


async def log(job_details, s):
    # Print to stderr, so we can immediately see output in docker logs
    if job_details:
        print(
            f"[{datetime.now().strftime('%c')}] job_details={job_details.id} {s}",
            file=sys.stderr,
        )
    else:
        print(f"[{datetime.now().strftime('%c')}] {s}", file=sys.stderr)


# Add a job
async def add_job(
    job_type, user_id, funcs, data={}, job_timeout="24h", scheduled_timestamp=None
):
    # Make sure there's not already a scheduled job of this type
    existing_job_details = (
        await JobDetails.query.where(JobDetails.user_id == user_id)
        .where(JobDetails.job_type == job_type)
        .where(JobDetails.status == "pending")
        .gino.all()
    )
    if existing_job_details:
        await log(
            None,
            f"Skipping adding {job_type} job for user_id={user_id}, job is already pending",
        )
        return

    # Add the job
    if not scheduled_timestamp:
        scheduled_timestamp = datetime.now()
    job_details = await JobDetails.create(
        job_type=job_type,
        user_id=user_id,
        data=json.dumps(data),
        scheduled_timestamp=scheduled_timestamp,
    )
    redis_job = jobs_q.enqueue_at(
        scheduled_timestamp,
        funcs[job_type],
        job_details.id,
        job_timeout=job_timeout,
        retry=Retry(max=3, interval=[60, 120, 240]),
    )
    await job_details.update(redis_id=redis_job.id).apply()


async def add_dm_job(funcs, dest_twitter_id, message, scheduled_timestamp=None):
    if not scheduled_timestamp:
        scheduled_timestamp = datetime.now()
    job_details = await JobDetails.create(
        job_type="dm",
        user_id=None,
        data=json.dumps({"dest_twitter_id": dest_twitter_id, "message": message}),
        scheduled_timestamp=scheduled_timestamp,
    )
    redis_job = dm_jobs_high_q.enqueue_at(
        scheduled_timestamp,
        funcs["dm"],
        job_details.id,
        job_timeout="10m",
        retry=Retry(max=3, interval=[60, 120, 240]),
    )
    await job_details.update(redis_id=redis_job.id).apply()


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
