"""
Entry point: runs the serial listener and FastAPI server concurrently.

The serial listener runs in a daemon thread; uvicorn owns the main
thread so its Ctrl+C signal handlers install normally.
"""

from __future__ import annotations

import logging
import threading

import uvicorn

from ssb_backend import history, serial_receiver
from ssb_backend.api import app


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    history.init_db()

    listener = threading.Thread(
        target=serial_receiver.run, name="serial-listener", daemon=True
    )
    listener.start()

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
