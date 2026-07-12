#!/usr/bin/env bash

set -e

CONTAINER_NAME="manager-postgres-dev"
POSTGRES_IMAGE="postgres:17.6"

cleanup() {
    echo ""
    echo "Zatrzymywanie lokalnego PostgreSQL..."

    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}

trap cleanup EXIT INT TERM

if ! command -v docker >/dev/null 2>&1; then
    echo "Błąd: Docker nie jest zainstalowany albo nie jest dostępny w PATH."
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Błąd: Docker Desktop nie jest uruchomiony."
    exit 1
fi

# Usuwa pozostałość po wcześniejszym, niepoprawnie zakończonym uruchomieniu.
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

echo "Uruchamianie PostgreSQL 17.6..."

docker run \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_DB=manager_dev \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -p 5432:5432 \
    -v manager-postgres-dev-data:/var/lib/postgresql/data \
    -d \
    "$POSTGRES_IMAGE"

echo "Oczekiwanie na PostgreSQL..."

until docker exec "$CONTAINER_NAME" \
    pg_isready \
    -U postgres \
    -d manager_dev >/dev/null 2>&1
do
    sleep 1
done

echo "PostgreSQL jest gotowy."

export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/manager_dev"

echo "Wykonywanie migracji..."
python manage.py migrate


python manage.py seed_demo_data

echo "Uruchamianie Django..."
python manage.py runserver