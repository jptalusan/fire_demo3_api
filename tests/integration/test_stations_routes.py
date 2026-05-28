"""Integration tests for /api/stations: filtered file listings, auth."""

import pytest

from backend.routes import stations as stations_mod


@pytest.fixture
def fake_data_dir(monkeypatch, tmp_path):
    for name in ("stations_default.csv", "stations_custom.json", "city.geojson",
                 "beats.geojson", "readme.txt", "other.csv"):
        (tmp_path / name).write_text("x")
    monkeypatch.setattr(stations_mod, "DATA_DIR", tmp_path)
    return tmp_path


def test_get_stations_filters_by_prefix(client, auth_headers, fake_data_dir):
    r = client.get("/api/stations/get-stations", headers=auth_headers)
    assert r.status_code == 200
    stations = set(r.json()["stations"])
    assert stations == {"stations_default.csv", "stations_custom.json"}


def test_get_shapes_filters_by_extension(client, auth_headers, fake_data_dir):
    r = client.get("/api/stations/get-shapes", headers=auth_headers)
    assert r.status_code == 200
    shapes = set(r.json()["shapes"])
    assert shapes == {"city.geojson", "beats.geojson"}


def test_get_stations_requires_auth(client):
    assert client.get("/api/stations/get-stations").status_code == 401


def test_get_shapes_requires_auth(client):
    assert client.get("/api/stations/get-shapes").status_code == 401
