import os
import sys
import requests
import json
from datetime import datetime, timedelta

import tweepy

from sqlalchemy import select, delete
from db import Tweet, Like, Thread, Nag, JobDetails, Tip, session as db_session

import redis
from rq import Queue

conn = redis.from_url(os.environ.get("REDIS_URL"))
jobs_q = Queue("jobs", connection=conn)
dm_jobs_high_q = Queue("dm_jobs_high", connection=conn)
dm_jobs_low_q = Queue("dm_jobs_low", connection=conn)


def log(job_details, s):
    # Print to stderr, so we can immediately see output in docker logs
    if job_details:
        print(
            f"[{datetime.now().strftime('%c')}] job_details={job_details.id} {s}",
            file=sys.stderr,
        )
    else:
        print(f"[{datetime.now().strftime('%c')}] {s}", file=sys.stderr)


# Add a job
def add_job(
    job_type, user_id, funcs, data={}, job_timeout="24h", scheduled_timestamp=None
):
    if not scheduled_timestamp:
        scheduled_timestamp = datetime.now()
    log(
        None,
        f"add_job: job_type={job_type}, user_id={user_id}, data={data}, job_timeout={job_timeout}, scheduled_timestamp={scheduled_timestamp}",
    )

    # Make sure there's not already a scheduled job of this type
    existing_job_details = db_session.scalar(
        select(JobDetails)
        .where(JobDetails.user_id == user_id)
        .where(JobDetails.job_type == job_type)
        .where(JobDetails.status == "pending")
    )
    if existing_job_details:
        log(
            None,
            f"Skipping adding {job_type} job for user_id={user_id}, job is already pending",
        )
        return

    # Add the job
    job_details = JobDetails(
        job_type=job_type,
        user_id=user_id,
        data=json.dumps(data),
        scheduled_timestamp=scheduled_timestamp,
    )
    db_session.add(job_details)
    db_session.commit()

    redis_job = jobs_q.enqueue_at(
        scheduled_timestamp,
        funcs[job_type],
        job_details.id,
        job_timeout=job_timeout,
        # retry=Retry(max=3, interval=[60, 120, 240]),
    )

    job_details.redis_id = redis_job.id
    db_session.add(job_details)
    db_session.commit()


def add_dm_job(
    funcs, dest_twitter_id, message, scheduled_timestamp=None, priority="high"
):
    if not scheduled_timestamp:
        scheduled_timestamp = datetime.now()
    log(
        None,
        f"add_dm_job: dest_twitter_id={dest_twitter_id}, scheduled_timestamp={scheduled_timestamp}",
    )

    job_details = JobDetails(
        job_type="dm",
        user_id=None,
        data=json.dumps({"dest_twitter_id": dest_twitter_id, "message": message}),
        scheduled_timestamp=scheduled_timestamp,
    )
    db_session.add(job_details)
    db_session.commit()

    if priority == "high":
        q = dm_jobs_high_q
    else:
        q = dm_jobs_low_q
    redis_job = q.enqueue_at(
        scheduled_timestamp,
        funcs["dm"],
        job_details.id,
        job_timeout="10m",
        # retry=Retry(max=3, interval=[60, 120, 240]),
    )

    job_details.redis_id = redis_job.id
    db_session.add(job_details)
    db_session.commit()


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


def send_admin_notification(message):
    # Webhook
    webhook_url = os.environ.get("ADMIN_WEBHOOK")
    try:
        requests.post(webhook_url, data=message)
    except:
        pass


def delete_user(user):
    db_session.execute(delete(Tip).where(Tip.user_id == user.id))
    db_session.execute(delete(Nag).where(Nag.user_id == user.id))
    db_session.execute(delete(JobDetails).where(JobDetails.user_id == user.id))
    db_session.execute(delete(Tweet).where(Tweet.user_id == user.id))
    db_session.execute(delete(Like).where(Like.user_id == user.id))
    db_session.execute(delete(Thread).where(Thread.user_id == user.id))
    db_session.commit()

    db_session.delete(user)
    db_session.commit()
