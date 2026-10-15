import logging
import sqlite3

import pytest
from conftest import TEST_PASSWORD

from campus import create_app


def test_anonymous_access(app):
    guest = app.test_client()
    assert guest.get("/").headers["Location"] == "/login"
    assert guest.get("/login").status_code == 200
    assert guest.get("/health").status_code == 200
    for method, url in [
        ("GET", "/api/rooms"),
        ("POST", "/api/buildings"),
        ("PUT", "/api/rooms/1"),
        ("DELETE", "/api/rooms/1"),
    ]:
        assert guest.open(url, method=method, json={}).status_code == 401


def test_login_logout_and_csrf(app, client):
    guest = app.test_client()
    token = guest.get("/api/auth/session").json["csrf_token"]
    payload = {"username": "tester", "password": TEST_PASSWORD}
    assert guest.post("/api/auth/login", json=payload).status_code == 403
    assert (
        guest.post("/api/auth/login", json=payload, headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    response = guest.post("/api/auth/login", json=payload, headers={"X-CSRF-Token": token})
    assert response.status_code == 200
    new_token = response.json["csrf_token"]
    assert new_token != token
    assert response.json["user"]["username"] == "tester"
    assert "password" not in response.get_data(as_text=True)
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    assert guest.get("/").status_code == 200
    assert guest.post("/api/departments", json={"name": "ИТ"}).status_code == 403
    assert guest.post("/api/auth/logout", headers={"X-CSRF-Token": new_token}).status_code == 204
    assert guest.get("/api/rooms").status_code == 401
    assert guest.get("/api/auth/session").json["user"] is None


@pytest.mark.parametrize("username,password", [("tester", "incorrect"), ("missing", "incorrect")])
def test_wrong_credentials(app, client, caplog, username, password):
    guest = app.test_client()
    token = guest.get("/api/auth/session").json["csrf_token"]
    with caplog.at_level(logging.INFO, logger="campus"):
        response = guest.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            headers={"X-CSRF-Token": token},
        )
    assert response.status_code == 401
    assert response.json["error"] == "Неверный логин или пароль."
    assert "Login failed" in caplog.text
    assert password not in caplog.text
    assert token not in caplog.text
    assert guest.get("/api/rooms").status_code == 401


def test_html_login(app, client):
    guest = app.test_client()
    token = guest.get("/api/auth/session").json["csrf_token"]
    wrong = guest.post(
        "/login", data={"username": "tester", "password": "wrong", "csrf_token": token}
    )
    assert wrong.status_code == 401
    assert "Неверный логин" in wrong.get_data(as_text=True)
    response = guest.post(
        "/login", data={"username": "tester", "password": TEST_PASSWORD, "csrf_token": token}
    )
    assert response.status_code == 302
    assert guest.get("/").status_code == 200


def test_create_user_cli(app):
    runner = app.test_cli_runner()
    result = runner.invoke(
        args=["create-user", "operator"], input="strong-password-123\nstrong-password-123\n"
    )
    assert result.exit_code == 0
    with sqlite3.connect(app.config["DATABASE_PATH"]) as db:
        stored = db.execute("SELECT password_hash FROM users WHERE username='operator'").fetchone()[
            0
        ]
    assert stored.startswith("pbkdf2:sha256:")
    assert "strong-password-123" not in stored
    assert "strong-password-123" not in result.output
    assert (
        runner.invoke(
            args=["create-user", "operator"], input="strong-password-123\nstrong-password-123\n"
        ).exit_code
        != 0
    )
    assert runner.invoke(args=["create-user", "short"], input="tiny\ntiny\n").exit_code != 0


def test_deleted_user_session_rejected(app, client):
    with sqlite3.connect(app.config["DATABASE_PATH"]) as db:
        db.execute("DELETE FROM users")
    assert client.get("/api/rooms").status_code == 401


def test_database_error_logged(app, caplog):
    guest = app.test_client()
    with sqlite3.connect(app.config["DATABASE_PATH"]) as db:
        db.execute("DROP TABLE users")
    with caplog.at_level(logging.ERROR, logger="campus"):
        assert guest.get("/health").status_code == 503
    assert "Database unavailable" in caplog.text
    assert "Traceback" in caplog.text


def test_unhandled_error_json_and_log(app, caplog):
    app.config["TESTING"] = False

    @app.get("/test-failure")
    def fail():
        raise RuntimeError("deliberate failure")

    with caplog.at_level(logging.ERROR, logger="campus"):
        response = app.test_client().get("/test-failure")
    assert response.status_code == 500
    assert "error" in response.json
    assert "deliberate failure" not in response.get_data(as_text=True)
    assert "deliberate failure" in caplog.text


@pytest.mark.parametrize(
    "secret", ["", "short", "<REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARACTERS>"]
)
def test_secret_required(tmp_path, secret):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app({"DATABASE_PATH": str(tmp_path / "db"), "SECRET_KEY": secret})
