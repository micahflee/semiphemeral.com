"""add indices to users

Revision ID: cc8c59b6b463
Revises: 307f6507e6d5
Create Date: 2022-10-28 18:43:26.527178

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "cc8c59b6b463"
down_revision = "307f6507e6d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("users_twitter_screen_name_idx", "users", ["twitter_screen_name"])


def downgrade():
    op.drop_index("users_twitter_screen_name_idx")
