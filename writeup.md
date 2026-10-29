# Week 5 Writeup — Data Explorer MCP Server

**MCP client:** Antigravity CLI 1.4.5 (`agy`), model Gemini 3.8 Flash (High)
**Repository:** https://github.com/berfinaksoyy/mcp-data-explorer-week5

## 1. What I built
- `search_countries(query, limit)` — the provided example, hardened (input and limit validation, accent-insensitive matching, clean upstream errors).
- `get_country_details(name)` — new tool. Resolves one country by name, official name, ISO code or alternative spelling, and returns currencies, languages, bordering countries (code + name) and the flag URL.

## 2. Transcript — agent calling both tools
Registration:
```text
$ agy mcp add data-explorer /Users/[REDACTED]/mcp-data-explorer-week5/.venv/bin/python /Users/[REDACTED]/mcp-data-explorer-week5/server.py
Added MCP server "data-explorer" (stdio)
$ agy mcp list
NAME           TYPE   STATUS   COMMAND/URL
data-explorer  stdio  enabled  /Users/[REDACTED]/mcp-data-explorer-week5/.venv/bin/python /Users/[REDACTED]/mcp-data-explorer-week5/server.py
```

Session (`agy`, run from the project folder):
```text
> Use the search_countries tool to find countries whose name contains "united".

● Called 2 MCP tools (data-explorer/search_countries ×2)
  Here are the countries found containing "united" (matching common or official names):

   Country                                | Capital          | Region           | Subregion
  ----------------------------------------|------------------|------------------|------------------
   United Arab Emirates                   | Abu Dhabi        | Asia             | Western Asia
   United Kingdom                         | London           | Europe           | Northern Europe
   United States                          | Washington D.C.  | Americas         | North America
   United States Minor Outlying Islands   | None             | Americas         | North America
   United States Virgin Islands           | Charlotte Amalie | Americas         | Caribbean
   Mexico (United Mexican States)         | Mexico City      | Americas         | North America
   Tanzania (United Republic of Tanzania) | Dodoma           | Africa           | Eastern Africa

> Use get_country_details for Turkey. What currency and languages does it use, and who are its neighbours?

● Called 1 MCP tool (data-explorer/get_country_details)
  Based on get_country_details for Turkey (Türkiye):
  • Currency: Turkish lira (TRY, symbol: ₺)
  • Languages: Turkish
  • Neighbours: Armenia (ARM), Azerbaijan (AZE), Bulgaria (BGR), Georgia (GEO),
    Greece (GRC), Iran (IRN), Iraq (IRQ), Syria (SYR)

> Get details for Korea.

● Called 3 MCP tools (data-explorer/get_country_details ×3)
  Searching for "Korea" matches two countries. Here are the details for both:
  ### South Korea
  • Official Name: Republic of Korea (KOR)
  • Currency: South Korean won (KRW, symbol: ₩)
  • Languages: Korean
  • Neighbours: North Korea (PRK)
  ### North Korea
  • Official Name: Democratic People's Republic of Korea (PRK)
  • Currency: North Korean won (KPW, symbol: ₩)
  • Languages: Korean
  • Neighbours: China (CHN), Russia (RUS), South Korea (KOR)

> Get details for Atlantis.

● Called 2 MCP tools (data-explorer/get_country_details, data-explorer/search_countries)
  No country was found matching "Atlantis".
  The get_country_details tool returned:
  │ Error: no country found matching 'Atlantis'
  │ Hint: check the spelling or use search_countries to find the exact name
  Since Atlantis is a mythical sunken island/civilization, it is not present in the country database.
```

What the transcript shows: for "Korea" the tool returned an ambiguity error with the two
matches, and the agent used that list to call `get_country_details` again for each country.
For "Atlantis" the agent followed the `hint` and checked with `search_countries` before
answering. The structured error messages let the agent recover instead of failing.

## 3. How I handled errors
- **Invalid input:** empty, whitespace-only, non-text or over-100-character values are rejected before any network call. `limit` must be 1–50.
- **Upstream failures:** the download has a 15-second timeout. Timeouts, HTTP status errors, connection errors, invalid JSON and an unexpected data format each return a short `{"error": ...}` message instead of an exception, so the server never crashes.
- **No result vs. ambiguous result:** an unknown name returns an error with a hint to use `search_countries`; a name that matches several countries (e.g. "Korea") returns the list of matches so the agent can ask the user or retry.
- **Retry:** a failed download is not cached, so the next call tries again.
- **Bug found in the starter hint:** the flag URL only works with a lowercase code (`deu.svg`); `DEU.svg` returns 404.
- **Evidence:** 44 offline tests in `test_server.py` fake the network to trigger every failure mode (`pytest -q`). `demo_client.py` calls the tools through a real MCP STDIO session.

## 4. What I learned
Before this assignment, I thought AI agents could reach the information they need on their own. With the MCP server, I learned that agents need the right tools to access outside data. What caught my attention most was that we can decide which information the agent can reach. For example, instead of sharing all the data, we limited its access by offering only two tools. I also realised that error messages matter. When the agent could not find a country, it used the guidance in the error message to search with another tool. This assignment taught me that building tools is not enough; it is just as important to design carefully how they work and what information they return.
