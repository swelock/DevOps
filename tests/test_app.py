import sqlite3

import pytest

from campus import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE_PATH": str(tmp_path / "test.sqlite3")})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def room(client):
    building = client.post("/api/buildings", json={"name": "Главный", "address": "Москва"})
    department = client.post("/api/departments", json={"name": "Кафедра ИТ"})
    return {
        "building_id": building.json["id"],
        "department_id": department.json["id"],
        "number": "101",
        "area": 40.5,
        "height": 3.2,
    }


@pytest.mark.parametrize(
    "resource,payload,update",
    [
        (
            "buildings",
            {"name": "Корпус", "address": "Адрес"},
            {"name": "Новый", "address": "Адрес 2"},
        ),
        ("departments", {"name": "Кафедра"}, {"name": "Деканат"}),
        ("rooms", None, None),
    ],
)
def test_crud(client, room, resource, payload, update):
    payload = payload or room
    update = update or dict(room, area=50, height=4, number="102")
    url = f"/api/{resource}"
    created = client.post(url, json=payload)
    assert created.status_code == 201
    location = created.headers["Location"]
    assert client.get(location).json == created.json
    assert created.json in client.get(url).json
    changed = client.put(location, json=update)
    assert changed.status_code == 200
    for key, value in update.items():
        assert changed.json[key] == value
    if resource == "rooms":
        assert created.json["volume"] == 129.6
        assert changed.json["volume"] == 200
    assert client.delete(location).status_code == 204
    assert client.get(location).status_code == 404


def test_unique_number_is_scoped_to_building(client, room):
    assert client.post("/api/rooms", json=room).status_code == 201
    assert client.post("/api/rooms", json=room).status_code == 409
    second = client.post("/api/buildings", json={"name": "Второй", "address": "Адрес"}).json
    assert client.post("/api/rooms", json=dict(room, building_id=second["id"])).status_code == 201


def test_update_conflict_rolls_back(client, room):
    client.post("/api/rooms", json=room)
    second = client.post("/api/rooms", json=dict(room, number="102")).headers["Location"]
    assert client.put(second, json=dict(room, area=100)).status_code == 409
    assert client.get(second).json["number"] == "102"
    assert client.get(second).json["area"] == room["area"]


@pytest.mark.parametrize(
    "resource,key", [("buildings", "building_id"), ("departments", "department_id")]
)
def test_restrict_parent_delete(client, room, resource, key):
    child = client.post("/api/rooms", json=room).headers["Location"]
    parent = f"/api/{resource}/{room[key]}"
    assert client.delete(parent).status_code == 409
    assert client.get(parent).status_code == 200
    assert client.delete(child).status_code == 204
    assert client.delete(parent).status_code == 204


@pytest.mark.parametrize(
    "field,value",
    [
        ("area", 0),
        ("area", -1),
        ("area", "40"),
        ("area", True),
        ("area", None),
        ("area", 100001),
        ("area", float("inf")),
        ("area", float("nan")),
        ("height", 0),
        ("height", 101),
        ("building_id", False),
        ("building_id", 1.5),
        ("building_id", 0),
        ("building_id", 10**30),
        ("number", " "),
        ("number", 101),
        ("number", "1" * 31),
        ("department_id", "1"),
    ],
)
def test_invalid_room_does_not_write(client, room, field, value):
    response = client.post("/api/rooms", json=dict(room, **{field: value}))
    assert response.status_code == 400
    assert response.json["error"]
    assert client.get("/api/rooms").json == []


@pytest.mark.parametrize("key", ["building_id", "department_id"])
def test_missing_parent(client, room, key):
    assert client.post("/api/rooms", json=dict(room, **{key: 999})).status_code == 409
    created = client.post("/api/rooms", json=room).headers["Location"]
    assert client.put(created, json=dict(room, **{key: 999})).status_code == 409
    assert client.get(created).json[key] == room[key]


@pytest.mark.parametrize(
    "payload", [None, [], "text", {}, {"name": "x", "extra": 1}, {"name": " "}, {"name": "x" * 101}]
)
def test_invalid_payload(client, payload):
    # Явное JSON null, а не отсутствие тела.
    import json

    response = client.post(
        "/api/departments", data=json.dumps(payload), content_type="application/json"
    )
    assert response.status_code == 400


def test_http_errors(client):
    assert client.post("/api/departments", data="{").status_code == 415
    assert (
        client.post("/api/departments", data="{", content_type="application/json").status_code
        == 400
    )
    assert (
        client.post(
            "/api/departments", data="x" * 17000, content_type="application/json"
        ).status_code
        == 413
    )
    assert client.patch("/api/departments/1", json={}).status_code == 405
    assert "GET" in client.patch("/api/departments/1").headers["Allow"]
    for url in [
        "/missing",
        "/api/missing",
        "/api/rooms/999",
        "/api/rooms/-1",
        "/api/rooms/999999999999999999999999",
    ]:
        response = client.get(url)
        assert response.status_code == 404
        assert "error" in response.json


def test_names_trimmed_and_unique(client):
    assert client.post("/api/departments", json={"name": " ИТ "}).json["name"] == "ИТ"
    assert client.post("/api/departments", json={"name": "ИТ"}).status_code == 409


def test_sql_text_is_data(client):
    name = "'); DROP TABLE rooms; --"
    assert client.post("/api/departments", json={"name": name}).json["name"] == name
    assert client.get("/api/rooms").status_code == 200


def test_persistence_and_environment(tmp_path, monkeypatch):
    path = tmp_path / "persistent.sqlite3"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    first = create_app().test_client()
    first.post("/api/departments", json={"name": "ИТ"})
    second = create_app().test_client()
    assert second.get("/api/departments").json[0]["name"] == "ИТ"


def test_schema_enforces_rules_without_api(app, client, room):
    with sqlite3.connect(app.config["DATABASE_PATH"]) as db:
        db.execute("PRAGMA foreign_keys = ON")
        for params in [(1, 1, "1", 0, 3), (999, 1, "1", 20, 3)]:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO rooms(building_id, department_id, number, area, height) "
                    "VALUES (?, ?, ?, ?, ?)",
                    params,
                )


def test_health_and_ui(app, client):
    assert client.get("/health").json == {"status": "ok", "database": "ok"}
    page = client.get("/")
    assert page.status_code == 200
    assert "Аудиторный фонд" in page.get_data(as_text=True)
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    with sqlite3.connect(app.config["DATABASE_PATH"]) as db:
        db.execute("DROP TABLE rooms")
    assert client.get("/health").status_code == 503


def test_head_is_read_only(client, room):
    location = client.post("/api/rooms", json=room).headers["Location"]
    for url in ("/api/rooms", location):
        response = client.head(url)
        assert response.status_code == 200
        assert response.data == b""
    assert len(client.get("/api/rooms").json) == 1
