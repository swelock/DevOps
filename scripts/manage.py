"""Командный интерфейс обслуживания БД. Запуск: python -m scripts.manage."""

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from campus.migrations import ROOT, migrate


def database_config():
    load_dotenv(ROOT / ".env")
    return {
        "DATABASE_ENGINE": os.environ.get("DATABASE_ENGINE", "sqlite"),
        "DATABASE_PATH": os.environ.get("DATABASE_PATH", str(ROOT / "instance/campus.sqlite3")),
        "DATABASE_HOST": os.environ.get("DATABASE_HOST", ""),
        "DATABASE_PORT": os.environ.get("DATABASE_PORT", "5432"),
        "DATABASE_NAME": os.environ.get("DATABASE_NAME", ""),
        "DATABASE_USER": os.environ.get("DATABASE_USER", ""),
        "DATABASE_PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
    }


def setup():
    import secrets

    path = ROOT / ".env"
    if not path.exists():
        text = (
            (ROOT / ".env.example")
            .read_text()
            .replace("<REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARACTERS>", secrets.token_hex(32))
        )
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write(text)
    key = os.environ.get("SECRET_KEY") or dotenv_values(path).get("SECRET_KEY", "")
    if not key or len(key) < 32 or key.startswith("<"):
        raise ValueError("Задайте SECRET_KEY в существующем .env (не менее 32 символов)")
    migrate(database_config())
    print("Окружение настроено, конфигурация сохранена, миграции применены.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "migrate", "backup", "restore"])
    parser.add_argument("--file")
    parser.add_argument("--revision", default="head")
    args = parser.parse_args()
    if args.command == "setup":
        setup()
        return
    config = database_config()
    if config["DATABASE_ENGINE"] == "sqlite":
        path = Path(config["DATABASE_PATH"])
        config["DATABASE_PATH"] = str(path if path.is_absolute() else ROOT / path)
    if args.command == "migrate":
        migrate(config, args.revision)
        print("Миграции применены: " + args.revision)
    elif args.command == "backup":
        from campus.backup import backup_database

        suffix = "sqlite3" if config["DATABASE_ENGINE"] == "sqlite" else "dump"
        destination = args.file or str(
            ROOT / "backups" / (datetime.now().strftime("%Y%m%d-%H%M%S-%f") + "." + suffix)
        )
        print(backup_database(config, destination))
    else:
        from campus.backup import restore_database

        if not args.file:
            parser.error("Для restore требуется --file /путь/к/копии")
        restore_database(config, args.file)
        print("Данные восстановлены из " + args.file)


if __name__ == "__main__":
    main()
