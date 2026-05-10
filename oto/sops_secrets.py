"""SOPS provider for oto secret resolution.

Lit un fichier YAML chiffré via SOPS + age. Le chemin du fichier est lu dans
`~/.otomata/config.yaml::sops_file` (défaut : `~/.otomata/secrets/secrets.yaml`
qui correspond à un `git clone otomata-tech/secrets ~/.otomata/secrets`).

Décrypt délégué au CLI `sops` (déjà installé), résultat parsé en YAML plat,
caché module-level (une seule décryption par process).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Dict, Optional

_cache: Optional[Dict[str, str]] = None
_DEFAULT_PATH = Path.home() / ".otomata" / "secrets" / "secrets.yaml"


def _resolve_path(configured: Optional[str]) -> Path:
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_PATH


def fetch_secrets(path: Optional[str] = None) -> Dict[str, str]:
    """Renvoie tous les secrets décryptés sous forme de dict clé→valeur."""
    global _cache
    if _cache is not None:
        return _cache

    secrets_file = _resolve_path(path)
    if not secrets_file.exists():
        raise FileNotFoundError(
            f"SOPS secrets file not found at {secrets_file}. "
            f"Clone the repo: git clone git@github.com:otomata-tech/secrets {secrets_file.parent}"
        )

    try:
        decrypted = subprocess.run(
            ["sops", "--decrypt", str(secrets_file)],
            capture_output=True, text=True, check=True,
        ).stdout
    except FileNotFoundError as e:
        raise RuntimeError(
            "sops CLI not found. Install it: "
            "https://github.com/getsops/sops/releases"
        ) from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"sops --decrypt failed (likely no age key configured). "
            f"Make sure ~/.config/sops/age/keys.txt exists and matches a recipient in .sops.yaml.\n"
            f"stderr: {e.stderr}"
        ) from e

    import yaml
    data = yaml.safe_load(decrypted) or {}
    # Force tous str pour comportement uniforme avec les autres providers.
    _cache = {str(k): str(v) for k, v in data.items()}
    return _cache


def invalidate_cache() -> None:
    """Force a re-decrypt on next fetch (utile après `sops edit`)."""
    global _cache
    _cache = None
