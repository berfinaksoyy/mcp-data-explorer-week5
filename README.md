# Data Explorer — MCP Server

An MCP server that gives an agent two tools over the open
[mledoze/countries](https://github.com/mledoze/countries) dataset (no API key).
The dataset is downloaded once over HTTPS and cached in memory. Transport: STDIO.

## Install
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
python server.py        # waits silently for an MCP client on STDIO; this is normal
pytest -q               # 44 offline tests (network is faked)
python demo_client.py   # starts the server over MCP and calls both tools
```

## Register in an MCP client
Use absolute paths to the virtualenv's Python and to `server.py`.

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`)
or **Antigravity** (Agent panel → `…` → MCP Servers → Manage MCP Servers → View raw config):
```json
{
  "mcpServers": {
    "data-explorer": {
      "command": "/absolute/path/to/mcp-data-explorer-week5/.venv/bin/python",
      "args": ["/absolute/path/to/mcp-data-explorer-week5/server.py"]
    }
  }
}
```
Restart / refresh the client; `data-explorer` should list two tools.

## Tool reference

### `search_countries(query, limit=5)`
Search by common or official name (case- and accent-insensitive).

| Parameter | Type | Rules |
|---|---|---|
| `query` | string | required, 1–100 characters |
| `limit` | integer | 1–50, default 5 |

Returns a list of `{name, capital, region, subregion}`. No match → `[]`.
```json
// search_countries("united", 2)
[
  {"name": "United Arab Emirates", "capital": "Abu Dhabi", "region": "Asia", "subregion": "Western Asia"},
  {"name": "United Kingdom", "capital": "London", "region": "Europe", "subregion": "Northern Europe"}
]
```

### `get_country_details(name)`
Details for exactly one country. `name` may be the common name, official name,
ISO code (`DE`, `DEU`) or an alternative spelling (`Turkey`).

| Parameter | Type | Rules |
|---|---|---|
| `name` | string | required, 1–100 characters |

```json
// get_country_details("Japan")
{
  "name": "Japan",
  "official_name": "Japan",
  "cca3": "JPN",
  "currencies": [{"code": "JPY", "name": "Japanese yen", "symbol": "¥"}],
  "languages": ["Japanese"],
  "borders": [],
  "flag_url": "https://raw.githubusercontent.com/mledoze/countries/master/data/jpn.svg"
}
```
`borders` lists `{code, name}` of neighbours (empty for island nations).

## Errors
Tools never raise; problems come back as data. `search_countries` returns `[{"error": ...}]`,
`get_country_details` returns `{"error": ...}`.

| Situation | Example message |
|---|---|
| Empty / too long / non-text input | `name must not be empty` |
| Bad `limit` | `limit must be a whole number between 1 and 50` |
| Unknown country | `no country found matching 'Atlantis'` + `hint` |
| Ambiguous name | `'Korea' matches 2 countries; please be more specific` + `matches` |
| Timeout (15 s) | `the country data source did not respond within 15 seconds; try again later` |
| HTTP error | `the country data source returned HTTP 503; try again later` |
| Network down | `could not reach the country data source (ConnectError); …` |
| Invalid / unexpected data | `… not valid JSON` / `… unexpected format` |

A failed download is not cached, so the next call retries.
