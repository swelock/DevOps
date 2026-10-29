"""Интеграция с настоящей SQLite: ограничения, транзакции, изоляция."""

import sqlite3

import pytest

from campus.database import connect


@pytest.fixture
def database(app):
    db = connect(app.config)
    with db.transaction():
        db.execute("INSERT INTO buildings (name, address) VALUES (?, ?)", ("Главный", "Москва"))
        db.execute("INSERT INTO departments (name) VALUES (?)", ("ИТ",))
    yield db
    db.close()


@pytest.mark.parametrize(
    "statement,parameters",
    [
        ("INSERT INTO buildings (name, address) VALUES (?, ?)", ("Главный", "Другой адрес")),
        ("INSERT INTO buildings (name, address) VALUES (?, ?)", ("Другой", " ")),
        ("INSERT INTO departments (name) VALUES (?)", ("ИТ",)),
        ("INSERT INTO departments (name) VALUES (?)", (" ",)),
        (
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 1, "101", 0, 3),
        ),
        (
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 1, "101", 100001, 3),
        ),
        (
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 1, "101", 20, 0),
        ),
        (
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 1, "101", 20, 101),
        ),
        (
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (999, 1, "101", 20, 3),
        ),
        (
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 999, "101", 20, 3),
        ),
    ],
)
def test_database_rejects_invalid_direct_sql(database, statement, parameters):
    with pytest.raises(sqlite3.IntegrityError), database.transaction():
        database.execute(statement, parameters)
    assert database.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0
    assert database.execute("SELECT COUNT(*) FROM buildings").fetchone()[0] == 1
    assert database.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 1


def test_transaction_rolls_back_all_writes_on_later_failure(database):
    with pytest.raises(sqlite3.IntegrityError), database.transaction():
        database.execute("INSERT INTO departments (name) VALUES (?)", ("Успешная первая запись",))
        database.execute("INSERT INTO departments (name) VALUES (?)", ("ИТ",))
    names = [row["name"] for row in database.execute("SELECT name FROM departments").fetchall()]
    assert names == ["ИТ"]
    with database.transaction():
        database.execute("INSERT INTO departments (name) VALUES (?)", ("После отката",))
    assert database.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 2


def test_transaction_rolls_back_application_exception(database):
    with pytest.raises(ValueError, match="Ошибка после записи"), database.transaction():
        database.execute("UPDATE departments SET name = ? WHERE id = ?", ("Изменённое", 1))
        raise ValueError("Ошибка после записи")
    assert (
        database.execute("SELECT name FROM departments WHERE id = ?", (1,)).fetchone()["name"]
        == "ИТ"
    )


def test_committed_data_visible_to_another_connection(app, database):
    with database.transaction():
        database.execute("INSERT INTO departments (name) VALUES (?)", ("Вторая кафедра",))
    second = connect(app.config)
    try:
        assert (
            second.execute("SELECT name FROM departments WHERE id = ?", (2,)).fetchone()["name"]
            == "Вторая кафедра"
        )
    finally:
        second.close()


def test_separate_database_has_no_test_records(app, database, tmp_path):
    isolated = connect(dict(app.config, DATABASE_PATH=str(tmp_path / "isolated.sqlite3")))
    try:
        assert (
            isolated.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []
        )
        assert database.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 1
    finally:
        isolated.close()


def test_database_connection_closes(app):
    database = connect(app.config)
    database.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        database.execute("SELECT 1")


@pytest.mark.parametrize("parent", ["buildings", "departments"])
def test_parent_delete_restricted_by_actual_foreign_key(database, parent):
    with database.transaction():
        database.execute(
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (1, 1, "101", 20, 3),
        )
    with pytest.raises(sqlite3.IntegrityError), database.transaction():
        database.execute(f"DELETE FROM {parent} WHERE id = ?", (1,))
    assert database.execute(f"SELECT COUNT(*) FROM {parent}").fetchone()[0] == 1
    assert database.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 1
