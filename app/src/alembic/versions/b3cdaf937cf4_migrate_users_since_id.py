"""migrate users.since_id

Revision ID: b3cdaf937cf4
Revises: caba2a0b2912
Create Date: 2021-02-02 11:16:24.697642

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b3cdaf937cf4"
down_revision = "caba2a0b2912"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "since_id", type_=sa.String, existing_type=sa.BigInteger)


def downgrade():
    op.alter_column("users", "since_id", type_=sa.BigInteger, existing_type=sa.String)
