import os
import asyncio
import functools
import tweepy
from datetime import datetime, timedelta

from db import Tweet, Thread


class TwitterRateLimit(Exception):
    pass


async def twitter_api_call(api, method, **kwargs):
    """
    Wrapper around Twitter API to support asyncio for all API calls. See:
    https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.run_in_executor
    https://docs.python.org/3/library/asyncio-eventloop.html#asyncio-pass-keywords
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, functools.partial(getattr(api, method), **kwargs)
    )
    return result


async def twitter_api(user):
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
    )
    auth.set_access_token(user.twitter_access_token, user.twitter_access_token_secret)
    api = tweepy.API(auth)
    return api


async def twitter_dm_api():
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_DM_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_DM_CONSUMER_KEY"),
    )
    auth.set_access_token(
        os.environ.get("TWITTER_DM_ACCESS_TOKEN"),
        os.environ.get("TWITTER_DM_ACCESS_KEY"),
    )
    api = tweepy.API(auth)
    return api


async def tweets_to_delete(user):
    """
    Return the tweets that are staged for deletion for this user
    """
    datetime_threshold = datetime.utcnow() - timedelta(days=user.tweets_days_threshold)

    # Select tweets from threads to exclude
    tweets_to_exclude = []
    threads = (
        await Thread.query.where(Thread.user_id == user.id)
        .where(Thread.should_exclude == True)
        .gino.all()
    )
    for thread in threads:
        for tweet in (
            await Tweet.query.where(Tweet.user_id == user.id)
            .where(Tweet.thread_id == thread.id)
            .where(Tweet.is_deleted == False)
            .order_by(Tweet.created_at)
            .gino.all()
        ):
            tweets_to_exclude.append(tweet.status_id)

    # Select tweets that we will delete
    tweets_to_delete = []
    for tweet in (
        await Tweet.query.where(Tweet.user_id == user.id)
        .where(Tweet.twitter_user_id == user.twitter_id)
        .where(Tweet.is_deleted == False)
        .where(Tweet.is_retweet == False)
        .where(Tweet.created_at < datetime_threshold)
        .where(Tweet.retweet_count < user.tweets_retweet_threshold)
        .where(Tweet.favorite_count < user.tweets_like_threshold)
        .order_by(Tweet.created_at)
        .gino.all()
    ):
        if tweet.status_id not in tweets_to_exclude:
            tweets_to_delete.append(tweet)

    return tweets_to_delete
