#!/bin/sh
# Run once on the Ubuntu server with: sudo sh deploy/lab/install-docker-ubuntu.sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

. /etc/os-release
if [ "$ID" != "ubuntu" ]; then
    echo "This installer is only for Ubuntu." >&2
    exit 1
fi

# This host's HTTP Ubuntu mirror returned a login page into the apt cache.
# Use Ubuntu's HTTPS mirror and remove only that invalid cached Release file.
ubuntu_sources=/etc/apt/sources.list.d/ubuntu.sources
if [ -f "$ubuntu_sources" ]; then
    cp -n "$ubuntu_sources" "$ubuntu_sources.pre-piap"
    sed -i \
        -e 's#http://archive.ubuntu.com/ubuntu/#https://archive.ubuntu.com/ubuntu/#g' \
        -e 's#http://security.ubuntu.com/ubuntu/#https://security.ubuntu.com/ubuntu/#g' \
        "$ubuntu_sources"
fi
# Discard cached package indexes fetched through the broken HTTP mirror.
# apt-get update downloads fresh indexes over HTTPS.
find /var/lib/apt/lists -maxdepth 1 -type f -delete

apt-get update
apt-get install -y docker.io docker-compose-v2 docker-buildx
systemctl enable --now docker
usermod -aG docker admin2
docker compose version
echo "Docker installed. A new SSH login is needed for admin2's docker group membership."
