import time
import sys
import click

from rq import Worker
from common import conn as redis_conn, jobs_q, dm_jobs_high_q, dm_jobs_low_q


@click.command()
@click.option("--dms", is_flag=True, default=False)
def main(dms):
    # Wait 30s to ensure redis jobs have been flushed
    print("Waiting 30s for jobs to be flushed ...", file=sys.stderr)
    time.sleep(30)

    if dms:
        queues = [dm_jobs_high_q, dm_jobs_low_q]
    else:
        queues = [jobs_q]

    # Start the worker
    print("Starting worker", file=sys.stderr)
    worker = Worker(queues, connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
