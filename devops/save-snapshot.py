import subprocess
import json
import sys
from datetime import datetime


def main():
    volume_name = "db-production"

    # Find the volume ID
    volumes = json.loads(
        subprocess.check_output(
            ["doctl", "compute", "volume", "list", "--output", "json"]
        )
    )

    volume_id = None
    for volume in volumes:
        if volume["name"] == volume_name:
            volume_id = volume["id"]
            break

    if not volume_id:
        print(f"volume with name {volume_name} not found")
        print()
        print(json.dumps(volumes, indent=2))
        sys.exit(-1)

    # Save the snapshot
    snapshot_name = f"db-production-{datetime.utcnow().strftime('%Y-%m-%d_%H%M')}"
    print(f"Saving snapshot: {snapshot_name}")
    print(
        subprocess.check_output(
            [
                "doctl",
                "compute",
                "volume",
                "snapshot",
                volume_id,
                "--snapshot-name",
                snapshot_name,
            ]
        )
    )


if __name__ == "__main__":
    main()
