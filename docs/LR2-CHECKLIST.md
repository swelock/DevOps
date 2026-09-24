# Проверка и защита лабораторной работы 2

Все команды выполняются на соответствующей машине. В примерах адрес сервера
приложения — `192.168.56.10`, БД — `192.168.56.20`.

## Перед защитой

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
curl http://192.168.56.10:8000/health
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

## Процесс порт и журнал

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
nc -vz 192.168.56.20 5432
```

С третьего узла в той же сети эта же команда должна завершиться тайм-аутом или
отказом. На сервере БД показать правило:

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
Первый `git grep` показывает только программные обращения к имени переменной, но
не реальный пароль. Файл `/etc/campus/campus.env` не находится в Git.
