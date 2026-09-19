#!/usr/bin/env bash
set -euo pipefail

# FinAI-BR Local Deployment Helper
# Deploys or updates the production instance manually via SSH.
#
# Usage:
#   ./infra/scripts/deploy-local.sh <USER> <HOST_IP> <IMAGE_TAG> [SSH_KEY_PATH]

if [ "$#" -lt 3 ]; then
    echo "Usage: $0 <SSH_USER> <HOST_IP> <IMAGE_TAG> [SSH_KEY_PATH]"
    echo "Example: $0 finai 34.123.45.67 ghcr.io/joaoferreira-dev/finai-br:latest ~/.ssh/id_ed25519"
    exit 1
fi

SSH_USER="$1"
HOST_IP="$2"
IMAGE_TAG="$3"
SSH_KEY="${4:-}"
APP_DIR="/opt/finai"

SSH_CMD=(ssh)
SCP_CMD=(scp)

if [ -n "${SSH_KEY}" ]; then
    SSH_CMD+=(-i "${SSH_KEY}")
    SCP_CMD+=(-i "${SSH_KEY}")
fi

echo "=== Deploying FinAI-BR to ${SSH_USER}@${HOST_IP} ==="

# Upload updated docker-compose.prod.yml
echo "Uploading docker-compose.prod.yml..."
"${SCP_CMD[@]}" docker-compose.prod.yml "${SSH_USER}@${HOST_IP}:${APP_DIR}/docker-compose.prod.yml"

# Execute pull and container restart
echo "Triggering container update..."
"${SSH_CMD[@]}" "${SSH_USER}@${HOST_IP}" bash -c "'
    cd ${APP_DIR}
    printf \"FINAI_IMAGE=${IMAGE_TAG}\n\" > .image.env
    docker compose --env-file .image.env -f docker-compose.prod.yml pull
    docker compose --env-file .image.env -f docker-compose.prod.yml up -d --remove-orphans
    docker compose --env-file .image.env -f docker-compose.prod.yml ps
'"

echo "=== Deployment finished successfully ==="
