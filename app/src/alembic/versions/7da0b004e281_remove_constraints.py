"""remove constraints

Revision ID: 7da0b004e281
Revises: ed240f8de55a
Create Date: 2022-10-30 20:41:56.265077

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7da0b004e281"
down_revision = "ed240f8de55a"
branch_labels = None
depends_on = None


def upgrade():
    pass
    # op.drop_constraint("jobs_users_fk", "users", type_="foreignkey")
    # op.drop_constraint("nags_users_fk", "users", type_="foreignkey")
    # op.drop_constraint("threads_users_fk", "users", type_="foreignkey")
    # op.drop_constraint("tips_users_fk", "users", type_="foreignkey")
    # op.drop_constraint("tweets_users_fk", "users", type_="foreignkey")
    # op.drop_constraint("tweets_threads_fk", "threads", type_="foreignkey")


def downgrade():
    pass
    # op.create_foreign_key("jobs_users_fk", "users", "jobs", ["id"], ["user_id"])
    # op.create_foreign_key("nags_users_fk", "users", "nags", ["id"], ["user_id"])
    # op.create_foreign_key("threads_users_fk", "users", "threads", ["id"], ["user_id"])
    # op.create_foreign_key("tips_users_fk", "users", "tips", ["id"], ["user_id"])
    # op.create_foreign_key("tweets_users_fk", "users", "tweets", ["id"], ["user_id"])
    # op.create_foreign_key("tweets_threads_fk", "threads", "tweets", ["id"], ["user_id"])
