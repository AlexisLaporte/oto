"""Reddit JSON API commands (subreddit, search, post)."""

import json
from typing import Optional

import typer

app = typer.Typer(help="Reddit (public JSON API, no auth)")


@app.command("subreddit")
def subreddit(
    name: str = typer.Argument(..., help="Subreddit name (without /r/)"),
    sort: str = typer.Option("hot", help="hot|new|top|rising|controversial"),
    limit: int = typer.Option(25, "--limit", "-n", help="Max posts (max 100)"),
    time: Optional[str] = typer.Option(None, help="hour|day|week|month|year|all (top/controversial only)"),
    after: Optional[str] = typer.Option(None, help="Pagination cursor"),
):
    """List posts from a subreddit."""
    from oto.tools.reddit import RedditClient
    result = RedditClient().subreddit(name, sort=sort, limit=limit, time=time, after=after)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Search query"),
    subreddit: Optional[str] = typer.Option(None, "--sub", "-s", help="Restrict to one subreddit"),
    sort: str = typer.Option("relevance", help="relevance|hot|top|new|comments"),
    time: str = typer.Option("all", help="hour|day|week|month|year|all"),
    limit: int = typer.Option(25, "--limit", "-n", help="Max results (max 100)"),
    after: Optional[str] = typer.Option(None, help="Pagination cursor"),
):
    """Search Reddit posts (globally or in one sub)."""
    from oto.tools.reddit import RedditClient
    result = RedditClient().search(
        query, subreddit=subreddit, sort=sort, time=time, limit=limit, after=after
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("search-subs")
def search_subs(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(25, "--limit", "-n", help="Max results"),
):
    """Search subreddits by name/description."""
    from oto.tools.reddit import RedditClient
    result = RedditClient().search_subreddits(query, limit=limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("post")
def post(
    url_or_id: str = typer.Argument(..., help="Reddit post URL, permalink or id"),
    comments: int = typer.Option(100, "--comments", "-c", help="Max comments"),
    depth: int = typer.Option(5, "--depth", "-d", help="Comment tree depth"),
):
    """Fetch a post and its comments tree."""
    from oto.tools.reddit import RedditClient
    result = RedditClient().post(url_or_id, comment_limit=comments, depth=depth)
    print(json.dumps(result, indent=2, ensure_ascii=False))
