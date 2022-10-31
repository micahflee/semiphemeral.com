"""add twitter_id to fascists

Revision ID: 2fd31b63d1f2
Revises: e70394be0af2
Create Date: 2022-10-31 11:05:21.238060

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2fd31b63d1f2"
down_revision = "e70394be0af2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fascists", sa.Column("twitter_id", sa.String))
    op.create_index("fascists_twitter_id_idx", "fascists", ["twitter_id"])


def downgrade():
    op.drop_column("fascists", "twitter_id")
    op.drop_index("fascists_twitter_id_idx")
