"""Небольшой адаптер SQLite/PostgreSQL без ORM."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # PostgreSQL не нужен для локального запуска и unit-тестов.
    psycopg = None
    dict_row = None


class Database:
    """Единый минимальный интерфейс для двух поддерживаемых СУБД."""

    def __init__(self, connection, engine):
        self.connection = connection
        self.engine = engine

    def execute(self, statement, parameters=()):
        if self.engine == "postgresql":
            statement = statement.replace("?", "%s")
        return self.connection.execute(statement, parameters)

    @contextmanager
    def transaction(self):
        try:
            yield
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def close(self):
        self.connection.close()


def connect(config):
    engine = config["DATABASE_ENGINE"]
    if engine == "sqlite":
        connection = sqlite3.connect(config["DATABASE_PATH"], timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return Database(connection, engine)
    if engine != "postgresql":
        raise ValueError("DATABASE_ENGINE должен быть sqlite или postgresql")
    if psycopg is None:
        raise RuntimeError("Для PostgreSQL установите зависимости из requirements.txt")
    required = {
        "DATABASE_HOST": config["DATABASE_HOST"],
        "DATABASE_NAME": config["DATABASE_NAME"],
        "DATABASE_USER": config["DATABASE_USER"],
        "DATABASE_PASSWORD": config["DATABASE_PASSWORD"],
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("Не заданы параметры PostgreSQL: " + ", ".join(missing))
    connection = psycopg.connect(
        host=config["DATABASE_HOST"],
        port=config["DATABASE_PORT"],
        dbname=config["DATABASE_NAME"],
        user=config["DATABASE_USER"],
        password=config["DATABASE_PASSWORD"],
        connect_timeout=3,
        row_factory=dict_row,
    )
    return Database(connection, engine)


def initialize_sqlite(database, schema_path):
    """PostgreSQL-схему создаёт администратор отдельным deploy-скриптом."""

    if database.engine == "sqlite":
        database.connection.executescript(Path(schema_path).read_text())


INTEGRITY_ERRORS = [sqlite3.IntegrityError]
DATABASE_ERRORS = [sqlite3.DatabaseError]
if psycopg is not None:
    INTEGRITY_ERRORS.append(psycopg.IntegrityError)
    DATABASE_ERRORS.append(psycopg.DatabaseError)
