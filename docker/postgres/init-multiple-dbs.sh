#!/usr/bin/env sh
set -eu

if [ -z "${POSTGRES_MULTIPLE_DATABASES:-}" ]; then
  exit 0
fi

echo "Creating multiple databases: $POSTGRES_MULTIPLE_DATABASES"

for db in $(echo "$POSTGRES_MULTIPLE_DATABASES" | tr ',' ' '); do
  db="$(echo "$db" | xargs || true)"
  if [ -n "$db" ]; then
    echo "  - creating database: $db"
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<SQL
CREATE DATABASE "$db";
SQL
  fi
done

