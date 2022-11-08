#!/usr/bin/env python3
import os
import json
import asyncio
import click
from datetime import datetime, timedelta

import db
from db import connect_db, disconnect_db, User, JobDetails, Like, Tweet
from common import (
    send_admin_notification,
    tweepy_client,
    tweepy_api_v1_1,
    delete_user,
    add_job,
    add_dm_job,
    conn,
    jobs_q,
    dm_jobs_high_q,
    dm_jobs_low_q,
)
import worker_jobs

import tweepy
from sqlalchemy import or_

import rq
from rq.job import Job as RQJob
from rq.registry import FailedJobRegistry


async def _send_reminders():
    await connect_db()

    # Do we need to send reminders?
    print("Checking if we need to send reminders")
    message = f"Hello! Just in case you forgot about me, your Semiphemeral account has been paused for several months. You can login at https://{os.environ.get('DOMAIN')}/ to unpause your account and start automatically deleting your old tweets and likes, except for the ones you want to keep."
    three_months_ago = datetime.now() - timedelta(days=90)
    reminded_users = []

    # Find all the paused users
    users = (
        await User.query.where(User.blocked == False)
        .where(User.paused == True)
        .gino.all()
    )
    for user in users:
        # Get the last job they finished
        last_job = (
            await JobDetails.query.where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "finished")
            .order_by(JobDetails.finished_timestamp.desc())
            .gino.first()
        )
        if last_job:
            # Was it it more than 3 months ago?
            if last_job.finished_timestamp < three_months_ago:
                remind = False

                # Let's make sure we also haven't sent them a DM in the last 3 months
                last_dm_job = (
                    await JobDetails.query.where(JobDetails.user_id == user.id)
                    .where(JobDetails.job_type == "dm")
                    .where(JobDetails.status == "finished")
                    .order_by(JobDetails.finished_timestamp.desc())
                    .gino.first()
                )
                if last_dm_job:
                    if last_dm_job.scheduled_timestamp < three_months_ago:
                        remind = True
                else:
                    remind = True

                if remind:
                    reminded_users.append(user.twitter_screen_name)
                    print(f"Reminding @{user.twitter_screen_name}")
                    await add_dm_job(
                        worker_jobs.funcs, user.twitter_id, message, priority="low"
                    )

    if len(reminded_users) > 0:
        admin_message = (
            f"Queued semiphemeral reminder DMs to {len(reminded_users)} users:\n\n"
            + "\n".join(reminded_users)
        )
        await send_admin_notification(admin_message)

    await disconnect_db()


async def _cleanup_users():
    await connect_db()

    users = await User.query.gino.all()
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
            await delete_user(user)
            users_deleted += 1

        i += 1

    admin_message = f"Deleted {users_deleted} users and all their data"
    print(admin_message)
    await send_admin_notification(admin_message)
    await disconnect_db()


async def _cleanup_dm_jobs():
    await connect_db()

    dm_jobs = await JobDetails.query.where(JobDetails.status == "pending").gino.all()
    print(f"there are {len(dm_jobs)} pending DM jobs")

    num_deleted = 0
    for dm_job in dm_jobs:
        user = await User.query.where(
            User.twitter_id == dm_job.dest_twitter_id
        ).gino.first()
        if not user:
            print(f"deleting DM job id={dm_job.id}")
            try:
                redis_job = RQJob.fetch(dm_job.redis_id, connection=conn)
                redis_job.cancel()
                redis_job.delete()
            except rq.exceptions.NoSuchJobError:
                pass

            await dm_job.delete()
            num_deleted += 1

    dm_jobs = await JobDetails.query.where(JobDetails.status == "pending").gino.all()
    print(f"now there are {len(dm_jobs)} pending DM jobs")

    admin_message = f"Deleted {num_deleted} pending DM jobs from deleted users"
    print(admin_message)
    await send_admin_notification(admin_message)
    await disconnect_db()


async def _update_fascists():
    await connect_db()

    user = await User.query.where(User.id == 1).gino.first()
    client = tweepy_client(user)

    # Mark all the likes as is_fascist=False
    print("Marking all likes as not fascist")
    await Like.update.values(is_fascist=False).gino.status()

    fascists = await db.Fascist.query.gino.all()
    print(f"Found {len(fascists)} Fascists")
    for fascist in fascists:
        # Get the twitter ID
        response = client.get_user(username=fascist.username, user_auth=True)
        try:
            await fascist.update(twitter_id=response["data"]["id"]).apply()
        except Exception as e:
            print(f"Error: {e}")
            print(json.dumps(response, indent=2))

        # Mark all the tweets from this user as is_fascist=True
        print(f"Marking tweets from @{fascist.username} as fascist")
        await Like.update.values(is_fascist=True).where(
            Like.author_id == fascist.twitter_id
        ).gino.status()


async def _fix_stalled_users():
    await connect_db()

    # Find all users
    users = (
        await User.query.where(User.blocked == False)
        .where(User.paused == False)
        .gino.all()
    )
    count = len(users)
    i = 0
    for user in users:
        pending_delete_jobs = (
            await JobDetails.query.where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "pending")
            .where(JobDetails.job_type == "delete")
            .gino.all()
        )
        if len(pending_delete_jobs) == 0:
            await add_job("delete", user.id, worker_jobs.funcs)
            print(f"[{i:,}/{count:,} @{user.twitter_screen_name} added delete job")

        i += 1

    await disconnect_db()


async def _cancel_dupe_jobs():
    await connect_db()
    i = 0
    print("querying users")
    users = (
        await User.query.where(User.blocked == False)
        .where(User.paused == False)
        .gino.all()
    )
    count = len(users)
    for user in users:
        for job_type in ["fetch", "delete"]:
            print(
                f"{i:,}/{count:,} @{user.twitter_screen_name} querying pending {job_type} jobs"
            )
            pending_jobs = (
                await JobDetails.query.where(JobDetails.user_id == user.id)
                .where(JobDetails.status == "pending")
                .where(JobDetails.job_type == job_type)
                .gino.all()
            )
            if len(pending_jobs) > 1:
                skipped_first = False
                for job in pending_jobs:
                    if not skipped_first:
                        skipped_first = True
                        continue

                    await job.update(
                        status="canceled", finished_timestamp=datetime.now()
                    ).apply()
                    print(
                        f"{i:,}/{count:,} @{user.twitter_screen_name} canceled {job_type} job {job.id}"
                    )

        i += 1

    await disconnect_db()


@click.group()
def main():
    """semiphemeral.com tasks"""


@main.command(
    "send-reminders",
    short_help="Send reminders to users who have been paused for months",
)
def send_reminders():
    asyncio.run(_send_reminders())


@main.command(
    "cleanup-users",
    short_help="Detect old users with deleted accounts, or who have revoked creds",
)
def cleanup_users():
    asyncio.run(_cleanup_users())


@main.command(
    "cleanup-dm-jobs",
    short_help="Delete DM jobs with users that have been deleted",
)
def cleanup_dm_jobs():
    asyncio.run(_cleanup_dm_jobs())


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


@main.command(
    "update-fascists",
    short_help="Set is_fascist=True for all likes from fascists",
)
def unblock_users():
    asyncio.run(_update_fascists())


@main.command(
    "fix-stalled-users",
    short_help="Cancel all jobs, and start new ones for non-paused users",
)
def fix_stalled_users():
    asyncio.run(_fix_stalled_users())


@main.command(
    "cancel-dupe-jobs",
    short_help="Each user should have at most 1 fetch and 1 delete job, this cancels dupes",
)
def cancel_dupe_jobs():
    asyncio.run(_cancel_dupe_jobs())


if __name__ == "__main__":
    main()
