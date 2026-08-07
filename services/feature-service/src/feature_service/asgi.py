"""ASGI entrypoint: `uvicorn feature_service.asgi:app`.

Kept separate from `app.py` so the factory itself has no import-time side
effects (constructing `FeatureServiceSettings()` reads the environment),
which keeps `create_app()` safe to call repeatedly from tests.
"""

from __future__ import annotations

from feature_service.app import create_app

app = create_app()
