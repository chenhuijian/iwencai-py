from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "iwencai-py"
ENV_AUTH_DIR = "IWENCAI_AUTH_DIR"


def _default_auth_dir() -> Path:
    configured = os.environ.get(ENV_AUTH_DIR)
    if configured:
        return Path(configured).expanduser()

    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME / "auth"
    return Path.home() / ".iwencai-auth"


DEFAULT_AUTH_DIR = _default_auth_dir()
DEFAULT_PROFILE_DIR = DEFAULT_AUTH_DIR / "browser-profile"
DEFAULT_STORAGE_STATE_FILE = DEFAULT_AUTH_DIR / "storage-state.json"
DEFAULT_AUTH_METADATA_FILE = DEFAULT_AUTH_DIR / "metadata.json"
