"""remove constraints, take two

Revision ID: e70394be0af2
Revises: 7da0b004e281
Create Date: 2022-10-30 21:02:29.160718

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e70394be0af2"
down_revision = "7da0b004e281"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("jobs_users_fk", "jobs", type_="foreignkey")
    op.drop_constraint("nags_users_fk", "nags", type_="foreignkey")
    op.drop_constraint("threads_users_fk", "threads", type_="foreignkey")
    op.drop_constraint("tips_users_fk", "tips", type_="foreignkey")
    op.drop_constraint("tweets_users_fk", "tweets", type_="foreignkey")
    op.drop_constraint("tweets_threads_fk", "tweets", type_="foreignkey")


def downgrade():
    op.create_foreign_key("jobs_users_fk", "jobs", "users", ["id"], ["user_id"])
    op.create_foreign_key("nags_users_fk", "nags", "users", ["id"], ["user_id"])
    op.create_foreign_key("threads_users_fk", "threads", "users", ["id"], ["user_id"])
    op.create_foreign_key("tips_users_fk", "tips", "users", ["id"], ["user_id"])
    op.create_foreign_key("tweets_users_fk", "tweets", "users", ["id"], ["user_id"])
    op.create_foreign_key("tweets_threads_fk", "tweets", "threads", ["id"], ["user_id"])
