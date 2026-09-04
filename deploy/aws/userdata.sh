#!/usr/bin/env bash
# PRAHARI on the cheapest always-on AWS box: one Lightsail or EC2 instance running Docker, with Caddy
# providing free HTTPS on an sslip.io hostname (no domain needed). Paste this as the instance's
# user data (Lightsail "Launch script" / EC2 "User data"). Ubuntu 22.04 or 24.04, 2 GB RAM minimum.
#
# After boot (5 to 10 minutes: the image build generates data and trains models once), open
#   https://<PUBLIC-IP with dots replaced by dashes>.sslip.io      e.g. https://13-233-10-20.sslip.io
# Health: https://.../api/health  ->  {"status":"ok", ...}
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

REPO="${PRAHARI_REPO:-https://github.com/arungeekay/prahari-ews.git}"
BRANCH="main"
APP_DIR=/opt/prahari

# ---- swap: the one-off image build (data generation + model training) peaks above 2 GB ----------
if ! swapon --show | grep -q swapfile; then
  fallocate -l 3G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---- docker --------------------------------------------------------------------------------------
apt-get update -y
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker

# ---- app -----------------------------------------------------------------------------------------
mkdir -p "$APP_DIR" && cd "$APP_DIR"
if [ ! -d repo ]; then git clone --depth 1 --branch "$BRANCH" "$REPO" repo; fi
git config --global --add safe.directory /opt/prahari/repo 2>/dev/null || true   # lets later "sudo git" redeploys read the root-owned clone

PUBLIC_IP=$(curl -fsS --max-time 5 http://checkip.amazonaws.com | tr -d '\n' || true)
HOST="${PRAHARI_HOST:-$(echo "$PUBLIC_IP" | tr . -).sslip.io}"

cat > docker-compose.yml <<EOF
services:
  prahari:
    build: ./repo
    restart: unless-stopped
    environment:
      PORT: "8001"
      DATA_SOURCE: synthetic
    expose: ["8001"]
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request,sys,json; sys.exit(0 if json.load(urllib.request.urlopen('http://localhost:8001/api/health')).get('status')=='ok' else 1)\""]
      interval: 15s
      timeout: 5s
      retries: 20
      start_period: 60s

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [prahari]

volumes:
  caddy_data:
  caddy_config:
EOF

cat > Caddyfile <<EOF
${HOST} {
    encode gzip
    reverse_proxy prahari:8001
}
EOF

# build once (bakes data + models), then serve; log to /var/log/prahari-build.log
docker compose build 2>&1 | tee /var/log/prahari-build.log
docker compose up -d
echo "PRAHARI is starting at https://${HOST}  (health: https://${HOST}/api/health)" | tee /var/log/prahari-url.txt
