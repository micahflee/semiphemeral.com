#!/usr/bin/env python3
import os
import base64
import tweepy
import asyncio
import logging
from cryptography import fernet
from aiohttp import web
from aiohttp_session import setup, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage


async def login(request):
    session = await get_session(request)
    if "api" in session:
        # If we're already logged in, redirect
        try:
            session["api"].me()
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
    session["auth"] = tweepy.OAuthHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
    )
    session["auth"].request_token = {
        "oauth_token": oauth_token,
        "oauth_token_secret": verifier,
    }

    try:
        session["auth"].get_access_token(verifier)
    except tweepy.TweepError:
        raise web.HTTPUnauthorized(text="Error, failed to get access token")

    session["api"] = tweepy.API(
        session["auth"], wait_on_rate_limit=True, wait_on_rate_limit_notify=True
    )

    # Redirect to app
    raise web.HTTPFound(location=f"https://{os.environ.get('FRONTEND_DOMAIN')}/app")


def main():
    app = web.Application()
    logging.basicConfig(filename="/var/backend/backend.log", level=logging.DEBUG)

    # Enable the debug toolbar in staging
    if os.environ.get("DEPLOY_ENVIRONMENT") == "staging":
        import aiohttp_debugtoolbar
        from aiohttp_debugtoolbar import toolbar_middleware_factory

        aiohttp_debugtoolbar.setup(app)

    # secret_key must be 32 url-safe base64-encoded bytes
    fernet_key = fernet.Fernet.generate_key()
    secret_key = base64.urlsafe_b64decode(fernet_key)
    setup(app, EncryptedCookieStorage(secret_key))

    # Define routes
    app.add_routes(
        [web.get("/login", login), web.get("/twitter_auth", twitter_auth),]
    )
    web.run_app(app)


if __name__ == "__main__":
    main()
