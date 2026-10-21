# Accelero

Backend for the Accelero room and device list. Each room has a name and zero or more devices. Data is stored in SQLite.

The sample seed matches the accelero3 Android client's dummy rooms: Room 1 has one device, Room 2 has two, and Room 3 has three. That client still reads its local dummy list; this service is the backend behind it.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
set -a && source .env && set +a
accelero
```

`python -m accelero` starts the same server. It listens on `127.0.0.1:8000` unless `ACCELERO_HOST` and `ACCELERO_PORT` say otherwise.

| Variable | Default | Purpose |
| --- | --- | --- |
| `ACCELERO_HOST` | `127.0.0.1` | Bind address |
| `ACCELERO_PORT` | `8000` | Bind port |
| `ACCELERO_DB` | `data/accelero.db` | SQLite file |
| `ACCELERO_SEED` | `true` | Insert the three sample rooms when the database file is created |

Seeding happens only when the database file does not exist yet. Emptying the rooms and restarting does not bring the samples back.

## API

| Method | Path | Body |
| --- | --- | --- |
| `GET` | `/health` | |
| `GET` | `/rooms` | |
| `POST` | `/rooms` | `{"name": "Kitchen"}` |
| `GET` | `/rooms/{id}` | |
| `PATCH` | `/rooms/{id}` | `{"name": "Library"}` |
| `DELETE` | `/rooms/{id}` | |
| `POST` | `/rooms/{id}/devices` | `{"name": "Lamp"}` |
| `DELETE` | `/rooms/{id}/devices/{device_id}` | |

Names are stripped, must be 1–80 characters, and cannot contain control characters. A missing room or device returns 404. `DELETE` of a room also deletes its devices.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Docker

```bash
docker build -t accelero .
docker run --rm -p 8000:8000 -v accelero-data:/data accelero
```

The image binds `0.0.0.0:8000` and stores the database in `/data/accelero.db`.
