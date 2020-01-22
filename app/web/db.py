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


class Tip(db.Model):
    __tablename__ = "tips"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    amount = db.Column(db.Float)
    timestamp = db.Column(db.DateTime)
    status = db.Column(db.String)


async def connect_db():
    password = os.environ.get("POSTGRES_PASSWORD")
    await db.set_bind(f"postgresql://semiphemeral:{password}@db/semiphemeral")
