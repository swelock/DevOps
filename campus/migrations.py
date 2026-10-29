"""Применение Alembic к SQLite и PostgreSQL без ORM."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parent.parent


def database_url(config):
    if config["DATABASE_ENGINE"] == "sqlite":
        path = Path(config["DATABASE_PATH"])
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return URL.create("sqlite", database=str(path))
    if config["DATABASE_ENGINE"] != "postgresql":
        raise ValueError("DATABASE_ENGINE должен быть sqlite или postgresql")
    return URL.create(
        "postgresql+psycopg",
        username=config["DATABASE_USER"],
        password=config["DATABASE_PASSWORD"],
        host=config["DATABASE_HOST"],
        port=int(config["DATABASE_PORT"]),
        database=config["DATABASE_NAME"],
    )


def migrate(config, revision="head"):
    settings = Config()
    settings.set_main_option("script_location", str(ROOT / "migrations"))
    engine = create_engine(database_url(config), poolclass=NullPool)
    try:
        with engine.begin() as connection:
            if engine.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                # sqlite3 в legacy-режиме сам не начинает транзакцию для DDL.
                connection.exec_driver_sql("BEGIN")
            settings.attributes["connection"] = connection
            command.upgrade(settings, revision)
    finally:
        engine.dispose()
