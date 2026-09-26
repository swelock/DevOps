# Результаты проверки ЛР2

Дата проверки: 26 сентября 2026 года.

## Выполнено локально

```text
make verify
Ruff: успешно
Ruff format --check: успешно
Pytest: 43 passed
bash -n deploy/scripts/*.sh: успешно
поиск явных секретов: совпадений нет
git diff --check: успешно
```

Пакеты `gunicorn==23.0.0`, `psycopg==3.2.10` и
`psycopg-binary==3.2.10` установлены из `requirements-dev.txt`. Команда
`gunicorn --check-config 'campus:create_app()'` завершилась успешно.

Выполнен smoke-тест через Gunicorn с двумя worker-процессами на локальной SQLite:

```text
GET http://127.0.0.1:8012/health
200 OK
{"database":"ok","status":"ok"}
```

## Проверено на Linux-стенде

Стенд развёрнут в VMware Fusion на двух Ubuntu Server 24.04 ARM64:

| Узел | Адрес | Служба | Результат после перезагрузки |
|---|---:|---|---|
| `campus-app` | `172.16.114.10/24` | `campus.service` | `enabled`, `active` |
| `campus-db` | `172.16.114.20/24` | `postgresql.service` | `enabled`, `active` |

Проверены следующие сценарии:

- вход по ключу под `devopsadmin`; `PermitRootLogin no`,
  `PasswordAuthentication no`, `PubkeyAuthentication yes`;
- приложение слушает `0.0.0.0:8000`, процессы Gunicorn принадлежат
  `campusapp`, PostgreSQL слушает только `127.0.0.1` и `172.16.114.20`;
- UFW разрешает `5432/tcp` только от `172.16.114.10`; соединение с сервера
  приложения успешно, с хоста VMware завершается тайм-аутом;
- `POST` для корпуса, подразделения и помещения возвращает `201`, объём
  помещения `48.5 × 3.2` рассчитан как `155.2`;
- после `SIGKILL` главного Gunicorn PID служба вернулась в `active`, PID
  изменился, `NRestarts` увеличился с 0 до 1;
- при остановленном PostgreSQL `/health` вернул HTTP 503, после запуска БД —
  снова HTTP 200;
- после перезагрузки обеих VM адреса сохранились, службы стартовали
  автоматически, тестовые данные остались в PostgreSQL;
- итоговый `GET http://172.16.114.10:8000/health`:
  `{"database":"ok","status":"ok"}`.
