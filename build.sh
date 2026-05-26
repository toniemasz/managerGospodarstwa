#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

python manage.py migrate

if [ "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --noinput || echo "Superużytkownik już istnieje lub pominięto tworzenie."
fi

python manage.py collectstatic --noinput