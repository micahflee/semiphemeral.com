"""add BlockJob and UnblockJob

Revision ID: 6047ff7d4c74
Revises: b47396881c9f
Create Date: 2020-02-24 17:06:04.474328

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6047ff7d4c74"
down_revision = "b47396881c9f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "block_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("twitter_username", sa.String),
        sa.Column("status", sa.String),
        sa.Column("scheduled_timestamp", sa.DateTime),
        sa.Column("blocked_timestamp", sa.DateTime),
    )
    op.create_table(
        "unblock_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("twitter_username", sa.String),
        sa.Column("status", sa.String),
        sa.Column("scheduled_timestamp", sa.DateTime),
        sa.Column("unblocked_timestamp", sa.DateTime),
    )


def downgrade():
    op.drop_table("block_jobs")
    op.drop_table("unblock_jobs")
