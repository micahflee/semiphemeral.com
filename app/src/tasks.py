#!/usr/bin/env python3
import os
import json
import click
from datetime import datetime, timedelta
import tweepy

from sqlalchemy import select, update, delete, or_
from db import (
    User,
    JobDetails,
    Like,
    Fascist,
    session as db_session,
)

from common import (
    send_admin_notification,
    tweepy_api_v1_1,
    delete_user,
    add_job,
    add_dm_job,
    conn,
    jobs_q,
)
import worker_jobs

import rq
from rq.job import Job as RQJob
from rq.registry import FailedJobRegistry


@click.group()
def main():
    """semiphemeral.com tasks"""


@main.command(
    "send-reminders",
    short_help="Send reminders to users who have been paused for months",
)
def send_reminders():
    # Do we need to send reminders?
    print("Checking if we need to send reminders")
    message = f"Hello! Just in case you forgot about me, your Semiphemeral account has been paused for several months. You can login at https://{os.environ.get('DOMAIN')}/ to unpause your account and start automatically deleting your old tweets and likes, except for the ones you want to keep. You can also use it to delete your DMs. (Considering Twitter's new owner, perhaps this is prudent.) And if you're not interested, you can login, go to Settings, and delete your account."
    three_months_ago = datetime.now() - timedelta(days=90)
    reminded_users = []

    # Find all the paused users
    users = db_session.scalars(
        select(User).where(User.blocked == False).where(User.paused == True)
    ).fetchall()
    for user in users:
        # Get the last job they finished
        last_job = db_session.scalar(
            select(JobDetails)
            .where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "finished")
            .order_by(JobDetails.finished_timestamp.desc())
        )
        if last_job:
            # Was it it more than 3 months ago?
            if last_job.finished_timestamp < three_months_ago:
                remind = False

                # Let's make sure we also haven't sent them a DM in the last 3 months
                last_dm_job = db_session.scalar(
                    select(JobDetails)
                    .where(JobDetails.user_id == user.id)
                    .where(JobDetails.job_type == "dm")
                    .where(JobDetails.status == "finished")
                    .order_by(JobDetails.finished_timestamp.desc())
                )
                if last_dm_job:
                    if last_dm_job.scheduled_timestamp < three_months_ago:
                        remind = True
                else:
                    remind = True

                if remind:
                    reminded_users.append(user.twitter_screen_name)
                    print(f"Reminding @{user.twitter_screen_name}")
                    add_dm_job(
                        worker_jobs.funcs, user.twitter_id, message, priority="low"
                    )

    if len(reminded_users) > 0:
        admin_message = (
            f"Queued semiphemeral reminder DMs to {len(reminded_users)} users:\n\n"
            + "\n".join(reminded_users)
        )
        send_admin_notification(admin_message)

    db_session.close()


@main.command(
    "cleanup-users",
    short_help="Detect old users with deleted accounts, or who have revoked creds",
)
def cleanup_users():
    users = db_session.scalars(select(User)).fetchall()
    i = 0
    count = len(users)
    users_deleted = 0
    for user in users:
        print(
            f"\r[{i:,}/{count:,}] checking @{user.twitter_screen_name} ..." + " " * 20,
            end="",
        )
        api = tweepy_api_v1_1(user)
        try:
            api.verify_credentials()
        except tweepy.errors.Unauthorized:
            print(
                f"\r[{i:,}/{count:,}, deleted {users_deleted:,}] deleting @{user.twitter_screen_name}"
            )
            delete_user(user)
            users_deleted += 1

        i += 1

    admin_message = f"Deleted {users_deleted} users and all their data"
    print(admin_message)
    send_admin_notification(admin_message)
    db_session.close()


@main.command(
    "cleanup-dm-jobs",
    short_help="Delete DM jobs with users that have been deleted",
)
def cleanup_dm_jobs():
    dm_jobs = db_session.scalars(
        select(JobDetails).where(JobDetails.status == "pending")
    ).fetchall()
    print(f"there are {len(dm_jobs)} pending DM jobs")

    num_deleted = 0
    for dm_job in dm_jobs:
        user = db_session.scalar(
            select(User).where(User.twitter_id == dm_job.dest_twitter_id)
        )
        if not user:
            print(f"deleting DM job id={dm_job.id}")
            try:
                redis_job = RQJob.fetch(dm_job.redis_id, connection=conn)
                redis_job.cancel()
                redis_job.delete()
            except rq.exceptions.NoSuchJobError:
                pass

            db_session.delete(dm_job)
            num_deleted += 1

    dm_jobs = db_session.scalars(
        select(JobDetails).where(JobDetails.status == "pending")
    ).fetchall()
    print(f"now there are {len(dm_jobs)} pending DM jobs")

    admin_message = f"Deleted {num_deleted} pending DM jobs from deleted users"
    print(admin_message)
    send_admin_notification(admin_message)
    db_session.close()


@main.command(
    "failed-jobs-registry",
    short_help="View failed jobs from the redis queue",
)
def failed_jobs_registry():
    registry = FailedJobRegistry(queue=jobs_q)

    # Show all failed job IDs and the exceptions they caused during runtime
    for job_id in registry.get_job_ids():
        job = RQJob.fetch(job_id, connection=conn)
        print(job_id, job.exc_info)


# TODO: fix this to make it use v1.1 API

# @main.command(
#     "update-fascists",
#     short_help="Set is_fascist=True for all likes from fascists",
# )
# def unblock_users():
#     user = db_session.scalar(select(User).where(User.id == 1))
#     api = tweepy_api_v1_1(user)

#     # Mark all the likes as is_fascist=False
#     print("Marking all likes as not fascist")
#     db_session.execute(update(Like).values(is_fascist=False))

#     fascists = db_session.scalars(select(Fascist)).fetchall()
#     print(f"Found {len(fascists)} Fascists")
#     for fascist in fascists:
#         # Get the twitter ID
#         res = api.lookup_users(screen_name=[fascist.username])
#         response = client.get_user(username=, user_auth=True)
#         try:
#             fascist.twitter_id = response["data"]["id"]
#             db_session.add(fascist)
#             db_session.commit()
#         except Exception as e:
#             print(f"Error: {e}")
#             print(json.dumps(response, indent=2))

#         # Mark all the tweets from this user as is_fascist=True
#         print(f"Marking tweets from @{fascist.username} as fascist")
#         db_session.execute(
#             update(Like)
#             .values(is_fascist=True)
#             .where(Like.author_id == fascist.twitter_id)
#         )


@main.command(
    "fix-stalled-users",
    short_help="Cancel all jobs, and start new ones for non-paused users",
)
def fix_stalled_users():
    # Find all users
    users = db_session.scalars(
        select(User).where(User.blocked == False).where(User.paused == False)
    ).fetchall()
    count = len(users)
    i = 0
    for user in users:
        pending_delete_jobs = db_session.scalars(
            select(JobDetails)
            .where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "pending")
            .where(JobDetails.job_type == "delete")
        ).fetchall()
        if len(pending_delete_jobs) == 0:
            add_job("delete", user.id, worker_jobs.funcs)
            print(f"[{i:,}/{count:,} @{user.twitter_screen_name} added delete job")

        i += 1

    db_session.close()


@main.command(
    "cancel-dupe-jobs",
    short_help="Each user should have at most 1 fetch and 1 delete job, this cancels dupes",
)
def cancel_dupe_jobs():
    i = 0
    users = db_session.scalars(
        select(User).where(User.blocked == False).where(User.paused == False)
    ).fetchall()
    count = len(users)
    for user in users:
        for job_type in ["fetch", "delete"]:
            pending_jobs = db_session.scalars(
                select(JobDetails)
                .where(JobDetails.user_id == user.id)
                .where(JobDetails.status == "pending")
                .where(JobDetails.job_type == job_type)
            )
            if len(pending_jobs) > 1:
                skipped_first = False
                for job in pending_jobs:
                    if not skipped_first:
                        skipped_first = True
                        continue

                    job.status = "canceled"
                    job.finished_timestamp = datetime.now()
                    db_session.add(job)
                    db_session.commit()
                    print(
                        f"{i:,}/{count:,} @{user.twitter_screen_name} canceled {job_type} job {job.id}"
                    )

        i += 1

    db_session.close()


@main.command(
    "count-deletes",
    short_help="Count total things deleted from twitter",
)
def count_deletes():
    fields = ["tweets_deleted", "retweets_deleted", "likes_deleted", "dms_deleted"]
    count = {}
    for field in fields:
        count[field] = 0

    jobs = db_session.scalars(
        select(JobDetails).where(JobDetails.status == "finished")
    ).fetchall()
    for job in jobs:
        data = json.loads(job.data)
        if "progress" in data:
            for field in fields:
                if field in data["progress"]:
                    count[field] += data["progress"][field]

    def to_mil(n):
        n_mils = round(n / 100000) / 10
        return f"{n_mils:,}M"

    print(
        f"As of today I've deleted {count['tweets_deleted']:,} tweets, {count['retweets_deleted']:,} retweets, {count['likes_deleted']:,} likes, and {count['dms_deleted']:,} direct messages from Twitter"
    )

    print(
        f"As of today I've deleted {to_mil(count['tweets_deleted'])} tweets, {to_mil(count['retweets_deleted'])} retweets, {to_mil(count['likes_deleted'])} likes, and {to_mil(count['dms_deleted'])} direct messages from Twitter"
    )


if __name__ == "__main__":
    main()
