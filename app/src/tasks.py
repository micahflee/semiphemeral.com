#!/usr/bin/env python3
import os
import json
import asyncio
import click
from datetime import datetime, timedelta

import peony
import db
from db import connect_db, User, JobDetails
from common import send_admin_notification, SemiphemeralPeonyClient, delete_user
import worker_jobs

import redis
import rq
from rq import Queue
from rq.job import Job as RQJob

conn = redis.from_url(os.environ.get("REDIS_URL"))
jobs_q = Queue("jobs", connection=conn)
dm_jobs_high_q = Queue("dm_jobs_high", connection=conn)
dm_jobs_low_q = Queue("dm_jobs_low", connection=conn)


async def _send_reminders():
    gino_db = await connect_db()

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

                    job_details = await JobDetails.create(
                        job_type="dm",
                        data=json.dumps(
                            {
                                "dest_twitter_id": user.twitter_id,
                                "message": message,
                            }
                        ),
                    )
                    redis_job = dm_jobs_low_q.enqueue(worker_jobs.dm, job_details.id)
                    await job_details.update(redis_id=redis_job.id).apply()

    if len(reminded_users) > 0:
        admin_message = (
            f"Queued semiphemeral reminder DMs to {len(reminded_users)} users:\n\n"
            + "\n".join(reminded_users)
        )
        await send_admin_notification(admin_message)


async def _cleanup_users():
    gino_db = await connect_db()

    users = await User.query.gino.all()
    i = 0
    count = len(users)
    users_deleted = 0
    for user in users:
        # See if the user has valid creds
        print(
            f"\r[{i:,}/{count:,}] checking @{user.twitter_screen_name} ..." + " " * 20,
            end="",
        )
        async with SemiphemeralPeonyClient(user) as client:
            try:
                await client.user
            except (
                peony.exceptions.InvalidOrExpiredToken,
                peony.exceptions.NotAuthenticated,
            ) as e:
                print(
                    f"\r[{i:,}/{count:,}, deleted {users_deleted:,}] deleting @{user.twitter_screen_name}: {e}"
                )
                await delete_user(user)
                users_deleted += 1

        i += 1

    admin_message = f"Deleted {users_deleted} users and all their data"
    print(admin_message)
    await send_admin_notification(admin_message)


async def _cleanup_dm_jobs():
    gino_db = await connect_db()

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


async def _unblock_users():
    gino_db = await connect_db()

    blocked_users = await User.query.where(User.blocked == True).gino.all()
    i = 0
    unblocked_user_count = 0
    count = len(blocked_users)
    for user in blocked_users:
        print(
            f"\r[{i}/{count}] checking @{user.twitter_screen_name} ..." + " " * 20,
            end="",
        )

        # Are they already unblocked?
        try:
            async with SemiphemeralPeonyClient(user) as client:
                friendship = await client.api.friendships.show.get(
                    source_screen_name=user.twitter_screen_name,
                    target_screen_name="semiphemeral",
                )

            if not friendship["relationship"]["source"]["blocked_by"]:
                unblocked_user_count += 1
                await user.update(paused=True, blocked=False).apply()
                print(
                    f"\r[{i}/{count}, unblocked {unblocked_user_count}], set @{user.twitter_screen_name} to unblocked"
                )
        except Exception as e:
            print(f"\r[{i}/{count}, deleting @{user.twitter_screen_name}: {e}")
            await delete_user(user)

        i += 1

    print("")


async def _onetime_2022_05_add_redis_jobs():
    await connect_db()

    # Convert Jobs
    count = 0
    jobs = await db.Job.query.gino.all()
    print(f"Found {len(jobs)} Jobs")
    for job in jobs:
        try:
            progress = json.loads(job.progress)
            data = {"progress": progress}
        except:
            data = {}

        job_details = await JobDetails.create(
            user_id=job.user_id,
            job_type=job.job_type,
            status=job.status,
            data=json.dumps(data),
            scheduled_timestamp=job.scheduled_timestamp,
            started_timestamp=job.started_timestamp,
            finished_timestamp=job.finished_timestamp,
        )

        # Create redis jobs for pending an active jobs, and make them all pending
        if job.status == "pending" or job.status == "active":
            if job_details.job_type == "fetch":
                redis_job = jobs_q.enqueue_at(
                    job.scheduled_timestamp, worker_jobs.fetch, job_details.id
                )
            elif job_details.job_type == "delete":
                redis_job = jobs_q.enqueue_at(
                    job.scheduled_timestamp, worker_jobs.delete, job_details.id
                )
            elif job_details.job_type == "delete_dms":
                redis_job = jobs_q.enqueue_at(
                    job.scheduled_timestamp, worker_jobs.delete_dms, job_details.id
                )
            elif job_details.job_type == "delete_dm_groups":
                redis_job = jobs_q.enqueue_at(
                    job.scheduled_timestamp,
                    worker_jobs.delete_dm_groups,
                    job_details.id,
                )
            await job_details.update(status="pending", redis_id=redis_job.id).apply()

        count += 1
        print(f"\rConverted {count}/{len(jobs)} Jobs     ", end="")

    print()

    # Convert DirectMessageJobs
    count = 0
    dm_jobs = await db.DirectMessageJob.query.gino.all()
    print(f"Found {len(dm_jobs)} DirectMessageJobs")
    for dm_job in dm_jobs:
        data = {
            "dest_twitter_id": dm_job.dest_twitter_id,
            "message": dm_job.message,
        }

        if dm_job.status == "pending":
            status = "pending"
        elif dm_job.status == "sent":
            status = "finished"
        else:
            status = "canceled"

        if dm_job.priority == 0:
            q = dm_jobs_high_q
        else:
            q = dm_jobs_low_q

        job_details = await JobDetails.create(
            job_type="dm",
            status=status,
            data=json.dumps(data),
            scheduled_timestamp=dm_job.scheduled_timestamp,
            started_timestamp=dm_job.sent_timestamp,
            finished_timestamp=dm_job.sent_timestamp,
        )

        # # Create redis jobs for pending jobs
        # if dm_job.status == "pending":
        #     redis_job = q.enqueue_at(
        #         dm_job.scheduled_timestamp, worker_jobs.dm, job_details.id
        #     )
        #     await job_details.update(redis_id=redis_job.id).apply()

        count += 1
        print(f"\rConverted {count}/{len(dm_jobs)} DirectMessageJobs     ", end="")

    print(
        "Skipped actually sending any pending DMs, because rewards are low and risks are high"
    )

    print()

    # Convert BlockJob
    count = 0
    block_jobs = await db.BlockJob.query.gino.all()
    print(f"Found {len(block_jobs)} BlockJobs")
    for block_job in block_jobs:
        data = {"twitter_username": block_job.twitter_username}
        if block_job.status == "pending":
            status = "pending"
        elif block_job.status == "blocked":
            status = "finished"
        else:
            status = "canceled"

        job_details = await JobDetails.create(
            user_id=block_job.user_id,
            job_type="block",
            status=status,
            data=json.dumps(data),
            scheduled_timestamp=block_job.scheduled_timestamp,
            started_timestamp=block_job.blocked_timestamp,
            finished_timestamp=block_job.blocked_timestamp,
        )

        # Create redis jobs for pending jobs
        if block_job.status == "pending":
            redis_job = q.enqueue_at(
                block_job.scheduled_timestamp, worker_jobs.block, job_details.id
            )
            await job_details.update(redis_id=redis_job.id).apply()

        count += 1
        print(f"\rConverted {count}/{len(block_jobs)} BlockJobs     ", end="")

    print()

    # Convert UnblockJob
    count = 0
    unblock_jobs = await db.UnblockJob.query.gino.all()
    print(f"Found {len(unblock_jobs)} UnblockJobs")
    for unblock_job in unblock_jobs:
        data = {"twitter_username": unblock_job.twitter_username}
        if unblock_job.status == "pending":
            status = "pending"
        elif unblock_job.status == "unblocked":
            status = "finished"
        else:
            status = "canceled"

        job_details = await JobDetails.create(
            user_id=unblock_job.user_id,
            job_type="unblock",
            status=status,
            data=json.dumps(data),
            scheduled_timestamp=unblock_job.scheduled_timestamp,
            started_timestamp=unblock_job.blocked_timestamp,
            finished_timestamp=unblock_job.blocked_timestamp,
        )

        # Create redis jobs for pending jobs
        if unblock_job.status == "pending":
            redis_job = q.enqueue_at(
                unblock_job.scheduled_timestamp, worker_jobs.unblock, job_details.id
            )
            await job_details.update(redis_id=redis_job.id).apply()

        count += 1
        print(f"\rConverted {count}/{len(unblock_jobs)} UnblockJobs     ", end="")

    print()


async def _onetime_2022_05_add_all_jobs():
    await connect_db()

    pending_jobs_count = 0
    new_jobs_count = 0

    # Find all the active users
    users = (
        await User.query.where(User.blocked == False)
        .where(User.paused == False)
        .gino.all()
    )
    for user in users:
        # Find pending delete jobs for this user
        jobs = (
            await JobDetails.query.where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "pending")
            .where(JobDetails.job_type == "delete")
            .gino.all()
        )
        if len(jobs) == 0:
            # Create a new delete job
            job_details = await JobDetails.create(
                job_type="delete",
                user_id=user.id,
            )
            redis_job = jobs_q.enqueue(
                worker_jobs.delete, job_details.id, job_timeout="24h"
            )
            await job_details.update(redis_id=redis_job.id).apply()

            new_jobs_count += 1
        else:
            pending_jobs_count += 1

        print(
            f"\r{pending_jobs_count:,} users with pending delete jobs, {new_jobs_count:,} delete jobs created",
            end="",
        )

    print()

async def _onetime_2022_10_fix_stalled_users():
    await connect_db()
    
    one_week_ago = datetime.now() - timedelta(days=7)

    # Find all the active users
    users = (
        await User.query.where(User.blocked == False)
        .where(User.paused == False)
        .gino.all()
    )
    count = len(users)
    i = 0
    users_fixed = 0
    for user in users:
        # Check if the user hasn't had a finished job in the last week
        is_stale = False
        last_job = (
            await JobDetails.query.where(JobDetails.user_id == user.id)
            .where(JobDetails.status == "finished")
            .order_by(JobDetails.finished_timestamp.desc())
            .gino.first()
        )
        if last_job:
            if last_job.finished_timestamp < one_week_ago:
                is_stale = True
        else:
            is_stale = True
        
        # If the user is stale, fix their account
        if is_stale:
            print(f"[{i:,}/{count:,}, fixed {users_fixed:,}] user @{user.twitter_screen_name} is stale, fixing ...")
            # Cancel the pending and active jobs
            pending_jobs = (
                await JobDetails.query.where(JobDetails.user_id == user.id)
                .where(JobDetails.status == "pending")
                .gino.all()
            )
            active_jobs = (
                await JobDetails.query.where(JobDetails.user_id == user.id)
                .where(JobDetails.status == "active")
                .gino.all()
            )
            jobs = pending_jobs + active_jobs

            for job in jobs:
                try:
                    redis_job = RQJob.fetch(job.redis_id, connection=conn)
                    redis_job.cancel()
                    redis_job.delete()
                except rq.exceptions.NoSuchJobError:
                    pass
                await job.update(status="canceled").apply()

            # Pause, and force semiphemeral to download all tweets
            await user.update(paused=True, since_id=None).apply()

            # Start semiphemeral
            await user.update(paused=False).apply()

            # Create a new delete job
            job_details = await JobDetails.create(
                job_type="delete",
                user_id=user.id,
            )
            redis_job = jobs_q.enqueue(
                worker_jobs.delete, job_details.id, job_timeout="24h"
            )
            await job_details.update(redis_id=redis_job.id).apply()

    print()


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
    "unblock-users",
    short_help="Set users to unblocked if they shouldn't be blocked",
)
def unblock_users():
    asyncio.run(_unblock_users())


@main.command(
    "2022-05-add-redis-jobs",
    short_help="Convert old jobs into JobDetails and redis jobs",
)
def onetime_2022_05_add_redis_jobs():
    asyncio.run(_onetime_2022_05_add_redis_jobs())


@main.command(
    "2022-05-add-all-jobs",
    short_help="Add jobs for everyone who isn't paused, and doesn't have a pending job",
)
def onetime_2022_05_add_all_jobs():
    asyncio.run(_onetime_2022_05_add_all_jobs())

@main.command(
    "2022-10-fix-stalled-users",
    short_help="Pause and restart users that are stalled",
)
def onetime_2022_10_fix_stalled_users():
    asyncio.run(_onetime_2022_10_fix_stalled_users())

if __name__ == "__main__":
    main()
