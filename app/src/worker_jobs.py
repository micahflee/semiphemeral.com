import asyncio
import sys
import jobs

# Long twitter threads need big recursion limits
sys.setrecursionlimit(5000)


def fetch(job_details_id):
    asyncio.run(jobs.fetch(job_details_id, block, dm))


def delete(job_details_id):
    asyncio.run(jobs.delete(job_details_id, delete, dm))


def delete_dms(job_details_id):
    asyncio.run(jobs.delete_dms(job_details_id, dm))


def delete_dm_groups(job_details_id):
    asyncio.run(jobs.delete_dm_groups(job_details_id, dm))


def block(job_details_id):
    asyncio.run(jobs.block(job_details_id, unblock, dm))


def unblock(job_details_id):
    asyncio.run(jobs.unblock(job_details_id))


def dm(job_details_id):
    asyncio.run(jobs.dm(job_details_id))
