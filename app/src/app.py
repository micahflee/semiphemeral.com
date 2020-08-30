#!/usr/bin/env python3
import os
import subprocess
import asyncio

from db import connect_db
from web import start_web_server
from jobs import start_jobs, start_dm_jobs


async def main():
    # Run database migrations
    print("Running database migrations")
    subprocess.run(["alembic", "upgrade", "head"])

    # Connect to the database
    print("Connecting to the database")
    await connect_db()

    # Start
    if os.environ.get("SEMIPHEMERAL_WEB") == "1":
        await start_web_server()
    elif os.environ.get("SEMIPHEMERAL_JOBS") == "1":
        await start_jobs()
    elif os.environ.get("SEMIPHEMERAL_DM_JOBS") == "1":
        await start_dm_jobs()


if __name__ == "__main__":
    asyncio.run(main())
