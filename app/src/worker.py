import socket
import time
import subprocess
import sys
import click


@click.command()
@click.option("--dms", is_flag=True, default=False)
def main(dms):
    # Wait 30s to ensure redis jobs have been flushed
    print("Waiting 30s for jobs to be flushed ...", file=sys.stderr)
    time.sleep(30)

    # Start the worker
    print("Starting worker", file=sys.stderr)
    args = [
        "rq",
        "worker",
        "--url",
        "redis://redis:6379",
        "--with-scheduler",
    ]
    if dms:
        args.append("dm_jobs_high")
        args.append("dm_jobs_low")
    else:
        args.append("jobs")
    subprocess.run(args)


if __name__ == "__main__":
    main()
