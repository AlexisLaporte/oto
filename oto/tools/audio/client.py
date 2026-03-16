"""Audio recorder API client — https://audio-recorder-transcript.tuls.me

Push local transcripts/summaries to tuls.me.

Authentication:
    TULS_API_TOKEN: API token from https://tuls.me (tuls_xxx format)
"""

import subprocess
from pathlib import Path
from typing import Optional, Any

import requests

from ...config import require_secret


class AudioClient:
    BASE_URL = "https://audio-recorder-transcript.tuls.me"

    def __init__(self, api_token: str = None):
        self.api_token = api_token or require_secret("TULS_API_TOKEN")

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = f"{self.BASE_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        resp = requests.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json() if resp.content else {}

    def list(self) -> list:
        """List all recordings."""
        return self._request("GET", "/api/audio/history")

    def get(self, recording_id: str) -> dict:
        """Get a recording with transcript and summary."""
        return self._request("GET", f"/api/audio/{recording_id}")

    def delete(self, recording_id: str) -> dict:
        """Delete a recording."""
        return self._request("DELETE", f"/api/audio/{recording_id}")

    def summarize(self, recording_id: str, prompt: str = None) -> dict:
        """Trigger AI summary on a transcribed recording."""
        data = {}
        if prompt:
            data["prompt"] = prompt
        return self._request("POST", f"/api/audio/{recording_id}/summarize", json=data)

    def create(
        self,
        transcript: str,
        summary: str = None,
        original_filename: str = None,
        duration_seconds: float = None,
        audio_path: Path = None,
    ) -> dict:
        """Create a recording from pre-processed transcript."""
        data = {"transcript": transcript}
        if summary:
            data["summary"] = summary
        if original_filename:
            data["original_filename"] = original_filename
        if duration_seconds is not None:
            data["duration_seconds"] = str(duration_seconds)

        files = None
        if audio_path and audio_path.exists():
            files = {"file": (audio_path.name, open(audio_path, "rb"), "audio/mpeg")}

        return self._request("POST", "/api/audio/recordings", data=data, files=files)

    def push(self, folder: Path, with_audio: bool = False) -> dict:
        """Push a local recording folder to tuls.me.

        Args:
            folder: Path to recording folder (must contain transcript.txt)
            with_audio: Include audio.mp3 in upload
        """
        transcript_path = folder / "transcript.txt"
        if not transcript_path.exists():
            raise FileNotFoundError(f"No transcript.txt in {folder}")

        transcript = transcript_path.read_text()
        summary = None
        summary_path = folder / "summary.md"
        if summary_path.exists():
            summary = summary_path.read_text()

        duration = None
        audio_path = folder / "audio.mp3"
        if audio_path.exists():
            duration = self._get_duration(audio_path)

        return self.create(
            transcript=transcript,
            summary=summary,
            original_filename=folder.name,
            duration_seconds=duration,
            audio_path=audio_path if with_audio else None,
        )

    @staticmethod
    def _get_duration(audio_path: Path) -> Optional[float]:
        """Extract duration from audio file via ffprobe."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(audio_path)],
                capture_output=True, text=True,
            )
            return float(result.stdout.strip()) if result.stdout.strip() else None
        except (subprocess.SubprocessError, ValueError):
            return None
