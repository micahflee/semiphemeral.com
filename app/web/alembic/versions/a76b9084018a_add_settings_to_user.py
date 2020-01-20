"""add settings to user

Revision ID: a76b9084018a
Revises: 6b7f5885b1cf
Create Date: 2020-01-19 15:51:33.148531

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a76b9084018a"
down_revision = "6b7f5885b1cf"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users", sa.Column("delete_tweets", sa.Boolean, default=False, nullable=False)
    )
    op.add_column(
        "users",
        sa.Column("tweets_days_threshold", sa.Integer, default=30, nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("tweets_retweet_threshold", sa.Integer, default=20, nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("tweets_like_threshold", sa.Integer, default=20, nullable=False),
    )
    op.add_column(
        "users",
        sa.Column(
            "tweets_threads_threshold", sa.Boolean, default=False, nullable=False
        ),
    )
    op.add_column(
        "users", sa.Column("retweets_likes", sa.Boolean, default=False, nullable=False)
    )
    op.add_column(
        "users",
        sa.Column(
            "retweets_likes_delete_retweets", sa.Boolean, default=True, nullable=True
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "retweets_likes_retweets_threshold", sa.Integer, default=30, nullable=False
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "retweets_likes_delete_likes", sa.Boolean, default=True, nullable=True
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "retweets_likes_likes_threshold", sa.Integer, default=60, nullable=False
        ),
    )
    op.add_column(
        "users", sa.Column("since_id", sa.String(), nullable=True),
    )
    op.add_column(
        "users", sa.Column("last_fetch", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_column("users", "delete_tweets")
    op.drop_column("users", "tweets_days_threshold")
    op.drop_column("users", "tweets_retweet_threshold")
    op.drop_column("users", "tweets_like_threshold")
    op.drop_column("users", "retweets_likes")
    op.drop_column("users", "retweets_likes_delete_retweets")
    op.drop_column("users", "retweets_likes_retweets_threshold")
    op.drop_column("users", "retweets_likes_delete_likes")
    op.drop_column("users", "retweets_likes_likes_threshold")
    op.drop_column("users", "since_id")
    op.drop_column("users", "last_fetch")
