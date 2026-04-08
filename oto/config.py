"""Configuration loader for otomata tools.

Secret resolution order:
1. Environment variable (always)
2. Configured provider (file or scaleway)
3. Default value
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Cache for parsed secrets files
_secrets_cache: Dict[Path, Dict[str, str]] = {}
_oto_config_cache: Optional[Dict[str, Any]] = None


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a .env file into a dictionary."""
    if path in _secrets_cache:
        return _secrets_cache[path]

    result = {}
    if path.exists():
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    value = value.strip()
                    # Remove quotes if present
                    if (value.startswith("'") and value.endswith("'")) or (
                        value.startswith('"') and value.endswith('"')
                    ):
                        value = value[1:-1]
                    result[key.strip()] = value

    _secrets_cache[path] = result
    return result


def _find_project_secrets() -> Optional[Path]:
    """Find .otomata/secrets.env in CWD or parent directories."""
    cwd = Path.cwd()

    # Check CWD and up to 4 parent levels
    for _ in range(5):
        secrets_file = cwd / ".otomata" / "secrets.env"
        if secrets_file.exists():
            return secrets_file
        if cwd.parent == cwd:
            break
        cwd = cwd.parent

    return None


def _get_user_secrets() -> Path:
    """Get user secrets file path (~/.otomata/secrets.env)."""
    return Path.home() / ".otomata" / "secrets.env"


def _get_oto_config() -> Dict[str, Any]:
    """Read ~/.otomata/config.yaml. Cached."""
    global _oto_config_cache
    if _oto_config_cache is not None:
        return _oto_config_cache

    config_file = Path.home() / ".otomata" / "config.yaml"
    if config_file.exists():
        import yaml
        with open(config_file) as f:
            _oto_config_cache = yaml.safe_load(f) or {}
    else:
        _oto_config_cache = {}
    return _oto_config_cache


def get_provider() -> str:
    """Return configured secret provider ('file' or 'scaleway')."""
    return _get_oto_config().get("secret_provider", "file")


def write_oto_config(config: Dict[str, Any]) -> None:
    """Write ~/.otomata/config.yaml."""
    global _oto_config_cache
    import yaml
    config_file = get_config_dir() / "config.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    _oto_config_cache = config


def get_search_provider() -> str:
    """Return configured search provider ('serper' or 'browser')."""
    return _get_oto_config().get("search_provider", "serper")


def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get a secret value.

    Resolution order:
    1. Environment variable (always, highest priority)
    2. Configured provider (file or scaleway)
    3. Default value

    Args:
        name: Secret name (e.g., 'GROQ_API_KEY', 'SIRENE_API_KEY')
        default: Default value if not found

    Returns:
        Secret value or default
    """
    # 1. Environment variable (always)
    env_val = os.environ.get(name)
    if env_val:
        return env_val

    # 2. Configured provider
    provider = get_provider()
    if provider == "scaleway":
        from oto.scaleway_secrets import fetch_secrets
        secrets = fetch_secrets()
        if name in secrets:
            return secrets[name]
    else:
        # File provider: project secrets then user secrets
        project_secrets = _find_project_secrets()
        if project_secrets:
            secrets = _parse_env_file(project_secrets)
            if name in secrets:
                return secrets[name]
        user_secrets = _get_user_secrets()
        secrets = _parse_env_file(user_secrets)
        if name in secrets:
            return secrets[name]

    return default


def get_json_secret(name: str) -> Optional[Dict[str, Any]]:
    """
    Get a secret that contains JSON data.

    Args:
        name: Secret name

    Returns:
        Parsed JSON as dictionary, or None if not found
    """
    value = get_secret(name)
    if value:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def require_secret(name: str) -> str:
    """
    Get a required secret, raise error if not found.

    Args:
        name: Secret name

    Returns:
        Secret value

    Raises:
        ValueError: If secret not found
    """
    value = get_secret(name)
    if value is None:
        raise ValueError(
            f"Required secret '{name}' not found. Set it via:\n"
            f"  - Environment variable: export {name}='...'\n"
            f"  - Project file: .otomata/secrets.env\n"
            f"  - User file: ~/.otomata/secrets.env"
        )
    return value


def get_config_dir() -> Path:
    """Get otomata config directory (~/.otomata/)."""
    config_dir = Path.home() / ".otomata"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_cache_dir() -> Path:
    """Get otomata cache directory (~/.cache/otomata/)."""
    cache_dir = Path.home() / ".cache" / "otomata"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def get_sessions_dir() -> Path:
    """Get browser sessions directory (~/.otomata/sessions/)."""
    sessions_dir = get_config_dir() / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir
