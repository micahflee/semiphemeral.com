#!/usr/bin/env python3
import os
import tweepy
import asyncio
from aiohttp import web


async def handle(request):
    name = request.match_info.get("name", "Anonymous")
    text = "Hello, " + name
    return web.Response(text=text)


def main():
    # Initialize tweepy
    auth = tweepy.OAuthHandler(
        os.environ.get("TWITTER_CONSUMER_TOKEN"),
        os.environ.get("TWITTER_CONSUMER_KEY"),
    )
    auth.set_access_token(
        os.environ.get("TWITTER_ACCESS_TOKEN"), os.environ.get("TWITTER_ACCESS_KEY")
    )
    api = tweepy.API(auth, wait_on_rate_limit=True, wait_on_rate_limit_notify=True)

    # Start the web app
    app = web.Application()
    app.add_routes([web.get("/", handle), web.get("/{name}", handle)])
    web.run_app(app)


if __name__ == "__main__":
    main()
