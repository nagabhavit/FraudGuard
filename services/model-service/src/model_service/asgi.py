"""ASGI entrypoint: `uvicorn model_service.asgi:app`.

Kept separate from `app.py` so the factory itself has no import-time side
effects beyond what `create_app()` already does deliberately (loading the
model) -- this module exists only so `create_app()` is called exactly
once, at process startup, not on every test that imports `app.py`.
"""

from __future__ import annotations

from model_service.app import create_app

app = create_app()
