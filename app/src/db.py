import os
import ssl
from gino import Gino

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


class Nag(db.Model):
    __tablename__ = "nags"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    timestamp = db.Column(db.DateTime)


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


class UnblockJob(db.Model):
    __tablename__ = "unblock_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)  # optional
    twitter_username = db.Column(db.String)
    status = db.Column(db.String)  # "pending", "unblocked"
    scheduled_timestamp = db.Column(db.DateTime)
    unblocked_timestamp = db.Column(db.DateTime)


class Thread(db.Model):
    __tablename__ = "threads"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    root_status_id = db.Column(db.String)
    should_exclude = db.Column(db.Boolean)


class Tweet(db.Model):
    __tablename__ = "tweets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime)
    twitter_user_id = db.Column(db.String)
    twitter_user_screen_name = db.Column(db.String)
    status_id = db.Column(db.String)
    text = db.Column(db.String)
    in_reply_to_screen_name = db.Column(db.String)
    in_reply_to_status_id = db.Column(db.String)
    in_reply_to_user_id = db.Column(db.String)
    retweet_count = db.Column(db.Integer)
    favorite_count = db.Column(db.Integer)
    retweeted = db.Column(db.Boolean)
    favorited = db.Column(db.Boolean)
    is_retweet = db.Column(db.Boolean)
    is_deleted = db.Column(db.Boolean)
    is_unliked = db.Column(db.Boolean)
    exclude_from_delete = db.Column(db.Boolean)
    is_fascist = db.Column(db.Boolean, default=False)
    thread_id = db.Column(db.Integer, db.ForeignKey("threads.id"))


class Fascist(db.Model):
    __tablename__ = "fascists"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String)
    comment = db.Column(db.String)


async def connect_db():
    ctx = ssl.create_default_context(
        cafile=os.path.abspath("digitalocean/ca-certificate.crt")
    )
    database_uri = os.environ.get("DATABASE_URI")

    return await db.set_bind(database_uri, ssl=ctx)
