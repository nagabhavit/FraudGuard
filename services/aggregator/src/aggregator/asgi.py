"""ASGI entrypoint: `uvicorn aggregator.asgi:app`.

Kept separate from `app.py` so the factory itself has no import-time side
effects (constructing `AggregatorSettings()` reads the environment), which
keeps `create_app()` safe to call repeatedly from tests.
"""

from __future__ import annotations

from aggregator.app import create_app

app = create_app()
