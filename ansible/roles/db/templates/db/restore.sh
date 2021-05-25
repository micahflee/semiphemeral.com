#!/bin/bash

FILENAME=/db/$1

echo "== Restore"
psql \
    -h "{{ db_private_ip }}" \
    -p 5432 \
    -U "{{ postgres_user }}" \
    -d "{{ postgres_db }}" \
    -f $FILENAME

echo "== Database restored, deleting backup from server"
rm $FILENAME
