PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS buildings (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 100),
    address TEXT NOT NULL CHECK(length(trim(address)) BETWEEN 1 AND 250)
);

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 100)
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY,
    building_id INTEGER NOT NULL REFERENCES buildings(id) ON DELETE RESTRICT,
    department_id INTEGER NOT NULL REFERENCES departments(id) ON DELETE RESTRICT,
    number TEXT NOT NULL CHECK(length(trim(number)) BETWEEN 1 AND 30),
    area REAL NOT NULL CHECK(area > 0 AND area <= 100000),
    height REAL NOT NULL CHECK(height > 0 AND height <= 100),
    UNIQUE(building_id, number)
);
