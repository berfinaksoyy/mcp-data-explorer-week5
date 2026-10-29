"""Offline tests for the Data Explorer tools.

The network is never used: `httpx.get` is replaced with a fake so every failure mode
(timeout, HTTP error, connection error, bad JSON) can be triggered on purpose.
Run: pytest -q
"""
import httpx
import pytest

import server

SAMPLE = [
    {
        "name": {"common": "Germany", "official": "Federal Republic of Germany"},
        "cca2": "DE", "cca3": "DEU", "altSpellings": ["DE", "Deutschland"],
        "capital": ["Berlin"], "region": "Europe", "subregion": "Western Europe",
        "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
        "languages": {"deu": "German"},
        "borders": ["AUT", "FRA"],
    },
    {
        "name": {"common": "Austria", "official": "Republic of Austria"},
        "cca2": "AT", "cca3": "AUT", "altSpellings": ["AT"],
        "capital": ["Vienna"], "region": "Europe", "subregion": "Central Europe",
        "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
        "languages": {"bar": "Austro-Bavarian German", "deu": "German"},
        "borders": ["DEU"],
    },
    {
        "name": {"common": "Türkiye", "official": "Republic of Türkiye"},
        "cca2": "TR", "cca3": "TUR", "altSpellings": ["TR", "Turkiye", "Republic of Turkey"],
        "capital": ["Ankara"], "region": "Asia", "subregion": "Western Asia",
        "currencies": {"TRY": {"name": "Turkish lira", "symbol": "₺"}},
        "languages": {"tur": "Turkish"},
        "borders": ["GRC"],
    },
    {
        "name": {"common": "North Korea", "official": "Democratic People's Republic of Korea"},
        "cca2": "KP", "cca3": "PRK", "altSpellings": ["KP"],
        "capital": ["Pyongyang"], "region": "Asia", "subregion": "Eastern Asia",
        "currencies": {}, "languages": {"kor": "Korean"}, "borders": [],
    },
    {
        "name": {"common": "South Korea", "official": "Republic of Korea"},
        "cca2": "KR", "cca3": "KOR", "altSpellings": ["KR"],
        "capital": ["Seoul"], "region": "Asia", "subregion": "Eastern Asia",
        "currencies": {}, "languages": {"kor": "Korean"}, "borders": [],
    },
    {
        "name": {"common": "Iceland", "official": "Iceland"},
        "cca2": "IS", "cca3": "ISL", "altSpellings": ["IS"],
        "capital": ["Reykjavik"], "region": "Europe", "subregion": "Northern Europe",
        "currencies": {"ISK": {"name": "Icelandic króna", "symbol": "kr"}},
        "languages": {"isl": "Icelandic"},
    },
]

REQUEST = httpx.Request("GET", server.DATA_URL)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self._bad_json = bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=REQUEST)
            raise httpx.HTTPStatusError("error", request=REQUEST, response=response)

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


@pytest.fixture(autouse=True)
def empty_cache():
    server._countries = None
    yield
    server._countries = None


def use_response(monkeypatch, response=None, exc=None):
    calls = []

    def fake_get(*args, **kwargs):
        calls.append(kwargs)
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(server.httpx, "get", fake_get)
    return calls


@pytest.fixture
def data(monkeypatch):
    return use_response(monkeypatch, FakeResponse(payload=SAMPLE))


# --- get_country_details: success ---------------------------------------------------

def test_details_returns_currencies_languages_borders_and_flag(data):
    result = server.get_country_details("Germany")
    assert result["name"] == "Germany"
    assert result["official_name"] == "Federal Republic of Germany"
    assert result["currencies"] == [{"code": "EUR", "name": "Euro", "symbol": "€"}]
    assert result["languages"] == ["German"]
    assert result["borders"] == [{"code": "AUT", "name": "Austria"}, {"code": "FRA", "name": "FRA"}]
    assert result["flag_url"].endswith("/data/deu.svg")


@pytest.mark.parametrize("query", ["germany", "  GERMANY ", "DE", "deu", "Deutschland", "Federal Republic of Germany"])
def test_details_accepts_names_codes_and_alt_spellings(data, query):
    assert server.get_country_details(query)["name"] == "Germany"


@pytest.mark.parametrize("query", ["Turkiye", "türkiye", "Turkey"])
def test_details_ignores_case_and_accents(data, query):
    assert server.get_country_details(query)["name"] == "Türkiye"


def test_details_island_has_empty_borders(data):
    assert server.get_country_details("Iceland")["borders"] == []


# --- get_country_details: failures --------------------------------------------------

@pytest.mark.parametrize("bad", ["", "   ", None, 42, "x" * 101])
def test_details_rejects_invalid_input_without_calling_network(monkeypatch, bad):
    calls = use_response(monkeypatch, FakeResponse(payload=SAMPLE))
    result = server.get_country_details(bad)
    assert "error" in result
    assert calls == []


def test_details_unknown_country(data):
    result = server.get_country_details("Atlantis")
    assert result["error"] == "no country found matching 'Atlantis'"
    assert "search_countries" in result["hint"]


def test_details_ambiguous_name_lists_options(data):
    result = server.get_country_details("Korea")
    assert "2 countries" in result["error"]
    assert result["matches"] == ["North Korea", "South Korea"]


# --- search_countries ---------------------------------------------------------------

def test_search_returns_model_friendly_rows(data):
    assert server.search_countries("germ") == [
        {"name": "Germany", "capital": "Berlin", "region": "Europe", "subregion": "Western Europe"}
    ]


def test_search_no_match_is_empty_list(data):
    assert server.search_countries("zzz") == []


def test_search_respects_limit(data):
    assert len(server.search_countries("korea", limit=1)) == 1


@pytest.mark.parametrize("limit", [0, -1, 51, True, "5"])
def test_search_rejects_bad_limit(data, limit):
    assert "error" in server.search_countries("a", limit=limit)[0]


@pytest.mark.parametrize("bad", ["", "  ", None])
def test_search_rejects_empty_query(data, bad):
    assert server.search_countries(bad) == [{"error": "query must not be empty" if bad is not None else "query must be text"}]


# --- upstream failures: both tools, never an exception ------------------------------

FAILURES = [
    (None, httpx.ReadTimeout("slow", request=REQUEST), "did not respond"),
    (None, httpx.ConnectError("offline", request=REQUEST), "could not reach"),
    (FakeResponse(status_code=503), None, "HTTP 503"),
    (FakeResponse(status_code=404), None, "HTTP 404"),
    (FakeResponse(bad_json=True), None, "not valid JSON"),
    (FakeResponse(payload={"unexpected": "shape"}), None, "unexpected format"),
]


@pytest.mark.parametrize("response,exc,message", FAILURES)
def test_details_upstream_failure_is_a_clean_error(monkeypatch, response, exc, message):
    use_response(monkeypatch, response, exc)
    result = server.get_country_details("Germany")
    assert set(result) == {"error"}
    assert message in result["error"]


@pytest.mark.parametrize("response,exc,message", FAILURES)
def test_search_upstream_failure_is_a_clean_error(monkeypatch, response, exc, message):
    use_response(monkeypatch, response, exc)
    result = server.search_countries("Germany")
    assert len(result) == 1 and message in result[0]["error"]


def test_request_uses_a_timeout(data):
    server.search_countries("germ")
    assert data[0]["timeout"] == server.REQUEST_TIMEOUT


def test_failure_is_not_cached_and_next_call_retries(monkeypatch):
    use_response(monkeypatch, exc=httpx.ConnectError("offline", request=REQUEST))
    assert "error" in server.get_country_details("Germany")
    use_response(monkeypatch, FakeResponse(payload=SAMPLE))
    assert server.get_country_details("Germany")["name"] == "Germany"


def test_dataset_is_downloaded_once(data):
    server.search_countries("germ")
    server.get_country_details("Austria")
    assert len(data) == 1
