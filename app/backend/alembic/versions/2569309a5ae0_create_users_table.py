"""create user table

Revision ID: 2569309a5ae0
Revises:
Create Date: 2020-01-12 14:55:55.948931

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2569309a5ae0"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("twitter_id", sa.Integer, nullable=False),
        sa.Column("twitter_screen_name", sa.String(), nullable=False),
        sa.Column("twitter_access_token", sa.String(), nullable=False),
        sa.Column("twitter_access_token_secret", sa.String(), nullable=False),
    )


def downgrade():
    op.drop_table("users")
