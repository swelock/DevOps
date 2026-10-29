"""Вместимость: чистая логика, контракт HTTP и сохранение изменений."""

import sqlite3

import pytest

from campus import APIError, validate


@pytest.fixture
def payload(client):
    building = client.post("/api/buildings", json={"name": "Корпус", "address": "Москва"}).json
    department = client.post("/api/departments", json={"name": "Кафедра"}).json
    return dict(
        building_id=building["id"],
        department_id=department["id"],
        number="101",
        area=40.5,
        height=3.2,
    )


@pytest.mark.parametrize("capacity", [1, 1000])
def test_capacity_inclusive_boundaries(client, payload, capacity):
    response = client.post("/api/rooms", json=dict(payload, capacity=capacity))
    assert response.status_code == 201
    assert response.json["capacity"] == capacity
    assert client.get(response.headers["Location"]).json["capacity"] == capacity


@pytest.mark.parametrize("value", [0, -1, 1001, 1.5, 1.0, True, False, "40", None, [], {}])
def test_invalid_capacity_does_not_change_record(client, payload, value):
    created = client.post("/api/rooms", json=dict(payload, capacity=40))
    location = created.headers["Location"]
    invalid = dict(payload, capacity=value)
    with pytest.raises(APIError, match="capacity"):
        validate("rooms", invalid)
    assert client.put(location, json=invalid).status_code == 400
    assert client.get(location).json == created.json
    assert client.post("/api/rooms", json=dict(invalid, number="102")).status_code == 400
    assert len(client.get("/api/rooms").json) == 1


def test_capacity_http_scenario_and_database_persistence(app, client, payload):
    created = client.post("/api/rooms", json=dict(payload, capacity=40))
    assert created.status_code == 201
    location = created.headers["Location"]
    changed = client.put(location, json=dict(payload, capacity=60, area=50))
    assert changed.status_code == 200
    assert changed.json["capacity"] == 60
    assert changed.json["volume"] == 160
    assert client.get("/api/rooms").json == [changed.json]
    # Читаем отдельным реальным соединением после завершения HTTP-запроса.
    with sqlite3.connect(app.config["DATABASE_PATH"]) as db:
        assert db.execute("SELECT capacity, area FROM rooms").fetchone() == (60, 50)
    assert client.delete(location).status_code == 204
    assert client.get("/api/rooms").json == []


def test_old_payload_defaults_to_one_without_mutating_input(client, payload):
    original = payload.copy()
    result = validate("rooms", payload)
    assert result["capacity"] == 1
    assert payload == original
    response = client.post("/api/rooms", json=payload)
    assert response.status_code == 201
    assert response.json["capacity"] == 1
    location = response.headers["Location"]
    assert client.put(location, json=dict(payload, capacity=20)).json["capacity"] == 20
    assert client.put(location, json=payload).json["capacity"] == 1
