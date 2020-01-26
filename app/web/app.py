#!/usr/bin/env python3
import os
import subprocess
import asyncio
import stripe

from db import connect_db
from web import start_web_server
from twitter import start_jobs


async def main():
    # Run database migrations
    subprocess.run(["alembic", "upgrade", "head"])

    # Init stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

    # Connect to the database
    await connect_db()

    # Start
    await asyncio.gather(start_web_server(), start_jobs())


if __name__ == "__main__":
    asyncio.run(main())
