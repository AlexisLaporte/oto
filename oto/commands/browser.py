"""Browser automation commands (LinkedIn, Crunchbase, Pappers, Indeed, G2)."""

import typer
from typing import Optional

app = typer.Typer(help="Browser automation tools (LinkedIn, Crunchbase, Indeed, etc.)")

# LinkedIn subcommands
linkedin_app = typer.Typer(help="LinkedIn scraping (profile, company, employees, search)")


def _linkedin_client(**kwargs):
    """Create LinkedInClient with common options."""
    from oto.tools.browser import LinkedInClient
    return LinkedInClient(**kwargs)


@linkedin_app.command("profile")
def linkedin_profile(
    url: str = typer.Argument(..., help="LinkedIn profile URL"),
    cookie: Optional[str] = typer.Option(None, envvar="LINKEDIN_COOKIE", help="li_at cookie"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Connect to existing Chrome via CDP"),
    identity: str = typer.Option("default", help="Identity for rate limiting"),
    profile: Optional[str] = typer.Option(None, help="Chrome profile directory path"),
    channel: Optional[str] = typer.Option(None, envvar="BROWSER_CHANNEL", help="Chrome channel"),
    no_rate_limit: bool = typer.Option(False, "--no-rate-limit", help="Disable rate limiting"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Scrape LinkedIn profile page."""
    import asyncio
    import json

    async def run():
        async with _linkedin_client(cookie=cookie, cdp_url=cdp_url, identity=identity, profile=profile, channel=channel, headless=headless, rate_limit=not no_rate_limit) as client:
            return await client.scrape_profile(url)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@linkedin_app.command("company")
def linkedin_company(
    url: str = typer.Argument(..., help="LinkedIn company URL"),
    cookie: Optional[str] = typer.Option(None, envvar="LINKEDIN_COOKIE", help="li_at cookie"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Connect to existing Chrome via CDP"),
    identity: str = typer.Option("default", help="Identity for rate limiting"),
    profile: Optional[str] = typer.Option(None, help="Chrome profile directory path"),
    channel: Optional[str] = typer.Option(None, envvar="BROWSER_CHANNEL", help="Chrome channel"),
    no_rate_limit: bool = typer.Option(False, "--no-rate-limit", help="Disable rate limiting"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Scrape LinkedIn company page."""
    import asyncio
    import json

    async def run():
        async with _linkedin_client(cookie=cookie, cdp_url=cdp_url, identity=identity, profile=profile, channel=channel, headless=headless, rate_limit=not no_rate_limit) as client:
            return await client.scrape_company(url)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@linkedin_app.command("search")
def linkedin_search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(5, help="Max results"),
    cookie: Optional[str] = typer.Option(None, envvar="LINKEDIN_COOKIE", help="li_at cookie"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Connect to existing Chrome via CDP"),
    profile: Optional[str] = typer.Option(None, help="Chrome profile directory path"),
    channel: Optional[str] = typer.Option(None, envvar="BROWSER_CHANNEL", help="Chrome channel"),
    no_rate_limit: bool = typer.Option(False, "--no-rate-limit", help="Disable rate limiting"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Search LinkedIn companies."""
    import asyncio
    import json

    async def run():
        async with _linkedin_client(cookie=cookie, cdp_url=cdp_url, profile=profile, channel=channel, headless=headless, rate_limit=not no_rate_limit) as client:
            return await client.search_companies(query, limit=limit)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@linkedin_app.command("people")
def linkedin_people(
    slug: str = typer.Argument(..., help="LinkedIn company slug"),
    limit: int = typer.Option(20, help="Max results"),
    cookie: Optional[str] = typer.Option(None, envvar="LINKEDIN_COOKIE", help="li_at cookie"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Connect to existing Chrome via CDP"),
    profile: Optional[str] = typer.Option(None, help="Chrome profile directory path"),
    channel: Optional[str] = typer.Option(None, envvar="BROWSER_CHANNEL", help="Chrome channel"),
    no_rate_limit: bool = typer.Option(False, "--no-rate-limit", help="Disable rate limiting"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """List people from a LinkedIn company page."""
    import asyncio
    import json

    async def run():
        async with _linkedin_client(cookie=cookie, cdp_url=cdp_url, profile=profile, channel=channel, headless=headless, rate_limit=not no_rate_limit) as client:
            return await client.get_company_people(slug, limit=limit)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@linkedin_app.command("employees")
def linkedin_employees(
    company: str = typer.Argument(..., help="LinkedIn company slug"),
    keywords: Optional[str] = typer.Option(None, help="Title keywords (comma-separated)"),
    limit: int = typer.Option(10, help="Max results"),
    cookie: Optional[str] = typer.Option(None, envvar="LINKEDIN_COOKIE", help="li_at cookie"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Connect to existing Chrome via CDP"),
    profile: Optional[str] = typer.Option(None, help="Chrome profile directory path"),
    channel: Optional[str] = typer.Option(None, envvar="BROWSER_CHANNEL", help="Chrome channel"),
    no_rate_limit: bool = typer.Option(False, "--no-rate-limit", help="Disable rate limiting"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Search company employees on LinkedIn."""
    import asyncio
    import json

    async def run():
        kw_list = keywords.split(",") if keywords else None
        async with _linkedin_client(cookie=cookie, cdp_url=cdp_url, profile=profile, channel=channel, headless=headless, rate_limit=not no_rate_limit) as client:
            return await client.search_employees(company, keywords=kw_list, limit=limit)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@linkedin_app.command("search-people")
def linkedin_search_people(
    keywords: str = typer.Argument(..., help="Search keywords (e.g., 'credit manager')"),
    geo: Optional[str] = typer.Option("105015875", help="Geo URN ID (default: France)"),
    limit: int = typer.Option(50, help="Max results"),
    pages: int = typer.Option(5, help="Max pages to scrape"),
    cookie: Optional[str] = typer.Option(None, envvar="LINKEDIN_COOKIE", help="li_at cookie"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Connect to existing Chrome via CDP"),
    profile: Optional[str] = typer.Option(None, help="Chrome profile directory path"),
    channel: Optional[str] = typer.Option(None, envvar="BROWSER_CHANNEL", help="Chrome channel"),
    no_rate_limit: bool = typer.Option(False, "--no-rate-limit", help="Disable rate limiting"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Search people on LinkedIn by keywords and location."""
    import asyncio
    import json

    async def run():
        async with _linkedin_client(cookie=cookie, cdp_url=cdp_url, profile=profile, channel=channel, headless=headless, rate_limit=not no_rate_limit) as client:
            return await client.search_people(keywords, geo=geo, limit=limit, pages=pages)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@linkedin_app.command("posts")
def linkedin_posts(
    url: str = typer.Argument(..., help="LinkedIn profile URL"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max posts"),
    cookie: Optional[str] = typer.Option(None, envvar="LINKEDIN_COOKIE", help="li_at cookie"),
    cdp_url: Optional[str] = typer.Option(None, "--cdp-url", help="Connect to existing Chrome via CDP"),
    profile: Optional[str] = typer.Option(None, help="Chrome profile directory path"),
    channel: Optional[str] = typer.Option(None, envvar="BROWSER_CHANNEL", help="Chrome channel"),
    no_rate_limit: bool = typer.Option(False, "--no-rate-limit", help="Disable rate limiting"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Scrape posts from a LinkedIn profile."""
    import asyncio
    import json

    async def run():
        async with _linkedin_client(cookie=cookie, cdp_url=cdp_url, profile=profile, channel=channel, headless=headless, rate_limit=not no_rate_limit) as client:
            return await client.scrape_profile_posts(url, max_posts=limit)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("crunchbase-company")
def crunchbase_company(
    slug: str = typer.Argument(..., help="Company slug or URL"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Get company from Crunchbase."""
    import asyncio
    import json
    from oto.tools.browser import CrunchbaseClient

    async def run():
        async with CrunchbaseClient(headless=headless) as client:
            return await client.get_company(slug)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("pappers-siren")
def pappers_siren(
    siren: str = typer.Argument(..., help="SIREN number"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Get French company data from Pappers."""
    import asyncio
    import json
    from oto.tools.browser import PappersClient

    async def run():
        async with PappersClient(headless=headless) as client:
            return await client.get_company_by_siren(siren)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("indeed-search")
def indeed_search(
    query: str = typer.Argument(..., help="Job search query"),
    location: str = typer.Option("", help="Location"),
    country: str = typer.Option("fr", help="Country code (fr, us, uk, de)"),
    limit: int = typer.Option(25, help="Max results"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Search jobs on Indeed."""
    import asyncio
    import json
    from oto.tools.browser import IndeedClient

    async def run():
        async with IndeedClient(country=country, headless=headless) as client:
            return await client.search_jobs(query, location=location, max_results=limit)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))


@app.command("g2-reviews")
def g2_reviews(
    url: str = typer.Argument(..., help="G2 product reviews URL"),
    limit: int = typer.Option(50, help="Max reviews"),
    headless: bool = typer.Option(True, help="Run headless"),
):
    """Scrape product reviews from G2."""
    import asyncio
    import json
    from oto.tools.browser import G2Client

    async def run():
        async with G2Client(headless=headless) as client:
            return await client.get_product_reviews(url, max_reviews=limit)

    result = asyncio.run(run())
    print(json.dumps(result, indent=2, ensure_ascii=False))
