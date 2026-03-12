"""WhatsApp client via Baileys (Node.js subprocess bridge)."""

import json
import subprocess
import sys
from pathlib import Path

from ...config import get_config_dir


SCRIPT = Path(__file__).parent / "node" / "whatsapp.mjs"
NODE_DIR = Path(__file__).parent / "node"


def _ensure_deps():
    """Install node_modules if missing."""
    if not (NODE_DIR / "node_modules").exists():
        print("Installing WhatsApp dependencies...", file=sys.stderr)
        subprocess.run(
            ["npm", "install", "--production"],
            cwd=str(NODE_DIR),
            check=True,
            capture_output=True,
        )


class WhatsAppClient:
    def __init__(self):
        self.auth_dir = str(get_config_dir() / "whatsapp" / "auth")
        _ensure_deps()

    def _run(self, command: str, interactive: bool = False, **kwargs) -> dict:
        """Run Node script with command and args, return parsed JSON."""
        cmd = ["node", str(SCRIPT), command, "--auth-dir", self.auth_dir]
        for k, v in kwargs.items():
            if v is not None:
                cmd.extend([f"--{k.replace('_', '-')}", str(v)])

        timeout = 120 if interactive else 60

        if interactive:
            # Let stderr flow to terminal (QR code display)
            result = subprocess.run(cmd, capture_output=False, stdout=subprocess.PIPE, text=True, timeout=timeout)
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.stderr:
                print(result.stderr, file=sys.stderr, end="")

        if result.returncode != 0:
            try:
                error = json.loads(result.stdout)
                raise RuntimeError(error.get("message", error.get("error", "Unknown error")))
            except (json.JSONDecodeError, TypeError):
                raise RuntimeError(f"WhatsApp error (exit {result.returncode})")

        return json.loads(result.stdout)

    def auth(self) -> dict:
        return self._run("auth", interactive=True)

    def send(self, to: str, message: str) -> dict:
        return self._run("send", to=to, message=message)

    def list_chats(self, limit: int = 20) -> dict:
        return self._run("list-chats", limit=limit)

    def read(self, chat: str, limit: int = 20) -> dict:
        return self._run("read", chat=chat, limit=limit)
