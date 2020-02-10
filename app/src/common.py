import os
import asyncio
import functools
import tweepy


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
