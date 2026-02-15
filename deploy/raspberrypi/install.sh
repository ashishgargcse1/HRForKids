#!/usr/bin/env bash
set -euo pipefail

APP_USER="hrforkids"
APP_GROUP="hrforkids"
APP_DIR="/opt/hrforkids"
DATA_DIR="/var/lib/hrforkids"
ENV_DIR="/etc/hrforkids"
SERVICE_NAME="hrforkids"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/raspberrypi/install.sh" >&2
  exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer only supports Linux." >&2
  exit 1
fi

ARCH="$(uname -m)"
if [[ "${ARCH}" != "aarch64" && "${ARCH}" != "armv7l" && "${ARCH}" != "armv6l" ]]; then
  echo "Warning: expected Raspberry Pi ARM architecture, got ${ARCH}. Continuing..."
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip rsync

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${APP_DIR}" --shell /usr/sbin/nologin "${APP_USER}"
fi

install -d -m 0755 -o "${APP_USER}" -g "${APP_GROUP}" "${APP_DIR}"
install -d -m 0755 -o "${APP_USER}" -g "${APP_GROUP}" "${DATA_DIR}"
install -d -m 0750 -o root -g "${APP_GROUP}" "${ENV_DIR}"

# Copy app source and top-level runtime files into /opt/hrforkids.
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'data' \
  ./ "${APP_DIR}/"

python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/app/requirements.txt"

if [[ ! -f "${ENV_DIR}/hrforkids.env" ]]; then
  install -m 0640 -o root -g "${APP_GROUP}" \
    "${APP_DIR}/deploy/raspberrypi/hrforkids.env.example" \
    "${ENV_DIR}/hrforkids.env"
fi

sed -i "s|^APP_DB_PATH=.*|APP_DB_PATH=${DATA_DIR}/app.db|" "${ENV_DIR}/hrforkids.env"

install -m 0644 "${APP_DIR}/deploy/raspberrypi/hrforkids.service" "/etc/systemd/system/${SERVICE_NAME}.service"

chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}" "${DATA_DIR}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo
echo "Install complete."
echo "Edit ${ENV_DIR}/hrforkids.env and set APP_SECRET to a strong random value."
echo "Service status: systemctl status ${SERVICE_NAME}"
echo "Logs: journalctl -u ${SERVICE_NAME} -f"
