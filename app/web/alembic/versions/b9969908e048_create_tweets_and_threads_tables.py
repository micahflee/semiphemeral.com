"""create tweets and threads tables

Revision ID: b9969908e048
Revises: 5ab2c9670f80
Create Date: 2020-01-25 22:04:32.396033

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b9969908e048"
down_revision = "5ab2c9670f80"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "threads",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("root_status_id", sa.Integer, nullable=True),
        sa.Column("should_exclude", sa.Boolean, default=False, nullable=False),
    )

    op.create_table(
        "tweets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("twitter_user_id", sa.Integer, nullable=True),
        sa.Column("twitter_user_screen_name", sa.String, nullable=True),
        sa.Column("status_id", sa.Integer, nullable=True),
        sa.Column("text", sa.String, nullable=True),
        sa.Column("in_reply_to_screen_name", sa.String, nullable=True),
        sa.Column("in_reply_to_status_id", sa.Integer, nullable=True),
        sa.Column("in_reply_to_user_id", sa.Integer, nullable=True),
        sa.Column("retweet_count", sa.Integer, nullable=True),
        sa.Column("favorite_count", sa.Integer, nullable=True),
        sa.Column("retweeted", sa.Boolean, nullable=True),
        sa.Column("favorited", sa.Boolean, nullable=True),
        sa.Column("is_retweet", sa.Boolean, nullable=True),
        sa.Column("is_deleted", sa.Boolean, nullable=True),
        sa.Column("is_unliked", sa.Boolean, nullable=True),
        sa.Column("exclude_from_delete", sa.Boolean, nullable=True),
        sa.Column("twitter_user_id", sa.Integer, nullable=True),
    )


def downgrade():
    op.drop_table("threads")
    op.drop_table("tweets")
