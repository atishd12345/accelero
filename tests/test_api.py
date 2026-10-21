"""API coverage for rooms, devices, validation, and seed behavior."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from accelero.app import create_app
from accelero.main import main
from accelero.store import MAX_NAME_LENGTH, Store


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "api.db"), seed=False)
    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rooms_start_empty(client: TestClient) -> None:
    assert client.get("/rooms").json() == []


def test_create_get_and_list_room(client: TestClient) -> None:
    created = client.post("/rooms", json={"name": "  Kitchen  "})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Kitchen"
    assert body["devices"] == []
    assert body["id"]

    fetched = client.get(f"/rooms/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    listed = client.get("/rooms")
    assert listed.json() == [body]


def test_rooms_stay_in_insertion_order(client: TestClient) -> None:
    first = client.post("/rooms", json={"name": "First"}).json()
    second = client.post("/rooms", json={"name": "Second"}).json()
    names = [room["name"] for room in client.get("/rooms").json()]
    assert names == ["First", "Second"]
    assert first["id"] != second["id"]


def test_rejects_blank_long_control_and_non_string_names(client: TestClient) -> None:
    for payload in (
        {"name": "   "},
        {"name": ""},
        {"name": "a" * (MAX_NAME_LENGTH + 1)},
        {"name": "bad\nname"},
        {"name": 12},
        {},
    ):
        response = client.post("/rooms", json=payload)
        assert response.status_code == 422

    assert client.get("/rooms").json() == []
    accepted = client.post("/rooms", json={"name": "a" * MAX_NAME_LENGTH})
    assert accepted.status_code == 201


def test_update_and_missing_room(client: TestClient) -> None:
    room_id = client.post("/rooms", json={"name": "Den"}).json()["id"]
    renamed = client.patch(f"/rooms/{room_id}", json={"name": "Library"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Library"

    missing = client.patch("/rooms/missing", json={"name": "Nope"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Room not found"
    assert client.get("/rooms/missing").status_code == 404


def test_devices_stay_in_insertion_order(client: TestClient) -> None:
    room_id = client.post("/rooms", json={"name": "Lab"}).json()["id"]
    client.post(f"/rooms/{room_id}/devices", json={"name": "A"})
    client.post(f"/rooms/{room_id}/devices", json={"name": "B"})
    names = [device["name"] for device in client.get(f"/rooms/{room_id}").json()["devices"]]
    assert names == ["A", "B"]


def test_device_crud_and_wrong_room(client: TestClient) -> None:
    kitchen = client.post("/rooms", json={"name": "Kitchen"}).json()["id"]
    hall = client.post("/rooms", json={"name": "Hall"}).json()["id"]

    created = client.post(f"/rooms/{kitchen}/devices", json={"name": " Lamp "})
    assert created.status_code == 201
    device = created.json()
    assert device["name"] == "Lamp"

    room = client.get(f"/rooms/{kitchen}").json()
    assert room["devices"] == [device]

    wrong_room = client.delete(f"/rooms/{hall}/devices/{device['id']}")
    assert wrong_room.status_code == 404
    assert wrong_room.json()["detail"] == "Device not found"
    assert client.get(f"/rooms/{kitchen}").json()["devices"] == [device]

    removed = client.delete(f"/rooms/{kitchen}/devices/{device['id']}")
    assert removed.status_code == 204
    assert client.get(f"/rooms/{kitchen}").json()["devices"] == []
    assert client.delete(f"/rooms/{kitchen}/devices/{device['id']}").status_code == 404


def test_unknown_room_rejects_device_create(client: TestClient) -> None:
    response = client.post("/rooms/missing/devices", json={"name": "Sensor"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found"


def test_delete_room_removes_its_devices(client: TestClient) -> None:
    room_id = client.post("/rooms", json={"name": "Office"}).json()["id"]
    device_id = client.post(f"/rooms/{room_id}/devices", json={"name": "Hub"}).json()["id"]

    deleted = client.delete(f"/rooms/{room_id}")
    assert deleted.status_code == 204
    assert client.get(f"/rooms/{room_id}").status_code == 404
    assert client.delete(f"/rooms/{room_id}/devices/{device_id}").status_code == 404
    assert client.delete(f"/rooms/{room_id}").status_code == 404
    assert client.get("/rooms").json() == []


def test_name_is_stored_literally(client: TestClient) -> None:
    hostile = "Room'); DROP TABLE rooms;--"
    created = client.post("/rooms", json={"name": hostile})
    assert created.status_code == 201
    assert created.json()["name"] == hostile
    assert client.get("/rooms").json()[0]["name"] == hostile


def test_invalid_json_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/rooms",
        content="{",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_unicode_name(client: TestClient) -> None:
    response = client.post("/rooms", json={"name": "Küche"})
    assert response.status_code == 201
    assert response.json()["name"] == "Küche"


def test_create_app_reads_seed_from_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    database = tmp_path / "env.db"
    monkeypatch.setenv("ACCELERO_DB", str(database))
    monkeypatch.delenv("ACCELERO_SEED", raising=False)
    with TestClient(create_app()) as client:
        assert [room["id"] for room in client.get("/rooms").json()] == ["1", "2", "3"]

    monkeypatch.setenv("ACCELERO_DB", str(tmp_path / "unseeded.db"))
    monkeypatch.setenv("ACCELERO_SEED", "false")
    with TestClient(create_app()) as client:
        assert client.get("/rooms").json() == []


def test_seed_matches_sample_rooms_and_does_not_repeat(tmp_path) -> None:
    path = tmp_path / "seed.db"
    app = create_app(db_path=str(path), seed=True)
    with TestClient(app) as client:
        rooms = client.get("/rooms").json()

    assert [room["id"] for room in rooms] == ["1", "2", "3"]
    assert [room["name"] for room in rooms] == ["Room 1", "Room 2", "Room 3"]
    assert [len(room["devices"]) for room in rooms] == [1, 2, 3]
    assert rooms[2]["devices"][2] == {"id": "3-3", "name": "Device 3"}

    again = Store(str(path), seed=True)
    assert [room["id"] for room in again.list_rooms()] == ["1", "2", "3"]


def test_deleting_every_room_is_not_reseeded(tmp_path) -> None:
    path = str(tmp_path / "once.db")
    first = create_app(db_path=path, seed=True)
    with TestClient(first) as client:
        for room in client.get("/rooms").json():
            assert client.delete(f"/rooms/{room['id']}").status_code == 204

    second = Store(path, seed=True)
    assert second.list_rooms() == []


def test_main_rejects_bad_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACCELERO_PORT", "nope")
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2

    monkeypatch.setenv("ACCELERO_PORT", "70000")
    with pytest.raises(SystemExit) as caught:
        main()
    assert caught.value.code == 2


def test_main_starts_with_configured_bind(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    started: dict[str, object] = {}

    def fake_run(app, host: str, port: int) -> None:
        started["app"] = app
        started["host"] = host
        started["port"] = port

    monkeypatch.setenv("ACCELERO_HOST", "0.0.0.0")
    monkeypatch.setenv("ACCELERO_PORT", "8123")
    monkeypatch.setenv("ACCELERO_DB", str(tmp_path / "main.db"))
    monkeypatch.setenv("ACCELERO_SEED", "false")
    monkeypatch.setattr("accelero.main.uvicorn.run", fake_run)

    main()

    assert started["host"] == "0.0.0.0"
    assert started["port"] == 8123
    with TestClient(started["app"]) as client:
        assert client.get("/rooms").json() == []


def test_data_persists_across_processes(tmp_path) -> None:
    path = str(tmp_path / "persist.db")
    with TestClient(create_app(db_path=path, seed=False)) as client:
        room_id = client.post("/rooms", json={"name": "Garage"}).json()["id"]
        client.post(f"/rooms/{room_id}/devices", json={"name": "Door"})

    with TestClient(create_app(db_path=path, seed=False)) as client:
        rooms = client.get("/rooms").json()

    assert rooms[0]["name"] == "Garage"
    assert rooms[0]["devices"][0]["name"] == "Door"
