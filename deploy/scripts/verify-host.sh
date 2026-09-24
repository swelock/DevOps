#!/usr/bin/env bash
set -Eeuo pipefail

ROLE=${1:-}
if [[ ${ROLE} == app ]]; then
  systemctl is-enabled campus.service
  systemctl is-active campus.service
  test "$(systemctl show -p User --value campus.service)" = campusapp
  curl --fail --show-error http://127.0.0.1:8000/health
  echo
  ss -lntp '( sport = :8000 )'
  journalctl -u campus.service -n 20 --no-pager
elif [[ ${ROLE} == db ]]; then
  systemctl is-enabled postgresql
  systemctl is-active postgresql
  ss -lntp '( sport = :5432 )'
  sudo -u postgres psql --dbname=campus --command='\dt+'
  ufw status verbose
else
  echo "Использование: $0 app|db" >&2
  exit 1
fi
