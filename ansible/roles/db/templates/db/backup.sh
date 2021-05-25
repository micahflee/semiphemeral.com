#!/bin/bash

TIMESTAMP=$(date +%F_%T)
FILENAME=/db/semiphemeral-{{ deploy_environment }}-$TIMESTAMP.sql

echo "== Dumping"
pg_dump \
    --clean \
    --if-exists \
    -h "{{ db_private_ip }}" \
    -p 5432 \
    -U "{{ postgres_user }}" \
    "{{ postgres_db }}" \
    -f $FILENAME

echo "== Compressing"
gzip $FILENAME

echo "== Finished"
echo "${FILENAME}.gz"
