"""migrate direct_message_jobs.dest_twitter_id

Revision ID: 0ed16aa8a5d7
Revises: b3cdaf937cf4
Create Date: 2021-02-02 11:17:09.108233

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0ed16aa8a5d7"
down_revision = "b3cdaf937cf4"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "direct_message_jobs",
        "dest_twitter_id",
        type_=sa.String,
        existing_type=sa.BigInteger,
    )


def downgrade():
    op.alter_column(
        "direct_message_jobs",
        "dest_twitter_id",
        type_=sa.BigInteger,
        existing_type=sa.String,
    )
