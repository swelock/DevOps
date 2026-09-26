#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Запустите скрипт через sudo из корня репозитория." >&2
  exit 1
fi

DB_SERVER_IP=${1:-172.16.114.20}
CLIENT_CIDR=${2:-172.16.114.0/24}
ADMIN_CIDR=${3:-172.16.114.0/24}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)

if [[ ! ${DB_SERVER_IP} =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "Некорректный IPv4-адрес сервера БД." >&2
  exit 1
fi
if [[ ! ${CLIENT_CIDR} =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]] ||
  [[ ! ${ADMIN_CIDR} =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]; then
  echo "Некорректная клиентская или административная CIDR-сеть." >&2
  exit 1
fi
if [[ ! -f ${PROJECT_DIR}/requirements.txt || ! -d ${PROJECT_DIR}/campus ]]; then
  echo "Не найден корень Project_DevOps." >&2
  exit 1
fi
read -rsp "Пароль роли campus_app, созданный на сервере БД: " DB_PASSWORD
echo
if [[ ! ${DB_PASSWORD} =~ ^[A-Za-z0-9_-]{16,128}$ ]]; then
  echo "Пароль не соответствует безопасному формату." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3-venv python3-pip rsync ufw curl netcat-openbsd

if ! id campusapp >/dev/null 2>&1; then
  useradd --system --home-dir /opt/campus --shell /usr/sbin/nologin campusapp
fi
install -d -m 0750 -o root -g campusapp /opt/campus/app /etc/campus

rsync -a --delete \
  --exclude .git --exclude .venv --exclude .env --exclude instance \
  --exclude __pycache__ --exclude .pytest_cache --exclude .ruff_cache \
  "${PROJECT_DIR}/" /opt/campus/app/
chown -R root:campusapp /opt/campus/app
find /opt/campus/app -type d -exec chmod 0750 {} +
find /opt/campus/app -type f -exec chmod 0640 {} +
chmod 0750 /opt/campus/app/deploy/scripts/*.sh

python3 -m venv /opt/campus/venv
/opt/campus/venv/bin/pip install --disable-pip-version-check -r /opt/campus/app/requirements.txt
chown -R root:campusapp /opt/campus/venv
find /opt/campus/venv -type d -exec chmod 0750 {} +

umask 0027
{
  echo 'APP_HOST=0.0.0.0'
  echo 'APP_PORT=8000'
  echo 'DATABASE_ENGINE=postgresql'
  echo "DATABASE_HOST=${DB_SERVER_IP}"
  echo 'DATABASE_PORT=5432'
  echo 'DATABASE_NAME=campus'
  echo 'DATABASE_USER=campus_app'
  echo "DATABASE_PASSWORD=${DB_PASSWORD}"
} >/etc/campus/campus.env
chown root:campusapp /etc/campus/campus.env
chmod 0640 /etc/campus/campus.env

install -m 0644 "${SCRIPT_DIR}/../systemd/campus.service" /etc/systemd/system/campus.service
systemctl daemon-reload
systemctl enable --now campus.service

ufw default deny incoming
ufw default allow outgoing
ufw allow from "${ADMIN_CIDR}" to any port 22 proto tcp comment 'SSH administration'
ufw allow from "${CLIENT_CIDR}" to any port 8000 proto tcp comment 'Campus application'
ufw --force enable

systemctl --no-pager --full status campus.service
curl --fail --show-error http://127.0.0.1:8000/health
echo
echo "Сервер приложения настроен: http://$(hostname -I | awk '{print $1}'):8000"
