"""migrate threads.root_status_id

Revision ID: 68436f16dcc1
Revises: 0ed16aa8a5d7
Create Date: 2021-02-02 11:17:43.291841

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "68436f16dcc1"
down_revision = "0ed16aa8a5d7"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "threads", "root_status_id", type_=sa.String, existing_type=sa.BigInteger
    )


def downgrade():
    op.alter_column(
        "threads", "root_status_id", type_=sa.BigInteger, existing_type=sa.String
    )
