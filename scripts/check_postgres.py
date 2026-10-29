"""Проверки PostgreSQL на временных БД; запуск на DB VM от postgres."""

import secrets
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

import psycopg
from psycopg import sql
from werkzeug.security import generate_password_hash

from campus import create_app
from campus.backup import backup_database, restore_database
from campus.database import connect
from campus.migrations import migrate

TABLES = ("buildings", "departments", "rooms", "users", "alembic_version")


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def config_for(name):
    return {
        "DATABASE_ENGINE": "postgresql",
        "DATABASE_HOST": "/var/run/postgresql",
        "DATABASE_PORT": 5432,
        "DATABASE_NAME": name,
        "DATABASE_USER": "postgres",
        # Unix socket использует peer; значение не является рабочим паролем.
        "DATABASE_PASSWORD": "peer",
    }


def snapshot(config):
    with closing(connect(config)) as database:
        return {
            table: [
                dict(row)
                for row in database.connection.execute(
                    sql.SQL("SELECT * FROM {} ORDER BY 1").format(sql.Identifier(table))
                ).fetchall()
            ]
            for table in TABLES
        }


def seed(config, password):
    with closing(connect(config)) as database, database.transaction():
        building_id = database.execute(
            "INSERT INTO buildings (name, address) VALUES (?, ?) RETURNING id",
            ("Исходный корпус", "Москва"),
        ).fetchone()["id"]
        department_id = database.execute(
            "INSERT INTO departments (name) VALUES (?) RETURNING id", ("Исходная кафедра",)
        ).fetchone()["id"]
        database.execute(
            "INSERT INTO rooms (building_id, department_id, number, area, height) "
            "VALUES (?, ?, ?, ?, ?)",
            (building_id, department_id, "101", 40.5, 3.2),
        )
        database.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            ("verify", generate_password_hash(password, method="pbkdf2:sha256")),
        )


def expect_rejected(config, statement, parameters, error_class):
    with closing(connect(config)) as database:
        try:
            with database.transaction():
                database.execute(statement, parameters)
        except error_class:
            return
    raise RuntimeError("PostgreSQL принял данные, нарушающие обязательное ограничение")


def check_constraints(config, original):
    room = original["rooms"][0]
    for value in (0, 1001):
        expect_rejected(
            config,
            "UPDATE rooms SET capacity = ? WHERE id = ?",
            (value, room["id"]),
            psycopg.errors.CheckViolation,
        )
    expect_rejected(
        config,
        "DELETE FROM buildings WHERE id = ?",
        (room["building_id"],),
        psycopg.errors.ForeignKeyViolation,
    )
    expect_rejected(
        config,
        "UPDATE rooms SET department_id = ? WHERE id = ?",
        (999999, room["id"]),
        psycopg.errors.ForeignKeyViolation,
    )
    expect_rejected(
        config,
        "INSERT INTO rooms (building_id, department_id, number, area, height) "
        "VALUES (?, ?, ?, ?, ?)",
        (room["building_id"], room["department_id"], room["number"], 10, 3),
        psycopg.errors.UniqueViolation,
    )
    check(snapshot(config) == original, "Отклонённые операции изменили данные")


def check_head(config):
    with closing(connect(config)) as database:
        version = database.execute("SELECT version_num FROM alembic_version").fetchone()
        check(version["version_num"] == "003", "Ожидалась миграция 003")
        indexes = database.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = ? AND tablename = ?",
            ("public", "rooms"),
        ).fetchall()
        names = {row["indexname"] for row in indexes}
        check(
            {"ix_rooms_building_id", "ix_rooms_department_id"} <= names,
            "Не созданы индексы внешних ключей",
        )


def check_http(config, password):
    app = create_app({**config, "TESTING": True, "SECRET_KEY": secrets.token_hex(32)})
    client = app.test_client()
    token = client.get("/api/auth/session").json["csrf_token"]
    login = client.post(
        "/api/auth/login",
        json={"username": "verify", "password": password},
        headers={"X-CSRF-Token": token},
    )
    check(login.status_code == 200, "Не прошёл вход через HTTP на PostgreSQL")
    client.environ_base["HTTP_X_CSRF_TOKEN"] = login.json["csrf_token"]
    check(client.get("/health").status_code == 200, "PostgreSQL health завершился ошибкой")
    room = client.get("/api/rooms").json[0]
    check(room["volume"] == 129.6, "Неверный расчёт объёма через HTTP/PostgreSQL")
    fields = ("building_id", "department_id", "number", "area", "height")
    payload = {key: room[key] for key in fields}
    payload.update(number="HTTP-102", capacity=50)
    created = client.post("/api/rooms", json=payload)
    check(created.status_code == 201, "Не создано помещение через HTTP/PostgreSQL")
    check(created.json["capacity"] == 50, "Вместимость не сохранилась через HTTP")
    location = created.headers["Location"]
    payload["capacity"] = 75
    changed = client.put(location, json=payload)
    check(changed.status_code == 200 and changed.json["capacity"] == 75, "Ошибка обновления")
    payload["capacity"] = 0
    check(client.put(location, json=payload).status_code == 400, "HTTP принял capacity=0")
    check(client.get(location).json["capacity"] == 75, "Неверный HTTP-запрос изменил запись")
    check(client.delete(location).status_code == 204, "Не удалено помещение через HTTP")
    check(client.get(location).status_code == 404, "Удалённое помещение осталось доступным")
    print("HTTP/PostgreSQL: вход, CRUD вместимости, ошибки и расчёт объёма — OK")


def check_upgrade_and_restore(config):
    password = secrets.token_urlsafe(24)
    migrate(config, "001")
    seed(config, password)
    before_upgrade = snapshot(config)
    migrate(config)
    check_head(config)
    original = snapshot(config)
    for table in ("buildings", "departments", "users"):
        check(original[table] == before_upgrade[table], "Миграция изменила прежние записи")
    old_room = before_upgrade["rooms"][0]
    check(original["rooms"] == [{**old_room, "capacity": 1}], "Не сохранилось помещение")
    check_constraints(config, original)
    print("Заполненная PostgreSQL: миграции 001 → 002 → 003 и ограничения — OK")

    with tempfile.TemporaryDirectory(prefix="campus-pg-backup-") as directory:
        backup = Path(directory) / "original.dump"
        backup_database(config, backup)
        with closing(connect(config)) as database, database.transaction():
            database.execute("DELETE FROM rooms")
            database.execute("UPDATE buildings SET address = ?", ("Повреждено",))
        check(snapshot(config) != original, "Контрольное повреждение не произошло")
        restore_database(config, backup)
        check(snapshot(config) == original, "Восстановленные строки отличаются от оригинала")
    check_constraints(config, original)
    with closing(connect(config)) as database, database.transaction():
        room = original["rooms"][0]
        inserted = database.execute(
            "INSERT INTO rooms (building_id, department_id, number, area, height, capacity) "
            "VALUES (?, ?, ?, ?, ?, ?) RETURNING id",
            (room["building_id"], room["department_id"], "102", 20, 3, 20),
        ).fetchone()
        check(inserted["id"] > room["id"], "Последовательность ID не восстановилась")
    print("PostgreSQL backup → повреждение → restore, все строки и sequence — OK")
    check_http(config, password)


def main():
    names = ["campus_verify_" + uuid.uuid4().hex for _ in range(2)]
    created = []
    # Локальное peer-соединение: скрипт запускается на DB VM от пользователя postgres.
    with psycopg.connect(
        host="/var/run/postgresql", dbname="postgres", user="postgres", autocommit=True
    ) as admin:
        try:
            for name in names:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)
            fresh_config, upgrade_config = map(config_for, names)
            migrate(fresh_config)
            migrate(fresh_config)
            check_head(fresh_config)
            fresh = snapshot(fresh_config)
            check(all(not fresh[table] for table in TABLES[:-1]), "Чистая БД содержит записи")
            print("Чистая PostgreSQL: миграции до 003 и повторное применение — OK")
            check_upgrade_and_restore(upgrade_config)
        finally:
            for name in reversed(created):
                admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    print("Все проверки PostgreSQL пройдены; временные БД удалены")


if __name__ == "__main__":
    main()
