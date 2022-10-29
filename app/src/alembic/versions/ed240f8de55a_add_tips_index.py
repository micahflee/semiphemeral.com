"""add tips index

Revision ID: ed240f8de55a
Revises: cc8c59b6b463
Create Date: 2022-10-29 12:01:19.515913

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ed240f8de55a"
down_revision = "cc8c59b6b463"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("tips_id_idx", "tips", ["id"])
    op.create_index("tips_user_id_idx", "tips", ["user_id"])
    op.create_index("tips_paid_idx", "tips", ["paid"])
    op.create_index("tips_refunded_idx", "tips", ["refunded"])
    op.create_index("tips_timestamp_idx", "tips", ["timestamp"])
    op.create_index("recurring_tips_id_idx", "recurring_tips", ["id"])
    op.create_index("recurring_tips_user_id_idx", "recurring_tips", ["user_id"])
    op.create_index(
        "recurring_tips_stripe_checkout_session_id_idx",
        "recurring_tips",
        ["stripe_checkout_session_id"],
    )
    op.create_index(
        "recurring_tips_stripe_customer_id_idx",
        "recurring_tips",
        ["stripe_customer_id"],
    )
    op.create_index("recurring_tips_status_idx", "recurring_tips", ["status"])
    op.create_index("recurring_tips_timestamp_idx", "recurring_tips", ["timestamp"])


def downgrade():
    op.drop_index("tips_id_idx")
    op.drop_index("tips_user_id_idx")
    op.drop_index("tips_paid_idx")
    op.drop_index("tips_refunded_idx")
    op.drop_index("tips_timestamp_idx")
    op.drop_index("recurring_tips_id_idx")
    op.drop_index("recurring_tips_user_id_idx")
    op.drop_index("recurring_tips_stripe_checkout_session_id_idx")
    op.drop_index("recurring_tips_stripe_customer_id_idx")
    op.drop_index("recurring_tips_status_idx")
    op.drop_index("recurring_tips_timestamp_idx")
