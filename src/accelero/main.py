"""Process entry point. Reads host, port, database path, and seed flag from the environment."""

from __future__ import annotations

import os
import sys

import uvicorn

from accelero.app import create_app


def main() -> None:
    host = os.environ.get("ACCELERO_HOST", "127.0.0.1")
    raw_port = os.environ.get("ACCELERO_PORT", "8000")
    try:
        port = int(raw_port)
    except ValueError:
        print(f"ACCELERO_PORT must be an integer, got {raw_port!r}", file=sys.stderr)
        raise SystemExit(2) from None
    if not 1 <= port <= 65535:
        print(f"ACCELERO_PORT must be between 1 and 65535, got {port}", file=sys.stderr)
        raise SystemExit(2)

    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
