#!/usr/bin/env python3
import os
import base64
import tweepy
import logging
import asyncio
import subprocess

from cryptography import fernet
from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage

import jinja2
import aiohttp_jinja2

from aiopg.sa import create_engine


from db import connect_db, db, User


async def _logged_in_user(session):
    """
    Return the currently logged in user
    """
    if "twitter_id" in session:
        # Get the user
        user = await User.query.where(
            User.twitter_id == session["twitter_id"]
        ).gino.first()
        return user

    return None


async def authentication_required(func):
    def wrapper(*args, **kwargs):
        session = await get_session(request)
        user = await _logged_in_user(session)
        if not user:
            raise web.HTTPFound(location="/")
        return await func(*args, **kwargs)

    return wrapper


async def auth_login(request):
    session = await get_session(request)
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
        session["oauth_token"] = auth.request_token["oauth_token"]
        raise web.HTTPFound(location=redirect_url)
    except tweepy.TweepError:
        raise web.HTTPUnauthorized(
            text="Error, failed to get request token from Twitter"
        )


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
    session["twitter_id"] = twitter_user.id

    # Does this user already exist?
    user = await User.query.where(User.twitter_id == twitter_user.id).gino.first()
    if user is None:
        # Create a new user
        user = await User.create(
            twitter_id=twitter_user.id,
            twitter_screen_name=twitter_user.screen_name,
            twitter_access_token=auth.access_token,
            twitter_access_token_secret=auth.access_token_secret,
        )

    # Redirect to app
    raise web.HTTPFound(location="/app")


async def auth_current_user(request):
    """
    If there's a currently logged in user, respond with information about it
    """
    session = await get_session(request)
    user = await _logged_in_user(session)

    if user:
        return web.json_response(
            {
                "current_user": {
                    "twitter_id": user.twitter_id,
                    "twitter_screen_name": user.twitter_screen_name,
                }
            }
        )
    else:
        return web.json_response({"current_user": None})


@aiohttp_jinja2.template("index.jinja2")
async def index(request):
    return {}


@aiohttp_jinja2.template("app.jinja2")
@authentication_required
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
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))

    # Define routes
    app.add_routes(
        [
            # Static files
            web.static("/static", "static"),
            # Authentication
            web.get("/auth/login", auth_login),
            web.get("/auth/twitter_callback", auth_twitter_callback),
            web.get("/auth/current_user", auth_current_user),
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
