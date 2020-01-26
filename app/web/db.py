import os
from gino import Gino

db = Gino()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    twitter_id = db.Column(db.String)
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

    since_id = db.Column(db.String)
    last_fetch = db.Column(db.DateTime)
    paused = db.Column(db.Boolean, default=True)


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
    progress = db.Column(db.String)
    scheduled_timestamp = db.Column(db.DateTime)
    started_timestamp = db.Column(db.DateTime)
    finished_timestamp = db.Column(db.DateTime)


async def connect_db():
    password = os.environ.get("POSTGRES_PASSWORD")
    await db.set_bind(f"postgresql://semiphemeral:{password}@db/semiphemeral")
