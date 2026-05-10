"""
Reddit public JSON API client.

Uses the unauthenticated `*.json` endpoints exposed by reddit.com — no OAuth,
no API key. Reddit blocks the default `python-requests` User-Agent, so a
custom UA is sent on every call.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import requests

from ... import __version__


class RedditClient:
    """
    Reddit JSON API (public reads only).

    Covers:
    - subreddit feeds (hot/new/top/rising)
    - search across all of Reddit or restricted to a subreddit
    - post + flat comments tree
    - subreddit discovery search
    """

    BASE_URL = "https://www.reddit.com"
    DEFAULT_UA = f"oto-cli/{__version__} (by /u/oto-bot)"

    def __init__(self, user_agent: Optional[str] = None, timeout: int = 15):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent or self.DEFAULT_UA
        self.timeout = timeout

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.BASE_URL}{path}" if path.startswith("/") else path
        r = self.session.get(url, params=params, timeout=self.timeout, allow_redirects=True)
        r.raise_for_status()
        return r.json()

    # ── Listings ──────────────────────────────────────────────────────────

    def subreddit(
        self,
        name: str,
        sort: str = "hot",
        limit: int = 25,
        time: Optional[str] = None,
        after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List posts from a subreddit.

        sort: hot|new|top|rising|controversial
        time: hour|day|week|month|year|all (only for top/controversial)
        """
        if sort not in {"hot", "new", "top", "rising", "controversial"}:
            raise ValueError(f"invalid sort: {sort}")
        params: Dict[str, Any] = {"limit": min(limit, 100), "raw_json": 1}
        if time and sort in {"top", "controversial"}:
            params["t"] = time
        if after:
            params["after"] = after
        data = self._get(f"/r/{name}/{sort}.json", params)
        return _parse_listing(data)

    def search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time: str = "all",
        limit: int = 25,
        after: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Search posts. If `subreddit` is set, restricts to that sub.

        sort: relevance|hot|top|new|comments
        time: hour|day|week|month|year|all
        """
        params: Dict[str, Any] = {
            "q": query,
            "sort": sort,
            "t": time,
            "limit": min(limit, 100),
            "raw_json": 1,
            "type": "link",
        }
        if after:
            params["after"] = after
        if subreddit:
            params["restrict_sr"] = "1"
            path = f"/r/{subreddit}/search.json"
        else:
            path = "/search.json"
        return _parse_listing(self._get(path, params))

    def search_subreddits(self, query: str, limit: int = 25) -> Dict[str, Any]:
        """Discover subreddits by name/description match."""
        data = self._get(
            "/subreddits/search.json",
            {"q": query, "limit": min(limit, 100), "raw_json": 1},
        )
        return _parse_listing(data)

    # ── Post + comments ───────────────────────────────────────────────────

    def post(self, url_or_id: str, comment_limit: int = 100, depth: int = 5) -> Dict[str, Any]:
        """
        Fetch a post and its comments tree.

        Accepts a full reddit URL, a permalink (/r/x/comments/id/...) or just the post id.
        """
        path = _post_path(url_or_id)
        data = self._get(
            f"{path}.json",
            {"limit": comment_limit, "depth": depth, "raw_json": 1},
        )
        if not isinstance(data, list) or len(data) < 2:
            raise RuntimeError(f"unexpected post payload: {type(data).__name__}")
        post = _parse_post_data(data[0]["data"]["children"][0]["data"])
        comments = _parse_comments(data[1]["data"]["children"])
        return {"post": post, "comments": comments}


# ── Parsing helpers ───────────────────────────────────────────────────────


def _parse_listing(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = data.get("data", {})
    children = payload.get("children", [])
    items = [_parse_child(c) for c in children]
    return {
        "items": [i for i in items if i],
        "after": payload.get("after"),
        "before": payload.get("before"),
    }


def _parse_child(child: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kind = child.get("kind")
    d = child.get("data") or {}
    if kind == "t3":
        return _parse_post_data(d)
    if kind == "t5":
        return {
            "kind": "subreddit",
            "name": d.get("display_name"),
            "title": d.get("title"),
            "subscribers": d.get("subscribers"),
            "description": d.get("public_description"),
            "url": f"https://www.reddit.com{d.get('url', '')}",
            "over_18": d.get("over18"),
        }
    return None


def _parse_post_data(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "post",
        "id": d.get("id"),
        "title": d.get("title"),
        "author": d.get("author"),
        "subreddit": d.get("subreddit"),
        "score": d.get("score"),
        "upvote_ratio": d.get("upvote_ratio"),
        "num_comments": d.get("num_comments"),
        "created_utc": d.get("created_utc"),
        "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
        "url": d.get("url_overridden_by_dest") or d.get("url"),
        "is_self": d.get("is_self"),
        "selftext": d.get("selftext") or None,
        "flair": d.get("link_flair_text"),
        "over_18": d.get("over_18"),
    }


def _parse_comments(children: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in children:
        if c.get("kind") != "t1":
            continue
        d = c.get("data") or {}
        replies = d.get("replies")
        sub = []
        if isinstance(replies, dict):
            sub = _parse_comments(replies.get("data", {}).get("children", []))
        out.append({
            "id": d.get("id"),
            "author": d.get("author"),
            "score": d.get("score"),
            "created_utc": d.get("created_utc"),
            "body": d.get("body"),
            "permalink": f"https://www.reddit.com{d.get('permalink', '')}",
            "replies": sub,
        })
    return out


def _post_path(url_or_id: str) -> str:
    s = url_or_id.strip()
    if s.startswith("http"):
        # strip protocol+host, drop trailing slash
        from urllib.parse import urlparse
        path = urlparse(s).path.rstrip("/")
        return path
    if s.startswith("/r/"):
        return s.rstrip("/")
    # bare id
    return f"/comments/{quote_plus(s)}"
