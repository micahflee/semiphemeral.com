#!/bin/bash

TIMESTAMP=$(date +%F_%T)
FILENAME=/opt/semiphemeral/semiphemeral-{{ deploy_environment }}-$TIMESTAMP.tar.gz

echo "== Compressing" &&
tar -czvf "$FILENAME" /opt/semiphemeral/data/redis/ &&

echo "== Finished" &&
echo "$FILENAME"
