"""add settings

Revision ID: a41bc63bf1dd
Revises: 4d60da56761c
Create Date: 2020-08-29 19:30:54.253697

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a41bc63bf1dd"
down_revision = "4d60da56761c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("tweets_enable_retweet_threshold", sa.Boolean, default=True),
    )
    op.add_column(
        "users",
        sa.Column("tweets_enable_like_threshold", sa.Boolean, default=True),
    )


def downgrade():
    op.drop_column("users", "tweets_enable_retweet_threshold")
    op.drop_column("users", "tweets_enable_like_threshold")
