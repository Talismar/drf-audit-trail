#!/bin/bash

python manage.py migrate
python manage.py migrate --database=audit_trail

python manage.py collectstatic --noinput

echo "Criando superusuário..."
python manage.py shell <<EOF
from django.contrib.auth.models import User
import os

username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'password')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')

if not User.objects.filter(username=username).exists():
    User.objects.create_superuser(username=username, password=password, email=email)
EOF

# exec uvicorn config.asgi:application --reload --host 0.0.0.0 --port 8000
echo "Iniciando o servidor Uvicorn..."
exec "$@"