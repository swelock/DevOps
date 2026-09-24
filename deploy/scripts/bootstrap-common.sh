#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Запустите скрипт через sudo." >&2
  exit 1
fi

ADMIN_USER=${ADMIN_USER:-devopsadmin}
PUBLIC_KEY_FILE=${1:-}

if [[ ! ${ADMIN_USER} =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
  echo "Некорректное имя ADMIN_USER." >&2
  exit 1
fi
if [[ -z ${PUBLIC_KEY_FILE} || ! -f ${PUBLIC_KEY_FILE} ]]; then
  echo "Использование: sudo $0 /путь/к/открытому_ключу.pub" >&2
  exit 1
fi
if ! grep -Eq '^ssh-(ed25519|rsa|ecdsa-sha2-nistp)' "${PUBLIC_KEY_FILE}"; then
  echo "Файл не похож на открытый SSH-ключ." >&2
  exit 1
fi
if ! id "${ADMIN_USER}" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "${ADMIN_USER}"
fi
usermod --append --groups sudo "${ADMIN_USER}"

install -d -m 0700 -o "${ADMIN_USER}" -g "${ADMIN_USER}" "/home/${ADMIN_USER}/.ssh"
install -m 0600 -o "${ADMIN_USER}" -g "${ADMIN_USER}" \
  "${PUBLIC_KEY_FILE}" "/home/${ADMIN_USER}/.ssh/authorized_keys"
install -m 0644 "$(dirname "$0")/../ssh/99-campus-hardening.conf" \
  /etc/ssh/sshd_config.d/99-campus-hardening.conf

sshd -t
systemctl reload ssh
echo "Проверьте вход во второй сессии: ssh ${ADMIN_USER}@<адрес>. Текущую сессию пока не закрывайте."
