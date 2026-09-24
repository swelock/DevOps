# Результаты локальной проверки ЛР2

Дата проверки: 24 сентября 2026 года.

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

## Требует проверки на Linux-стенде

На текущем компьютере отсутствуют Vagrant, Multipass и VirtualBox, поэтому нельзя
достоверно заявить о создании и перезагрузке двух VM. После создания стенда нужно
пройти `deploy/README.md` и все шаги `docs/LR2-CHECKLIST.md`, зафиксировать вывод
команд и только затем отметить стендовую часть ЛР2 выполненной.
