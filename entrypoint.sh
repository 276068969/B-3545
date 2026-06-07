#!/bin/sh

echo "=== Mahjong Score Tracker Starting ==="

echo "Creating migrations..."
python manage.py makemigrations --noinput

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Initializing default data..."
python manage.py init_data

echo "Starting Gunicorn server..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
