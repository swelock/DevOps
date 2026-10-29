# ЛР2: пошаговая шпаргалка для защиты

## 1. Что у тебя вообще работает

На Mac запущен VMware Fusion. В нём две виртуальные машины с Ubuntu:

- **APP** — `campus-app`, адрес `172.16.114.10`. Здесь Python-приложение Flask запускается через Gunicorn. Его служба называется `campus.service`, порт — `8000`.
- **DB** — `campus-db`, адрес `172.16.114.20`. Здесь PostgreSQL 16, база `campus`, порт — `5432`. Настоящая служба кластера — `postgresql@16-main`.
- **MAC** — твой обычный Терминал macOS. Для проверки изоляции БД он выступает посторонним узлом: это не сервер приложения.

Путь запроса: браузер → APP:8000 → DB:5432 → ответ приложению → браузер.

`devopsadmin` — пользователь для твоего входа по SSH и администрирования через sudo.
`campusapp` — системный пользователь, от которого работает приложение. У него нет интерактивного входа.
`campus_app` — роль внутри PostgreSQL, которой приложение читает и меняет данные.
`campus_owner` — отдельная роль-владелец базы и таблиц. Приложение под ней не работает.

Это разные учётные записи. Пароль для входа на сайт тоже отдельный: это не пароль PostgreSQL.

**Для ЛР2 Docker и ручной запуск `python run.py` не нужны. Управляем уже установленной Linux-службой.**

## 2. Что проверено на реальных машинах 29.10.2026

Все пять пунктов защиты выполнены вживую:

1. Обе VM действительно перезагружены. После загрузки PostgreSQL и приложение запустились автоматически, адреса сохранились, `/health` вернул HTTP 200. Смена boot ID подтвердила перезагрузку.
2. PostgreSQL остановлен: кластер стал `down`, порт 5432 перестал слушаться. Приложение осталось `active`, `/health` вернул HTTP 503, журнал содержит ошибку подключения. После запуска БД получен HTTP 200 без перезапуска приложения.
3. Найдены главный процесс и рабочие процессы Gunicorn, пользователь `campusapp`, порт 8000 и журнал службы.
4. Через отдельный временный drop-in изменён `RestartSec`: `3s → 10s → 3s`. Временный файл удалён, служба восстановлена.
5. С APP подключение к DB:5432 успешно. С Mac оно завершается тайм-аутом. На DB UFW разрешает 5432 только адресу APP.

Дополнительно: SIGKILL главного процесса Gunicorn привёл к автоперезапуску. PID сменился с 30400 на 30413, `NRestarts` стал 1, `/health` вернул 200. После последующей перезагрузки эти PID и счётчик уже могут отличаться.

Проверены также SSH по ключу, запрет root/password login, права `root:campusapp 0640` на конфигурацию, запрет записи исходников пользователем приложения и разделение владельца БД и роли приложения.

Это проверка работающего стенда и файлов развёртывания. Полный прогон тестов приложения и аудит всей истории Git в эту проверку не входят.

## 3. Подготовка перед приходом преподавателя

Включи обе VM в VMware Fusion. Открой три окна или вкладки Терминала на Mac.
Команды ниже вводи по блокам: подпись APP/DB/MAC говорит, в каком окне.

### Окно APP: подключиться к серверу приложения

В Терминале Mac:

```bash
ssh -i ~/.ssh/campus_lab_lr2 devopsadmin@172.16.114.10
hostname
```

Должно вывести `campus-app`. Теперь команды этой вкладки выполняются на APP.

### Окно DB: подключиться к серверу базы

В другой вкладке Терминала Mac:

```bash
ssh -i ~/.ssh/campus_lab_lr2 devopsadmin@172.16.114.20
hostname
```

Должно вывести `campus-db`. Теперь это окно DB.

### Окно MAC: оставить локальным

Третью вкладку оставь без SSH. Здесь выполняется проверка с постороннего узла.

Открой в браузере [приложение](http://172.16.114.10:8000) и [проверку здоровья](http://172.16.114.10:8000/health).
Нормальный ответ health: `{"database":"ok","status":"ok"}`.

Команды вводи без символа `$` в начале. `sudo` означает выполнение с административными правами.
Если после `systemctl status` открылся длинный экран, нажми `q`. В командах ниже есть `--no-pager`, чтобы этого не происходило.

## 4. Пункт защиты №1: перезагрузка и автозапуск

**Смысл:** показать, что после включения Linux всё работает без IDE, ручного запуска Python и команды `systemctl start`.

Сначала в окне **DB**:

```bash
sudo reboot
```

SSH-соединение оборвётся — это нормально. Подожди примерно 20–40 секунд и в том же окне снова подключись:

```bash
ssh -i ~/.ssh/campus_lab_lr2 devopsadmin@172.16.114.20
hostname
uptime -s
ip -br address
systemctl is-enabled postgresql
systemctl is-active postgresql@16-main
pg_lsclusters
```

Ждём `campus-db`, новое время загрузки, адрес `172.16.114.20/24`, `enabled`, `active`, строку `16 main 5432 online`.
`enabled` — настроен запуск при загрузке; `active` — работает прямо сейчас. Одно не заменяет другое.

Потом в окне **APP**:

```bash
sudo reboot
```

После разрыва SSH и загрузки снова подключись:

```bash
ssh -i ~/.ssh/campus_lab_lr2 devopsadmin@172.16.114.10
hostname
uptime -s
ip -br address
systemctl is-enabled campus
systemctl is-active campus
curl --max-time 10 -i http://127.0.0.1:8000/health
```

Ждём `campus-app`, адрес `172.16.114.10/24`, `enabled`, `active`, `HTTP/1.1 200 OK` и JSON с двумя `ok`.
Если сразу после включения SSH пишет `Connection refused` или тайм-аут — подожди немного и повтори подключение.

**Что сказать:** «Обе машины перезагружены. Адреса постоянные. PostgreSQL и campus запустились автоматически. Health подтверждает, что приложение подключается к БД».

## 5. Пункт защиты №2: остановить БД и объяснить состояние приложения

Сначала в окне **DB**:

```bash
sudo systemctl stop postgresql
sleep 3
pg_lsclusters
sudo ss -lntp '( sport = :5432 )'
```

Ждём `down` у кластера и отсутствие строки LISTEN для 5432. Если остановка ещё идёт, повтори две последние команды через несколько секунд.

Теперь в окне **APP**:

```bash
curl --max-time 10 -i http://127.0.0.1:8000/health
systemctl status campus --no-pager -l
sudo journalctl -u campus --since '5 minutes ago' -n 60 --no-pager
```

Правильный результат:

- HTTP **503 SERVICE UNAVAILABLE**: приложение приняло запрос, но не смогло выполнить его без БД.
- `campus` остаётся **active (running)**: процесс веб-сервера жив.
- В журнале есть `Database unavailable`, `psycopg.OperationalError` и ошибка подключения к `172.16.114.20:5432`. Конкретный текст зависит от момента запроса.

Если JSON показывает русские буквы как `\u0411...`, это обычное JSON-кодирование. Смотри прежде всего HTTP-статус.

**Что сказать:** «Служба приложения работает, но зависимость недоступна. Поэтому systemd показывает active, а проверка здоровья — 503. Причина видна в журнале: нет подключения к PostgreSQL».

### Обязательно вернуть БД

В окне **DB**:

```bash
sudo systemctl start postgresql
pg_lsclusters
```

Должно быть `online`. В окне **APP**:

```bash
curl --max-time 10 -i http://127.0.0.1:8000/health
```

Должен вернуться HTTP 200. Приложение специально не перезапускаем: показываем, что оно само снова подключается к работающей БД.

## 6. Пункт защиты №3: найти процесс, порт и журналы

Всё ниже — в окне **APP**.

### Процесс: кто работает и под каким пользователем

```bash
systemctl show campus -p MainPID -p User -p Restart -p RestartUSec
pgrep -a -u campusapp -f gunicorn
```

`MainPID` — номер главного процесса Gunicorn. `User=campusapp` — пользователь службы.
`pgrep` показывает главный и два рабочих процесса. Несколько процессов здесь нормально: в запуске указано `--workers 2`.

Чтобы показать Linux-процесс с его родителем и полным именем пользователя:

```bash
MAIN_PID=$(systemctl show campus -p MainPID --value)
ps -p "$MAIN_PID" -o user:20,pid,ppid,args
```

`PID` — номер процесса, `PPID` — номер его родителя. У главного процесса службы родитель обычно PID 1, то есть systemd.

### Порт: кто принимает соединения

```bash
sudo ss -lntp '( sport = :8000 )'
```

Ждём `LISTEN`, адрес `0.0.0.0:8000`, имя `gunicorn` и PID.
`0.0.0.0` означает все IPv4-интерфейсы этой VM. Это адрес прослушивания; в браузере открываем `172.16.114.10`.

Буквы у `ss`: `l` — слушающие сокеты, `n` — числовые адреса/порты, `t` — TCP, `p` — процессы.
С `sudo` доступна информация о процессах службы.

### Журналы: что происходило

```bash
sudo journalctl -u campus -n 50 --no-pager
sudo journalctl -u campus -b --no-pager
```

Первая команда — последние 50 записей; вторая — записи с текущей загрузки.
Для просмотра вживую:

```bash
sudo journalctl -u campus -f
```

Обнови страницу в браузере — появится запись запроса. Нажми **Ctrl+C**, чтобы закончить просмотр. Служба от этого не остановится.

На **DB** аналогичные команды:

```bash
sudo ss -lntp '( sport = :5432 )'
sudo journalctl -u postgresql@16-main -n 30 --no-pager
sudo tail -n 30 /var/log/postgresql/postgresql-16-main.log
```

Собственные сообщения PostgreSQL могут находиться именно в файле журнала, а в journal — события запуска/остановки.

**Что сказать:** «Через systemctl нахожу службу и главный PID, через ps — процесс и пользователя, через ss — слушающий порт и процесс, через journalctl — журнал».

## 7. Пункт защиты №4: изменить параметр и вернуть обратно

Меняем `RestartSec` — задержку перед автоматическим запуском после аварии: с 3 до 10 секунд.
Порт, пароль и адрес БД менять для этой проверки не требуется.
Все команды — в окне **APP**.

Сначала посмотри исходное значение:

```bash
systemctl show campus -p RestartUSec
```

Ждём `RestartUSec=3s`. Название вывода отличается от настройки: в unit-файле `RestartSec`, в `systemctl show` — `RestartUSec`.

Создаём отдельный временный файл настройки. Если первая команда вывела `STOP`, дальше этот блок не выполняй: файл уже существует, его нельзя перезаписывать вслепую.

```bash
test ! -e /run/systemd/system/campus.service.d/90-lr2-defense.conf && echo OK || echo STOP
```

Только если выведено `OK`:

```bash
sudo mkdir -p /run/systemd/system/campus.service.d
printf '[Service]\nRestartSec=10s\n' | sudo tee /run/systemd/system/campus.service.d/90-lr2-defense.conf
sudo systemctl daemon-reload
sudo systemctl restart campus
systemctl show campus -p RestartUSec
systemctl cat campus
```

Ждём `RestartUSec=10s`. В `systemctl cat` видно исходный unit и дополнительный файл.
`daemon-reload` заставляет systemd перечитать определения служб; `restart` перезапускает само приложение.
Файл под `/run` временный и исчезнет после перезагрузки, но на защите возвращаем настройку явно.

### Восстановление

```bash
sudo rm /run/systemd/system/campus.service.d/90-lr2-defense.conf
sudo systemctl daemon-reload
sudo systemctl restart campus
systemctl show campus -p RestartUSec
sleep 2
curl --max-time 10 -i http://127.0.0.1:8000/health
```

Ждём `RestartUSec=3s` и HTTP 200. После restart может понадобиться ещё секунда на запуск Gunicorn; тогда повтори curl.

Удаляем только свой файл. `systemctl revert` здесь не нужен: он может удалить и другие настройки службы.

**Что сказать:** «Изменил задержку перезапуска через drop-in, проверил эффективное значение, удалил свой drop-in и подтвердил возврат к 3 секундам».

## 8. Пункт защиты №5: посторонний узел не может подключиться к БД

Сначала убедись, что DB включена, `pg_lsclusters` показывает `online`, `/health` возвращает 200.
Проверка недоступности при выключенной БД ничего не доказывает про firewall.

В окне **APP**:

```bash
nc -vz -w 3 172.16.114.20 5432
```

Ждём `succeeded`: серверу приложения доступ разрешён.

Теперь в окне **MAC**, без SSH:

```bash
nc -vz -G 3 172.16.114.20 5432
```

Ждём тайм-аут, на текущем стенде `Operation timed out`. Ключ `-G` здесь для macOS, на Ubuntu используем `-w`.

В окне **DB** покажи причину:

```bash
sudo ufw status numbered
sudo -u postgres psql -Atc 'show listen_addresses;'
sudo grep -n 'campus_app' /etc/postgresql/16/main/pg_hba.conf
```

Правильная картина:

- UFW включён, входящие соединения по умолчанию запрещены.
- 5432 разрешён только от `172.16.114.10`, нет общего разрешения `5432 ALLOW Anywhere`.
- PostgreSQL слушает `127.0.0.1,172.16.114.20`.
- В pg_hba есть `host campus campus_app 172.16.114.10/32 scram-sha-256`.

`/32` — один конкретный IPv4-адрес. UFW ограничивает TCP-доступ, pg_hba отдельно ограничивает допустимые подключения внутри PostgreSQL.

**Что сказать:** «База работает. С сервера приложения TCP-подключение проходит, с моего Mac — нет. Firewall разрешает порт БД только IP сервера приложения. PostgreSQL дополнительно ограничивает доступ через pg_hba».

Если преподаватель требует именно третью Linux-VM, на ней выполни Linux-вариант `nc -vz -w 3 ...`. В текущей проверке посторонним узлом был Mac.

## 9. Дополнительная проверка: автоматический перезапуск после аварии

Это есть в задании, хотя не выделено отдельным пунктом списка защиты.
Делай при работающей БД, в окне **APP**, один раз:

```bash
systemctl show campus -p MainPID -p NRestarts
MAIN_PID=$(systemctl show campus -p MainPID --value)
sudo kill -KILL "$MAIN_PID"
sleep 5
systemctl show campus -p MainPID -p NRestarts -p ActiveState
curl --max-time 10 -i http://127.0.0.1:8000/health
```

Ждём другой PID, увеличившийся счётчик, `ActiveState=active`, HTTP 200.
`kill -KILL` аварийно завершает главный процесс. `Restart=on-failure` заставляет systemd поднять его через 3 секунды.
Обычный `sudo systemctl stop campus` — сознательная остановка: после неё автоперезапуск не должен происходить.
Не повторяй SIGKILL много раз подряд: unit ограничивает частоту запусков.

## 10. Если спросят про остальные требования ЛР2

### Где конфигурация и почему пароль не в коде

На **APP**:

```bash
systemctl cat campus
sudo stat -c '%U:%G %a %n' /etc/campus/campus.env /opt/campus/app
namei -l /etc/campus/campus.env /opt/campus/app
```

В unit видно `EnvironmentFile=/etc/campus/campus.env`. Файл имеет `root:campusapp 640`, каталог кода — `root:campusapp 750`.
640: владелец читает и пишет, группа читает, остальные не имеют доступа. У каталога 750 группа может читать и проходить внутрь, но не менять содержимое.
Не выводи содержимое campus.env на проектор: там пароль БД и SECRET_KEY.

### Как доказать, что приложение не root и не меняет код

```bash
systemctl show campus -p User -p Group
id campusapp
sudo -u campusapp test -r /etc/campus/campus.env && echo 'Конфигурация читается'
sudo -u campusapp test ! -w /opt/campus/app && echo 'Запись в каталог кода запрещена'
```

### SSH по ключу, запрет root и пароля

На каждой VM:

```bash
sudo sshd -T | grep -E 'permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication'
```

Ждём `permitrootlogin no`, `passwordauthentication no`, `kbdinteractiveauthentication no`, `pubkeyauthentication yes`.

### Минимальные права роли БД

На **DB**:

```bash
sudo -u postgres psql -d campus -c '\du+ campus_app'
sudo -u postgres psql -d campus -c '\l+ campus'
sudo -u postgres psql -d campus -c '\dt+'
sudo -u postgres psql -d campus -c '\dp'
```

`campus_app` не суперпользователь и не владелец БД/таблиц. Владелец — `campus_owner`.
Рабочая роль получает CONNECT, доступ к схеме, SELECT/INSERT/UPDATE/DELETE и использование sequence. Изменять структуру базы приложение не должно.

### Где команды повторного развёртывания

В проекте: `deploy/scripts/bootstrap-common.sh`, `setup-db-server.sh`, `setup-app-server.sh`; unit — `deploy/systemd/campus.service`; шаблоны сети — `deploy/netplan/`.
Они нужны для установки. На готовом стенде ради демонстрации заново их не запускай: используй команды проверки из этой шпаргалки.

На действующих VM сетевой файл может называться `50-cloud-init.yaml`, хотя пример в инструкции — `01-campus.yaml`. Найти настоящий файл можно через `sudo ls -l /etc/netplan`. Фактический результат показывай через `ip -br address` и `ip route`.

## 11. Если что-то пошло не так

- **Не подключается SSH к обеим VM:** проверь, включены ли они в Fusion и подключён ли сетевой адаптер. В консоли VM выполни `ip -br address`.
- **Permission denied (publickey):** проверь пользователя `devopsadmin` и ключ `~/.ssh/campus_lab_lr2`. Генерировать новый ключ поверх старого не нужно.
- **HTTP 503:** на DB `pg_lsclusters`; на APP `nc -vz -w 3 172.16.114.20 5432` и `sudo journalctl -u campus -n 60 --no-pager`. Живой процесс ещё не означает доступную БД.
- **Connection refused на APP:8000:** `systemctl status campus --no-pager -l`, затем журнал. После только что выполненного restart подожди пару секунд.
- **Служба упёрлась в лимит запусков:** устрани причину из журнала, затем `sudo systemctl reset-failed campus` и `sudo systemctl start campus`.
- **На БД написано active (exited):** `postgresql.service` — общая служба-обёртка. Проверяй также `postgresql@16-main`, `pg_lsclusters`, порт 5432 и реальный запрос. Одного статуса обёртки недостаточно.
- **С Mac nc к БД молчит:** подожди заданные 3 секунды. Тайм-аут здесь ожидаемый результат изоляции.
- **API без входа вернул 401:** это работа авторизации. Для проверки зависимости от БД используй `/health`, а не анонимный `/api/rooms`.

## 12. Последняя проверка перед окончанием защиты

На **DB**:

```bash
pg_lsclusters
sudo ufw status
```

На **APP**:

```bash
systemctl is-active campus
systemctl show campus -p RestartUSec
curl --max-time 10 -i http://127.0.0.1:8000/health
```

Должны остаться `online`, активный firewall, `active`, `RestartUSec=3s`, HTTP 200.

Главное, что нужно понимать: **процесс работает**, **служба включена в автозапуск**, **приложение готово обслуживать запросы** и **доступ разрешён из сети** — четыре разные проверки.
