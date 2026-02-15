#!/usr/bin/env bash
set -euo pipefail

APP_USER="hrforkids"
APP_GROUP="hrforkids"
APP_DIR="/opt/hrforkids"
DATA_DIR="/var/lib/hrforkids"
ENV_DIR="/etc/hrforkids"
SERVICE_NAME="hrforkids"
REMOVE_DATA="${1:-}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/raspberrypi/uninstall.sh [--delete-data]" >&2
  exit 1
fi

if systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service"; then
  systemctl stop "${SERVICE_NAME}" || true
  systemctl disable "${SERVICE_NAME}" || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload
fi

rm -rf "${APP_DIR}"
rm -rf "${ENV_DIR}"

if [[ "${REMOVE_DATA}" == "--delete-data" ]]; then
  rm -rf "${DATA_DIR}"
fi

if id -u "${APP_USER}" >/dev/null 2>&1; then
  userdel "${APP_USER}" || true
fi

if getent group "${APP_GROUP}" >/dev/null 2>&1; then
  groupdel "${APP_GROUP}" || true
fi

echo "Uninstall complete."
if [[ "${REMOVE_DATA}" == "--delete-data" ]]; then
  echo "Application data removed from ${DATA_DIR}."
else
  echo "Application data kept at ${DATA_DIR}."
  echo "To remove data too: sudo bash deploy/raspberrypi/uninstall.sh --delete-data"
fi
