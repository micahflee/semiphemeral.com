"""add user relationships

Revision ID: 66e9eb59f8ab
Revises: 6047ff7d4c74
Create Date: 2020-02-25 19:40:17.942541

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "66e9eb59f8ab"
down_revision = "6047ff7d4c74"
branch_labels = None
depends_on = None


def upgrade():
    op.create_foreign_key(
        constraint_name="tips_users_fk",
        source_table="tips",
        referent_table="users",
        local_cols=["user_id"],
        remote_cols=["id"],
    )
    op.create_foreign_key(
        constraint_name="nags_users_fk",
        source_table="nags",
        referent_table="users",
        local_cols=["user_id"],
        remote_cols=["id"],
    )
    op.create_foreign_key(
        constraint_name="jobs_users_fk",
        source_table="jobs",
        referent_table="users",
        local_cols=["user_id"],
        remote_cols=["id"],
    )
    op.create_foreign_key(
        constraint_name="threads_users_fk",
        source_table="threads",
        referent_table="users",
        local_cols=["user_id"],
        remote_cols=["id"],
    )
    op.create_foreign_key(
        constraint_name="tweets_users_fk",
        source_table="tweets",
        referent_table="users",
        local_cols=["user_id"],
        remote_cols=["id"],
    )


def downgrade():
    op.drop_constraint(
        constraint_name="tips_users_fk", table_name="tweets", type_="foreignkey"
    )
    op.drop_constraint(
        constraint_name="nags_users_fk", table_name="tweets", type_="foreignkey"
    )
    op.drop_constraint(
        constraint_name="jobs_users_fk", table_name="tweets", type_="foreignkey"
    )
    op.drop_constraint(
        constraint_name="threads_users_fk", table_name="tweets", type_="foreignkey"
    )
    op.drop_constraint(
        constraint_name="tweets_users_fk", table_name="tweets", type_="foreignkey"
    )
