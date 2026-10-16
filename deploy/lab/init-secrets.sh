#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
umask 077

if [ -e .env.lab ] || [ -e deploy/lab/secrets/jwt_private.pem ]; then
    echo "Deployment secrets already exist; leaving them unchanged." >&2
    exit 0
fi

mkdir -p deploy/lab/secrets
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out deploy/lab/secrets/jwt_private.pem >/dev/null 2>&1
openssl pkey -in deploy/lab/secrets/jwt_private.pem -pubout -out deploy/lab/secrets/jwt_public.pem >/dev/null 2>&1

{
    printf 'MYSQL_ROOT_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'PIAP_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'PIAP_MINIO_ROOT_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'PIAP_NEO4J_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'PIAP_GOVERNANCE_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'PIAP_WEB_BIND_ADDRESS=0.0.0.0\n'
    printf 'PIAP_WEB_PORT=8080\n'
    printf 'PIAP_VOLCENGINE_API_KEY=\n'
    printf 'PIAP_VOLCENGINE_MODEL_ID=\n'
    printf 'PIAP_VOLCENGINE_EMBED_MODEL=\n'
} > .env.lab

echo "Created .env.lab and a private JWT key pair. Keep these files on the server." >&2
