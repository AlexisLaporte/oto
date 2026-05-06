"""PDF generation from markdown via pandoc + weasyprint."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_CSS = Path(__file__).parent / "templates" / "default.css"


class PdfError(RuntimeError):
    """Raised when PDF generation fails."""


def _check_dependencies() -> None:
    for tool in ("pandoc", "weasyprint"):
        if shutil.which(tool) is None:
            raise PdfError(
                f"{tool} not found in PATH. Install pandoc and weasyprint "
                "(pip install weasyprint, apt install pandoc)."
            )


def generate_pdf(
    input_md: Path | str,
    output_pdf: Path | str | None = None,
    template_css: Path | str | None = None,
    standalone: bool = True,
) -> Path:
    """Render a markdown file to PDF via pandoc + weasyprint.

    The document title/subtitle should be set in the markdown's YAML
    frontmatter (`title:` and `subtitle:`), not passed via --metadata title.
    """
    _check_dependencies()

    input_md = Path(input_md).expanduser().resolve()
    if not input_md.exists():
        raise PdfError(f"Input markdown not found: {input_md}")

    output_pdf = (
        Path(output_pdf).expanduser().resolve()
        if output_pdf
        else input_md.with_suffix(".pdf")
    )
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    css = (
        Path(template_css).expanduser().resolve()
        if template_css
        else DEFAULT_CSS
    )
    if not css.exists():
        raise PdfError(f"Template CSS not found: {css}")

    cmd = [
        "pandoc",
        str(input_md),
        "-o",
        str(output_pdf),
        "--pdf-engine=weasyprint",
        "-c",
        str(css),
    ]
    if standalone:
        cmd.append("--standalone")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise PdfError(
            f"pandoc failed (exit {result.returncode}):\n{result.stderr}"
        )

    return output_pdf
