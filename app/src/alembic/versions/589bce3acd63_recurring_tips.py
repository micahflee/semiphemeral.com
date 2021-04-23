"""recurring tips

Revision ID: 589bce3acd63
Revises: c9df871a570d
Create Date: 2021-04-23 18:55:39.292308

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "589bce3acd63"
down_revision = "c9df871a570d"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recurring_tips",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("payment_processor", sa.String),
        sa.Column("stripe_checkout_session_id", sa.String),
        sa.Column("stripe_customer_id", sa.String),
        sa.Column("status", sa.String),
        sa.Column("amount", sa.Float),
        sa.Column("timestamp", sa.DateTime),
    )
    op.add_column("tips", sa.Column("recurring_tip_id", sa.Integer))


def downgrade():
    op.drop_table("recurring_tips")
    op.drop_column("tips", "recurring_tip_id")
