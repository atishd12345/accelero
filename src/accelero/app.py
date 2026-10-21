"""HTTP API for Accelero rooms and devices."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator

from accelero.store import (
    DeviceNotFound,
    RoomNotFound,
    Store,
    ValidationError,
    clean_name,
)


class NameBody(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        try:
            return clean_name(value)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc


class DeviceOut(BaseModel):
    id: str
    name: str


class RoomOut(BaseModel):
    id: str
    name: str
    devices: list[DeviceOut]


def _seed_from_env(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_app(db_path: str | None = None, seed: bool | None = None) -> FastAPI:
    """Build the API. Pass db_path and seed in tests; otherwise read the environment."""
    if db_path is None:
        db_path = os.environ.get("ACCELERO_DB", "data/accelero.db")
    if seed is None:
        seed = _seed_from_env(os.environ.get("ACCELERO_SEED"))

    store = Store(db_path, seed=seed)
    app = FastAPI(title="Accelero", version="0.1.0")
    app.state.store = store

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/rooms", response_model=list[RoomOut])
    def list_rooms() -> list[dict[str, Any]]:
        return store.list_rooms()

    @app.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
    def create_room(body: NameBody) -> dict[str, Any]:
        return store.create_room(body.name)

    @app.get("/rooms/{room_id}", response_model=RoomOut)
    def get_room(room_id: str) -> dict[str, Any]:
        try:
            return store.get_room(room_id)
        except RoomNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found") from None

    @app.patch("/rooms/{room_id}", response_model=RoomOut)
    def update_room(room_id: str, body: NameBody) -> dict[str, Any]:
        try:
            return store.update_room(room_id, body.name)
        except RoomNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found") from None

    @app.delete("/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_room(room_id: str) -> None:
        try:
            store.delete_room(room_id)
        except RoomNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found") from None

    @app.post(
        "/rooms/{room_id}/devices",
        response_model=DeviceOut,
        status_code=status.HTTP_201_CREATED,
    )
    def add_device(room_id: str, body: NameBody) -> dict[str, str]:
        try:
            return store.add_device(room_id, body.name)
        except RoomNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found") from None

    @app.delete(
        "/rooms/{room_id}/devices/{device_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_device(room_id: str, device_id: str) -> None:
        try:
            store.delete_device(room_id, device_id)
        except RoomNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Room not found") from None
        except DeviceNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Device not found") from None

    return app
