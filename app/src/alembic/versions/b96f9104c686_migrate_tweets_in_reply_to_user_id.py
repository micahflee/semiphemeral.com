"""migrate tweets.in_reply_to_user_id

Revision ID: b96f9104c686
Revises: d5f983210426
Create Date: 2021-02-02 11:20:15.509314

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b96f9104c686"
down_revision = "d5f983210426"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "tweets", "in_reply_to_user_id", type_=sa.String, existing_type=sa.BigInteger
    )


def downgrade():
    op.alter_column(
        "tweets", "in_reply_to_user_id", type_=sa.BigInteger, existing_type=sa.String
    )
