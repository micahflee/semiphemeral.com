import subprocess
import json
from datetime import datetime, timedelta


def main():
    snapshots = json.loads(
        subprocess.check_output(
            ["doctl", "compute", "snapshot", "list", "--output", "json"]
        )
    )

    for snapshot in snapshots:
        now = datetime.utcnow()
        created_at = datetime.strptime(snapshot["created_at"], "%Y-%m-%dT%H:%M:%SZ")
        age = now - created_at
        if snapshot["name"].startswith("db-production-") and age >= timedelta(days=7):
            print(f"Deleting snapshot: {snapshot['name']}, age: {age}")
            subprocess.run(
                ["doctl", "compute", "snapshot", "delete", "--force", snapshot["id"]]
            )


if __name__ == "__main__":
    main()
