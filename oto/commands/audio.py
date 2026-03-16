"""Audio recorder commands — push transcripts to tuls.me."""

import json
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Audio recorder — transcripts & summaries on tuls.me")


def _out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _client():
    from oto.tools.audio import AudioClient
    return AudioClient()


@app.command("push")
def push(
    folder: Optional[str] = typer.Argument(None, help="Recording folder path (default: latest in ~/Recordings)"),
    with_audio: bool = typer.Option(False, "--with-audio", help="Include audio.mp3 in upload"),
):
    """Push a local recording to tuls.me."""
    path = _resolve_folder(folder)
    try:
        result = _client().push(path, with_audio=with_audio)
        _out(result)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        raise typer.Exit(1)
    except Exception as e:
        if "409" in str(e):
            print(f"Already pushed: {path.name}")
            raise typer.Exit(0)
        raise


@app.command("list")
def list_recordings():
    """List all recordings."""
    _out(_client().list())


@app.command("get")
def get(recording_id: str = typer.Argument(..., help="Recording ID")):
    """Get a recording with transcript and summary."""
    _out(_client().get(recording_id))


@app.command("delete")
def delete(recording_id: str = typer.Argument(..., help="Recording ID")):
    """Delete a recording."""
    _client().delete(recording_id)
    print(f"Deleted {recording_id}")


@app.command("summarize")
def summarize(
    recording_id: str = typer.Argument(..., help="Recording ID"),
    prompt: Optional[str] = typer.Option(None, "--prompt", "-p", help="Custom summary prompt"),
):
    """Trigger AI summary on a transcribed recording."""
    _out(_client().summarize(recording_id, prompt=prompt))


def _resolve_folder(folder: Optional[str]) -> Path:
    """Resolve recording folder path (default: latest in ~/Recordings)."""
    if folder:
        path = Path(folder).expanduser()
        if not path.is_absolute():
            recordings_dir = Path.home() / "Recordings"
            path = recordings_dir / folder
        if not path.is_dir():
            print(f"Error: Not a directory: {path}")
            raise typer.Exit(1)
        return path

    recordings_dir = Path.home() / "Recordings"
    if not recordings_dir.is_dir():
        print(f"Error: {recordings_dir} not found")
        raise typer.Exit(1)

    folders = sorted(recordings_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    folders = [f for f in folders if f.is_dir()]
    if not folders:
        print("Error: No recordings found")
        raise typer.Exit(1)
    return folders[0]
