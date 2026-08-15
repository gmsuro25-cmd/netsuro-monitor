from __future__ import annotations

import os
from pathlib import Path


def read_secret(name: str, default: str | None = None) -> str | None:
    file_path = os.environ.get(f"{name}_FILE")
    if file_path:
        try:
            return Path(file_path).read_text().rstrip("\r\n")
        except OSError as error:
            raise RuntimeError(f"could not read secret file for {name}") from error
    return os.environ.get(name, default)


def require_production_value(name: str, value: str | None, min_length: int = 1):
    if os.environ.get("APP_ENV", "local") != "production":
        return
    normalized = (value or "").lower()
    if (
        len(value or "") < min_length
        or "change_me" in normalized
        or "changeme" in normalized
        or "replace_me" in normalized
    ):
        raise RuntimeError(f"{name} is missing or insecure for production")
