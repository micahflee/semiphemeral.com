"""migrate tweets.status_id

Revision ID: 85ae2884e20b
Revises: 643026fb55b3
Create Date: 2021-02-02 11:18:54.319719

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "85ae2884e20b"
down_revision = "643026fb55b3"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("tweets", "status_id", type_=sa.String, existing_type=sa.BigInteger)


def downgrade():
    op.alter_column("tweets", "status_id", type_=sa.BigInteger, existing_type=sa.String)
