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


async def login(request):
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
            raise web.HTTPFound(
                location=f"https://{os.environ.get('FRONTEND_DOMAIN')}/app"
            )

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


async def twitter_auth(request):
    params = request.rel_url.query
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
    raise web.HTTPFound(location=f"https://{os.environ.get('FRONTEND_DOMAIN')}/app")


async def current_user(request):
    """
    If there's a currently logged in user, respond with information about it
    """
    session = await get_session(request)
    user = await _logged_in_user(session)
    print(user)

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


async def app_factory():
    # connect to the database
    await connect_db()

    # create the web app
    app = web.Application()
    logging.basicConfig(filename="/var/backend/backend.log", level=logging.DEBUG)

    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))

    # Define routes
    app.add_routes(
        [
            web.get("/login", login),
            web.get("/twitter_auth", twitter_auth),
            web.get("/current_user", current_user),
        ]
    )

    return app


if __name__ == "__main__":
    # Start with database migrations
    subprocess.run(["alembic", "upgrade", "head"])

    web.run_app(app_factory())
