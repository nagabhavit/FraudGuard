"""Where the model artifact lives on disk.

Shared by `ml/pipelines/train.py` (which writes here) and `model-service`
(which reads from here), so the path is declared once.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelArtifactSettings(BaseSettings):
    """Not derived from `fraudguard_common.BaseServiceSettings`: where the
    model artifact lives is orthogonal to which service is running.
    """

    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", case_sensitive=False, protected_namespaces=()
    )

    model_path: str = "ml/models/fraud_model.txt"
    model_metadata_path: str = "ml/models/fraud_model.meta.json"


class LocalModelArtifactSettings(ModelArtifactSettings):
    """Reads `.env` for local entry points only -- never inside a container
    image, where configuration must come from real environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        protected_namespaces=(),
    )
