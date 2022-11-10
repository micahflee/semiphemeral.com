import os

from flask import Flask

import worker_jobs
from common import log, jobs_q, dm_jobs_high_q, dm_jobs_low_q

from sqlalchemy import select, update
from db import (
    User,
    JobDetails,
    session as db_session,
)


def enqueue_job(job_details, i, num_jobs):
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
        select(JobDetails).where(JobDetails.status == "pending")
    ).fetchall()
    num_jobs = len(jobs)
    log(None, f"Enqueing {num_jobs:,} jobs")
    i = 0
    for job_details in jobs:
        enqueue_job(job_details, i, num_jobs)
        i += 1

    # Disconnect
    db_session.close()

    # There's an rq-dashboard issue where it's not compatible with the latest click
    # so for now, we'll just replace it with a simple flask service

    # # Start the rq-dashboard
    # subprocess.run(["rq-dashboard", "--redis-url", os.environ.get("REDIS_URL")])

    app = Flask(__name__)

    @app.route("/")
    def hello_world():
        return "<p>Some day we'll have rq-dashboard again maybe</p>"

    app.run(host="0.0.0.0", port=9181)


if __name__ == "__main__":
    main()
