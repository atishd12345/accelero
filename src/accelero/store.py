"""SQLite persistence for rooms and the devices inside them."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

MAX_NAME_LENGTH = 80

# Matches the sample rooms in the accelero3 Android client: room n has n devices.
SEED_ROOMS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("1", "Room 1", [("1-1", "Device 1")]),
    ("2", "Room 2", [("2-1", "Device 1"), ("2-2", "Device 2")]),
    (
        "3",
        "Room 3",
        [("3-1", "Device 1"), ("3-2", "Device 2"), ("3-3", "Device 3")],
    ),
]


class RoomNotFound(LookupError):
    """Raised when a room id is not in the store."""


class DeviceNotFound(LookupError):
    """Raised when a device id is not in the given room."""


class ValidationError(ValueError):
    """Raised when a room or device name is unusable."""


def clean_name(value: object) -> str:
    """Return a stripped name, or raise ValidationError."""
    if not isinstance(value, str):
        raise ValidationError("name is required")
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("name is required")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationError(f"name must be at most {MAX_NAME_LENGTH} characters")
    if any(ord(char) < 32 for char in cleaned):
        raise ValidationError("name contains invalid characters")
    return cleaned


class Store:
    """File-backed store. A new database is seeded once when seed=True."""

    def __init__(self, path: str, seed: bool = False) -> None:
        self.path = path
        database = Path(path)
        database.parent.mkdir(parents=True, exist_ok=True)
        fresh = not database.exists()
        self._init_db(seed=seed and fresh)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self, seed: bool) -> None:
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rooms (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    room_id TEXT NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    name TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_devices_room ON devices(room_id)"
            )
            if not seed:
                return
            for room_id, name, devices in SEED_ROOMS:
                conn.execute(
                    "INSERT OR IGNORE INTO rooms (id, name) VALUES (?, ?)",
                    (room_id, name),
                )
                for device_id, device_name in devices:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO devices (id, room_id, name)
                        VALUES (?, ?, ?)
                        """,
                        (device_id, room_id, device_name),
                    )

    def list_rooms(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rooms = conn.execute("SELECT id, name FROM rooms ORDER BY seq").fetchall()
            devices = conn.execute(
                "SELECT id, room_id, name FROM devices ORDER BY seq"
            ).fetchall()
        grouped: dict[str, list[dict[str, str]]] = {}
        for device in devices:
            grouped.setdefault(device["room_id"], []).append(
                {"id": device["id"], "name": device["name"]}
            )
        return [
            {
                "id": room["id"],
                "name": room["name"],
                "devices": grouped.get(room["id"], []),
            }
            for room in rooms
        ]

    def get_room(self, room_id: str) -> dict[str, Any]:
        with self._conn() as conn:
            room = self._room(conn, room_id)
        if room is None:
            raise RoomNotFound(room_id)
        return room

    def create_room(self, name: str) -> dict[str, Any]:
        cleaned = clean_name(name)
        room_id = uuid.uuid4().hex
        with self._conn() as conn:
            conn.execute("INSERT INTO rooms (id, name) VALUES (?, ?)", (room_id, cleaned))
            room = self._room(conn, room_id)
        if room is None:
            raise RuntimeError(f"room {room_id} missing after insert")
        return room

    def update_room(self, room_id: str, name: str) -> dict[str, Any]:
        cleaned = clean_name(name)
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE rooms SET name = ? WHERE id = ?", (cleaned, room_id)
            )
            if cursor.rowcount == 0:
                raise RoomNotFound(room_id)
            room = self._room(conn, room_id)
        if room is None:
            raise RuntimeError(f"room {room_id} missing after update")
        return room

    def delete_room(self, room_id: str) -> None:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
            if cursor.rowcount == 0:
                raise RoomNotFound(room_id)

    def add_device(self, room_id: str, name: str) -> dict[str, str]:
        cleaned = clean_name(name)
        device_id = uuid.uuid4().hex
        with self._conn() as conn:
            if self._room(conn, room_id) is None:
                raise RoomNotFound(room_id)
            conn.execute(
                "INSERT INTO devices (id, room_id, name) VALUES (?, ?, ?)",
                (device_id, room_id, cleaned),
            )
        return {"id": device_id, "name": cleaned}

    def delete_device(self, room_id: str, device_id: str) -> None:
        with self._conn() as conn:
            if self._room(conn, room_id) is None:
                raise RoomNotFound(room_id)
            cursor = conn.execute(
                "DELETE FROM devices WHERE id = ? AND room_id = ?",
                (device_id, room_id),
            )
            if cursor.rowcount == 0:
                raise DeviceNotFound(device_id)

    def _room(self, conn: sqlite3.Connection, room_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT id, name FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
        if row is None:
            return None
        devices = conn.execute(
            "SELECT id, name FROM devices WHERE room_id = ? ORDER BY seq",
            (room_id,),
        ).fetchall()
        return {
            "id": row["id"],
            "name": row["name"],
            "devices": [{"id": device["id"], "name": device["name"]} for device in devices],
        }
