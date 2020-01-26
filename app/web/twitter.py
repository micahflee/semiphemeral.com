import asyncio
from datetime import datetime, timedelta

import tweepy

from common import twitter_api
from db import Job, User


class JobRescheduled(Exception):
    pass


def ensure_user_follows_us(func):
    async def wrapper(job):
        user = await User.query.where(User.id == job.user_id).gino.first()
        api = await twitter_api(user)

        # Is the user following us?
        friendship = api.show_friendship(
            source_id=user.twitter_id, target_screen_name="semiphemeral"
        )[0]

        if not friendship.following:
            reschedule_timedelta_in_the_future = timedelta(minutes=30)

            # If we've already sent a follow request but it still hasn't been accepted
            if friendship.following_requested:
                await reschedule_job(job, reschedule_timedelta_in_the_future)

            # Follow
            followed_user = api.create_friendship("semiphemeral", follow=True)

            # If we're still not following but have now sent a follow request
            if not followed_user.following and followed_user.follow_request_sent:
                await reschedule_job(job, reschedule_timedelta_in_the_future)

        return await func(job)

    return wrapper


async def reschedule_job(job, timedelta_in_the_future):
    await job.update(
        status="pending", scheduled_timestamp=datetime.now() + timedelta_in_the_future
    ).apply()
    raise JobRescheduled()


@ensure_user_follows_us
async def fetch(job):
    user = await User.query.where(User.id == job.user_id).gino.first()
    api = await twitter_api(user)

    # TODO: fetch tweets


@ensure_user_follows_us
async def delete(job):
    pass


async def start_job(job):
    await job.update(status="active", started_timestamp=datetime.now()).apply()

    if job.job_type == "fetch":
        try:
            await fetch(job)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()
        except JobRescheduled:
            pass

    elif job.job_type == "delete":
        try:
            await fetch(job)
            await delete(job)
            await job.update(
                status="finished", finished_timestamp=datetime.now()
            ).apply()
        except JobRescheduled:
            pass


async def start_jobs():
    # In case the app crashed in the middle of any previous jobs, change all "active"
    # jobs to "pending" so they'll start over
    await Job.update.values(status="pending").where(
        Job.status == "active"
    ).gino.status()

    # Infinitely loop looking for pending jobs
    while True:
        for job in (
            await Job.query.where(Job.status == "pending")
            .where(Job.scheduled_timestamp <= datetime.now())
            .gino.all()
        ):
            await start_job(job)

        await asyncio.sleep(60)
