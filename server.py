"""Data Explorer — an MCP server over an open country dataset.

Wraps the open `mledoze/countries` dataset (the data REST Countries was built on) and
exposes it to an agent as two MCP tools over STDIO:

- search_countries(query, limit)  -> short list of matching countries
- get_country_details(name)       -> currencies, languages, borders and flag URL

The dataset is one JSON file on GitHub. No API key. It is fetched over HTTPS on the
first call and cached in memory. Every failure (empty input, HTTP error, timeout,
broken data, no result) comes back as a structured message; the server never crashes.

Setup:
    pip install -r requirements.txt
Run (STDIO) — register this command in your MCP client (e.g. Claude Desktop / an IDE):
    python server.py
"""
import unicodedata

import httpx
from mcp.server.fastmcp import FastMCP

DATA_URL = "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"
# Each country has a 3-letter `cca3` code; its flag lives at this URL.
FLAG_URL = "https://raw.githubusercontent.com/mledoze/countries/master/data/{cca3}.svg"

REQUEST_TIMEOUT = 15.0  # seconds; a slow upstream must not hang the agent
MAX_QUERY_LENGTH = 100
MAX_LIMIT = 50

mcp = FastMCP("data-explorer")

_countries: list[dict] | None = None  # in-memory cache of the dataset


class DataUnavailable(Exception):
    """The dataset could not be loaded. The message is safe to show to the agent."""


def load_countries() -> list[dict]:
    """Download the dataset once and cache it.

    Raises DataUnavailable with a short, model-friendly message on any failure.
    A failed download is not cached, so the next call tries again.
    """
    global _countries
    if _countries is not None:
        return _countries
    try:
        resp = httpx.get(DATA_URL, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        raise DataUnavailable(
            f"the country data source did not respond within {REQUEST_TIMEOUT:.0f} seconds; try again later"
        ) from None
    except httpx.HTTPStatusError as exc:
        raise DataUnavailable(
            f"the country data source returned HTTP {exc.response.status_code}; try again later"
        ) from None
    except httpx.HTTPError as exc:
        raise DataUnavailable(
            f"could not reach the country data source ({type(exc).__name__}); check the network and try again"
        ) from None
    except ValueError:  # invalid JSON
        raise DataUnavailable("the country data source returned data that is not valid JSON") from None

    if not isinstance(data, list) or not all(isinstance(c, dict) and "name" in c for c in data):
        raise DataUnavailable("the country data source returned data in an unexpected format")
    _countries = data
    return _countries


def _normalize(text: str) -> str:
    """Lowercase and strip accents, so 'Türkiye' matches 'turkiye'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold().strip()


def _clean_text(value: object, field: str) -> tuple[str | None, str | None]:
    """Validate a free-text argument. Returns (cleaned_text, error_message)."""
    if not isinstance(value, str):
        return None, f"{field} must be text"
    cleaned = value.strip()
    if not cleaned:
        return None, f"{field} must not be empty"
    if len(cleaned) > MAX_QUERY_LENGTH:
        return None, f"{field} must be at most {MAX_QUERY_LENGTH} characters"
    return cleaned, None


def _names(country: dict) -> tuple[str, str]:
    name = country.get("name") or {}
    common = name.get("common") or ""
    return common, name.get("official") or common


@mcp.tool()
def search_countries(query: str, limit: int = 5) -> list[dict]:
    """Search countries by name. Returns a list of {name, capital, region, subregion}.

    Matching is case- and accent-insensitive on the common and official names.
    `limit` must be between 1 and 50. An empty list means no country matched.
    On a problem the list holds one item: {"error": "..."}.
    """
    q, error = _clean_text(query, "query")
    if error:
        return [{"error": error}]
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return [{"error": f"limit must be a whole number between 1 and {MAX_LIMIT}"}]
    try:
        countries = load_countries()
    except DataUnavailable as exc:
        return [{"error": str(exc)}]

    needle = _normalize(q)
    matches = [
        c for c in countries
        if any(needle in _normalize(n) for n in _names(c))
    ]
    # No matches is not an error: return an empty list.
    results = []
    for c in matches[:limit]:
        common, _ = _names(c)
        results.append(
            {
                "name": common,
                "capital": (c.get("capital") or [None])[0],
                "region": c.get("region"),
                "subregion": c.get("subregion"),
            }
        )
    return results


def _find_country(countries: list[dict], name: str) -> tuple[dict | None, dict | None]:
    """Resolve a user-supplied name to exactly one country.

    Order: exact match on common/official name, ISO code (cca2/cca3) or alternative
    spelling; then a unique partial match. Returns (country, error_dict).
    """
    needle = _normalize(name)

    exact = []
    for c in countries:
        keys = set(_names(c))
        keys.update(str(c.get(code) or "") for code in ("cca2", "cca3"))
        keys.update(c.get("altSpellings") or [])
        if needle in {_normalize(k) for k in keys if k}:
            exact.append(c)
    if len(exact) == 1:
        return exact[0], None

    candidates = exact or [
        c for c in countries
        if any(needle in _normalize(n) for n in _names(c))
        or any(needle in _normalize(a) for a in c.get("altSpellings") or [])
    ]
    if len(candidates) == 1:
        return candidates[0], None
    if not candidates:
        return None, {
            "error": f"no country found matching '{name}'",
            "hint": "check the spelling or use search_countries to find the exact name",
        }
    options = sorted(_names(c)[0] for c in candidates)
    return None, {
        "error": f"'{name}' matches {len(options)} countries; please be more specific",
        "matches": options[:10],
    }


@mcp.tool()
def get_country_details(name: str) -> dict:
    """Get details for one country: currencies, languages, bordering countries and flag URL.

    `name` can be the common name ("Germany"), the official name ("Federal Republic of
    Germany"), an ISO code ("DE" / "DEU") or a common alternative spelling ("Turkey").
    Matching is case- and accent-insensitive. On a problem the result is
    {"error": "..."} (plus "matches" when the name is ambiguous).
    """
    cleaned, error = _clean_text(name, "name")
    if error:
        return {"error": error}
    try:
        countries = load_countries()
    except DataUnavailable as exc:
        return {"error": str(exc)}

    country, problem = _find_country(countries, cleaned)
    if problem:
        return problem

    common, official = _names(country)
    by_code = {c.get("cca3"): _names(c)[0] for c in countries}
    currencies = [
        {"code": code, "name": (info or {}).get("name"), "symbol": (info or {}).get("symbol")}
        for code, info in (country.get("currencies") or {}).items()
    ]
    borders = [
        {"code": code, "name": by_code.get(code, code)}
        for code in country.get("borders") or []
    ]
    cca3 = country.get("cca3")
    return {
        "name": common,
        "official_name": official,
        "cca3": cca3,
        "currencies": currencies,
        "languages": sorted((country.get("languages") or {}).values()),
        "borders": borders,  # empty list for island nations
        "flag_url": FLAG_URL.format(cca3=cca3.lower()) if cca3 else None,
    }


if __name__ == "__main__":
    mcp.run()
