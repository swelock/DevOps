"""HTTP API и веб-интерфейс учёта аудиторного фонда."""

import math
import os
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

ROOT = Path(__file__).resolve().parent.parent
FIELDS = {
    "buildings": {"name": 100, "address": 250},
    "departments": {"name": 100},
    "rooms": {
        "building_id": None,
        "department_id": None,
        "number": 30,
        "area": None,
        "height": None,
    },
}


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


def get_db():
    if "db" not in g:
        from flask import current_app

        g.db = sqlite3.connect(current_app.config["DATABASE_PATH"], timeout=5)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def validate(resource, data):
    if not isinstance(data, dict) or set(data) != set(FIELDS[resource]):
        raise APIError("Передайте JSON-объект ровно с полями: " + ", ".join(FIELDS[resource]))
    result = {}
    for field, limit in FIELDS[resource].items():
        value = data[field]
        if limit:
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
                raise APIError(f"Поле {field}: строка длиной от 1 до {limit} символов.")
            value = value.strip()
        elif field.endswith("_id"):
            if type(value) is not int or not 1 <= value <= 9223372036854775807:
                raise APIError(f"Поле {field}: положительный целочисленный ID.")
        else:
            maximum = 100000 if field == "area" else 100
            if (
                type(value) not in (int, float)
                or not 0 < value <= maximum
                or not math.isfinite(value)
            ):
                raise APIError(f"Поле {field}: число больше 0 и не больше {maximum}.")
        result[field] = value
    return result


def serialize(resource, row):
    data = dict(row)
    if resource == "rooms":
        data["volume"] = round(data["area"] * data["height"], 2)
    return data


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DATABASE_PATH=os.environ.get("DATABASE_PATH", "instance/campus.sqlite3"),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if config:
        app.config.update(config)
    path = Path(app.config["DATABASE_PATH"])
    if not path.is_absolute():
        path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    app.config["DATABASE_PATH"] = str(path)

    @app.teardown_appcontext
    def close_db(_error):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        get_db().executescript(Path(__file__).with_name("schema.sql").read_text())

    @app.errorhandler(APIError)
    def api_error(error):
        return jsonify(error=error.message), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        messages = {
            400: "Некорректный JSON или запрос.",
            404: "Адрес не найден.",
            405: "Метод не поддерживается.",
            413: "Тело запроса больше 16 КиБ.",
            415: "Ожидается Content-Type: application/json.",
        }
        response = error.get_response()
        response.data = app.json.dumps({"error": messages.get(error.code, error.name)})
        response.content_type = "application/json"
        return response

    @app.errorhandler(sqlite3.IntegrityError)
    def integrity_error(error):
        message = str(error)
        if "UNIQUE constraint" in message:
            text = "Такая запись уже существует: имя или номер помещения в корпусе заняты."
        elif "FOREIGN KEY constraint" in message:
            text = "Связь нарушена: справочник отсутствует или используется помещениями."
        else:
            text = "Данные нарушают ограничения базы данных."
        return jsonify(error=text), 409

    @app.errorhandler(sqlite3.DatabaseError)
    def database_error(error):
        app.logger.error("Database unavailable: %s", error)
        return jsonify(error="База данных недоступна. Повторите запрос позже."), 503

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        for table in FIELDS:
            get_db().execute(f"SELECT id FROM {table} LIMIT 1").fetchone()
        return jsonify(status="ok", database="ok")

    @app.route("/api/<resource>", methods=["GET", "POST"])
    @app.route("/api/<resource>/<int:item_id>", methods=["GET", "PUT", "DELETE"])
    def collection(resource, item_id=None):
        if resource not in FIELDS:
            raise APIError("Ресурс не найден.", 404)
        db = get_db()
        if item_id is not None:
            if not 1 <= item_id <= 9223372036854775807:
                raise APIError("Запись не найдена.", 404)
            row = db.execute(f"SELECT * FROM {resource} WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise APIError("Запись не найдена.", 404)
        if request.method in ("GET", "HEAD"):
            if item_id is not None:
                return jsonify(serialize(resource, row))
            rows = db.execute(f"SELECT * FROM {resource} ORDER BY id").fetchall()
            return jsonify([serialize(resource, row) for row in rows])
        if request.method == "DELETE":
            with db:
                db.execute(f"DELETE FROM {resource} WHERE id = ?", (item_id,))
            return "", 204
        values = validate(resource, request.get_json())
        # Имена таблиц и столбцов взяты из FIELDS, значения всегда параметризованы.
        with db:
            if request.method == "POST":
                fields = ", ".join(values)
                marks = ", ".join("?" for _ in values)
                cursor = db.execute(
                    f"INSERT INTO {resource} ({fields}) VALUES ({marks})", tuple(values.values())
                )
                item_id = cursor.lastrowid
            else:
                assignments = ", ".join(f"{field} = ?" for field in values)
                db.execute(
                    f"UPDATE {resource} SET {assignments} WHERE id = ?", (*values.values(), item_id)
                )
        row = db.execute(f"SELECT * FROM {resource} WHERE id = ?", (item_id,)).fetchone()
        response = jsonify(serialize(resource, row))
        if request.method == "POST":
            response.status_code = 201
            response.headers["Location"] = f"/api/{resource}/{item_id}"
        return response

    return app
