"""Чистая, заполненная и существующая до Alembic база."""

import sqlite3
from pathlib import Path

import pytest

from campus.migrations import ROOT, database_url, migrate


def config_for(path):
    return {"DATABASE_ENGINE": "sqlite", "DATABASE_PATH": str(path)}


def seed(connection):
    connection.execute("INSERT INTO buildings VALUES (1, 'Корпус', 'Москва')")
    connection.execute("INSERT INTO departments VALUES (1, 'ИТ')")
    connection.execute("INSERT INTO rooms VALUES (1, 1, 1, '101', 40, 3)")
    connection.execute("INSERT INTO users VALUES (1, 'operator', 'existing-hash')")
    connection.commit()


def snapshot(connection):
    return {
        table: connection.execute(f"SELECT * FROM {table}").fetchall()
        for table in ("buildings", "departments", "rooms", "users")
    }


def test_clean_database_and_repeated_upgrade(tmp_path):
    config = config_for(tmp_path / "clean.sqlite3")
    migrate(config)
    migrate(config)
    with sqlite3.connect(config["DATABASE_PATH"]) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("003",)
        assert {row[1] for row in db.execute("PRAGMA table_info(rooms)")} == {
            "id",
            "building_id",
            "department_id",
            "number",
            "area",
            "height",
            "capacity",
        }
        indexes = {row[1] for row in db.execute("PRAGMA index_list(rooms)")}
        assert {"ix_rooms_building_id", "ix_rooms_department_id"} <= indexes


@pytest.mark.parametrize("legacy", [False, True])
def test_upgrade_preserves_all_old_data_and_foreign_keys(tmp_path, legacy):
    config = config_for(tmp_path / "populated.sqlite3")
    if not legacy:
        migrate(config, "001")
    with sqlite3.connect(config["DATABASE_PATH"]) as db:
        if legacy:
            db.executescript((ROOT / "campus/schema.sql").read_text())
        seed(db)
        before = snapshot(db)
    migrate(config, "002")
    with sqlite3.connect(config["DATABASE_PATH"]) as db:
        assert snapshot(db) == before
    migrate(config)
    with sqlite3.connect(config["DATABASE_PATH"]) as db:
        after = snapshot(db)
        assert after["rooms"] == [(*before["rooms"][0], 1)]
        for table in ("buildings", "departments", "users"):
            assert after[table] == before[table]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for capacity in (0, 1001, None):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("UPDATE rooms SET capacity = ?", (capacity,))
        db.execute("UPDATE rooms SET capacity = 1000")
        assert db.execute("SELECT capacity FROM rooms").fetchone() == (1000,)


def test_database_url_and_unknown_engine(tmp_path):
    config = config_for(tmp_path / "dir/file.sqlite3")
    assert Path(database_url(config).database).parent.is_dir()
    config["DATABASE_ENGINE"] = "mysql"
    with pytest.raises(ValueError, match="DATABASE_ENGINE"):
        database_url(config)
    url = database_url(
        dict(
            DATABASE_ENGINE="postgresql",
            DATABASE_USER="u",
            DATABASE_PASSWORD="secret@:/",
            DATABASE_HOST="localhost",
            DATABASE_NAME="test",
            DATABASE_PORT="5432",
        )
    )
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "secret@:/"
    assert "secret" not in str(url)


def test_failed_schema_change_rolls_back_ddl_and_revision(tmp_path, monkeypatch):
    from alembic import op

    config = config_for(tmp_path / "atomic.sqlite3")
    migrate(config, "001")
    real_create_index = op.create_index

    def fail_second_index(name, *args, **kwargs):
        if name == "ix_rooms_department_id":
            raise RuntimeError("Контрольный отказ второй DDL-команды")
        return real_create_index(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(op, "create_index", fail_second_index)
        with pytest.raises(RuntimeError, match="Контрольный отказ"):
            migrate(config)
    with sqlite3.connect(config["DATABASE_PATH"]) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("001",)
        indexes = {row[1] for row in db.execute("PRAGMA index_list(rooms)")}
        assert "ix_rooms_building_id" not in indexes
    migrate(config)
    with sqlite3.connect(config["DATABASE_PATH"]) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("003",)
