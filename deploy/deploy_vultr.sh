#!/usr/bin/env bash
# Deploy Tripwire Sandbox to a fresh Vultr Ubuntu 22.04/24.04 cloud compute VM.
# NOT YET RUN: requires a Vultr account. Usage (on the VM, as root):
#   git clone https://github.com/Cubiczan/tripwire-sandbox && cd tripwire-sandbox && bash deploy/deploy_vultr.sh
set -euo pipefail
if ! command -v docker >/dev/null; then
  apt-get update -y
  apt-get install -y ca-certificates curl
  curl -fsSL https://get.docker.com | sh
fi
docker pull python:3.12-slim          # sandbox image
[ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "Edit .env to add VULTR_INFERENCE_API_KEY (empty = mock mode)"; }
docker compose up -d --build
if command -v ufw >/dev/null; then ufw allow 80/tcp || true; fi
sleep 3
curl -fsS http://localhost/status && echo && echo "Up on http://$(curl -fsS ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')/"
