"""Проверки восстановления после удаления и защиты рабочей базы от плохой копии."""

import sqlite3
import subprocess
from unittest.mock import Mock

import pytest

from campus.backup import backup_database, restore_database


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "working.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE buildings (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO buildings VALUES (7, 'Главный')")
    return {"DATABASE_ENGINE": "sqlite", "DATABASE_PATH": str(path)}


def read_buildings(config):
    with sqlite3.connect(config["DATABASE_PATH"]) as connection:
        return connection.execute("SELECT id, name FROM buildings ORDER BY id").fetchall()


def test_backup_and_restore_after_deletion_and_change(database, tmp_path):
    copy = backup_database(database, tmp_path / "copies" / "before.sqlite3")
    assert copy.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(database["DATABASE_PATH"]) as connection:
        connection.execute("DELETE FROM buildings")
        connection.execute("INSERT INTO buildings VALUES (8, 'Повреждено')")
    assert read_buildings(database) == [(8, "Повреждено")]
    restore_database(database, copy)
    assert read_buildings(database) == [(7, "Главный")]
    assert copy.is_file()


def test_restore_into_missing_database(database, tmp_path):
    copy = backup_database(database, tmp_path / "copy.sqlite3")
    restored = dict(database, DATABASE_PATH=str(tmp_path / "new" / "restored.sqlite3"))
    restore_database(restored, copy)
    assert read_buildings(restored) == [(7, "Главный")]


def test_restore_invalid_copy_keeps_original(database, tmp_path):
    invalid = tmp_path / "invalid.sqlite3"
    invalid.write_text("This is not a database")
    with pytest.raises(sqlite3.DatabaseError):
        restore_database(database, invalid)
    assert read_buildings(database) == [(7, "Главный")]


def test_restore_broken_foreign_keys_keeps_original(database, tmp_path):
    broken = tmp_path / "broken.sqlite3"
    with sqlite3.connect(broken) as connection:
        connection.execute("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE children (parent_id INTEGER REFERENCES parents(id))")
        connection.execute("INSERT INTO children VALUES (99)")
    with pytest.raises(ValueError, match="внешние ключи"):
        restore_database(database, broken)
    assert read_buildings(database) == [(7, "Главный")]


def test_backup_does_not_overwrite_existing_copy(database, tmp_path):
    copy = backup_database(database, tmp_path / "copy.sqlite3")
    original = copy.read_bytes()
    with pytest.raises(ValueError, match="уже существует"):
        backup_database(database, copy)
    assert copy.read_bytes() == original
    with pytest.raises(ValueError, match="уже существует"):
        backup_database(database, database["DATABASE_PATH"])


def test_restore_rejects_working_database_as_source(database):
    with pytest.raises(ValueError, match="из неё самой"):
        restore_database(database, database["DATABASE_PATH"])
    assert read_buildings(database) == [(7, "Главный")]


def test_backup_missing_source_does_not_create_empty_database(tmp_path):
    config = {"DATABASE_ENGINE": "sqlite", "DATABASE_PATH": str(tmp_path / "missing.sqlite3")}
    with pytest.raises(ValueError, match="не найден"):
        backup_database(config, tmp_path / "copy.sqlite3")
    assert not (tmp_path / "missing.sqlite3").exists()
    assert not (tmp_path / "copy.sqlite3").exists()
    assert not list(tmp_path.glob(".backup-*"))


def test_restore_missing_copy_keeps_original(database, tmp_path):
    with pytest.raises(ValueError, match="не найден"):
        restore_database(database, tmp_path / "missing.sqlite3")
    assert read_buildings(database) == [(7, "Главный")]


@pytest.fixture
def postgres_config():
    return {
        "DATABASE_ENGINE": "postgresql",
        "DATABASE_HOST": "127.0.0.1",
        "DATABASE_PORT": 5432,
        "DATABASE_NAME": "campus_test",
        "DATABASE_USER": "test_user",
        "DATABASE_PASSWORD": "test-only-value",
    }


def test_postgres_uses_custom_dump_and_transactional_restore(
    postgres_config, tmp_path, monkeypatch
):
    runner = Mock()
    monkeypatch.setattr("campus.backup.shutil.which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr("campus.backup.subprocess.run", runner)
    copy = backup_database(postgres_config, tmp_path / "copy.dump")
    dump = runner.call_args
    assert dump.args[0][0] == "/usr/bin/pg_dump"
    assert "--format=custom" in dump.args[0]
    assert "--schema=public" in dump.args[0]
    assert postgres_config["DATABASE_PASSWORD"] not in dump.args[0]
    assert dump.kwargs["env"]["PGPASSWORD"] == postgres_config["DATABASE_PASSWORD"]
    assert dump.kwargs["check"] is True
    restore_database(postgres_config, copy)
    restore = runner.call_args
    assert restore.args[0][0] == "/usr/bin/pg_restore"
    for flag in ("--single-transaction", "--clean", "--if-exists", "--no-owner", "--no-acl"):
        assert flag in restore.args[0]
    assert str(copy) == restore.args[0][-1]


def test_postgres_failed_dump_removes_partial_file(postgres_config, tmp_path, monkeypatch):
    monkeypatch.setattr("campus.backup.shutil.which", lambda name: "/usr/bin/" + name)
    failure = Mock(side_effect=subprocess.CalledProcessError(1, ["pg_dump"], stderr=b"private"))
    monkeypatch.setattr("campus.backup.subprocess.run", failure)
    with pytest.raises(RuntimeError, match="pg_dump") as error:
        backup_database(postgres_config, tmp_path / "failed.dump")
    assert "private" not in str(error.value)
    assert not list(tmp_path.iterdir())


def test_postgres_missing_client(postgres_config, tmp_path, monkeypatch):
    monkeypatch.setattr("campus.backup.shutil.which", lambda _name: None)
    with pytest.raises(RuntimeError, match="Установите клиент PostgreSQL"):
        backup_database(postgres_config, tmp_path / "copy.dump")


def test_postgres_missing_configuration(postgres_config, tmp_path, monkeypatch):
    monkeypatch.setattr("campus.backup.shutil.which", lambda name: "/usr/bin/" + name)
    postgres_config["DATABASE_PASSWORD"] = ""
    with pytest.raises(ValueError, match="параметры PostgreSQL"):
        backup_database(postgres_config, tmp_path / "copy.dump")


def test_unknown_engine_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="DATABASE_ENGINE"):
        backup_database({"DATABASE_ENGINE": "unknown"}, tmp_path / "copy.dump")
