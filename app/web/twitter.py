import asyncio
from datetime import datetime

from db import Job


async def fetch(job):
    pass


async def delete(job):
    pass


async def start_job(job):
    await job.update(status="active", started_timestamp=datetime.now()).apply()

    if job.job_type == "fetch":
        await fetch(job)
        await job.update(status="finished", finished_timestamp=datetime.now()).apply()

    elif job.job_type == "delete":
        await fetch(job)
        await delete(job)
        await job.update(status="finished", finished_timestamp=datetime.now()).apply()


async def start_jobs():
    # In case the app crashed in the middle of any previous jobs, change all "active"
    # jobs to "pending" so they'll start over
    await Job.update.values(status="pending").where(
        Job.status == "active"
    ).gino.status()

    # Infinitely loop looking for pending jobs
    while True:
        await asyncio.sleep(60)

        for job in (
            await Job.query.where(Job.status == "pending")
            .where(Job.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
            await start_job(job)
