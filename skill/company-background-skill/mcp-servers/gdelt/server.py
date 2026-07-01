"""
GDELT MCP Server
-----------------
Wraps the free, keyless GDELT DOC 2.0 API (full-text global news search) as
MCP tools so Claude can search worldwide news coverage for adverse media /
background-investigation purposes.

No API key required. GDELT's DOC API searches a rolling ~3-month window of
global news coverage across 100+ languages (auto-translated to English for
search purposes).

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

Setup:
    pip install mcp httpx

Run (stdio transport, for Claude Desktop / Claude Code config):
    python server.py
"""

from typing import Optional
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gdelt")

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
TIMEOUT = 20.0


def _get(params: dict) -> dict:
    """Shared GET helper with basic error surfacing."""
    try:
        resp = httpx.get(GDELT_DOC_API, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        # GDELT sometimes returns text/html with a JSON body; force parse.
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"GDELT returned HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except httpx.RequestError as e:
        return {"error": f"Request to GDELT failed: {e}"}
    except ValueError:
        return {"error": "GDELT response was not valid JSON", "raw": resp.text[:500]}


@mcp.tool()
def search_news(
    query: str,
    timespan: str = "3months",
    max_records: int = 25,
    sort: str = "hybridrel",
) -> dict:
    """
    Search global news coverage for a company or person name (adverse media /
    background research). Searches the last ~3 months of GDELT-monitored
    news across 100+ languages (machine-translated to English for matching).

    Args:
        query: Search term(s). Use quotes for exact phrases, e.g. '"Acme Holdings"'.
               You can combine terms with AND/OR, e.g. '"Acme Holdings" AND fraud'.
        timespan: Time window, e.g. "1week", "1month", "3months" (max lookback
                  for the free DOC API is roughly 3 months of full-text search).
        max_records: Number of articles to return (1-250).
        sort: "hybridrel" (relevance+recency blend), "datedesc" (newest first),
              or "dateasc" (oldest first).

    Returns:
        dict with a list of matching articles: title, url, domain, seendate, language.
    """
    max_records = max(1, min(max_records, 250))
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": max_records,
        "timespan": timespan,
        "sort": sort,
        "format": "json",
    }
    data = _get(params)
    if "error" in data:
        return data

    articles = data.get("articles", [])
    return {
        "query": query,
        "timespan": timespan,
        "count": len(articles),
        "articles": [
            {
                "title": a.get("title"),
                "url": a.get("url"),
                "domain": a.get("domain"),
                "seendate": a.get("seendate"),
                "language": a.get("language"),
                "sourcecountry": a.get("sourcecountry"),
            }
            for a in articles
        ],
    }


@mcp.tool()
def search_news_tone(
    query: str,
    timespan: str = "3months",
) -> dict:
    """
    Get a tone/sentiment timeline for coverage of a company or person, rather
    than a raw article list. Useful for spotting periods of unusually
    negative coverage (potential scandal windows) worth investigating further
    with search_news.

    Args:
        query: Search term(s), same syntax as search_news.
        timespan: Time window, e.g. "1month", "3months".

    Returns:
        dict with a timeline of average tone scores over the period
        (negative values = more negative coverage).
    """
    params = {
        "query": query,
        "mode": "timelinetone",
        "timespan": timespan,
        "format": "json",
    }
    data = _get(params)
    if "error" in data:
        return data

    timeline = data.get("timeline", [])
    return {"query": query, "timespan": timespan, "timeline": timeline}


if __name__ == "__main__":
    mcp.run()
