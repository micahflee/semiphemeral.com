import os
import asyncio
import click
from datetime import datetime, timedelta

import tweepy

from db import connect_db, User, Job, DirectMessageJob
from common import send_admin_dm, tweepy_api, tweepy_api_call, delete_user


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
            await Job.query.where(Job.user_id == user.id)
            .where(Job.status == "finished")
            .order_by(Job.finished_timestamp.desc())
            .gino.first()
        )
        if last_job:
            # Was it it more than 3 months ago?
            if last_job.finished_timestamp < three_months_ago:
                remind = False

                # Let's make sure we also haven't sent them a DM in the last 3 months
                last_dm_job = (
                    await DirectMessageJob.query.where(
                        DirectMessageJob.dest_twitter_id == user.twitter_id
                    )
                    .order_by(DirectMessageJob.sent_timestamp.desc())
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
                    await DirectMessageJob.create(
                        dest_twitter_id=user.twitter_id,
                        message=message,
                        status="pending",
                        scheduled_timestamp=datetime.now(),
                        priority=9,
                    )

    if len(reminded_users) > 0:
        admin_message = (
            f"Queued semiphemeral reminder DMs to {len(reminded_users)} users:\n\n"
            + "\n".join(reminded_users)
        )
        await send_admin_dm(admin_message)


async def _cleanup_users():
    gino_db = await connect_db()

    users = await User.query.gino.all()
    i = 0
    count = len(users)
    users_deleted = 0
    for user in users:
        # See if the user has valid creds
        print(
            f"\r[{i}/{count}] checking @{user.twitter_screen_name} ..." + " " * 20,
            end="",
        )
        api = await tweepy_api(user)
        try:
            await tweepy_api_call(None, api, "me")
            # print(f"\r[{i}/{count}] checking @{user.twitter_screen_name} valid")
        except tweepy.error.TweepError as e:
            print(
                f"\r[{i}/{count}, deleted {users_deleted}] deleting @{user.twitter_screen_name}: {e}"
            )
            await delete_user(user)
            users_deleted += 1

        i += 1

    print(f"deleted {users_deleted} users and all their data")


def _cleanup_dm_jobs():
    gino_db = await connect_db()

    dm_jobs = await DirectMessageJob.query.where(
        DirectMessageJob.status == "pending"
    ).gino.all()
    print(f"there are {len(dm_jobs))} pending DM jobs")
    
    for dm_job in dm_jobs:
        user = await User.query.where(User.twitter_id == dm_job.dest_twitter_id)
        if not user:
            print(f"deleting DM job id={dm_job.id}")
            await dm_job.delete()
    
    dm_jobs = await DirectMessageJob.query.where(
        DirectMessageJob.status == "pending"
    ).gino.all()
    print(f"now there are {len(dm_jobs))} pending DM jobs")


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


if __name__ == "__main__":
    main()
