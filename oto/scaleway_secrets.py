"""Scaleway Secret Manager client for oto secrets.

Stores all secrets as a single JSON payload in one Scaleway secret ('otomata-secrets').
Auth via ~/.config/scw/config.yaml (same as scw CLI).
"""

import base64
import json
from pathlib import Path
from typing import Dict, Optional

import requests

_SCW_CONFIG = Path.home() / ".config" / "scw" / "config.yaml"
_BASE_URL = "https://api.scaleway.com/secret-manager/v1beta1/regions/{region}/secrets"
_SECRET_NAME = "otomata-secrets"

# Module-level cache — one API call per process
_cache: Optional[Dict[str, str]] = None


def _load_scw_credentials() -> dict:
    """Load Scaleway credentials from ~/.config/scw/config.yaml."""
    if not _SCW_CONFIG.exists():
        raise ValueError(
            f"Scaleway config not found at {_SCW_CONFIG}. "
            "Run 'scw init' to configure."
        )

    # Parse YAML manually (top-level key: value lines) to avoid pyyaml dependency here
    # Full YAML parsing is in config.py where pyyaml is available
    import yaml

    with open(_SCW_CONFIG) as f:
        data = yaml.safe_load(f)

    required = ("access_key", "secret_key", "default_project_id")
    for key in required:
        if key not in data:
            raise ValueError(
                f"Missing '{key}' in {_SCW_CONFIG}. Run 'scw init'."
            )

    return {
        "secret_key": data["secret_key"],
        "project_id": data["default_project_id"],
        "region": data.get("default_region", "fr-par"),
    }


def _headers(creds: dict) -> dict:
    return {
        "X-Auth-Token": creds["secret_key"],
        "Content-Type": "application/json",
    }


def _base_url(creds: dict) -> str:
    return _BASE_URL.format(region=creds["region"])


def _find_secret_id(creds: dict) -> Optional[str]:
    """Find the otomata-secrets secret ID, or None."""
    resp = requests.get(
        _base_url(creds),
        headers=_headers(creds),
        params={"name": _SECRET_NAME, "project_id": creds["project_id"]},
        timeout=10,
    )
    resp.raise_for_status()
    secrets = resp.json().get("secrets", [])
    return secrets[0]["id"] if secrets else None


def fetch_secrets() -> Dict[str, str]:
    """Fetch all secrets from Scaleway Secret Manager. Cached per process."""
    global _cache
    if _cache is not None:
        return _cache

    creds = _load_scw_credentials()
    secret_id = _find_secret_id(creds)
    if not secret_id:
        _cache = {}
        return _cache

    resp = requests.get(
        f"{_base_url(creds)}/{secret_id}/versions/latest/access",
        headers=_headers(creds),
        timeout=10,
    )
    resp.raise_for_status()

    raw = base64.b64decode(resp.json()["data"])
    _cache = json.loads(raw)
    return _cache


def push_secrets(secrets: Dict[str, str]) -> str:
    """Push secrets dict to Scaleway SM. Creates secret if needed. Returns version ID."""
    creds = _load_scw_credentials()
    secret_id = _find_secret_id(creds)

    if not secret_id:
        resp = requests.post(
            _base_url(creds),
            headers=_headers(creds),
            json={
                "name": _SECRET_NAME,
                "project_id": creds["project_id"],
                "type": "opaque",
            },
            timeout=10,
        )
        resp.raise_for_status()
        secret_id = resp.json()["id"]

    payload = base64.b64encode(json.dumps(secrets).encode()).decode()
    resp = requests.post(
        f"{_base_url(creds)}/{secret_id}/versions",
        headers=_headers(creds),
        json={"data": payload, "disable_previous": True},
        timeout=10,
    )
    resp.raise_for_status()

    # Invalidate cache
    global _cache
    _cache = None

    return resp.json()["revision"]
