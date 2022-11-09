import os

from sqlalchemy import (
    create_engine,
    Column,
    ForeignKey,
    Integer,
    Float,
    String,
    Boolean,
    DateTime,
)
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    twitter_id = Column(String)
    twitter_screen_name = Column(String)
    twitter_access_token = Column(String)
    twitter_access_token_secret = Column(String)
    twitter_dms_access_token = Column(String)
    twitter_dms_access_token_secret = Column(String)

    delete_tweets = Column(Boolean, default=False)
    tweets_days_threshold = Column(Integer, default=30)
    tweets_enable_retweet_threshold = Column(Boolean, default=True)
    tweets_retweet_threshold = Column(Integer, default=20)
    tweets_enable_like_threshold = Column(Boolean, default=True)
    tweets_like_threshold = Column(Integer, default=20)
    tweets_threads_threshold = Column(Boolean, default=True)

    retweets_likes = Column(Boolean, default=False)
    retweets_likes_delete_retweets = Column(Boolean, default=True)
    retweets_likes_retweets_threshold = Column(Integer, default=30)
    retweets_likes_delete_likes = Column(Boolean, default=True)
    retweets_likes_likes_threshold = Column(Integer, default=60)

    direct_messages = Column(Boolean, default=False)
    direct_messages_threshold = Column(Integer, default=7)

    since_id = Column(String)
    last_fetch = Column(DateTime)
    paused = Column(Boolean, default=True)
    blocked = Column(Boolean)


class Tip(Base):
    __tablename__ = "tips"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    payment_processor = Column(String)
    stripe_charge_id = Column(String)
    stripe_payment_intent = Column(String)
    receipt_url = Column(String)
    paid = Column(Boolean)
    refunded = Column(Boolean)
    amount = Column(Float)
    timestamp = Column(DateTime)
    recurring_tip_id = Column(Integer)


class RecurringTip(Base):
    __tablename__ = "recurring_tips"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    payment_processor = Column(String)
    stripe_checkout_session_id = Column(String)
    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(String)
    status = Column(String)
    amount = Column(Float)
    timestamp = Column(DateTime)


class Nag(Base):
    __tablename__ = "nags"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime)


class JobDetails(Base):
    __tablename__ = "job_details"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)  # not required for all job types
    job_type = Column(
        String
    )  # "fetch", "delete", "delete_dms", "delete_dm_groups", "dm", "block", "unblock"
    status = Column(
        String, default="pending"
    )  # "pending", "active", "finished", "canceled"
    data = Column(String, default="{}")  # JSON object
    redis_id = Column(String)
    scheduled_timestamp = Column(DateTime)
    started_timestamp = Column(DateTime)
    finished_timestamp = Column(DateTime)

    def __str__(self):
        return (
            f"JobDetails: type={self.job_type}, status={self.status}, data={self.data}"
        )


class DirectMessageJob(Base):
    __tablename__ = "direct_message_jobs"

    id = Column(Integer, primary_key=True)
    dest_twitter_id = Column(String)
    message = Column(String)
    status = Column(String)  # "pending", "sent", "failed"
    scheduled_timestamp = Column(DateTime)
    sent_timestamp = Column(DateTime)
    priority = Column(Integer)


class BlockJob(Base):
    __tablename__ = "block_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)  # optional
    twitter_username = Column(String)
    status = Column(String)  # "pending", "blocked"
    scheduled_timestamp = Column(DateTime)
    blocked_timestamp = Column(DateTime)

    def __str__(self):
        return f"BlockJob: user=@{self.twitter_username}"


class UnblockJob(Base):
    __tablename__ = "unblock_jobs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)  # optional
    twitter_username = Column(String)
    status = Column(String)  # "pending", "unblocked"
    scheduled_timestamp = Column(DateTime)
    unblocked_timestamp = Column(DateTime)

    def __str__(self):
        return f"UnblockJob: user=@{self.twitter_username}"


class Thread(Base):
    __tablename__ = "threads"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    conversation_id = Column(String)
    should_exclude = Column(Boolean)


class Tweet(Base):
    __tablename__ = "tweets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    twitter_id = Column(String)
    created_at = Column(DateTime)
    text = Column(String)
    is_retweet = Column(Boolean)
    retweet_id = Column(String)
    is_reply = Column(Boolean)
    retweet_count = Column(Integer)
    like_count = Column(Integer)
    exclude_from_delete = Column(Boolean)
    is_deleted = Column(Boolean)
    thread_id = Column(Integer, ForeignKey("threads.id"))


class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    twitter_id = Column(String)
    created_at = Column(DateTime)
    author_id = Column(String)
    is_deleted = Column(Boolean)
    is_fascist = Column(Boolean)


class Fascist(Base):
    __tablename__ = "fascists"
    id = Column(Integer, primary_key=True)
    username = Column(String)
    twitter_id = Column(String)
    comment = Column(String)


engine = create_engine(os.environ.get("DATABASE_URI"), future=True)
session = Session(engine)


# tries = 0
# success = False
# while not success:
#     try:
#         gino_db = await db.set_bind(database_uri)
#         success = True
#     except TooManyConnectionsError:
#         tries += 1
#         print(
#             f"Try {tries}: Failed connecting to db, TooManyConnectionsError, waiting 60s",
#             file=sys.stderr,
#         )
#         await asyncio.sleep(60)

# return gino_db


# async def disconnect_db():
#     await db.pop_bind().close()
