"""create initial tables

Revision ID: c56f64167dc5
Revises:
Create Date: 2020-01-26 17:31:39.045531

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c56f64167dc5"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("twitter_id", sa.BigInteger),
        sa.Column("twitter_screen_name", sa.String),
        sa.Column("twitter_access_token", sa.String),
        sa.Column("twitter_access_token_secret", sa.String),
        sa.Column("delete_tweets", sa.Boolean, default=False),
        sa.Column("tweets_days_threshold", sa.Integer, default=30),
        sa.Column("tweets_retweet_threshold", sa.Integer, default=20),
        sa.Column("tweets_like_threshold", sa.Integer, default=20),
        sa.Column("tweets_threads_threshold", sa.Boolean, default=True),
        sa.Column("retweets_likes", sa.Boolean, default=False),
        sa.Column("retweets_likes_delete_retweets", sa.Boolean, default=True),
        sa.Column("retweets_likes_retweets_threshold", sa.Integer, default=30),
        sa.Column("retweets_likes_delete_likes", sa.Boolean, default=True),
        sa.Column("retweets_likes_likes_threshold", sa.Integer, default=60),
        sa.Column("since_id", sa.BigInteger),
        sa.Column("last_fetch", sa.DateTime),
        sa.Column("paused", sa.Boolean, default=True),
    )

    op.create_table(
        "tips",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("charge_id", sa.String),
        sa.Column("receipt_url", sa.String),
        sa.Column("paid", sa.Boolean),
        sa.Column("refunded", sa.Boolean),
        sa.Column("amount", sa.Integer),
        sa.Column("timestamp", sa.DateTime),
    )

    op.create_table(
        "nags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("timestamp", sa.DateTime),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("job_type", sa.String),
        sa.Column("status", sa.String),
        sa.Column("progress", sa.String),
        sa.Column("scheduled_timestamp", sa.DateTime),
        sa.Column("started_timestamp", sa.DateTime),
        sa.Column("finished_timestamp", sa.DateTime),
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("root_status_id", sa.BigInteger),
        sa.Column("should_exclude", sa.Boolean),
    )

    op.create_table(
        "tweets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("created_at", sa.DateTime),
        sa.Column("twitter_user_id", sa.BigInteger),
        sa.Column("twitter_user_screen_name", sa.String),
        sa.Column("status_id", sa.BigInteger),
        sa.Column("text", sa.String),
        sa.Column("in_reply_to_screen_name", sa.String),
        sa.Column("in_reply_to_status_id", sa.BigInteger),
        sa.Column("in_reply_to_user_id", sa.BigInteger),
        sa.Column("retweet_count", sa.Integer),
        sa.Column("favorite_count", sa.Integer),
        sa.Column("retweeted", sa.Boolean),
        sa.Column("favorited", sa.Boolean),
        sa.Column("is_retweet", sa.Boolean),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("is_unliked", sa.Boolean),
        sa.Column("exclude_from_delete", sa.Boolean),
        sa.Column("thread_id", sa.Integer),
    )


def downgrade():
    op.drop_table("users")
    op.drop_table("tips")
    op.drop_table("nags")
    op.drop_table("jobs")
    op.drop_table("threads")
    op.drop_table("tweets")
