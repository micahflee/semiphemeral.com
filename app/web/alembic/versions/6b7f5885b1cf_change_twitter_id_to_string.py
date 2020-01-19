"""change twitter_id to string

Revision ID: 6b7f5885b1cf
Revises: 2569309a5ae0
Create Date: 2020-01-18 21:04:14.759534

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6b7f5885b1cf"
down_revision = "2569309a5ae0"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        table_name="users", column_name="twitter_id", nullable=False, type_=sa.String()
    )


def downgrade():
    op.alter_column(
        table_name="users", column_name="twitter_id", nullable=False, type_=sa.Integer
    )
