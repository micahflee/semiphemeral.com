import socket
import time
import subprocess
import sys
import click


@click.command()
@click.option("--dms", is_flag=True, default=False)
def main(dms):
    # Wait for monitor port to be open
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("monitor", 9181))
            break
        except:
            print("Waiting for monitor to finish initializing...", file=sys.stderr)
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
    pass
