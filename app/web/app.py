#!/usr/bin/env python3
import os
import base64
import tweepy
import logging
import asyncio
import subprocess

from aiohttp import web
from aiohttp_session import setup, get_session, new_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage

import jinja2
import aiohttp_jinja2

from aiopg.sa import create_engine


from db import connect_db, db, User


async def _twitter_api(user):
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
    )
    auth.set_access_token(user.twitter_access_token, user.twitter_access_token_secret)
    api = tweepy.API(auth)
    return api


async def _logged_in_user(session):
    """
    Return the currently logged in user
    """
    if "twitter_id" in session:
        # Get the user
        user = await User.query.where(
            User.twitter_id == session["twitter_id"]
        ).gino.first()

        # Get the twitter API for the user, and make sure it works
        try:
            api = await _twitter_api(user)
            api.me()
            return user
        except:
            return None
    return None


def authentication_required_401(func):
    async def wrapper(request):
        session = await get_session(request)
        user = await _logged_in_user(session)
        if not user:
            raise web.HTTPUnauthorized(text="Authentication required")
        return await func(request)

    return wrapper


def authentication_required_302(func):
    async def wrapper(request):
        session = await get_session(request)
        user = await _logged_in_user(session)
        if not user:
            raise web.HTTPFound(location="/")
        return await func(request)

    return wrapper


async def auth_login(request):
    session = await new_session(request)
    user = await _logged_in_user(session)
    if user:
        # If we're already logged in, redirect
        auth = tweepy.OAuthHandler(
            os.environ.get("TWITTER_CONSUMER_TOKEN"),
            os.environ.get("TWITTER_CONSUMER_KEY"),
        )
        auth.set_access_token(
            user.twitter_access_token, user.twitter_access_token_secret
        )
        api = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)

        # Validate user
        twitter_user = api.me()
        if session["twitter_id"] == twitter_user.id:
            raise web.HTTPFound("/app")

    # Otherwise, authorize with Twitter
    try:
        auth = tweepy.OAuthHandler(
            os.environ.get("TWITTER_CONSUMER_TOKEN"),
            os.environ.get("TWITTER_CONSUMER_KEY"),
        )
        redirect_url = auth.get_authorization_url()
        raise web.HTTPFound(location=redirect_url)
    except tweepy.TweepError:
        raise web.HTTPUnauthorized(
            text="Error, failed to get request token from Twitter"
        )


async def auth_logout(request):
    session = await get_session(request)
    del session["twitter_id"]
    raise web.HTTPFound(location="/")


async def auth_twitter_callback(request):
    params = request.rel_url.query
    if "denied" in params:
        raise web.HTTPFound(location="/")

    if "oauth_token" not in params or "oauth_verifier" not in params:
        raise web.HTTPUnauthorized(
            text="Error, oauth_token and oauth_verifier are required"
        )

    oauth_token = params["oauth_token"]
    verifier = params["oauth_verifier"]

    # Authenticate with twitter
    session = await get_session(request)
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
    )
    auth.request_token = {
        "oauth_token": oauth_token,
        "oauth_token_secret": verifier,
    }

    try:
        auth.get_access_token(verifier)
    except tweepy.TweepError:
        raise web.HTTPUnauthorized(text="Error, failed to get access token")

    try:
        api = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)
        twitter_user = api.me()
    except tweepy.TweepError:
        raise web.HTTPUnauthorized(text="Error, error using Twitter API")

    # Save values in the session
    session["twitter_id"] = twitter_user.id_str

    # Does this user already exist?
    user = await User.query.where(User.twitter_id == twitter_user.id_str).gino.first()
    if user is None:
        # Create a new user
        user = await User.create(
            twitter_id=twitter_user.id_str,
            twitter_screen_name=twitter_user.screen_name,
            twitter_access_token=auth.access_token,
            twitter_access_token_secret=auth.access_token_secret,
        )

    # Redirect to app
    raise web.HTTPFound(location="/app")


@authentication_required_401
async def api_get_user(request):
    """
    If there's a currently logged in user, respond with information about it
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    api = await _twitter_api(user)
    twitter_user = api.me()

    return web.json_response(
        {
            "user": {
                "twitter_id": user.twitter_id,
                "twitter_screen_name": user.twitter_screen_name,
                "profile_image_url": twitter_user.profile_image_url_https,
            },
            "settings": {
                "delete_tweets": user.delete_tweets,
                "tweets_days_threshold": user.tweets_days_threshold,
                "tweets_retweet_threshold": user.tweets_retweet_threshold,
                "tweets_like_threshold": user.tweets_like_threshold,
                "tweets_threads_threshold": user.tweets_threads_threshold,
                "retweets_likes": user.retweets_likes,
                "retweets_likes_delete_retweets": user.retweets_likes_delete_retweets,
                "retweets_likes_retweets_threshold": user.retweets_likes_retweets_threshold,
                "retweets_likes_delete_likes": user.retweets_likes_delete_likes,
                "retweets_likes_likes_threshold": user.retweets_likes_likes_threshold,
            },
            "last_fetch": user.last_fetch,
        }
    )


@authentication_required_401
async def api_settings(request):
    """
    Update the settings for the currently-logged in user
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    data = await request.json()

    # Validate
    expected_fields = {
        "delete_tweets": bool,
        "tweets_days_threshold": int,
        "tweets_retweet_threshold": int,
        "tweets_like_threshold": int,
        "tweets_threads_threshold": bool,
        "retweets_likes": bool,
        "retweets_likes_delete_retweets": bool,
        "retweets_likes_retweets_threshold": int,
        "retweets_likes_delete_likes": bool,
        "retweets_likes_likes_threshold": int,
    }
    for field in expected_fields:
        if field not in data:
            raise web.HTTPBadRequest(text=f"Missing field: {field}")
        if type(data[field]) != expected_fields[field]:
            raise web.HTTPBadRequest(
                text=f"Invalid type: {field} should be {expected_fields[field]}, not {type(data[field])}"
            )

    # Update settings in the database
    await user.update(
        delete_tweets=data["delete_tweets"],
        tweets_days_threshold=data["tweets_days_threshold"],
        tweets_retweet_threshold=data["tweets_retweet_threshold"],
        tweets_like_threshold=data["tweets_like_threshold"],
        tweets_threads_threshold=data["tweets_threads_threshold"],
        retweets_likes=data["retweets_likes"],
        retweets_likes_delete_retweets=data["retweets_likes_delete_retweets"],
        retweets_likes_retweets_threshold=data["retweets_likes_retweets_threshold"],
        retweets_likes_delete_likes=data["retweets_likes_delete_likes"],
        retweets_likes_likes_threshold=data["retweets_likes_likes_threshold"],
    ).apply()

    return web.json_response(True)


@aiohttp_jinja2.template("index.jinja2")
async def index(request):
    session = await get_session(request)
    user = await _logged_in_user(session)
    logged_in = user is not None
    return {"logged_in": logged_in}


@aiohttp_jinja2.template("app.jinja2")
@authentication_required_302
async def app_main(request):
    return {"deploy_environment": os.environ.get("DEPLOY_ENVIRONMENT")}


async def app_factory():
    # connect to the database
    await connect_db()

    # create the web app
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("templates"))
    logging.basicConfig(filename="/var/web/web.log", level=logging.DEBUG)

    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = os.environ.get("COOKIE_FERNET_KEY")
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))

    # Define routes
    app.add_routes(
        [
            # Static files
            web.static("/static", "static"),
            # Authentication
            web.get("/auth/login", auth_login),
            web.get("/auth/logout", auth_logout),
            web.get("/auth/twitter_callback", auth_twitter_callback),
            # API
            web.get("/api/get_user", api_get_user),
            web.post("/api/settings", api_settings),
            # Web
            web.get("/", index),
            web.get("/app", app_main),
        ]
    )

    return app


if __name__ == "__main__":
    # Start with database migrations
    subprocess.run(["alembic", "upgrade", "head"])

    web.run_app(app_factory())
