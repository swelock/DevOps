"""Правила предметной области без HTTP, Flask-контекста и базы данных."""

import math

import pytest

from campus import APIError, serialize, validate


@pytest.fixture
def valid_room():
    return {
        "building_id": 1,
        "department_id": 2,
        "number": "101",
        "area": 40.5,
        "height": 3.2,
    }


@pytest.mark.parametrize("field,maximum", [("area", 100000), ("height", 100)])
@pytest.mark.parametrize("boundary", ["minimum_positive", "maximum"])
def test_dimensions_accept_both_valid_boundaries(valid_room, field, maximum, boundary):
    value = 0.000001 if boundary == "minimum_positive" else maximum
    result = validate("rooms", dict(valid_room, **{field: value}))
    assert result[field] == value


@pytest.mark.parametrize("field,maximum", [("area", 100000), ("height", 100)])
@pytest.mark.parametrize(
    "invalid", [0, -0.000001, True, False, None, "1", [], {}, math.nan, math.inf, -math.inf]
)
def test_dimensions_reject_invalid_values(valid_room, field, maximum, invalid):
    with pytest.raises(APIError) as error:
        validate("rooms", dict(valid_room, **{field: invalid}))
    assert error.value.status == 400
    assert field in error.value.message


@pytest.mark.parametrize("field,maximum", [("area", 100000), ("height", 100)])
def test_dimensions_reject_just_above_upper_bound(valid_room, field, maximum):
    with pytest.raises(APIError):
        validate("rooms", dict(valid_room, **{field: maximum + 0.000001}))


@pytest.mark.parametrize("field", ["building_id", "department_id"])
@pytest.mark.parametrize("value", [1, 9223372036854775807])
def test_id_accepts_inclusive_database_bounds(valid_room, field, value):
    assert validate("rooms", dict(valid_room, **{field: value}))[field] == value


@pytest.mark.parametrize("field", ["building_id", "department_id"])
@pytest.mark.parametrize("value", [0, -1, 9223372036854775808, True, False, 1.0, "1", None])
def test_id_rejects_invalid_type_or_range(valid_room, field, value):
    with pytest.raises(APIError):
        validate("rooms", dict(valid_room, **{field: value}))


@pytest.mark.parametrize(
    "resource,field,maximum",
    [("buildings", "name", 100), ("buildings", "address", 250), ("departments", "name", 100)],
)
@pytest.mark.parametrize("length", [1, "maximum"])
def test_directory_text_limits_are_inclusive(resource, field, maximum, length):
    payload = (
        {"name": "Название", "address": "Адрес"} if resource == "buildings" else {"name": "ИТ"}
    )
    text = "я" * (maximum if length == "maximum" else length)
    payload[field] = f"  {text}\t"
    assert validate(resource, payload)[field] == text


@pytest.mark.parametrize(
    "resource,field,maximum",
    [("buildings", "name", 100), ("buildings", "address", 250), ("departments", "name", 100)],
)
@pytest.mark.parametrize("kind", ["empty", "spaces", "too_long", "not_string"])
def test_directory_text_rejects_invalid_values(resource, field, maximum, kind):
    payload = (
        {"name": "Название", "address": "Адрес"} if resource == "buildings" else {"name": "ИТ"}
    )
    payload[field] = {
        "empty": "",
        "spaces": " \t\n",
        "too_long": "я" * (maximum + 1),
        "not_string": 1,
    }[kind]
    with pytest.raises(APIError):
        validate(resource, payload)


@pytest.mark.parametrize("length", [1, 30])
def test_room_number_limits_and_trimming(valid_room, length):
    number = "А" * length
    assert validate("rooms", dict(valid_room, number=f" {number} "))["number"] == number


@pytest.mark.parametrize("value", ["", " \t\n", "А" * 31, 101, True, None])
def test_room_number_rejects_invalid_values(valid_room, value):
    with pytest.raises(APIError):
        validate("rooms", dict(valid_room, number=value))


def test_validation_does_not_mutate_input(valid_room):
    valid_room["number"] = "  101  "
    original = valid_room.copy()
    result = validate("rooms", valid_room)
    assert valid_room == original
    assert result is not valid_room
    assert result["number"] == "101"


@pytest.mark.parametrize("payload", [None, [], "text", {}, {"name": "ИТ", "unexpected": 1}])
def test_payload_requires_exact_directory_contract(payload):
    with pytest.raises(APIError):
        validate("departments", payload)


@pytest.mark.parametrize(
    "area,height,expected",
    [(40.5, 3.2, 129.6), (1.234, 3, 3.7), (0.01, 0.01, 0.0), (100000, 100, 10000000)],
)
def test_volume_is_product_rounded_to_two_places(area, height, expected):
    row = {"id": 7, "area": area, "height": height}
    assert serialize("rooms", row) == dict(row, volume=expected)
    assert "volume" not in row


@pytest.mark.parametrize("resource", ["buildings", "departments"])
def test_directory_serialization_adds_no_volume(resource):
    row = {"id": 1, "name": "ИТ"}
    assert serialize(resource, row) == row
    assert serialize(resource, row) is not row
