"""Search facade — dispatches to serper or browser based on config."""

import typer
from typing import Optional

app = typer.Typer(help="Web search (dispatches to serper or browser via config)")


def _search_serper(query: str, num: int, tbs: Optional[str]) -> dict:
    from oto.tools.serper import SerperClient
    return SerperClient().search(query, num=num, tbs=tbs)


def _search_browser(query: str, num: int) -> dict:
    import asyncio
    from oto.tools.browser import GoogleSearchClient

    async def run():
        async with GoogleSearchClient() as client:
            return await client.search(query, num=num)

    return asyncio.run(run())


@app.command("web")
def web(
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    num: int = typer.Option(10, "--num", "-n", help="Number of results"),
    tbs: Optional[str] = typer.Option(None, help="Time filter (e.g. qdr:y, serper only)"),
):
    """Search the web (provider from config: serper or browser)."""
    import json
    from oto.config import get_search_provider

    provider = get_search_provider()
    if provider == "browser":
        result = _search_browser(query, num)
    else:
        result = _search_serper(query, num, tbs)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("news")
def news(
    query: str = typer.Option(..., "--query", "-q", help="Search query"),
    num: int = typer.Option(10, "--num", "-n", help="Number of results"),
    tbs: Optional[str] = typer.Option(None, help="Time filter (e.g. qdr:w)"),
):
    """Search news (always via Serper — no browser equivalent)."""
    import json
    from oto.tools.serper import SerperClient

    client = SerperClient()
    result = client.search_news(query, num=num, tbs=tbs)
    print(json.dumps(result, indent=2, ensure_ascii=False))
