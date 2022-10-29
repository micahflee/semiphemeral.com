"""create tweet index

Revision ID: 307f6507e6d5
Revises: 57ec4b505a7a
Create Date: 2022-10-28 17:41:58.274722

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '307f6507e6d5'
down_revision = '57ec4b505a7a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("tweets_created_at_idx", "tweets", ["created_at"])


def downgrade():
    op.drop_index("tweets_created_at_idx")
