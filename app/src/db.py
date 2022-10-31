import os
import asyncio
from gino import Gino
from asyncpg.exceptions import TooManyConnectionsError

db = Gino()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    twitter_id = db.Column(db.String)
    twitter_screen_name = db.Column(db.String)
    twitter_access_token = db.Column(db.String)
    twitter_access_token_secret = db.Column(db.String)
    twitter_dms_access_token = db.Column(db.String)
    twitter_dms_access_token_secret = db.Column(db.String)

    delete_tweets = db.Column(db.Boolean, default=False)
    tweets_days_threshold = db.Column(db.Integer, default=30)
    tweets_enable_retweet_threshold = db.Column(db.Boolean, default=True)
    tweets_retweet_threshold = db.Column(db.Integer, default=20)
    tweets_enable_like_threshold = db.Column(db.Boolean, default=True)
    tweets_like_threshold = db.Column(db.Integer, default=20)
    tweets_threads_threshold = db.Column(db.Boolean, default=True)

    retweets_likes = db.Column(db.Boolean, default=False)
    retweets_likes_delete_retweets = db.Column(db.Boolean, default=True)
    retweets_likes_retweets_threshold = db.Column(db.Integer, default=30)
    retweets_likes_delete_likes = db.Column(db.Boolean, default=True)
    retweets_likes_likes_threshold = db.Column(db.Integer, default=60)

    direct_messages = db.Column(db.Boolean, default=False)
    direct_messages_threshold = db.Column(db.Integer, default=7)

    since_id = db.Column(db.String)
    last_fetch = db.Column(db.DateTime)
    paused = db.Column(db.Boolean, default=True)
    blocked = db.Column(db.Boolean)


class Tip(db.Model):
    __tablename__ = "tips"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    payment_processor = db.Column(db.String)
    stripe_charge_id = db.Column(db.String)
    stripe_payment_intent = db.Column(db.String)
    receipt_url = db.Column(db.String)
    paid = db.Column(db.Boolean)
    refunded = db.Column(db.Boolean)
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime)
    recurring_tip_id = db.Column(db.Integer)


class RecurringTip(db.Model):
    __tablename__ = "recurring_tips"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    payment_processor = db.Column(db.String)
    stripe_checkout_session_id = db.Column(db.String)
    stripe_customer_id = db.Column(db.String)
    stripe_subscription_id = db.Column(db.String)
    status = db.Column(db.String)
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime)


class Nag(db.Model):
    __tablename__ = "nags"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    timestamp = db.Column(db.DateTime)


class JobDetails(db.Model):
    __tablename__ = "job_details"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)  # not required for all job types
    job_type = db.Column(
        db.String
    )  # "fetch", "delete", "delete_dms", "delete_dm_groups", "dm", "block", "unblock"
    status = db.Column(
        db.String, default="pending"
    )  # "pending", "active", "finished", "canceled"
    data = db.Column(db.String, default="{}")  # JSON object
    redis_id = db.Column(db.String)
    scheduled_timestamp = db.Column(db.DateTime)
    started_timestamp = db.Column(db.DateTime)
    finished_timestamp = db.Column(db.DateTime)

    def __str__(self):
        return (
            f"JobDetails: type={self.job_type}, status={self.status}, data={self.data}"
        )


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    job_type = db.Column(
        db.String
    )  # "fetch", "delete", "delete_dms", "delete_dm_groups"
    status = db.Column(
        db.String
    )  # "pending", "active", "finished", "canceled", "blocked"
    progress = db.Column(db.String)  # JSON object
    scheduled_timestamp = db.Column(db.DateTime)
    started_timestamp = db.Column(db.DateTime)
    finished_timestamp = db.Column(db.DateTime)
    container_name = db.Column(db.String)

    def __str__(self):
        return f"Job: type={self.job_type}, user_id={self.user_id}"


class DirectMessageJob(db.Model):
    __tablename__ = "direct_message_jobs"

    id = db.Column(db.Integer, primary_key=True)
    dest_twitter_id = db.Column(db.String)
    message = db.Column(db.String)
    status = db.Column(db.String)  # "pending", "sent", "failed"
    scheduled_timestamp = db.Column(db.DateTime)
    sent_timestamp = db.Column(db.DateTime)
    priority = db.Column(db.Integer)


class BlockJob(db.Model):
    __tablename__ = "block_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)  # optional
    twitter_username = db.Column(db.String)
    status = db.Column(db.String)  # "pending", "blocked"
    scheduled_timestamp = db.Column(db.DateTime)
    blocked_timestamp = db.Column(db.DateTime)

    def __str__(self):
        return f"BlockJob: user=@{self.twitter_username}"


class UnblockJob(db.Model):
    __tablename__ = "unblock_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)  # optional
    twitter_username = db.Column(db.String)
    status = db.Column(db.String)  # "pending", "unblocked"
    scheduled_timestamp = db.Column(db.DateTime)
    unblocked_timestamp = db.Column(db.DateTime)

    def __str__(self):
        return f"UnblockJob: user=@{self.twitter_username}"


class Thread(db.Model):
    __tablename__ = "threads"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    conversation_id = db.Column(db.String)
    should_exclude = db.Column(db.Boolean)


class Tweet(db.Model):
    __tablename__ = "tweets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    twitter_id = db.Column(db.String)
    created_at = db.Column(db.DateTime)
    text = db.Column(db.String)
    is_retweet = db.Column(db.Boolean)
    retweet_id = db.Column(db.String)
    is_reply = db.Column(db.Boolean)
    retweet_count = db.Column(db.Integer)
    like_count = db.Column(db.Integer)
    exclude_from_delete = db.Column(db.Boolean)
    is_deleted = db.Column(db.Boolean)
    thread_id = db.Column(db.Integer, db.ForeignKey("threads.id"))


class Like(db.Model):
    __tablename__ = "likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    twitter_id = db.Column(db.String)
    created_at = db.Column(db.DateTime)
    author_id = db.Column(db.String)
    is_deleted = db.Column(db.Boolean)
    is_fascist = db.Column(db.Boolean)


class Fascist(db.Model):
    __tablename__ = "fascists"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String)
    twitter_id = db.Column(db.String)
    comment = db.Column(db.String)


async def connect_db():
    database_uri = os.environ.get("DATABASE_URI")

    wait_min = 1
    tries = 0
    success = False
    while not success:
        try:
            gino_db = await db.set_bind(database_uri)
            success = True
        except TooManyConnectionsError:
            tries += 1
            wait_min += 1
            print(
                f"Try {tries}: Failed connecting to db, TooManyConnectionsError, waiting {wait_min} min"
            )
            await asyncio.sleep(60 * wait_min)

    return gino_db
