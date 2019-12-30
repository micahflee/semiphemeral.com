#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER semiphemeral;
    CREATE DATABASE semiphemeral;
    GRANT ALL PRIVILEGES ON DATABASE semiphemeral TO semiphemeral;
EOSQL