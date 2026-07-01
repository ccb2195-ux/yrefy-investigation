"""
OpenSanctions MCP Server
------------------------
Wraps the OpenSanctions API (sanctions lists, PEPs, watchlists) as MCP tools.

OpenSanctions is free for non-commercial use (journalism, academic research,
anti-corruption work). Businesses need a data license -- see
https://www.opensanctions.org/api/ for current terms. Free API keys are
issued to journalists, anti-corruption activists, and academic researchers
on request.

Requires an API key (free to request). Put it in a .env file next to this
script (see .env.example) rather than exporting it manually every time:

    OPENSANCTIONS_API_KEY=your-key-here

Setup:
    pip install -r requirements.txt

Run (stdio transport):
    python server.py
"""

import os
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load .env from the same directory as this file, regardless of the
# working directory the MCP client launches it from.
load_dotenv(Path(__file__).parent / ".env")

mcp = FastMCP("opensanctions")

API_BASE = "https://api.opensanctions.org"
TIMEOUT = 20.0


def _headers() -> dict:
    api_key = os.environ.get("OPENSANCTIONS_API_KEY")
    if not api_key:
        return {}
    return {"Authorization": f"ApiKey {api_key}"}


def _check_key() -> Optional[dict]:
    if not os.environ.get("OPENSANCTIONS_API_KEY"):
        return {
            "error": "OPENSANCTIONS_API_KEY is not set. Create a .env file "
                     "next to server.py (copy .env.example) containing "
                     "OPENSANCTIONS_API_KEY=your-key-here. Request a free "
                     "key at https://www.opensanctions.org/api/ (free for "
                     "journalists, academic researchers, and anti-corruption "
                     "work; businesses need a data license)."
        }
    return None


@mcp.tool()
def search_entity(query: str, schema: str = "Thing", limit: int = 10) -> dict:
    """
    Free-text search for a person or company across OpenSanctions' aggregated
    sanctions lists, PEP (politically exposed persons) data, and other
    watchlists.

    Args:
        query: Name to search for, e.g. "Acme Holdings" or "Jane Doe".
        schema: Entity type filter -- "Person", "Company", "Organization",
                or "Thing" (default, no filter).
        limit: Max results to return (1-50).

    Returns:
        dict with matching entities, including their risk topics
        (sanction, sanction.linked, role.pep, crime, etc.) and source datasets.
    """
    key_error = _check_key()
    if key_error:
        return key_error

    limit = max(1, min(limit, 50))
    params = {"q": query, "limit": limit}
    if schema and schema != "Thing":
        params["schema"] = schema

    try:
        resp = httpx.get(f"{API_BASE}/search/default", params=params, headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"OpenSanctions returned HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except httpx.RequestError as e:
        return {"error": f"Request to OpenSanctions failed: {e}"}

    results = data.get("results", [])
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "id": r.get("id"),
                "caption": r.get("caption"),
                "schema": r.get("schema"),
                "topics": r.get("properties", {}).get("topics", []),
                "datasets": r.get("datasets", []),
                "score": r.get("score"),
            }
            for r in results
        ],
    }


@mcp.tool()
def match_entity(
    name: str,
    schema: str = "Company",
    country: Optional[str] = None,
    birth_date: Optional[str] = None,
) -> dict:
    """
    Screen a single named entity against sanctions/PEP/watchlist data using
    OpenSanctions' fuzzy matching algorithm (higher precision than
    search_entity for compliance-style screening -- returns confidence scores
    per candidate match).

    Args:
        name: Full legal name of the person or company to screen.
        schema: "Company", "Person", or "Organization".
        country: Optional ISO country code to narrow matching (e.g. "us").
        birth_date: Optional ISO date (YYYY-MM-DD), only relevant for
                    schema="Person" -- improves match precision significantly.

    Returns:
        dict with scored candidate matches and their risk topics.
    """
    key_error = _check_key()
    if key_error:
        return key_error

    properties = {"name": [name]}
    if country:
        properties["country"] = [country]
    if birth_date and schema == "Person":
        properties["birthDate"] = [birth_date]

    payload = {"queries": {"q1": {"schema": schema, "properties": properties}}}

    try:
        resp = httpx.post(f"{API_BASE}/match/default", json=payload, headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"OpenSanctions returned HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except httpx.RequestError as e:
        return {"error": f"Request to OpenSanctions failed: {e}"}

    matches = data.get("responses", {}).get("q1", {}).get("results", [])
    return {
        "name": name,
        "schema": schema,
        "count": len(matches),
        "matches": [
            {
                "id": m.get("id"),
                "caption": m.get("caption"),
                "score": m.get("score"),
                "match": m.get("match"),
                "topics": m.get("properties", {}).get("topics", []),
                "datasets": m.get("datasets", []),
            }
            for m in matches
        ],
    }


@mcp.tool()
def get_entity(entity_id: str) -> dict:
    """
    Retrieve the full record for a specific OpenSanctions entity ID (as
    returned by search_entity or match_entity), including relationships
    (ownership, family, associates) where available.

    Args:
        entity_id: The OpenSanctions entity ID, e.g. "NK-a1b2c3".

    Returns:
        dict with the full entity record.
    """
    key_error = _check_key()
    if key_error:
        return key_error

    try:
        resp = httpx.get(f"{API_BASE}/entities/{entity_id}", headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"OpenSanctions returned HTTP {e.response.status_code}", "detail": e.response.text[:500]}
    except httpx.RequestError as e:
        return {"error": f"Request to OpenSanctions failed: {e}"}


if __name__ == "__main__":
    mcp.run()
