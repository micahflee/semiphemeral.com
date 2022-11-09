import asyncio
import os
import subprocess

import worker_jobs

from common import log, jobs_q, dm_jobs_high_q, dm_jobs_low_q

from sqlalchemy import select, update
from db import (
    User,
    JobDetails,
    session as db_session,
)


async def enqueue_job(job_details, i, num_jobs):
    func = None
    job_id = None
    job_timeout = "10m"

    if job_details.job_type == "fetch":
        func = worker_jobs.fetch
        job_id = job_details.id
        job_timeout = "24h"
    elif job_details.job_type == "delete":
        func = worker_jobs.delete
        job_id = job_details.id
        job_timeout = "24h"
    elif job_details.job_type == "delete_dms":
        func = worker_jobs.delete_dms
        job_id = job_details.id
        job_timeout = "24h"
    elif job_details.job_type == "delete_dm_groups":
        func = worker_jobs.delete_dm_groups
        job_id = job_details.id
        job_timeout = "24h"
    elif job_details.job_type == "block":
        func = worker_jobs.block
        job_id = job_details.id
    elif job_details.job_type == "unblock":
        func = worker_jobs.unblock
        job_id = job_details.id
    elif job_details.job_type == "dm":
        func = worker_jobs.dm
        job_id = job_details.id

    if job_details.scheduled_timestamp:
        redis_job = jobs_q.enqueue_at(
            job_details.scheduled_timestamp,
            func,
            job_id,
            job_timeout=job_timeout,
            # retry=RQRetry(max=3, interval=[60, 120, 240]),
        )
        await log(
            None,
            f"{i:,}/{num_jobs:,} Enqueued scheduled job for {job_details.scheduled_timestamp}",
        )
    else:
        redis_job = jobs_q.enqueue(
            func,
            job_id,
            job_timeout=job_timeout,
            # retry=RQRetry(max=3, interval=[60, 120, 240]),
        )
        await log(None, f"{i:,}/{num_jobs:,} Enqueued job ASAP")

    job_details.redis_id = redis_job.id
    db_session.add(job_details)
    db_session.commit()


async def main():
    # Empty the queues
    jobs_q.empty()
    dm_jobs_high_q.empty()
    dm_jobs_low_q.empty()

    # If staging, start by pausing all users and cancel all pending jobs
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        await log(
            None, "Staging environment, so pausing all users and canceling all jobs"
        )
        db_session.execute(update(User).values({"paused": True}))
        db_session.execute(
            update(JobDetails).values(
                {"status": "canceled"}.where(JobDetails.status == "active")
            )
        )
        db_session.execute(
            update(JobDetails).values(
                {"status": "canceled"}.where(JobDetails.status == "pending")
            )
        )

    # Mark active jobs pending
    await log(None, "Make 'active' jobs 'pending'")
    db_session.execute(
        update(JobDetails).values(
            {"status": "pending"}.where(JobDetails.status == "active")
        )
    )

    # Add pending jobs to the worker queues
    jobs = db_session.scalars(
        select(JobDetails).where(JobDetails.status == "pending")
    ).fetchall()
    num_jobs = len(jobs)
    await log(None, f"Enqueing {num_jobs:,} jobs")
    i = 0
    for job_details in jobs:
        await enqueue_job(job_details, i, num_jobs)
        i += 1

    # Disconnect
    db_session.close()

    # Start the rq-dashboard
    subprocess.run(["rq-dashboard", "--redis-url", os.environ.get("REDIS_URL")])


if __name__ == "__main__":
    asyncio.run(main())
