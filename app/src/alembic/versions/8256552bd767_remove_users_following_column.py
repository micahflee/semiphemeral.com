"""remove users.following column

Revision ID: 8256552bd767
Revises: 66e9eb59f8ab
Create Date: 2020-02-27 18:47:46.019978

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8256552bd767"
down_revision = "66e9eb59f8ab"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("users", "following")


def downgrade():
    op.add_column("users", sa.Column("following", sa.Boolean))
