"""add relationship between threads and tweets

Revision ID: 3a1dae769419
Revises: 2bfc623cb018
Create Date: 2020-02-11 21:01:14.264279

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "3a1dae769419"
down_revision = "2bfc623cb018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_foreign_key(
        constraint_name="tweets_threads_fk",
        source_table="tweets",
        referent_table="threads",
        local_cols=["thread_id"],
        remote_cols=["id"],
    )


def downgrade():
    op.drop_constraint(
        constraint_name="tweets_threads_fk", table_name="tweets", type_="foreignkey"
    )
