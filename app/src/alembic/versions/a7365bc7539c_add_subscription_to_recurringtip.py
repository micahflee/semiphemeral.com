"""add subscription to recurringtip

Revision ID: a7365bc7539c
Revises: 589bce3acd63
Create Date: 2021-04-25 14:29:17.863882

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7365bc7539c"
down_revision = "589bce3acd63"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("recurring_tips", sa.Column("stripe_subscription_id", sa.String))


def downgrade():
    op.drop_column("recurring_tips", "stripe_subscription_id")
