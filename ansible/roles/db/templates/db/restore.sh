#!/bin/bash

GZ_FILENAME=/db/$1
FILENAME=$(echo $GZ_FILENAME | cut -d"." -f1-2)

echo "== Decompressing" &&
gunzip "$GZ_FILENAME" &&

echo "== Restore" &&
psql \
    -h "{{ db_private_ip }}" \
    -p 5432 \
    -U "{{ postgres_user }}" \
    -d "{{ postgres_db }}" \
    -f "$FILENAME" &&

echo "== Database restored, deleting backup from server" && 
rm "$FILENAME"
