#!/bin/bash
# Installiert Node.js 24 (ARM64, offiziell, mit Pr??fsumme) und n8n im Linux (WSL) f??r Watson Studio.
set -e
V=v24.22.2
ARCH=$(uname -m)
echo "Linux-Architektur: $ARCH"
[ "$ARCH" = "aarch64" ] || { echo "Erwartet aarch64 (ARM64)"; exit 1; }

apt-get -qq update >/dev/null 2>&1 || true
command -v curl >/dev/null || apt-get -qq install -y curl xz-utils >/dev/null

if [ ! -x /opt/node24/bin/node ]; then
  cd /tmp
  curl -fsSLO https://nodejs.org/dist/$V/node-$V-linux-arm64.tar.xz
  curl -fsSL https://nodejs.org/dist/$V/SHASUMS256.txt | grep " node-$V-linux-arm64.tar.xz\$" > sum.txt
  sha256sum -c sum.txt
  mkdir -p /opt/node24
  tar -xJf node-$V-linux-arm64.tar.xz -C /opt/node24 --strip-components=1
  rm -f node-$V-linux-arm64.tar.xz sum.txt
fi
export PATH=/opt/node24/bin:$PATH
echo "Node: $(node -v) $(node -p process.arch) abi$(node -p process.versions.modules)"

mkdir -p /opt/watson-n8n/daten
cd /opt/watson-n8n
[ -f package.json ] || echo '{"name":"watson-n8n","private":true}' > package.json
npm install n8n@2.46.6 --no-fund --no-audit --loglevel=error
test -f node_modules/n8n/bin/n8n && echo "N8N_OK"
