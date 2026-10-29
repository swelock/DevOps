"""Резервные копии SQLite и PostgreSQL без передачи паролей в аргументах."""

# subprocess нужен для pg_dump/pg_restore; вызов ниже передаёт argv без shell.
import os
import shutil
import sqlite3
import subprocess  # nosec B404
import tempfile
from contextlib import closing
from pathlib import Path


def _sqlite_source(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Файл базы данных не найден.")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Нарушена целостность SQLite.")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Нарушены внешние ключи SQLite.")
    except Exception:
        connection.close()
        raise
    return connection


def _postgres_command(config, program, options):
    executable = shutil.which(program)
    if executable is None:
        raise RuntimeError(f"Установите клиент PostgreSQL: команда {program} не найдена.")
    required = ("DATABASE_HOST", "DATABASE_NAME", "DATABASE_USER", "DATABASE_PASSWORD")
    if any(not config.get(name) for name in required):
        raise ValueError("Не заданы обязательные параметры PostgreSQL.")
    environment = os.environ.copy()
    environment.update(
        PGHOST=str(config["DATABASE_HOST"]),
        PGPORT=str(config.get("DATABASE_PORT", 5432)),
        PGDATABASE=str(config["DATABASE_NAME"]),
        PGUSER=str(config["DATABASE_USER"]),
        PGPASSWORD=str(config["DATABASE_PASSWORD"]),
        PGCONNECT_TIMEOUT="5",
    )
    try:
        # Абсолютный путь получен через which; аргументы отдельные, пароль только в env.
        subprocess.run(  # nosec B603
            [executable, "--no-password", *options],
            env=environment,
            shell=False,
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError):
        raise RuntimeError(f"Команда {program} завершилась с ошибкой.") from None


def _engine(config):
    engine = config["DATABASE_ENGINE"]
    if engine not in ("sqlite", "postgresql"):
        raise ValueError("DATABASE_ENGINE должен быть sqlite или postgresql")
    return engine


def backup_database(config, destination):
    """Создать новую копию. Существующий файл не перезаписывается; права 0600."""
    engine = _engine(config)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Файл резервной копии уже существует.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".backup-", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        if engine == "sqlite":
            with closing(_sqlite_source(config["DATABASE_PATH"])) as source:
                with closing(sqlite3.connect(temporary)) as target:
                    source.backup(target)
        else:
            _postgres_command(
                config,
                "pg_dump",
                [
                    "--format=custom",
                    "--schema=public",
                    "--no-owner",
                    "--no-acl",
                    "--file",
                    str(temporary),
                ],
            )
        # Создание hard link атомарно отказывается перезаписывать уже появившийся файл.
        os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def restore_database(config, source):
    """Восстановить копию; приложение должно быть остановлено перед выполнением."""
    engine = _engine(config)
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError("Файл резервной копии не найден.")
    if engine == "postgresql":
        _postgres_command(
            config,
            "pg_restore",
            [
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--single-transaction",
                "--exit-on-error",
                "--schema=public",
                "--dbname",
                str(config["DATABASE_NAME"]),
                str(source),
            ],
        )
        return
    destination = Path(config["DATABASE_PATH"]).resolve()
    if source == destination:
        raise ValueError("Нельзя восстановить базу из неё самой.")
    # До открытия рабочей базы проверяем файл целиком, включая внешние ключи.
    with closing(_sqlite_source(source)) as backup:
        destination.parent.mkdir(parents=True, exist_ok=True)
        # SQLite backup выполняет замену данных одной транзакцией, включая базу в WAL.
        with closing(sqlite3.connect(destination)) as database:
            backup.backup(database)
    os.chmod(destination, 0o600)
