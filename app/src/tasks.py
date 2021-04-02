import os
import asyncio
import click
from datetime import datetime, timedelta

from db import connect_db, User, Job, DirectMessageJob
from common import send_admin_dm


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
                    )

    if len(reminded_users) > 0:
        admin_message = (
            f"Queued semiphemeral reminder DMs to {len(reminded_users)} users:\n\n"
            + "\n".join(reminded_users)
        )
        await send_admin_dm(admin_message)


@click.group()
def main():
    """semiphemeral.com tasks"""


@main.command(
    "send-reminders",
    short_help="Send reminders to users who have been paused for months",
)
def send_reminders():
    asyncio.run(_send_reminders())


if __name__ == "__main__":
    main()
