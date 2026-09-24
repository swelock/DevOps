# Черновик PR для ЛР2

## Заголовок

`feat: deploy campus application as a Linux service`

## Связанная задача

`Closes LR2-01` — после создания GitHub Issue заменить на фактическую ссылку и номер.

## Что изменено

- добавлен PostgreSQL-режим приложения с сохранением SQLite для локальной разработки;
- добавлены Linux-пользователи, SSH hardening, статическая адресация и UFW;
- приложение устанавливается в `/opt/campus` и запускается через Gunicorn/systemd;
- схема PostgreSQL создаётся владельцем без права входа, прикладная роль получает
  только `CONNECT`, `USAGE`, CRUD таблиц и доступ к последовательностям;
- секретная конфигурация создаётся на сервере вне репозитория;
- добавлены сценарий защиты и повторяемые скрипты.

## Проверки автора

- [ ] `make verify`
- [ ] развёртывание на двух чистых Ubuntu VM
- [ ] `sudo deploy/scripts/verify-host.sh app`
- [ ] `sudo deploy/scripts/verify-host.sh db`
- [ ] полная проверка `docs/LR2-CHECKLIST.md`

## Критические файлы приёмки

Изменены `Makefile` и `requirements.txt`: добавлена проверка shell-скриптов и
runtime-зависимости Gunicorn/psycopg. Проверки не отключались и не ослаблялись.
