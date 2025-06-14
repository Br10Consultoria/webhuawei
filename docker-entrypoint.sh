#!/bin/bash
set -e

# Carrega variáveis do .env (sem logs no terminal)
if [ -f /app/.env ]; then
  set -o allexport
  . /app/.env
  set +o allexport
fi

# Aguarda o Redis estar disponível
until nc -z redis 6379; do
  sleep 2
done

# Inicia a aplicação com Gunicorn
exec gunicorn --bind 0.0.0.0:5000 \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    "src.app:create_app()"
