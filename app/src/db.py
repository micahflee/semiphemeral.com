import os
import ssl
from gino import Gino

db = Gino()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    twitter_id = db.Column(db.BigInteger)
    twitter_screen_name = db.Column(db.String)
    twitter_access_token = db.Column(db.String)
    twitter_access_token_secret = db.Column(db.String)

    delete_tweets = db.Column(db.Boolean, default=False)
    tweets_days_threshold = db.Column(db.Integer, default=30)
    tweets_retweet_threshold = db.Column(db.Integer, default=20)
    tweets_like_threshold = db.Column(db.Integer, default=20)
    tweets_threads_threshold = db.Column(db.Boolean, default=True)

    retweets_likes = db.Column(db.Boolean, default=False)
    retweets_likes_delete_retweets = db.Column(db.Boolean, default=True)
    retweets_likes_retweets_threshold = db.Column(db.Integer, default=30)
    retweets_likes_delete_likes = db.Column(db.Boolean, default=True)
    retweets_likes_likes_threshold = db.Column(db.Integer, default=60)

    since_id = db.Column(db.BigInteger)
    last_fetch = db.Column(db.DateTime)
    paused = db.Column(db.Boolean, default=True)
    following = db.Column(db.Boolean)
    blocked = db.Column(db.Boolean)


class Tip(db.Model):
    __tablename__ = "tips"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    charge_id = db.Column(db.String)
    receipt_url = db.Column(db.String)
    paid = db.Column(db.Boolean)
    refunded = db.Column(db.Boolean)
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime)


class Nag(db.Model):
    __tablename__ = "nags"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime)


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    job_type = db.Column(db.String)  # "fetch", "delete"
    status = db.Column(db.String)  # "pending", "active", "finished", "canceled"
    progress = db.Column(db.String)  # JSON object
    scheduled_timestamp = db.Column(db.DateTime)
    started_timestamp = db.Column(db.DateTime)
    finished_timestamp = db.Column(db.DateTime)


class DirectMessageJob(db.Model):
    __tablename__ = "direct_message_jobs"

    id = db.Column(db.Integer, primary_key=True)
    dest_twitter_id = db.Column(db.BigInteger)
    message = db.Column(db.String)
    status = db.Column(db.String)  # "pending", "sent"
    scheduled_timestamp = db.Column(db.DateTime)
    sent_timestamp = db.Column(db.DateTime)


class Thread(db.Model):
    __tablename__ = "threads"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    root_status_id = db.Column(db.BigInteger)
    should_exclude = db.Column(db.Boolean)


class Tweet(db.Model):
    __tablename__ = "tweets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime)
    twitter_user_id = db.Column(db.BigInteger)
    twitter_user_screen_name = db.Column(db.String)
    status_id = db.Column(db.BigInteger)
    text = db.Column(db.String)
    in_reply_to_screen_name = db.Column(db.String)
    in_reply_to_status_id = db.Column(db.BigInteger)
    in_reply_to_user_id = db.Column(db.BigInteger)
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
    twitter_user_screen_name = db.Column(db.String)
    comment = db.Column(db.String)


async def connect_db():
    ctx = ssl.create_default_context(
        cafile=os.path.abspath("digitalocean/ca-certificate.crt")
    )
    database_uri = os.environ.get("DATABASE_URI")

    await db.set_bind(database_uri, ssl=ctx)
