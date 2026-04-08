"""Direct Serper API commands (web search, news, scrape, suggestions)."""

import typer
from typing import Optional

app = typer.Typer(help="Serper API (Google search, news, scrape)")


@app.command("web")
def web(
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    num: int = typer.Option(10, "--num", "-n", help="Number of results"),
    tbs: Optional[str] = typer.Option(None, help="Time filter (e.g. qdr:y)"),
):
    """Search the web via Serper (Google)."""
    import json
    from oto.tools.serper import SerperClient

    client = SerperClient()
    result = client.search(query, num=num, tbs=tbs)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("news")
def news(
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    num: int = typer.Option(10, "--num", "-n", help="Number of results"),
    tbs: Optional[str] = typer.Option(None, help="Time filter (e.g. qdr:w)"),
):
    """Search news via Serper (Google News)."""
    import json
    from oto.tools.serper import SerperClient

    client = SerperClient()
    result = client.search_news(query, num=num, tbs=tbs)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("scrape")
def scrape(
    url: str = typer.Argument(..., help="URL to scrape"),
    markdown: bool = typer.Option(False, "--markdown", "-m", help="Include markdown"),
):
    """Scrape a web page via Serper."""
    import json
    from oto.tools.serper import SerperClient

    client = SerperClient()
    result = client.scrape_page(url, include_markdown=markdown)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("suggestions")
def suggestions(
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    country: Optional[str] = typer.Option(None, help="Country code (e.g. fr)"),
):
    """Get search autocomplete suggestions via Serper."""
    import json
    from oto.tools.serper import SerperClient

    client = SerperClient()
    result = client.get_suggestions(query, country=country)
    print(json.dumps(result, indent=2, ensure_ascii=False))
