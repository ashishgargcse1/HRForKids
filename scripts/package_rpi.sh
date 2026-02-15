#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/dist"
TS="$(date +%Y%m%d_%H%M%S)"
PKG_DIR="${OUT_DIR}/hrforkids-rpi"
ARCHIVE="${OUT_DIR}/hrforkids-rpi-${TS}.tar.gz"

mkdir -p "${PKG_DIR}" "${OUT_DIR}"
rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}"

rsync -a \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'dist' \
  --exclude 'data/*.db' \
  "${ROOT_DIR}/" "${PKG_DIR}/"

tar -C "${OUT_DIR}" -czf "${ARCHIVE}" "hrforkids-rpi"
rm -rf "${PKG_DIR}"

echo "Created ${ARCHIVE}"
echo "Deploy on Pi:"
echo "  1) scp ${ARCHIVE} pi@<pi-ip>:/tmp/"
echo "  2) ssh pi@<pi-ip>"
echo "  3) sudo mkdir -p /opt/hrforkids-src && sudo tar -xzf /tmp/$(basename "${ARCHIVE}") -C /opt/hrforkids-src"
echo "  4) cd /opt/hrforkids-src/hrforkids-rpi && sudo bash deploy/raspberrypi/install.sh"
