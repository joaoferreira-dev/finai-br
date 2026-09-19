#!/usr/bin/env bash
set -euo pipefail

# FinAI-BR Compute Engine Startup Script
# Configures 2GB swap, Docker Engine, Docker Compose plugin, and /opt/finai directory.

ADMIN_USER="${ADMIN_USER:-finai}"
APP_DIR="/opt/finai"

echo "=== [FinAI-BR] Starting instance bootstrap ==="

# 1. Configure 2GB Swapfile (vital for 1GB RAM e2-micro instance)
if [ ! -f /swapfile ]; then
    echo "=== [FinAI-BR] Creating 2GB swapfile ==="
    fallocate -l 2G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab

    # Kernel memory tuning
    sysctl vm.swappiness=10
    sysctl vm.vfs_cache_pressure=50
    cat << 'EOF' > /etc/sysctl.d/99-finai-swap.conf
vm.swappiness=10
vm.vfs_cache_pressure=50
EOF
    echo "=== [FinAI-BR] Swapfile configured successfully ==="
else
    echo "=== [FinAI-BR] Swapfile already exists ==="
fi

# 2. Install prerequisites & Docker Engine
echo "=== [FinAI-BR] Installing Docker & Docker Compose ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# Configure Docker repository
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
fi

ARCH="$(dpkg --print-architecture)"
CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y --no-install-recommends \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

# 3. Configure Docker Daemon log limits to protect the 30GB disk
cat << 'EOF' > /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker
systemctl enable docker

# 4. Create App Directory and permissions
echo "=== [FinAI-BR] Setting up application directory at ${APP_DIR} ==="
mkdir -p "${APP_DIR}"

if id "${ADMIN_USER}" &>/dev/null; then
    usermod -aG docker "${ADMIN_USER}"
    chown -R "${ADMIN_USER}:${ADMIN_USER}" "${APP_DIR}"
fi
chmod 755 "${APP_DIR}"

echo "=== [FinAI-BR] Bootstrap completed successfully ==="
