import asyncio
import jobs

funcs = None


def fetch(job_details_id):
    global funcs
    asyncio.run(jobs.fetch(job_details_id, funcs))


def delete(job_details_id):
    global funcs
    asyncio.run(jobs.fetch(job_details_id, funcs, disconnect=False))
    asyncio.run(jobs.delete(job_details_id, funcs))


def delete_dms(job_details_id):
    global funcs
    asyncio.run(jobs.delete_dms(job_details_id, funcs))


def delete_dm_groups(job_details_id):
    global funcs
    asyncio.run(jobs.delete_dm_groups(job_details_id, funcs))


def block(job_details_id):
    global funcs
    asyncio.run(jobs.block(job_details_id, funcs))


def unblock(job_details_id):
    global funcs
    asyncio.run(jobs.unblock(job_details_id, funcs))


def dm(job_details_id):
    global funcs
    asyncio.run(jobs.dm(job_details_id, funcs))


funcs = {
    "fetch": fetch,
    "delete": delete,
    "delete_dms": delete_dms,
    "delete_dm_groups": delete_dm_groups,
    "block": block,
    "unblock": unblock,
    "dm": dm,
}
