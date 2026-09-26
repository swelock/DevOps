#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Запустите скрипт через sudo." >&2
  exit 1
fi

APP_SERVER_IP=${1:-172.16.114.10}
DB_SERVER_IP=${2:-172.16.114.20}
ADMIN_CIDR=${3:-172.16.114.0/24}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SCHEMA_TMP=''

cleanup() {
  [[ -z ${SCHEMA_TMP} ]] || rm -f "${SCHEMA_TMP}"
}
trap cleanup EXIT

if [[ ! ${APP_SERVER_IP} =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] ||
  [[ ! ${DB_SERVER_IP} =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "Некорректный IPv4-адрес сервера." >&2
  exit 1
fi
if [[ ! ${ADMIN_CIDR} =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]]; then
  echo "Некорректная административная CIDR-сеть." >&2
  exit 1
fi
read -rsp "Новый пароль роли campus_app (A-Z, a-z, 0-9, _, -, минимум 16): " DB_PASSWORD
echo
if [[ ! ${DB_PASSWORD} =~ ^[A-Za-z0-9_-]{16,128}$ ]]; then
  echo "Пароль не соответствует безопасному формату." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql ufw

PG_VERSION=$(pg_lsclusters --no-header | awk 'NR == 1 {print $1}')
PG_CONFIG_DIR="/etc/postgresql/${PG_VERSION}/main"
install -d -m 0755 "${PG_CONFIG_DIR}/conf.d"
printf "listen_addresses = '127.0.0.1,%s'\npassword_encryption = 'scram-sha-256'\n" \
  "${DB_SERVER_IP}" >"${PG_CONFIG_DIR}/conf.d/99-campus.conf"
chmod 0644 "${PG_CONFIG_DIR}/conf.d/99-campus.conf"

HBA_FILE="${PG_CONFIG_DIR}/pg_hba.conf"
sed -i '/# BEGIN CAMPUS APP/,/# END CAMPUS APP/d' "${HBA_FILE}"
printf '\n# BEGIN CAMPUS APP\nhost campus campus_app %s/32 scram-sha-256\n# END CAMPUS APP\n' \
  "${APP_SERVER_IP}" >>"${HBA_FILE}"

systemctl restart postgresql

sudo -u postgres psql --set=ON_ERROR_STOP=on --dbname=postgres <<SQL
\set app_password '${DB_PASSWORD}'
SELECT 'CREATE ROLE campus_owner NOLOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'campus_owner') \gexec
SELECT format('CREATE ROLE campus_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'campus_app') \gexec
SELECT format('ALTER ROLE campus_app PASSWORD %L', :'app_password') \gexec
SELECT 'CREATE DATABASE campus OWNER campus_owner'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'campus') \gexec
REVOKE ALL ON DATABASE campus FROM PUBLIC;
GRANT CONNECT ON DATABASE campus TO campus_app;
SQL

SCHEMA_TMP=$(mktemp /tmp/campus-schema.XXXXXX.sql)
install -m 0644 "${SCRIPT_DIR}/../postgresql/schema.sql" "${SCHEMA_TMP}"

sudo -u postgres psql --set=ON_ERROR_STOP=on --dbname=campus <<SQL
ALTER SCHEMA public OWNER TO campus_owner;
SET ROLE campus_owner;
\i '${SCHEMA_TMP}'
RESET ROLE;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO campus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO campus_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO campus_app;
ALTER DEFAULT PRIVILEGES FOR ROLE campus_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO campus_app;
ALTER DEFAULT PRIVILEGES FOR ROLE campus_owner IN SCHEMA public
  GRANT USAGE ON SEQUENCES TO campus_app;
SQL

ufw default deny incoming
ufw default allow outgoing
ufw allow from "${ADMIN_CIDR}" to any port 22 proto tcp comment 'SSH administration'
ufw allow from "${APP_SERVER_IP}" to any port 5432 proto tcp comment 'PostgreSQL from app'
ufw --force enable

echo "Сервер БД настроен. Используйте тот же пароль при настройке сервера приложения."
