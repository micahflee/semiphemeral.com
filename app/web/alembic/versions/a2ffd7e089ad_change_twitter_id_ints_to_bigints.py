"""change twitter id ints to bigints

Revision ID: a2ffd7e089ad
Revises: 417fc065a82f
Create Date: 2020-01-26 17:16:26.154092

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a2ffd7e089ad"
down_revision = "417fc065a82f"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        table_name="users",
        column_name="twitter_id",
        type_=sa.BigInteger,
        postgresql_using="expr",
    )
    op.alter_column(
        table_name="users",
        column_name="since_id",
        type_=sa.BigInteger,
        postgresql_using="expr",
    )
    op.alter_column(
        table_name="threads",
        column_name="root_status_id",
        type_=sa.BigInteger,
        postgresql_using="expr",
    )
    op.alter_column(
        table_name="tweets",
        column_name="twitter_user_id",
        type_=sa.BigInteger,
        postgresql_using="expr",
    )
    op.alter_column(
        table_name="tweets",
        column_name="status_id",
        type_=sa.BigInteger,
        postgresql_using="expr",
    )
    op.alter_column(
        table_name="tweets",
        column_name="in_reply_to_status_id",
        type_=sa.BigInteger,
        postgresql_using="expr",
    )
    op.alter_column(
        table_name="tweets",
        column_name="in_reply_to_user_id",
        type_=sa.BigInteger,
        postgresql_using="expr",
    )


def downgrade():
    op.alter_column(table_name="users", column_name="twitter_id", type_=sa.String)
    op.alter_column(table_name="users", column_name="since_id", type_=sa.Integer)
    op.alter_column(
        table_name="threads", column_name="root_status_id", type_=sa.Integer
    )
    op.alter_column(
        table_name="tweets", column_name="twitter_user_id", type_=sa.Integer
    )
    op.alter_column(table_name="tweets", column_name="status_id", type_=sa.Integer)
    op.alter_column(
        table_name="tweets", column_name="in_reply_to_status_id", type_=sa.Integer
    )
    op.alter_column(
        table_name="tweets", column_name="in_reply_to_user_id", type_=sa.Integer
    )
