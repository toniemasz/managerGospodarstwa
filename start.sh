#!/usr/bin/env bash

set -euo pipefail

python manage.py migrate
#python manage.py seed_demo_data
python manage.py runserver