"""add fascists table

Revision ID: b47396881c9f
Revises: 975687104fd6
Create Date: 2020-02-23 16:41:59.352386

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b47396881c9f"
down_revision = "975687104fd6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fascists",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("twitter_user_screen_name", sa.String),
        sa.Column("comment", sa.String),
    )
    op.add_column("tweets", sa.Column("is_fascist", sa.Boolean, default=False))


def downgrade():
    op.drop_table("fascists")
    op.drop_column("tweets", "is_fascist")
