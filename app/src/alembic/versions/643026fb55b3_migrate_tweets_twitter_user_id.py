"""migrate tweets.twitter_user_id

Revision ID: 643026fb55b3
Revises: 68436f16dcc1
Create Date: 2021-02-02 11:18:21.008054

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "643026fb55b3"
down_revision = "68436f16dcc1"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "tweets", "twitter_user_id", type_=sa.String, existing_type=sa.BigInteger
    )


def downgrade():
    op.alter_column(
        "tweets", "twitter_user_id", type_=sa.BigInteger, existing_type=sa.String
    )
