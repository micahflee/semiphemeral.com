"""migrate tweets.in_reply_to_status_id

Revision ID: d5f983210426
Revises: 85ae2884e20b
Create Date: 2021-02-02 11:19:43.036186

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d5f983210426"
down_revision = "85ae2884e20b"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "tweets", "in_reply_to_status_id", type_=sa.String, existing_type=sa.BigInteger
    )


def downgrade():
    op.alter_column(
        "tweets", "in_reply_to_status_id", type_=sa.BigInteger, existing_type=sa.String
    )
