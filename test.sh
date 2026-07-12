#!/usr/bin/env bash

set -e

CONTAINER_NAME="manager-postgres-test"
POSTGRES_IMAGE="postgres:17.6"

cleanup() {
    echo ""
    echo "Zatrzymywanie testowego PostgreSQL..."
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

cleanup

echo "Uruchamianie PostgreSQL 17.6..."

docker run \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_DB=manager_ci \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -p 5432:5432 \
    -d \
    "$POSTGRES_IMAGE"

echo "Oczekiwanie na PostgreSQL..."

until docker exec "$CONTAINER_NAME" \
    pg_isready -U postgres -d manager_ci >/dev/null 2>&1
do
    sleep 1
done

echo "PostgreSQL gotowy."

export TEST_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/manager_ci"

echo "Uruchamianie testów..."

pytest "$@"