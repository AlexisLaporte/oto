"""Oto CLI - composable toolkit for AI agents."""

import importlib
import sys
from pathlib import Path

import typer

app = typer.Typer(
    name="oto",
    help="CLI toolkit for AI agents. JSON on stdout, composable with pipes.",
    no_args_is_help=True,
)

# Auto-discover commands from oto/commands/*.py
_commands_dir = Path(__file__).parent / "commands"
for _cmd_file in sorted(_commands_dir.glob("*.py")):
    if _cmd_file.name.startswith("_"):
        continue
    _module_name = _cmd_file.stem
    try:
        _module = importlib.import_module(f"oto.commands.{_module_name}")
    except ImportError:
        continue
    if hasattr(_module, "app"):
        app.add_typer(_module.app, name=_module_name)


def main():
    try:
        app()
    except ValueError as e:
        if "not found. Set it via:" in str(e):
            print(f"Error: {e}", file=sys.stderr)
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
