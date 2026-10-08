#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu 24.04 server: Docker Engine, the
# Compose plugin, Git, and a swap file. Safe to run again: every step checks
# whether it is already done.
#
#   Run on the SERVER, from the repository folder:   bash deploy/server-setup.sh
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as the normal user (ubuntu), not as root. It uses sudo where needed." >&2
    exit 1
fi

echo "==> Installing Docker Engine from Docker's official apt repository"
if ! command -v docker >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl git
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    # shellcheck disable=SC1091
    codename="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
    sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${codename}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo "    Docker is already installed: $(docker --version)"
fi

echo "==> Allowing user '$USER' to run docker without sudo"
if ! id -nG "$USER" | grep -qw docker; then
    sudo usermod -aG docker "$USER"
    echo "    Added. Log out and log in again for it to take effect."
fi

echo "==> Making sure Docker starts when the server boots"
sudo systemctl enable --now docker >/dev/null

# Building the images (npm, pip) needs more memory than a small instance has.
# Swap is slow disk memory: it prevents a frozen server during the build.
echo "==> Swap file (2 GiB)"
if ! sudo swapon --show | grep -q /swapfile; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
    sudo swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
else
    echo "    Swap is already active."
fi

echo
docker --version
sudo docker compose version
free -h | sed -n '1p;3p'
echo
echo "Done. If you were just added to the docker group: log out, log in, then continue."
