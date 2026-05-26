#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# ZMUSZAMY RANGERA DO WYGENEROWANIA SCHEMATU TABEL DLA TWOJEJ APLIKACJI
python manage.py makemigrations sows
python manage.py makemigrations

# Uruchomienie migracji tabel do bazy Supabase
python manage.py migrate

if [ "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --noinput || echo "Superużytkownik już istnieje lub pominięto tworzenie."
fi

# Zbieranie plików CSS i JS
python manage.py collectstatic --noinputput