"""add dm settings

Revision ID: 5a8952165d08
Revises: 564f4b56ab3c
Create Date: 2020-09-03 17:45:48.809972

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5a8952165d08"
down_revision = "564f4b56ab3c"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("twitter_dms_access_token", sa.String))
    op.add_column("users", sa.Column("twitter_dms_access_token_secret", sa.String))
    op.add_column(
        "users", sa.Column("direct_messages", sa.Boolean, server_default="FALSE")
    )
    op.add_column(
        "users", sa.Column("direct_messages_threshold", sa.Integer, server_default="7")
    )


def downgrade():
    op.drop_column("users", "twitter_dms_access_token")
    op.drop_column("users", "twitter_dms_access_token_secret")
    op.drop_column("users", "direct_messages")
    op.drop_column("users", "direct_messages_threshold")
