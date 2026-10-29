"""HTTP API и веб-интерфейс учёта аудиторного фонда."""

import logging
import math
import os
import secrets
from datetime import timedelta
from pathlib import Path

import click
from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from campus.database import DATABASE_ERRORS, INTEGRITY_ERRORS, connect

ROOT = Path(__file__).resolve().parent.parent
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32), method="pbkdf2:sha256")
FIELDS = {
    "buildings": {"name": 100, "address": 250},
    "departments": {"name": 100},
    "rooms": {
        "building_id": None,
        "department_id": None,
        "number": 30,
        "area": None,
        "height": None,
        "capacity": None,
    },
}


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


def get_db():
    if "db" not in g:
        from flask import current_app

        g.db = connect(current_app.config)
    return g.db


def validate(resource, data):
    # Старые клиенты не передавали вместимость; PUT по-прежнему заменяет всю запись.
    if resource == "rooms" and isinstance(data, dict) and "capacity" not in data:
        data = dict(data, capacity=1)
    if not isinstance(data, dict) or set(data) != set(FIELDS[resource]):
        raise APIError("Передайте JSON-объект ровно с полями: " + ", ".join(FIELDS[resource]))
    result = {}
    for field, limit in FIELDS[resource].items():
        value = data[field]
        if limit:
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
                raise APIError(f"Поле {field}: строка длиной от 1 до {limit} символов.")
            value = value.strip()
        elif field == "capacity":
            if type(value) is not int or not 1 <= value <= 1000:
                raise APIError("Поле capacity: целое число от 1 до 1000 мест.")
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
        DATABASE_ENGINE=os.environ.get("DATABASE_ENGINE", "sqlite"),
        DATABASE_PATH=os.environ.get("DATABASE_PATH", "instance/campus.sqlite3"),
        DATABASE_HOST=os.environ.get("DATABASE_HOST", ""),
        DATABASE_PORT=int(os.environ.get("DATABASE_PORT", "5432")),
        DATABASE_NAME=os.environ.get("DATABASE_NAME", ""),
        DATABASE_USER=os.environ.get("DATABASE_USER", ""),
        DATABASE_PASSWORD=os.environ.get("DATABASE_PASSWORD", ""),
        MAX_CONTENT_LENGTH=16 * 1024,
        SECRET_KEY=os.environ.get("SECRET_KEY", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_REFRESH_EACH_REQUEST=False,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    if config:
        app.config.update(config)
    if (
        not app.config["SECRET_KEY"]
        or len(app.config["SECRET_KEY"]) < 32
        or app.config["SECRET_KEY"].startswith("<")
    ):
        raise ValueError("Задайте SECRET_KEY длиной не менее 32 символов в окружении или .env")
    app.logger.setLevel(logging.INFO)
    if app.config["DATABASE_ENGINE"] == "sqlite":
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

    if app.config["DATABASE_ENGINE"] == "sqlite":
        from campus.migrations import migrate

        migrate(app.config)
    elif app.config["DATABASE_ENGINE"] != "postgresql":
        raise ValueError("DATABASE_ENGINE должен быть sqlite или postgresql")

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.cli.command("create-user")
    @click.argument("username")
    @click.password_option(confirmation_prompt=True)
    def create_user(username, password):
        """Создать пользователя; пароль вводится скрыто и не попадает в историю shell."""
        username = username.strip()
        if not 1 <= len(username) <= 100 or not 10 <= len(password) <= 128:
            raise click.ClickException("Логин: 1–100 символов; пароль: 10–128 символов.")
        db = get_db()
        if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            raise click.ClickException("Такой пользователь уже существует.")
        with db.transaction():
            db.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password, method="pbkdf2:sha256")),
            )
        click.echo("Пользователь создан.")

    @app.before_request
    def protect_requests():
        if request.endpoint is None or request.endpoint == "static":
            return None
        g.user = None
        if session.get("user_id"):
            g.user = (
                get_db()
                .execute("SELECT id, username FROM users WHERE id = ?", (session["user_id"],))
                .fetchone()
            )
        if request.endpoint in ("index", "collection") and g.user is None:
            if request.endpoint == "index":
                return redirect(url_for("login"))
            raise APIError("Сначала войдите в систему.", 401)
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            token = request.headers.get("X-CSRF-Token")
            if request.endpoint == "login":
                token = request.form.get("csrf_token")
            expected = session.get("csrf_token")
            if not token or not expected or not secrets.compare_digest(token, expected):
                raise APIError("Неверный защитный токен. Обновите страницу.", 403)

    def authenticate(username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            raise APIError("Передайте логин и пароль строками.")
        if not 1 <= len(username.strip()) <= 100 or not 1 <= len(password) <= 128:
            raise APIError("Некорректная длина логина или пароля.")
        user = (
            get_db()
            .execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
            .fetchone()
        )
        # Проверка фиктивного хеша сохраняет одинаковый путь для неизвестного логина.
        password_hash = user["password_hash"] if user else app.config["DUMMY_PASSWORD_HASH"]
        if not check_password_hash(password_hash, password) or user is None:
            app.logger.warning("Login failed")
            raise APIError("Неверный логин или пароль.", 401)
        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        csrf_token()
        app.logger.info("Login succeeded user_id=%s", user["id"])
        return {"id": user["id"], "username": user["username"]}

    app.config["DUMMY_PASSWORD_HASH"] = DUMMY_PASSWORD_HASH

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        if request.method == "POST":
            try:
                authenticate(request.form.get("username"), request.form.get("password"))
            except APIError as exc:
                error = exc.message
                return render_template("login.html", error=error), exc.status
            return redirect(url_for("index"))
        return render_template("login.html", error=error)

    @app.get("/api/auth/session")
    def auth_session():
        return jsonify(user=dict(g.user) if g.user else None, csrf_token=csrf_token())

    @app.post("/api/auth/login")
    def auth_login():
        data = request.get_json()
        if not isinstance(data, dict) or set(data) != {"username", "password"}:
            raise APIError("Передайте username и password.")
        user = authenticate(data["username"], data["password"])
        return jsonify(user=user, csrf_token=csrf_token())

    @app.post("/api/auth/logout")
    def auth_logout():
        app.logger.info("Logout user_id=%s", session.get("user_id"))
        session.clear()
        return "", 204

    @app.after_request
    def log_response(response):
        app.logger.info("HTTP %s %s status=%s", request.method, request.path, response.status_code)
        if request.endpoint in (
            "index",
            "login",
            "auth_session",
            "auth_login",
            "auth_logout",
            "collection",
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

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

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify(error="Внутренняя ошибка сервера. Обратитесь к администратору."), 500

    def integrity_error(error):
        message = str(error).lower()
        if "unique" in message or "duplicate key" in message:
            text = "Такая запись уже существует: имя или номер помещения в корпусе заняты."
        elif "foreign key" in message:
            text = "Связь нарушена: справочник отсутствует или используется помещениями."
        else:
            text = "Данные нарушают ограничения базы данных."
        return jsonify(error=text), 409

    def database_error(error):
        app.logger.exception("Database unavailable")
        return jsonify(error="База данных недоступна. Повторите запрос позже."), 503

    for error_class in INTEGRITY_ERRORS:
        app.register_error_handler(error_class, integrity_error)
    for error_class in DATABASE_ERRORS:
        app.register_error_handler(error_class, database_error)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        for table in (*FIELDS, "users"):
            # Имена из FIELDS, значения параметризованы.
            get_db().execute(f"SELECT id FROM {table} LIMIT 1").fetchone()  # nosec B608
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
            # Имена из FIELDS, значения параметризованы.
            row = db.execute(f"SELECT * FROM {resource} WHERE id = ?", (item_id,)).fetchone()  # nosec B608
            if row is None:
                raise APIError("Запись не найдена.", 404)
        if request.method in ("GET", "HEAD"):
            if item_id is not None:
                return jsonify(serialize(resource, row))
            # Имена из FIELDS, значения параметризованы.
            rows = db.execute(f"SELECT * FROM {resource} ORDER BY id").fetchall()  # nosec B608
            return jsonify([serialize(resource, row) for row in rows])
        if request.method == "DELETE":
            with db.transaction():
                # Имена из FIELDS, значения параметризованы.
                db.execute(f"DELETE FROM {resource} WHERE id = ?", (item_id,))  # nosec B608
            return "", 204
        values = validate(resource, request.get_json())
        # Имена таблиц и столбцов взяты из FIELDS, значения всегда параметризованы.
        with db.transaction():
            if request.method == "POST":
                fields = ", ".join(values)
                marks = ", ".join("?" for _ in values)
                returning = " RETURNING id" if db.engine == "postgresql" else ""
                cursor = db.execute(
                    # Имена из FIELDS, значения параметризованы.
                    f"INSERT INTO {resource} ({fields}) VALUES ({marks}){returning}",  # nosec B608
                    tuple(values.values()),
                )
                item_id = cursor.fetchone()["id"] if returning else cursor.lastrowid
            else:
                assignments = ", ".join(f"{field} = ?" for field in values)
                db.execute(
                    # Имена из FIELDS, значения параметризованы.
                    f"UPDATE {resource} SET {assignments} WHERE id = ?",  # nosec B608
                    (*values.values(), item_id),
                )
        # Имена из FIELDS, значения параметризованы.
        row = db.execute(f"SELECT * FROM {resource} WHERE id = ?", (item_id,)).fetchone()  # nosec B608
        response = jsonify(serialize(resource, row))
        if request.method == "POST":
            response.status_code = 201
            response.headers["Location"] = f"/api/{resource}/{item_id}"
        return response

    return app
