import socket
import time
import subprocess
import sys

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
subprocess.run(
    [
        "rq",
        "worker",
        "--url",
        "redis://redis:6379",
        "--with-scheduler",
        "jobs",
    ]
)
