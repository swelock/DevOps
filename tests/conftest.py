import pytest
from werkzeug.security import generate_password_hash

from campus import create_app, get_db

TEST_PASSWORD = "test-password-123"
TEST_HASH = generate_password_hash(TEST_PASSWORD, method="pbkdf2:sha256")


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-only-for-tests-32-characters")
    monkeypatch.setenv("DATABASE_ENGINE", "sqlite")


def add_test_user(app):
    with app.app_context():
        with get_db().transaction():
            get_db().execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)", ("tester", TEST_HASH)
            )


def sign_in(client):
    token = client.get("/api/auth/session").json["csrf_token"]
    response = client.post(
        "/api/auth/login",
        json={"username": "tester", "password": TEST_PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    client.environ_base["HTTP_X_CSRF_TOKEN"] = response.json["csrf_token"]
    return client


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE_PATH": str(tmp_path / "test.sqlite3")})


@pytest.fixture
def client(app):
    add_test_user(app)
    return sign_in(app.test_client())
