#!/usr/bin/env python3
import os
import base64
import tweepy
import logging
import asyncio

from cryptography import fernet
from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from aiopg.sa import create_engine


async def connect_db():
    database = os.environ.get("POSTGRES_DB")
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")

    async with create_engine(
        user=user, database=database, host="db", password=password
    ) as engine:
        async with engine.acquire() as conn:
            return conn


async def login(request):
    session = await get_session(request)
    if (
        "access_token" in session
        and "access_token_secret" in session
        and "user_id" in session
        and "user_screen_name" in session
    ):
        # If we're already logged in, redirect
        try:
            auth = tweepy.OAuthHandler(
                os.environ.get("TWITTER_CONSUMER_TOKEN"),
                os.environ.get("TWITTER_CONSUMER_KEY"),
            )
            auth.set_access_token(
                session["access_token"], session["access_token_secret"]
            )
            api = tweepy.API(
                auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True
            )

            # Validate user
            user = api.me()
            if (
                session["user_id"] == user.id
                and session["user_screen_name"] == user.screen_name
            ):
                raise web.HTTPFound(
                    location=f"https://{os.environ.get('FRONTEND_DOMAIN')}/app"
                )
        except:
            # Not actually logged in
            pass

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
        user = api.me()
    except tweepy.TweepError:
        raise web.HTTPUnauthorized(text="Error, error using Twitter API")

    # Save values in the session
    session["user_id"] = user.id
    session["user_screen_name"] = user.screen_name
    session["access_token"] = auth.access_token
    session["access_token_secret"] = auth.access_token_secret

    # Redirect to app
    raise web.HTTPFound(location=f"https://{os.environ.get('FRONTEND_DOMAIN')}/app")


async def app_factory():
    conn = await connect_db()

    app = web.Application()
    logging.basicConfig(filename="/var/backend/backend.log", level=logging.DEBUG)

    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))

    # Define routes
    app.add_routes(
        [web.get("/login", login), web.get("/twitter_auth", twitter_auth),]
    )

    return app


if __name__ == "__main__":
    web.run_app(app_factory())

