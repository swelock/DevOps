"""Повторная первоначальная настройка сохраняет секрет и пользовательские данные."""

import sqlite3

import pytest
from dotenv import dotenv_values

from scripts import manage


def test_setup_creates_secret_and_preserves_existing_data(tmp_path, monkeypatch):
    template = "SECRET_KEY=<REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARACTERS>\n"
    (tmp_path / ".env.example").write_text(template)
    monkeypatch.setattr(manage, "ROOT", tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    database_path = tmp_path / "working.sqlite3"
    monkeypatch.setattr(
        manage,
        "database_config",
        lambda: {
            "DATABASE_ENGINE": "sqlite",
            "DATABASE_PATH": str(database_path),
        },
    )
    manage.setup()
    env = (tmp_path / ".env").read_bytes()
    assert len(dotenv_values(tmp_path / ".env")["SECRET_KEY"]) == 64
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(database_path) as db:
        db.execute("INSERT INTO departments (name) VALUES (?)", ("Сохранить",))
    manage.setup()
    assert (tmp_path / ".env").read_bytes() == env
    with sqlite3.connect(database_path) as db:
        assert db.execute("SELECT name FROM departments").fetchall() == [("Сохранить",)]
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == ("003",)


def test_setup_rejects_invalid_existing_secret_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(manage, "ROOT", tmp_path)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    existing = "SECRET_KEY=short\n"
    (tmp_path / ".env").write_text(existing)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        manage.setup()
    assert (tmp_path / ".env").read_text() == existing
