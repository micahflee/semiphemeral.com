"""modify tweets

Revision ID: 7294f6432f33
Revises: 2fd31b63d1f2
Create Date: 2022-10-31 11:26:37.706854

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7294f6432f33"
down_revision = "2fd31b63d1f2"
branch_labels = None
depends_on = None


def upgrade():
    # Update tweets table
    op.alter_column("tweets", "status_id", new_column_name="twitter_id")
    op.alter_column("tweets", "favorite_count", new_column_name="like_count")
    op.add_column("tweets", sa.Column("retweet_id", sa.String))
    op.drop_column("tweets", "twitter_user_id")
    op.drop_column("tweets", "twitter_user_screen_name")
    op.drop_column("tweets", "in_reply_to_screen_name")
    op.drop_column("tweets", "in_reply_to_status_id")
    op.drop_column("tweets", "in_reply_to_user_id")
    op.drop_column("tweets", "retweeted")
    op.drop_column("tweets", "favorited")
    op.drop_column("tweets", "is_unliked")
    op.drop_column("tweets", "is_fascist")
    # op.drop_index("tweets_twitter_user_id_idx")
    # op.drop_index("tweets_retweeted_idx")
    # op.drop_index("tweets_favorited_idx")
    # op.drop_index("tweets_is_unliked_idx")
    # op.drop_index("tweets_is_fascist_idx")

    # Update threads table
    op.alter_column("threads", "root_status_id", new_column_name="conversation_id")
    op.create_index("threads_conversation_id_idx", "threads", ["conversation_id"])

    # Create likes table
    op.create_table(
        "likes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("twitter_id", sa.String),
        sa.Column("created_at", sa.DateTime),
        sa.Column("author_id", sa.String),
        sa.Column("is_deleted", sa.Boolean),
        sa.Column("is_fascist", sa.Boolean),
    )
    op.create_index("likes_user_id_idx", "likes", ["user_id"])
    op.create_index("likes_author_id_idx", "likes", ["author_id"])
    op.create_index("likes_is_deleted_idx", "likes", ["is_deleted"])
    op.create_index("likes_is_fascist_idx", "likes", ["is_fascist"])


def downgrade():
    # There's no going back from this
    pass
