import asyncio
import os
import subprocess

import redis
import rq
from rq import Queue
from rq.job import Job as RQJob, Retry as RQRetry

import worker_jobs

from common import log

from db import (
    db,
    connect_db,
    User,
    JobDetails,
)

print(f"Connecting to redis at: {os.environ.get('REDIS_URL')}")
conn = redis.from_url(os.environ.get("REDIS_URL"))

jobs_q = Queue("jobs", connection=conn)
dm_jobs_high_q = Queue("dm_jobs_high", connection=conn)
dm_jobs_low_q = Queue("dm_jobs_low", connection=conn)


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
            retry=RQRetry(max=3, interval=[60, 120, 240]),
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
            retry=RQRetry(max=3, interval=[60, 120, 240]),
        )
        await log(None, f"{i:,}/{num_jobs:,} Enqueued job ASAP")

    await job_details.update(redis_id=redis_job.id).apply()


async def main():
    # Empty the queues
    jobs_q.empty()
    dm_jobs_high_q.empty()
    dm_jobs_low_q.empty()

    # Connect to the database
    await connect_db()

    # If staging, start by pausing all users and cancel all pending jobs
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        await log(
            None, "Staging environment, so pausing all users and canceling all jobs"
        )
        await User.update.values(paused=True).gino.status()

        await JobDetails.update.values(status="pending").where(
            JobDetails.status == "active"
        ).gino.status()

        pending_jobs = await JobDetails.query.where(
            JobDetails.status == "pending"
        ).gino.all()
        for job in pending_jobs:
            try:
                redis_job = RQJob.fetch(job.redis_id, connection=conn)
                redis_job.cancel()
                redis_job.delete()
            except rq.exceptions.NoSuchJobError:
                pass

        await JobDetails.update.values(status="canceled").where(
            JobDetails.status == "pending"
        ).gino.status()

    # Start all active jobs
    await log(None, "Make 'active' jobs as 'pending'")
    await JobDetails.update.values(status="pending").where(
        JobDetails.status == "active"
    ).gino.status()
    jobs = await JobDetails.query.where(JobDetails.status == "pending").gino.all()
    await log(None, f"Enqueing {len(jobs):,} jobs")
    i = 0
    num_jobs = len(jobs)
    for job_details in jobs:
        await enqueue_job(job_details, i, num_jobs)
        i += 1

    # Start the rq-dashboard
    subprocess.run(["rq-dashboard", "--redis-url", os.environ.get("REDIS_URL")])


if __name__ == "__main__":
    asyncio.run(main())
