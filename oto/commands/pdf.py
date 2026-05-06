"""PDF generation commands — markdown → PDF via pandoc + weasyprint."""

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    help="Generate PDFs from markdown using a sober editorial template.",
    no_args_is_help=True,
)


@app.command("md")
def md(
    input_md: Path = typer.Argument(..., help="Input markdown file"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output PDF path (default: same basename with .pdf)",
    ),
    template: Optional[Path] = typer.Option(
        None, "--template", "-t",
        help="Custom CSS template (default: oto bundled template)",
    ),
):
    """Render a markdown file to PDF.

    The document title/subtitle should be set via YAML frontmatter
    (title:, subtitle:) in the markdown — not via --metadata title.
    """
    from oto.tools.pdf import generate_pdf, PdfError

    try:
        out = generate_pdf(input_md, output, template)
    except PdfError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(str(out))


@app.command("template")
def show_template():
    """Print the path of the bundled default CSS template."""
    from oto.tools.pdf import DEFAULT_CSS

    typer.echo(str(DEFAULT_CSS))
