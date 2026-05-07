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

        timeout = 120 if interactive else 120

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

        if not result.stdout.strip():
            stderr_tail = result.stderr.strip()[-300:] or "(empty)"
            raise RuntimeError(
                f"WhatsApp bridge exited 0 but produced no stdout. "
                f"Message status unknown. stderr: {stderr_tail}"
            )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"WhatsApp bridge returned non-JSON stdout (status unknown): "
                f"{result.stdout.strip()[:300]}"
            ) from e

    def auth(self) -> dict:
        return self._run("auth", interactive=True)

    def auth_stream(self):
        """Run pairing in NDJSON mode and yield events as they come.

        Yields dicts of the form `{"type": "qr", "value": "..."}` (raw QR
        string from Baileys, suitable for canvas rendering) and a final
        `{"type": "result", "data": {...}}` or `{"type": "error", ...}`.

        The subprocess inherits a 120s timeout from Baileys (5 attempts of
        ~120s each on the Node side). Caller may break early; closing the
        generator terminates the subprocess.
        """
        cmd = [
            "node", str(SCRIPT), "auth",
            "--auth-dir", self.auth_dir,
            "--json-events",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,  # line-buffered
        )
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def send(self, to: str, message: str) -> dict:
        return self._run("send", to=to, message=message)

    def list_chats(self, limit: int = 20) -> dict:
        return self._run("list-chats", limit=limit)

    def read(self, chat: str, limit: int = 20) -> dict:
        return self._run("read", chat=chat, limit=limit)
