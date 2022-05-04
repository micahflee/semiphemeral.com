#!/bin/bash

TARBALL_FILENAME=/opt/semiphemeral/$1

echo "== Decompressing" &&
tar -xzfv "$TARBALL_FILENAME" -C / &&

echo "== Database restored, deleting backup from server" &&
rm "$FILENAME"
