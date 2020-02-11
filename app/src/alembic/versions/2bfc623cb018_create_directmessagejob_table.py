"""create DirectMessageJob table

Revision ID: 2bfc623cb018
Revises: c56f64167dc5
Create Date: 2020-02-10 21:02:59.494017

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2bfc623cb018"
down_revision = "c56f64167dc5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "direct_message_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dest_twitter_id", sa.BigInteger),
        sa.Column("message", sa.String),
        sa.Column("status", sa.String),
        sa.Column("scheduled_timestamp", sa.DateTime),
        sa.Column("sent_timestamp", sa.DateTime),
    )


def downgrade():
    op.drop_table("direct_message_jobs")
