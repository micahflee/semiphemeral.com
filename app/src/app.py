#!/usr/bin/env python3
import asyncio

from db import connect_db
from web import start_web_server


async def main():
    print("Connecting to the database")
    await connect_db()
    await start_web_server()


if __name__ == "__main__":
    asyncio.run(main())
