"""create indices

Revision ID: 4930a8e7628f
Revises: 8256552bd767
Create Date: 2020-07-17 17:30:00.079275

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4930a8e7628f"
down_revision = "8256552bd767"
branch_labels = None
depends_on = None


def upgrade():
    # (1.38s) UPDATE tweets SET thread_id=$1 WHERE tweets.id = $2 RETURNING tweets.thread_id
    # (40.66s) SELECT tweets.* FROM tweets WHERE tweets.user_id = $1 AND tweets.status_id = $2
    # (27.32s) SELECT tweets.* FROM tweets WHERE tweets.user_id = $1 AND tweets.twitter_user_id = $2 AND tweets.status_id = $3
    # (19.39s) SELECT tweets.* FROM tweets WHERE tweets.thread_id IS NULL AND tweets.user_id = $1 AND tweets.twitter_user_id = $2 AND tweets.is_deleted = $6 AND tweets.is_retweet = $7 AND tweets.created_at < $3 AND tweets.retweet_count < $4 AND tweets.favorite_count < $5
    # (29.11s) SELECT tweets.* FROM tweets WHERE tweets.user_id = $1 ORDER BY tweets.status_id DESC
    # (43.75s) SELECT tweets.* FROM tweets WHERE tweets.user_id = $1 AND tweets.favorited = $3 AND tweets.is_fascist = $4 AND tweets.created_at > $2
    # (35.07s) SELECT tweets.* FROM tweets JOIN threads ON threads.id = tweets.thread_id WHERE tweets.user_id = $1 AND tweets.twitter_user_id = $2 AND tweets.is_deleted = $6 AND tweets.is_retweet = $7 AND tweets.created_at < $3 AND tweets.retweet_count < $4 AND tweets.favorite_count < $5 AND threads.should_exclude = $8 AND tweets.exclude_from_delete = $9
    # (36.97s) SELECT tweets.* FROM tweets WHERE tweets.user_id = $1 AND tweets.twitter_user_id = $2 AND tweets.is_deleted = $4 AND tweets.is_retweet = $5 AND tweets.created_at < $3 ORDER BY tweets.created_at
    # (30.14s) SELECT tweets.* FROM tweets WHERE tweets.user_id = $1 AND tweets.twitter_user_id != $2 AND tweets.is_unliked = $4 AND tweets.favorited = $5 AND tweets.created_at < $3 ORDER BY tweets.created_at
    # (43.13s) SELECT tweets.* FROM tweets WHERE tweets.user_id = $1 AND tweets.is_fascist = $2 ORDER BY tweets.created_at DESC
    # (7.73s) DELETE FROM tweets WHERE tweets.user_id = $1
    op.create_index("tweets_id_idx", "tweets", ["id"])
    op.create_index("tweets_user_id_idx", "tweets", ["user_id"])
    op.create_index("tweets_twitter_user_id_idx", "tweets", ["twitter_user_id"])
    op.create_index("tweets_status_id_idx", "tweets", ["status_id"])
    op.create_index("tweets_thread_id_idx", "tweets", ["thread_id"])
    op.create_index("tweets_favorited_idx", "tweets", ["favorited"])
    op.create_index("tweets_retweeted_idx", "tweets", ["retweeted"])
    op.create_index("tweets_is_deleted_idx", "tweets", ["is_deleted"])
    op.create_index("tweets_is_retweet_idx", "tweets", ["is_retweet"])
    op.create_index("tweets_is_unliked_idx", "tweets", ["is_unliked"])
    op.create_index("tweets_is_fascist_idx", "tweets", ["is_fascist"])
    op.create_index("tweets_exclude_from_delete_idx", "tweets", ["exclude_from_delete"])

    # (1.28s) UPDATE jobs SET progress=$1 WHERE jobs.id = $2 RETURNING jobs.progress
    op.create_index("jobs_id_idx", "jobs", ["id"])

    # (1.77s) SELECT jobs.* FROM jobs WHERE jobs.user_id = $1 AND jobs.job_type = $2 AND jobs.status = $3
    op.create_index(
        "jobs_user_id_job_type_status_idx", "jobs", ["user_id", "job_type", "status"]
    )

    # (2.90s) SELECT threads.id, threads.user_id, threads.root_status_id, threads.should_exclude FROM threads WHERE threads.user_id = $1 AND threads.root_status_id = $2
    op.create_index("threads_id_idx", "threads", ["id"])

    # (4.88s) UPDATE threads SET should_exclude=$1 WHERE threads.user_id = $2
    # (44.33s) SELECT threads.* FROM threads JOIN tweets ON threads.id = tweets.thread_id WHERE threads.id = tweets.thread_id AND threads.user_id = $1 AND tweets.user_id = $2 AND tweets.is_deleted = $5 AND tweets.is_retweet = $6 AND tweets.retweet_count >= $3 AND tweets.favorite_count >= $4
    # (1.29s) DELETE FROM threads WHERE threads.user_id = $1
    op.create_index("threads_user_id_idx", "threads", ["user_id"])

    # (6.52s) SELECT tweets.* FROM tweets JOIN threads ON threads.id = tweets.thread_id WHERE tweets.user_id = $1 AND tweets.twitter_user_id = $2 AND tweets.is_deleted = $6 AND tweets.is_retweet = $7 AND tweets.created_at < $3 AND tweets.retweet_count < $4 AND tweets.favorite_count < $5 AND threads.should_exclude = $8
    op.create_index("threads_should_exclude_idx", "threads", ["should_exclude"])

    # (1.21s) UPDATE direct_message_jobs SET status=$1, sent_timestamp=$2 WHERE direct_message_jobs.id = $3 RETURNING direct_message_jobs.status, direct_message_jobs.sent_timestamp
    op.create_index("direct_message_jobs_id_idx", "direct_message_jobs", ["id"])


def downgrade():
    op.drop_index("tweets_id_idx")
    op.drop_index("tweets_user_id_idx")
    op.drop_index("tweets_twitter_user_id_idx")
    op.drop_index("tweets_status_id_idx")
    op.drop_index("tweets_thread_id_idx")
    op.drop_index("tweets_favorited_idx")
    op.drop_index("tweets_retweeted_idx")
    op.drop_index("tweets_is_deleted_idx")
    op.drop_index("tweets_is_retweet_idx")
    op.drop_index("tweets_is_unliked_idx")
    op.drop_index("tweets_is_fascist_idx")
    op.drop_index("tweets_exclude_from_delete_idx")
    op.drop_index("jobs_id_idx")
    op.drop_index("jobs_user_id_job_type_status_idx")
    op.drop_index("threads_id_idx")
    op.drop_index("threads_user_id_idx")
    op.drop_index("threads_should_exclude_idx")
    op.drop_index("direct_message_jobs_id_idx")
