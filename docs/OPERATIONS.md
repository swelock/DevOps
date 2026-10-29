# Эксплуатация и проверка Linux-стенда

Все команды выполняются на соответствующей машине. В примерах адрес сервера
приложения — `172.16.114.10`, БД — `172.16.114.20`.

Для пошаговой демонстрации на защите используйте [шпаргалку ЛР2](LR2-DEFENSE.md):
в ней указаны реальные SSH-команды, ожидаемые ответы и восстановление после
каждой проверки. Контрольное изменение выполняется отдельным временным drop-in
с удалением только своего файла, без общего `systemctl revert`.

## Проверка конфигурации и прав

На сервере приложения:

```bash
sudo /opt/campus/app/deploy/scripts/verify-host.sh app
systemctl cat campus.service
namei -l /etc/campus/campus.env /opt/campus/app
sudo -u campusapp test -r /etc/campus/campus.env
sudo -u campusapp test ! -w /opt/campus/app
```

На сервере БД:

```bash
sudo /путь/к/Project_DevOps/deploy/scripts/verify-host.sh db
sudo -u postgres psql -d campus -c '\du+ campus_app'
sudo -u postgres psql -d campus -c '\l+ campus'
```

Убедиться, что `ufw status` не содержит лишних разрешающих правил.

## Перезагрузка и автозапуск

```bash
# Сначала сервер БД, затем сервер приложения.
sudo reboot
systemctl is-enabled postgresql   # на БД: enabled
systemctl is-active postgresql    # на БД: active
systemctl is-enabled campus       # на приложении: enabled
systemctl is-active campus        # на приложении: active
curl http://172.16.114.10:8000/health
```

Ожидается `{"database":"ok","status":"ok"}`.

## Остановка БД и диагностика

```bash
# На сервере БД
sudo systemctl stop postgresql

# На сервере приложения
curl -i http://127.0.0.1:8000/health
systemctl status campus --no-pager
journalctl -u campus -n 30 --no-pager
```

Ожидается HTTP `503`, сообщение о недоступной БД и запись в журнале. Затем:

```bash
# На сервере БД
sudo systemctl start postgresql
# На сервере приложения
curl --fail http://127.0.0.1:8000/health
```

## Процесс, порт и журнал

```bash
systemctl show campus -p MainPID -p User -p Restart
ps -o user,pid,ppid,cmd -C gunicorn
ss -lntp '( sport = :8000 )'
journalctl -u campus --since '10 minutes ago' --no-pager
```

Процессы принадлежат `campusapp`, а не `root`; слушается только порт приложения.

## Автоперезапуск после аварии

```bash
MAIN_PID=$(systemctl show campus -p MainPID --value)
sudo kill -KILL "${MAIN_PID}"
sleep 5
systemctl is-active campus
systemctl show campus -p NRestarts -p MainPID
curl --fail http://127.0.0.1:8000/health
```

Служба снова `active`, PID изменился, счётчик перезапусков увеличился.

## Контрольное изменение службы

```bash
sudo systemctl edit campus
```

Ввести временное значение:

```ini
[Service]
RestartSec=10s
```

Затем выполнить:

```bash
sudo systemctl daemon-reload
sudo systemctl restart campus
systemctl show campus -p RestartUSec  # 10s
sudo systemctl revert campus
sudo systemctl daemon-reload
sudo systemctl restart campus
systemctl show campus -p RestartUSec  # снова 3s
```

## Сетевая изоляция БД

С сервера приложения соединение должно устанавливаться:

```bash
nc -vz 172.16.114.20 5432
```

С третьего узла в той же сети эта же команда должна завершиться тайм-аутом или
отказом. Проверка правил на сервере БД:

```bash
sudo ufw status numbered
sudo -u postgres psql -Atc 'show listen_addresses; show hba_file;'
sudo grep -n 'campus_app' /etc/postgresql/*/main/pg_hba.conf
```

## SSH и отсутствие секретов

```bash
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|pubkeyauthentication'
git grep -nE '(DATABASE_PASSWORD|postgresql://)' -- ':!*.example' ':!*.md'
git status --ignored --short
```

Ожидается `permitrootlogin no`, `passwordauthentication no`, ключи включены.
Команда `git grep` должна выводить только программные обращения к имени переменной, но
не реальный пароль. Файл `/etc/campus/campus.env` не находится в Git.

## Миграции и копии — ЛР3

Локально достаточно `make setup`. Для существующей SQLite перед обновлением:

```bash
make backup
make migrate
make verify
```

Миграции только прямые: 001 — исходная схема, 002 — индексы связей,
003 — вместимость. Таблицы старой версии принимаются ревизией 001 без очистки;
старые помещения после 003 получают `capacity=1`.

Для восстановления остановить локальный сервер (Ctrl+C), выбрать нужную копию:

```bash
make restore FILE=backups/имя.sqlite3
make run
```

SQLite-копия создаётся через backup API, а не копированием открытого файла.
Перед восстановлением проверяются целостность и внешние ключи. Новая копия
не перезаписывает существующую; файлы создаются с правами 0600.

### PostgreSQL на DB VM

Код проекта доставляется локально, без секретов. После резервного копирования
и остановки `campus.service` на App VM администратор на DB VM выполняет:

```bash
sudo bash deploy/scripts/migrate-db-server.sh
```

Helper устанавливает инструменты в `/opt/campus-db`, применяет миграции от
`campus_owner` через локальную peer-аутентификацию и сохраняет права `campus_app`.
При новой установке его вызывает `setup-db-server.sh`. При обновлении App VM
обновляются код и runtime-зависимости, затем запускается `campus.service`.

Далее команды обслуживания выполняются на DB VM. Оболочка ниже не содержит
рабочего пароля: системный пользователь postgres подтверждается через Unix socket.

```bash
cd /opt/campus-db/app
sudo -u postgres env \
  DATABASE_ENGINE=postgresql DATABASE_HOST=/var/run/postgresql DATABASE_PORT=5432 \
  DATABASE_NAME=campus DATABASE_USER=postgres DATABASE_PASSWORD=peer \
  PGOPTIONS='-c role=campus_owner' \
  /opt/campus-db/venv/bin/python -m scripts.manage backup --file /tmp/campus.dump
```

Путь копии должен быть доступен postgres. Рабочие копии хранятся вне репозитория в `/var/backups/campus` (postgres, 0700).
Копии перед обновлением находятся в root-каталоге `/var/backups/campus-lr3-20261022`.
Для `make backup` вместо последней строки можно использовать:
`make VENV=/opt/campus-db/venv/bin/python backup FILE=/путь/к/копии.dump`.
В `/opt/campus-db/app` запись кода закрыта, поэтому FILE указывается явно.
Для восстановления используется тот же набор переменных и команда
`make VENV=/opt/campus-db/venv/bin/python restore FILE=/путь/к/копии.dump`.
Перед этим на App VM остановить службу: `sudo systemctl stop campus`.

PostgreSQL-копия — custom-format pg_dump схемы public, восстановление —
pg_restore с `--clean --if-exists --single-transaction`. При ошибке транзакция
откатывается. Утилиты клиента должны соответствовать версии сервера (на стенде 16).
Копия не переносит владельцев и ACL; после восстановления выполняется:

```bash
sudo -u postgres psql -v ON_ERROR_STOP=1 -d campus <<'SQL'
ALTER SCHEMA public OWNER TO campus_owner;
GRANT USAGE ON SCHEMA public TO campus_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO campus_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO campus_app;
ALTER DEFAULT PRIVILEGES FOR ROLE campus_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO campus_app;
ALTER DEFAULT PRIVILEGES FOR ROLE campus_owner IN SCHEMA public
  GRANT USAGE ON SEQUENCES TO campus_app;
SQL
```

Затем на App VM: `sudo systemctl start campus`, проверка `/health`, вход и чтение
помещений. Backup/restore рабочей БД выполняет администратор, не runtime-роль приложения.

### Автоматические проверки миграций и восстановления

`make test` всегда проверяет SQLite: пустую БД, 001 → 002 → 003 с данными,
старую БД без alembic_version, ограничения и восстановление после удаления.
`make verify` дополнительно проверяет чувствительность тестов к четырём поломкам.

Реальный PostgreSQL проверяется на DB VM от postgres:

```bash
cd /opt/campus-db/app
sudo -u postgres make VENV=/opt/campus-db/venv/bin/python postgres-check
```

Или `make postgres-check` с VENV, если рабочий каталог и окружение доступны
пользователю postgres. Скрипт создаёт две случайно названные временные БД:
чистую и заполненную. Проверяет миграции, ограничения, HTTP API, затем удаляет
помещения, меняет адрес и восстанавливает копию. Сравниваются все строки,
пользователи и версия схемы, проверяются sequence. Временные БД удаляются в finally.
Этот сценарий не удаляет данные из рабочей campus и требует локального admin-доступа.
