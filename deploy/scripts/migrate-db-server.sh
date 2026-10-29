#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Запустите миграции сервера БД через sudo." >&2
  exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_DIR=$(cd -- "${SCRIPT_DIR}/../.." && pwd)
APP_DIR=/opt/campus-db/app
VENV_DIR=/opt/campus-db/venv
PEER_PLACEHOLDER=peer

if [[ ! -f ${PROJECT_DIR}/requirements.txt || ! -d ${PROJECT_DIR}/migrations ]]; then
  echo "Не найден проект с миграциями." >&2
  exit 1
fi

if ! command -v make >/dev/null ||
  [[ $(dpkg-query -W -f='${Status}' python3-venv 2>/dev/null) != 'install ok installed' ]]; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv make
fi

install -d -m 0750 -o root -g postgres /opt/campus-db "${APP_DIR}"
# На сервер БД переносится только код обслуживания, без .env и рабочих данных.
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='.env.*' \
  -C "${PROJECT_DIR}" -cf - \
  campus migrations scripts Makefile requirements.txt requirements-dev.txt requirements-lock.txt pyproject.toml \
  deploy/postgresql/schema.sql | tar -C "${APP_DIR}" -xf -
chown -R root:postgres "${APP_DIR}"
find "${APP_DIR}" -type d -exec chmod 0750 {} +
find "${APP_DIR}" -type f -exec chmod 0640 {} +

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --disable-pip-version-check \
  -r "${APP_DIR}/requirements.txt"
chown -R root:postgres "${VENV_DIR}"
chmod -R g+rX,o-rwx "${VENV_DIR}"

cd "${APP_DIR}"
# Peer аутентифицирует системного postgres; DDL выполняется от campus_owner.
# Значение peer не является паролем: оно нужно только валидатору конфигурации.
sudo -u postgres env \
  DATABASE_ENGINE=postgresql DATABASE_HOST=/var/run/postgresql DATABASE_PORT=5432 \
  DATABASE_NAME=campus DATABASE_USER=postgres DATABASE_PASSWORD=${PEER_PLACEHOLDER} \
  PGOPTIONS='-c role=campus_owner' \
  "${VENV_DIR}/bin/python" -m scripts.manage migrate

sudo -u postgres psql --set=ON_ERROR_STOP=on --dbname=campus <<'SQL'
GRANT USAGE ON SCHEMA public TO campus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO campus_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO campus_app;
ALTER DEFAULT PRIVILEGES FOR ROLE campus_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO campus_app;
ALTER DEFAULT PRIVILEGES FOR ROLE campus_owner IN SCHEMA public
  GRANT USAGE ON SEQUENCES TO campus_app;
SQL

echo "Миграции БД применены; campus_app сохраняет только доступ к данным."
