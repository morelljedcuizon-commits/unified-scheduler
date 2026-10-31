"""App-owned Google Desktop client configuration, loaded only for sign-in."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys

from .providers.errors import ProviderError

GOOGLE_CLIENT_CONFIG_ENV = "UNIFIED_SCHEDULER_GOOGLE_CLIENT_CONFIG"
_PACKAGE_DIR = Path(__file__).resolve().parent
_CONFIG_NAME = "google-oauth-client.json"


def read_google_client_config(path: str | Path) -> dict:
    """Validate a Desktop client and retain only the fields OAuth needs.

    The build also uses this function so unrelated fields cannot end up in the
    distributed client configuration. User tokens never belong in this file.
    """
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict) or "web" in config or "type" in config:
            raise ValueError
        installed = config.get("installed")
        if not isinstance(installed, dict):
            raise ValueError
        fields = ("client_id", "client_secret", "auth_uri", "token_uri")
        if any(not isinstance(installed.get(key), str) or not installed[key].strip() for key in fields):
            raise ValueError
        if (not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", installed["client_id"])
                or installed["auth_uri"] != "https://accounts.google.com/o/oauth2/auth"
                or installed["token_uri"] != "https://oauth2.googleapis.com/token"):
            raise ValueError
        return {"installed": {key: installed[key] for key in fields}}
    except (OSError, ValueError, TypeError):
        raise ProviderError(
            "This build's Google sign-in configuration is invalid or unreadable. "
            "Contact the app publisher. App owners: check Google setup in the README."
        ) from None


def resolve_google_client_config_path(legacy_path: str | None = None) -> Path | None:
    """Prefer the app's client, retaining saved paths from earlier versions."""
    override = os.environ.get(GOOGLE_CLIENT_CONFIG_ENV, "").strip()
    if override:
        # An explicit but broken override must fail rather than silently use a
        # different OAuth application's identity.
        return Path(override).expanduser()
    bundled = _PACKAGE_DIR / "resources" / _CONFIG_NAME
    if bundled.is_file():
        return bundled
    if not getattr(sys, "frozen", False) and _PACKAGE_DIR.parent.name == "src":
        development = _PACKAGE_DIR.parent.parent / "local-config" / _CONFIG_NAME
        if development.is_file():
            return development
    return Path(legacy_path).expanduser() if legacy_path else None


def load_google_client_config(legacy_path: str | None = None) -> dict:
    path = resolve_google_client_config_path(legacy_path)
    if path is None:
        raise ProviderError(
            "Google sign-in is not configured in this build. "
            "Contact the app publisher for a build with Google sign-in. "
            "App owners: see Google setup in the README."
        )
    return read_google_client_config(path)
