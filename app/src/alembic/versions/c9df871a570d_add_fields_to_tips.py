"""add fields to tips

Revision ID: c9df871a570d
Revises: b4659e7f1af9
Create Date: 2021-04-18 19:17:52.689938

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9df871a570d"
down_revision = "b4659e7f1af9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tips", sa.Column("payment_processor", sa.String, default="stripe"))
    op.add_column("tips", sa.Column("stripe_payment_intent", sa.String))
    op.alter_column("tips", "charge_id", new_column_name="stripe_charge_id")
    op.create_index("tips_stripe_charge_id_idx", "tips", ["stripe_charge_id"])
    op.create_index("tips_stripe_payment_intent_idx", "tips", ["stripe_payment_intent"])


def downgrade():
    op.drop_column("tips", "payment_processor")
    op.drop_column("tips", "stripe_payment_intent")
    op.alter_column("tips", "stripe_charge_id", new_column_name="charge_id")
    op.drop_index("tips_stripe_charge_id_idx")
    op.drop_index("tips_stripe_payment_intent_idx")
