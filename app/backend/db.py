import os
from gino import Gino

db = Gino()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer(), primary_key=True)
    twitter_id = db.Column(db.Integer())
    twitter_screen_name = db.Column(db.String())
    twitter_access_token = db.Column(db.String())
    twitter_access_token_secret = db.Column(db.String())


async def connect_db():
    password = os.environ.get("POSTGRES_PASSWORD")
    await db.set_bind(f"postgresql://semiphemeral:{password}@db/semiphemeral")
