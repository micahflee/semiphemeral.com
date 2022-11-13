import os
import time
from datetime import datetime

import worker_jobs
from common import log, jobs_q, dm_jobs_high_q, dm_jobs_low_q, conn as redis_conn

from sqlalchemy import select, update
from db import (
    User,
    JobDetails,
    session as db_session,
)

from rq.job import Job as RQJob
from rq.registry import FailedJobRegistry


def enqueue_job(job_details, i=0, num_jobs=0):
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
        log(
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
        log(None, f"{i:,}/{num_jobs:,} Enqueued job ASAP")

    job_details.redis_id = redis_job.id
    db_session.add(job_details)
    db_session.commit()


def main():
    # Empty the queues
    jobs_q.empty()
    dm_jobs_high_q.empty()
    dm_jobs_low_q.empty()

    # If staging, start by pausing all users and cancel all pending jobs
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        log(None, "Staging environment, so pausing all users and canceling all jobs")
        db_session.execute(update(User).values({"paused": True}))
        db_session.execute(
            update(JobDetails)
            .values({"status": "canceled"})
            .where(JobDetails.status == "active")
        )
        db_session.execute(
            update(JobDetails)
            .values({"status": "canceled"})
            .where(JobDetails.status == "pending")
        )
        db_session.commit()

    # Mark active jobs pending
    log(None, "Make 'active' jobs 'pending'")
    db_session.execute(
        update(JobDetails)
        .values({"status": "pending"})
        .where(JobDetails.status == "active")
    )
    db_session.commit()

    # Add pending jobs to the worker queues
    jobs = db_session.scalars(
        select(JobDetails)
        .where(JobDetails.status == "pending")
        .order_by(JobDetails.scheduled_timestamp)
    ).fetchall()
    num_jobs = len(jobs)
    log(None, f"Enqueing {num_jobs:,} jobs")
    i = 0
    for job_details in jobs:
        try:
            enqueue_job(job_details, i, num_jobs)
        except:
            pass
        i += 1

    jobs_registry = FailedJobRegistry(queue=jobs_q)
    with open("/var/web/exceptions.log", "a") as f:
        logged_job_ids = []
        while True:
            # Log exceptions
            exceptions_logged = 0
            for job_id in jobs_registry.get_job_ids():
                if job_id not in logged_job_ids:
                    job = RQJob.fetch(job_id, connection=redis_conn)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"job_id is {job_id}, timestamp is {now}\n")
                    f.write(job.exc_info)
                    f.write("===\n")
                    f.flush()
                    logged_job_ids.append(job_id)
                    exceptions_logged += 1
            if exceptions_logged > 0:
                log(None, f"Logged {exceptions_logged} exceptions")

            # Retry failed jobs
            active_jobs = db_session.scalars(
                select(JobDetails).where(JobDetails.status == "active")
            ).fetchall()
            for job in active_jobs:
                redis_job = RQJob.fetch(job.redis_id, connection=redis_conn)
                if redis_job.get_status() in ["failed", "canceled"]:
                    log(
                        None,
                        f"job {job.job_type} job_id={job.id} {redis_job.get_status()}: {redis_job.exc_info} (trying again)",
                    )
                    job.status = "pending"
                    db_session.add(job)
                    db_session.commit()
                    enqueue_job(job)

            time.sleep(300)


if __name__ == "__main__":
    main()
