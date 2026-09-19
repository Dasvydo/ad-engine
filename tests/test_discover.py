"""Discovery: candidate records, a quota that refuses, and no snapshot wire.

Four properties are worth a test here and the rest is bookkeeping.

**The quota is enforced, not documented.** The Ad Library rate limit is a
reported figure with no published number; the tests below prove a call is
refused at the boundary and that the refused call never reaches the
transport.

**The token is a header, never a URL and never a message.** A URL can be
logged; a message can be a public Actions log. The tests below build a real
urllib request against a fake urlopen and then make the transport raise with
the token in it.

**A snapshot page is never requested.** Not rate-limited, not disabled by a
flag: there is no transport for it. The test for it makes every socket in
the process explode, hands the stub snapshot URLs, and asserts nothing ever
targeted facebook.com/ads/library.

**An outlier is not a far-reaching ad.** The ratio is reach per day against
the same page's other ads in the same run, so the tests pin what happens
when that baseline is missing or zero rather than letting a
ZeroDivisionError decide.

Every test here is offline. The transport is injected; no test needs a token.
"""
import io
import json
import socket
import urllib.request
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from engine import discover


# ---------------------------------------------------------------------------
# The seam: one callable, one URL and one token in, one JSON document out.
# ---------------------------------------------------------------------------


class FakeArchive:
    """A stand-in for discover._http. Records every URL and token it is handed.

    Bodies are consumed in order across calls - pages are searched first,
    then queries in seed order, then pagination - so a test lines its bodies
    up the way the run will ask for them. The last body is reused once the
    list runs out; with no bodies at all, every call is empty.
    """

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, token: str) -> dict:
        self.calls.append((url, token))
        if not self.bodies:
            return {"data": []}
        return self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]

    def params(self, index: int = 0) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.urls[index]).query).items()}


TODAY = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def ad(ad_id, *, page_id="1007614045762121", page_name="Balance", start="2026-08-01T09:00:00+0000",
       stop=None, reach=1000, body="Se om vi kan gore dit regnskab bedre", title="Balance",
       description="Bogforing uden bovl", caption="balance.dk", platforms=("facebook", "instagram"),
       languages=("da",), snapshot=True) -> dict:
    """One raw archived ad as the API returns it."""
    record = {
        "id": str(ad_id),
        "page_id": page_id,
        "page_name": page_name,
        "ad_creation_time": start,
        "ad_delivery_start_time": start,
        "ad_creative_bodies": [body] if body is not None else None,
        "ad_creative_link_titles": [title] if title is not None else None,
        "ad_creative_link_descriptions": [description] if description is not None else None,
        "ad_creative_link_captions": [caption] if caption is not None else None,
        "publisher_platforms": list(platforms),
        "languages": list(languages),
        "eu_total_reach": reach,
    }
    if stop is not None:
        record["ad_delivery_stop_time"] = stop
    if snapshot:
        record["ad_snapshot_url"] = (
            f"https://www.facebook.com/ads/archive/render_ad/?id={ad_id}&access_token=snap"
        )
    return record


def body(*ads, next_after=None) -> dict:
    """A result page. `next_after` gives it a paging.next link and cursor."""
    document = {"data": list(ads), "paging": {"cursors": {"before": "b", "after": next_after or "e"}}}
    if next_after:
        document["paging"]["next"] = (
            f"https://graph.facebook.com/ads_archive?after={next_after}&limit=100"
        )
    return document


def client(transport, *, budget=discover.HOURLY_BUDGET_CALLS, token="test-token") -> discover.AdLibraryClient:
    """A client with a stub transport and a fake token. Never touches the wire."""
    return discover.AdLibraryClient(token, budget=budget, transport=transport)


def write_seeds(tmp_path, document: str):
    path = tmp_path / "seeds.yaml"
    path.write_text(document, encoding="utf-8")
    return path


BALANCE = discover.Page("balance-dk", "Balance", "1007614045762121", "icp-adjacent", ("DK",))
FYXER = discover.Page("fyxer", "Fyxer", "555", "competitor", ("GB",))

ONE_PAGE = """
countries: [DK, LT]
pages:
  - id: balance-dk
    name: Balance - Your AI Powered Accountants
    page_id: "1007614045762121"
    origin: icp-adjacent
    countries: [DK]
queries:
  - regnskab
  - query: buhalteris
    countries: [LT]
    languages: [lt]
own:
  page_id:
  page_name:
  ad_account_id:
"""


# ---------------------------------------------------------------------------
# Contract C2 - the record shape a downstream task consumes
# ---------------------------------------------------------------------------

C2_KEYS = {"id", "platform", "url", "channel", "origin", "metrics", "copy", "outlier_ratio"}
C2_METRIC_KEYS = {"eu_total_reach", "days_running", "active", "variants", "page_id",
                  "publisher_platforms", "languages", "countries"}
C2_COPY_KEYS = {"primary_text", "headline", "description", "link_caption"}


def test_a_candidate_carries_exactly_the_contract_keys():
    api = FakeArchive(body(ad("961046237012883")))
    seeds = discover.Seeds(countries=("DK",), queries=(discover.Query("regnskab"),))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert set(rows[0]) == C2_KEYS
    assert set(rows[0]["metrics"]) == C2_METRIC_KEYS
    assert set(rows[0]["copy"]) == C2_COPY_KEYS


def test_a_candidate_reads_its_values_off_the_api():
    api = FakeArchive(body(ad("961046237012883", reach=12000, start="2026-08-08T12:00:00+0000")))
    seeds = discover.Seeds(countries=("DK",), pages=(BALANCE,))
    row = discover.discover(seeds, client=client(api), today=TODAY)[0]
    assert row["id"] == "fb-961046237012883"
    assert row["platform"] == "meta-ad"
    assert row["url"] == "https://www.facebook.com/ads/library/?id=961046237012883"
    assert row["channel"] == "Balance"
    assert row["origin"] == "icp-adjacent"
    assert row["metrics"] == {
        "eu_total_reach": 12000, "days_running": 41, "active": True, "variants": 1,
        "page_id": "1007614045762121", "publisher_platforms": ["facebook", "instagram"],
        "languages": ["da"], "countries": ["DK"],
    }
    assert row["copy"] == {
        "primary_text": "Se om vi kan gore dit regnskab bedre", "headline": "Balance",
        "description": "Bogforing uden bovl", "link_caption": "balance.dk",
    }
    assert row["outlier_ratio"] == discover.NO_BASELINE


def test_copy_is_the_first_card_and_blank_when_absent():
    api = FakeArchive(body(
        ad("1", body=None, title=None, description=None, caption=None),
        {**ad("2"), "ad_creative_bodies": ["first card", "second card"]},
    ))
    seeds = discover.Seeds(countries=("DK",), pages=(BALANCE,))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert rows[0]["copy"] == {"primary_text": "", "headline": "", "description": "", "link_caption": ""}
    assert rows[1]["copy"]["primary_text"] == "first card"


def test_the_record_is_json_serialisable():
    """It is written to disk and read by another module; nothing exotic in it."""
    row = discover.candidate(id="fb-1", url="u", channel="c", origin="competitor")
    assert json.loads(json.dumps(row)) == row


@pytest.mark.parametrize("platform", ["youtube", "instagram", "", "META-AD"])
def test_an_unknown_platform_is_refused(platform):
    with pytest.raises(ValueError, match="platform"):
        discover.candidate(id="fb-1", platform=platform, url="u", channel="c", origin="competitor")


@pytest.mark.parametrize("origin", ["competitors", "own", "adjacent", ""])
def test_an_unknown_origin_is_refused(origin):
    with pytest.raises(ValueError, match="origin"):
        discover.candidate(id="fb-1", url="u", channel="c", origin=origin)


@pytest.mark.parametrize("bad_id", ["961046237012883", "yt-abc", "fb-", "ig-x"])
def test_an_id_without_the_fb_prefix_is_refused(bad_id):
    with pytest.raises(ValueError, match="fb-"):
        discover.candidate(id=bad_id, url="u", channel="c", origin="competitor")


def test_the_platform_and_prefix_are_the_contract_constants():
    assert discover.PLATFORM == "meta-ad" and discover.PLATFORMS == ("meta-ad",)
    assert discover.ID_PREFIX == "fb-"
    assert discover.ORIGINS == ("competitor", "icp-adjacent")


def test_an_ad_returned_by_two_searches_appears_once():
    """Deduplication is what keeps ids globally unique across a whole run."""
    api = FakeArchive(body(ad("1")), body(ad("1")))
    seeds = discover.Seeds(countries=("DK",), queries=(discover.Query("one"), discover.Query("two")))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert [r["id"] for r in rows] == ["fb-1"]


# ---------------------------------------------------------------------------
# Quota - the property this module exists for
# ---------------------------------------------------------------------------


def test_one_search_of_one_page_costs_one_call():
    api = FakeArchive(body())
    c = client(api)
    c.archive(countries=["DK"], search_terms="regnskab")
    assert c.quota.spent == 1


def test_each_result_page_is_charged():
    api = FakeArchive(body(ad("1"), next_after="c2"), body(ad("2"), next_after="c3"), body(ad("3")))
    c = client(api)
    ads = c.archive(countries=["DK"], search_terms="regnskab", max_pages=3)
    assert [a["id"] for a in ads] == ["1", "2", "3"]
    assert c.quota.spent == 3
    assert len(api.calls) == 3


def test_paging_stops_at_max_pages_even_with_more_to_read():
    api = FakeArchive(body(ad("1"), next_after="c2"), body(ad("2"), next_after="c3"), body(ad("3")))
    c = client(api)
    c.archive(countries=["DK"], search_terms="regnskab", max_pages=2)
    assert c.quota.spent == 2


def test_paging_stops_when_next_is_absent():
    api = FakeArchive(body(ad("1")), body(ad("2")))
    c = client(api)
    ads = c.archive(countries=["DK"], search_terms="regnskab", max_pages=5)
    assert [a["id"] for a in ads] == ["1"]
    assert c.quota.spent == 1


def test_the_second_page_is_asked_for_by_cursor_on_the_same_url():
    """paging.next is a URL Meta wrote; this module follows the cursor on its own."""
    api = FakeArchive(body(ad("1"), next_after="CURSOR2"), body(ad("2")))
    client(api).archive(countries=["DK"], search_terms="regnskab")
    assert "after" not in api.params(0)
    assert api.params(1)["after"] == "CURSOR2"
    assert api.params(1)["search_terms"] == "regnskab"
    assert all(urlparse(u).path.endswith("/ads_archive") for u in api.urls)


def test_a_next_link_without_a_cursor_is_refused_not_followed():
    api = FakeArchive({"data": [ad("1")], "paging": {"next": "https://graph.facebook.com/ads_archive?limit=100"}})
    with pytest.raises(discover.ApiError, match="after"):
        client(api).archive(countries=["DK"], search_terms="regnskab")


def test_the_default_page_size_and_page_count_are_the_contract_constants():
    assert discover.DEFAULT_LIMIT == 100
    assert discover.DEFAULT_MAX_PAGES == 2
    api = FakeArchive(body())
    client(api).archive(countries=["DK"], search_terms="q")
    assert api.params()["limit"] == "100"


def test_a_call_that_would_exceed_the_budget_is_refused():
    """The boundary: one call left buys one search, zero buys none."""
    api = FakeArchive(body())
    c = client(api, budget=1)
    c.archive(countries=["DK"], search_terms="first")
    assert c.quota.remaining == 0
    with pytest.raises(discover.QuotaExceededError):
        c.archive(countries=["DK"], search_terms="second")


def test_the_refused_call_never_reaches_the_transport():
    """Refusing after the request would be theatre - Meta counts on receipt."""
    api = FakeArchive(body())
    c = client(api, budget=0)
    with pytest.raises(discover.QuotaExceededError):
        c.archive(countries=["DK"], search_terms="too expensive")
    assert api.calls == []


def test_a_refused_call_spends_nothing():
    c = client(FakeArchive(), budget=0)
    with pytest.raises(discover.QuotaExceededError):
        c.archive(countries=["DK"], search_terms="q")
    assert c.quota.spent == 0
    assert c.quota.remaining == 0


def test_the_refusal_carries_the_numbers_and_the_advice():
    c = client(FakeArchive(), budget=0)
    with pytest.raises(discover.QuotaExceededError) as excinfo:
        c.archive(countries=["DK"], search_terms="q")
    error = excinfo.value
    assert error.endpoint == "ads_archive"
    assert error.needed == 1 and error.remaining == 0 and error.budget == 0
    message = str(error)
    assert "0" in message and "seeds.yaml" in message and "613" in message


def test_the_second_page_is_refused_when_only_the_first_is_affordable():
    """A run out of calls keeps what the paid page returned and stops there."""
    api = FakeArchive(body(ad("1"), next_after="c2"), body(ad("2")))
    c = client(api, budget=1)
    with pytest.raises(discover.QuotaExceededError):
        c.archive(countries=["DK"], search_terms="q")
    assert len(api.calls) == 1


def test_the_default_budget_is_the_reported_hourly_allowance():
    assert discover.HOURLY_BUDGET_CALLS == 200
    assert client(FakeArchive()).quota.budget == 200


def test_affords_reports_without_charging():
    quota = discover.Quota(budget=1)
    assert quota.affords("ads_archive")
    assert quota.spent == 0
    quota.charge("ads_archive")
    assert not quota.affords("ads_archive")


def test_an_unpriced_endpoint_is_refused_rather_than_assumed_free():
    quota = discover.Quota()
    with pytest.raises(ValueError, match="insights"):
        quota.charge("insights")


def test_the_costs_are_one_per_page():
    assert discover.UNIT_COSTS == {"ads_archive": 1}


def test_a_negative_budget_is_refused():
    with pytest.raises(ValueError, match="negative"):
        discover.Quota(budget=-1)


def test_the_shipped_plan_stays_far_inside_one_hour():
    """The property is the HEADROOM, not today's page count.

    This asserted page_calls == 1 and max_calls == 12, which was true of a
    seed file carrying two pages and went red the day eleven real page ids
    were added - a test failing because the work went well. What the budget
    rule actually says (docs/COST.md) is that one sweep stays far enough
    inside the hourly allowance that a same-hour re-run still fits, so that
    is what is pinned here. The arithmetic is re-derived rather than
    hardcoded, so adding a page moves the number and never the verdict.
    """
    seeds = discover.load_seeds()
    planned = discover.plan(seeds)

    pages = len(seeds.pages)
    expected_page_calls = -(-pages // discover.MAX_PAGE_IDS_PER_CALL)  # ceil
    assert planned["page_calls"] == expected_page_calls
    assert planned["query_calls"] == len(seeds.queries)
    assert planned["max_calls"] == (
        (expected_page_calls + len(seeds.queries)) * discover.DEFAULT_MAX_PAGES
    )

    # A sweep and a same-hour re-run together stay under a fifth of the
    # allowance. Two sweeps at a tenth each is the rule; the margin is what
    # a hand-run --dry-run and a retry live in.
    assert planned["max_calls"] < discover.HOURLY_BUDGET_CALLS / 10


# ---------------------------------------------------------------------------
# The request - what is asked for, and how
# ---------------------------------------------------------------------------


def test_page_ids_are_batched_ten_to_a_call():
    api = FakeArchive(body())
    c = client(api)
    c.archive(countries=["DK"], page_ids=[str(n) for n in range(23)])
    assert len(api.calls) == 3
    assert c.quota.spent == 3
    batches = [json.loads(api.params(i)["search_page_ids"]) for i in range(3)]
    assert [len(b) for b in batches] == [10, 10, 3]
    assert batches[0] == [str(n) for n in range(10)]
    assert discover.MAX_PAGE_IDS_PER_CALL == 10


def test_ten_page_ids_are_one_call_and_eleven_are_two():
    api = FakeArchive(body())
    c = client(api)
    c.archive(countries=["DK"], page_ids=[str(n) for n in range(10)])
    assert c.quota.spent == 1
    c.archive(countries=["DK"], page_ids=[str(n) for n in range(11)])
    assert c.quota.spent == 3


def test_countries_travel_as_a_json_list():
    api = FakeArchive(body())
    client(api).archive(countries=["DK", "LT"], search_terms="q")
    assert json.loads(api.params()["ad_reached_countries"]) == ["DK", "LT"]


def test_a_keyword_search_is_unordered_over_all_ad_types():
    api = FakeArchive(body())
    client(api).archive(countries=["DK"], search_terms="buhalterine apskaita")
    params = api.params()
    assert params["search_terms"] == "buhalterine apskaita"
    assert params["search_type"] == "KEYWORD_UNORDERED"
    assert params["ad_type"] == "ALL"
    assert params["ad_active_status"] == "ALL"


def test_a_page_search_sends_no_search_terms():
    """Searching a competitor by name returns everyone talking about it."""
    api = FakeArchive(body())
    client(api).archive(countries=["GB"], page_ids=["555"])
    assert "search_terms" not in api.params()
    assert "search_type" not in api.params()


def test_the_fields_are_the_contract_list_joined_by_commas():
    api = FakeArchive(body())
    client(api).archive(countries=["DK"], search_terms="q")
    assert api.params()["fields"] == ",".join(discover.FIELDS)
    assert "eu_total_reach" in discover.FIELDS
    assert "ad_delivery_stop_time" in discover.FIELDS
    for political_only in ("impressions", "spend", "currency"):
        assert political_only not in discover.FIELDS


def test_the_window_and_languages_and_status_are_passed_through():
    api = FakeArchive(body())
    client(api).archive(countries=["LT"], search_terms="q", date_min="2026-06-20",
                        languages=["lt"], active_status="ACTIVE")
    params = api.params()
    assert params["ad_delivery_date_min"] == "2026-06-20"
    assert json.loads(params["languages"]) == ["lt"]
    assert params["ad_active_status"] == "ACTIVE"


def test_no_window_means_no_date_parameter():
    api = FakeArchive(body())
    client(api).archive(countries=["DK"], search_terms="q")
    assert "ad_delivery_date_min" not in api.params()
    assert "languages" not in api.params()


def test_an_unknown_active_status_is_refused():
    with pytest.raises(ValueError, match="active_status"):
        client(FakeArchive()).archive(countries=["DK"], search_terms="q", active_status="LIVE")


def test_a_search_with_nothing_to_search_is_refused():
    with pytest.raises(ValueError, match="page_ids"):
        client(FakeArchive()).archive(countries=["DK"])
    with pytest.raises(ValueError, match="country"):
        client(FakeArchive()).archive(countries=[], search_terms="q")


def test_every_call_goes_to_the_unversioned_archive_endpoint(monkeypatch):
    monkeypatch.delenv(discover.GRAPH_VERSION_ENV, raising=False)
    api = FakeArchive(body())
    client(api).archive(countries=["DK"], search_terms="q")
    assert api.urls[0].startswith("https://graph.facebook.com/ads_archive?")
    assert discover.API == "https://graph.facebook.com/ads_archive"


def test_the_environment_can_insert_a_graph_version(monkeypatch):
    monkeypatch.setenv(discover.GRAPH_VERSION_ENV, "v21.0")
    api = FakeArchive(body())
    client(api).archive(countries=["DK"], search_terms="q")
    assert api.urls[0].startswith("https://graph.facebook.com/v21.0/ads_archive?")
    monkeypatch.setenv(discover.GRAPH_VERSION_ENV, "21.0")
    assert discover.api_url() == "https://graph.facebook.com/v21.0/ads_archive"


def test_a_malformed_graph_version_is_refused_with_the_shape(monkeypatch):
    monkeypatch.setenv(discover.GRAPH_VERSION_ENV, "latest")
    with pytest.raises(discover.DiscoveryError, match="v21.0"):
        discover.api_url()


# ---------------------------------------------------------------------------
# The token - a header, never a URL, never a message
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, text: str):
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_default_transport_sends_the_token_as_a_bearer_header(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["timeout"] = timeout
        return FakeResponse(json.dumps({"data": []}))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = discover._http("https://graph.facebook.com/ads_archive?limit=1", "sekrit-token")
    assert result == {"data": []}
    assert seen["headers"]["Authorization"] == "Bearer sekrit-token"
    assert seen["headers"]["Accept"] == "application/json"
    assert "sekrit-token" not in seen["url"]
    assert seen["timeout"] == discover.HTTP_TIMEOUT_SECONDS


def test_the_token_is_never_in_a_url_the_transport_sees():
    api = FakeArchive(body(ad("1"), next_after="c2"), body())
    c = client(api, token="sekrit-token")
    c.archive(countries=["DK"], page_ids=["1", "2"], search_terms="q", languages=["da"])
    assert api.calls, "the transport was called"
    for url, token in api.calls:
        assert "sekrit-token" not in url
        assert token == "sekrit-token"


def test_the_token_is_scrubbed_from_a_provider_error_that_echoes_it():
    """Meta answers a bad token with the token beside the message. It is the
    body an operator needs, so it is kept and the value cut out of it."""
    def failing(url, token):
        raise discover.ApiError(
            f"Ad Library API 400: Invalid OAuth access token - {token} (code 190)")

    with pytest.raises(discover.ApiError) as excinfo:
        client(failing, token="sekrit-token").archive(countries=["DK"], search_terms="q")
    message = str(excinfo.value)
    assert "sekrit-token" not in message
    assert "Invalid OAuth access token" in message


def test_any_exception_from_a_transport_is_scrubbed_and_unchained():
    def failing(url, token):
        raise KeyError(f"broke with sekrit-token in hand")

    with pytest.raises(discover.ApiError) as excinfo:
        client(failing, token="sekrit-token").archive(countries=["DK"], search_terms="q")
    error = excinfo.value
    assert "sekrit-token" not in str(error)
    assert "KeyError" in str(error)
    assert error.__context__ is None and error.__cause__ is None


def test_the_token_is_absent_from_a_quota_refusal():
    with pytest.raises(discover.QuotaExceededError) as excinfo:
        client(FakeArchive(), budget=0, token="sekrit-token").archive(countries=["DK"], search_terms="q")
    assert "sekrit-token" not in str(excinfo.value)


def test_an_error_object_in_a_200_body_is_not_read_as_zero_results():
    api = FakeArchive({"error": {"message": "Calls to this api have exceeded the rate limit.",
                                 "type": "OAuthException", "code": 613}})
    with pytest.raises(discover.ApiError, match="rate limit") as excinfo:
        client(api).archive(countries=["DK"], search_terms="q")
    assert "613" in str(excinfo.value)
    assert "seeds.yaml" in str(excinfo.value)


def test_an_expired_token_error_names_the_secret_and_the_status_command():
    api = FakeArchive({"error": {"message": "Error validating access token",
                                 "type": "OAuthException", "code": 190}})
    with pytest.raises(discover.ApiError) as excinfo:
        client(api).archive(countries=["DK"], search_terms="q")
    message = str(excinfo.value)
    assert "META_ACCESS_TOKEN" in message
    assert "engine.oauth --status" in message


def test_a_permission_error_names_identity_confirmation():
    api = FakeArchive({"error": {"message": "(#10) Application does not have permission",
                                 "type": "OAuthException", "code": 10}})
    with pytest.raises(discover.ApiError, match="facebook.com/ID"):
        client(api).archive(countries=["DK"], search_terms="q")


def test_an_http_error_body_reaches_the_operator(monkeypatch):
    import urllib.error

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {},
            io.BytesIO(json.dumps({"error": {"message": "Invalid parameter", "code": 100}}).encode()),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(discover.ApiError, match="Invalid parameter") as excinfo:
        discover._http("https://graph.facebook.com/ads_archive?limit=1", "t")
    assert "code 100" in str(excinfo.value)


def test_a_missing_token_is_named_without_a_socket(monkeypatch):
    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_TOKEN_ISSUED", raising=False)
    with pytest.raises(discover.MissingTokenError) as excinfo:
        discover.AdLibraryClient(transport=FakeArchive())
    assert "META_ACCESS_TOKEN" in str(excinfo.value)


def test_a_token_passed_in_needs_nothing_from_the_environment(monkeypatch):
    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_TOKEN_ISSUED", raising=False)
    assert client(FakeArchive()).quota.remaining == 200


# ---------------------------------------------------------------------------
# Time - the two clocks the archive uses
# ---------------------------------------------------------------------------


def test_days_running_from_iso_strings_with_a_basic_offset():
    assert discover.days_running("2026-08-08T12:00:00+0000", None, TODAY) == 41


def test_days_running_from_epoch_integers():
    start = int(datetime(2026, 8, 8, 12, tzinfo=timezone.utc).timestamp())
    stop = int(datetime(2026, 9, 1, 12, tzinfo=timezone.utc).timestamp())
    assert discover.days_running(start, None, TODAY) == 41
    assert discover.days_running(start, stop, TODAY) == 24
    assert discover.days_running(str(start), str(stop), TODAY) == 24


def test_a_finished_ad_is_measured_stop_minus_start():
    assert discover.days_running("2026-08-01T00:00:00+0000", "2026-08-15T00:00:00+0000", TODAY) == 14


def test_a_scheduled_stop_in_the_future_is_measured_to_today():
    assert discover.days_running("2026-09-01T00:00:00+0000", "2026-12-01T00:00:00+0000", TODAY) == 17
    assert discover.is_active("2026-12-01T00:00:00+0000", TODAY) is True


def test_active_when_the_stop_is_absent_and_inactive_when_it_is_past():
    assert discover.is_active(None, TODAY) is True
    assert discover.is_active("", TODAY) is True
    assert discover.is_active("2026-09-01T00:00:00+0000", TODAY) is False


def test_whole_days_are_floored_and_never_negative():
    assert discover.days_running("2026-09-17T13:26:25+0000", None, TODAY) == 0
    assert discover.days_running("2026-09-30T00:00:00+0000", None, TODAY) == 0


def test_a_missing_start_cannot_be_dated():
    with pytest.raises(ValueError, match="ad_delivery_start_time"):
        discover.days_running(None, None, TODAY)


def test_an_unreadable_timestamp_names_both_accepted_forms():
    with pytest.raises(ValueError, match="epoch"):
        discover.parse_time("yesterday")


@pytest.mark.parametrize("value", ["2026-09-17T13:26:25+0000", "2026-09-17T13:26:25Z",
                                   "2026-09-17T13:26:25", "2026-09-17T13:26:25+00:00"])
def test_every_iso_spelling_reads_as_the_same_utc_moment(value):
    assert discover.parse_time(value) == datetime(2026, 9, 17, 13, 26, 25, tzinfo=timezone.utc)


def test_today_may_be_a_date_a_datetime_or_absent():
    from datetime import date
    assert discover.days_running("2026-09-01", None, date(2026, 9, 18)) == 17
    assert discover.days_running("2026-09-01", None, datetime(2026, 9, 18)) == 17
    assert discover.days_running("2020-01-01", None, None) > 2000


def test_the_window_is_dated_from_today():
    api = FakeArchive(body())
    seeds = discover.Seeds(countries=("DK",), queries=(discover.Query("q"),))
    discover.discover(seeds, client=client(api), today=TODAY, days=30)
    assert api.params()["ad_delivery_date_min"] == "2026-08-19"


def test_a_candidate_from_a_finished_ad_is_kept_and_marked_inactive():
    api = FakeArchive(body(ad("1", start="2026-07-01T00:00:00+0000", stop="2026-08-01T00:00:00+0000")))
    seeds = discover.Seeds(countries=("DK",), pages=(BALANCE,))
    row = discover.discover(seeds, client=client(api), today=TODAY)[0]
    assert row["metrics"]["active"] is False
    assert row["metrics"]["days_running"] == 31


def test_an_ad_without_a_start_time_is_skipped_not_guessed():
    undated = ad("1")
    del undated["ad_delivery_start_time"]
    api = FakeArchive(body(undated, ad("2")))
    seeds = discover.Seeds(countries=("DK",), pages=(BALANCE,))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert [r["id"] for r in rows] == ["fb-2"]


# ---------------------------------------------------------------------------
# Variants - how many versions of one hook a page is running
# ---------------------------------------------------------------------------


def rows_for(page_id: str, *specs, origin="competitor") -> list[dict]:
    """specs: reach, (reach, days) or (reach, days, primary_text)."""
    rows = []
    for n, spec in enumerate(specs):
        reach, days, text = (spec, 1, "") if not isinstance(spec, tuple) else (spec + (1, ""))[:3]
        rows.append(discover.candidate(
            id=f"fb-{page_id}-{n}", url="u", channel=page_id, origin=origin,
            page_id=page_id, eu_total_reach=reach, days_running=days, primary_text=text,
        ))
    return rows


def test_variants_count_the_ads_of_a_page_that_open_with_the_same_hook():
    rows = rows_for("p1", (10, 1, "Free to sign up!"), (10, 1, "free to sign up"),
                    (10, 1, "Free to sign up."), (10, 1, "Something else"))
    counted = discover.add_variants(rows)
    assert [r["metrics"]["variants"] for r in counted] == [3, 3, 3, 1]


def test_variants_are_counted_per_page_not_across_pages():
    rows = rows_for("p1", (10, 1, "Same hook")) + rows_for("p2", (10, 1, "Same hook"))
    assert [r["metrics"]["variants"] for r in discover.add_variants(rows)] == [1, 1]


def test_variants_fall_back_to_the_headline_when_the_body_is_empty():
    a = discover.candidate(id="fb-a", url="u", channel="c", origin="competitor", page_id="p",
                           headline="Book a demo")
    b = discover.candidate(id="fb-b", url="u", channel="c", origin="competitor", page_id="p",
                           headline="Book a demo")
    assert [r["metrics"]["variants"] for r in discover.add_variants([a, b])] == [2, 2]


def test_textless_ads_are_not_each_others_variants():
    rows = rows_for("p1", (10, 1, ""), (10, 1, ""))
    assert [r["metrics"]["variants"] for r in discover.add_variants(rows)] == [1, 1]


def test_variants_land_in_the_discovered_record():
    api = FakeArchive(body(ad("1", body="Free to sign up"), ad("2", body="Free to sign up"),
                           ad("3", body="Another line")))
    seeds = discover.Seeds(countries=("DK",), pages=(BALANCE,))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert [r["metrics"]["variants"] for r in rows] == [2, 2, 1]


# ---------------------------------------------------------------------------
# Outlier ratio - the difference between an outlier and a far-reaching ad
# ---------------------------------------------------------------------------


def test_the_ratio_is_reach_per_day_over_the_median_of_the_other_ads():
    scored = discover.add_outlier_ratios(rows_for("p", 10, 20, 30, 300))
    # For the 300: the others are 10, 20, 30 - median 20 - so 15x.
    assert scored[3]["outlier_ratio"] == 15.0


def test_reach_is_divided_by_days_running_before_it_is_compared():
    """A launch that bought 60k in three days beats a slow burn to 60k in sixty."""
    scored = discover.add_outlier_ratios(rows_for("p", (1000, 10), (1000, 10), (60000, 3)))
    assert scored[2]["outlier_ratio"] == 200.0  # 20000/day over 100/day


def test_day_zero_counts_as_one_day():
    scored = discover.add_outlier_ratios(rows_for("p", (100, 1), (100, 1), (500, 0)))
    assert scored[2]["outlier_ratio"] == 5.0


def test_the_ad_itself_is_excluded_from_its_own_baseline():
    """Included, a lone hit drags its own baseline up and hides itself."""
    scored = discover.add_outlier_ratios(rows_for("p", 10, 10, 1000))
    assert scored[2]["outlier_ratio"] == 100.0


def test_an_ordinary_ad_scores_about_one():
    scored = discover.add_outlier_ratios(rows_for("p", 100, 100, 100, 100))
    assert [r["outlier_ratio"] for r in scored] == [1.0, 1.0, 1.0, 1.0]


def test_a_far_reaching_ad_on_a_far_reaching_page_is_not_an_outlier():
    """The whole point: 50k is unremarkable when the page always does 50k."""
    scored = discover.add_outlier_ratios(rows_for("big", 50000, 51000, 49000))
    assert all(r["outlier_ratio"] < 1.2 for r in scored)


def test_a_page_with_no_other_ad_yields_the_documented_sentinel():
    scored = discover.add_outlier_ratios(rows_for("lonely", 999999))
    assert scored[0]["outlier_ratio"] == discover.NO_BASELINE
    assert discover.NO_BASELINE == 0.0
    assert discover.MIN_BASELINE_ADS == 1


def test_a_baseline_of_zero_reach_yields_the_sentinel_not_a_divide_by_zero():
    scored = discover.add_outlier_ratios(rows_for("new", 0, 0, 500))
    assert [r["outlier_ratio"] for r in scored] == [discover.NO_BASELINE] * 3


def test_each_page_gets_its_own_baseline():
    scored = discover.add_outlier_ratios(rows_for("small", 10, 10, 200) + rows_for("big", 50000, 50000, 50000))
    assert scored[2]["outlier_ratio"] == 20.0
    assert scored[5]["outlier_ratio"] == 1.0


def test_ads_without_a_page_id_are_not_each_others_baseline():
    scored = discover.add_outlier_ratios(rows_for("", 10, 1000))
    assert [r["outlier_ratio"] for r in scored] == [discover.NO_BASELINE] * 2


def test_the_sentinel_sorts_below_every_real_outlier():
    """Downstream ranks on this field; a sentinel must never win the ranking."""
    scored = discover.add_outlier_ratios(rows_for("p", 10, 20, 300) + rows_for("x", 9))
    ranked = sorted(scored, key=lambda r: r["outlier_ratio"], reverse=True)
    assert ranked[-1]["metrics"]["page_id"] == "x"


def test_the_ratio_is_rounded_to_three_places():
    scored = discover.add_outlier_ratios(rows_for("p", 3, 3, 7))
    assert scored[2]["outlier_ratio"] == 2.333


# ---------------------------------------------------------------------------
# Origin - pages first, first find wins
# ---------------------------------------------------------------------------


def test_an_ad_from_a_seeded_page_carries_that_pages_origin():
    api = FakeArchive(body(ad("1", page_id="555", page_name="Fyxer")))
    seeds = discover.Seeds(countries=("DK",), pages=(FYXER,))
    row = discover.discover(seeds, client=client(api), today=TODAY)[0]
    assert row["origin"] == "competitor"
    assert row["channel"] == "Fyxer"


def test_a_query_result_is_icp_adjacent_unless_the_query_says_otherwise():
    api = FakeArchive(body(ad("1", page_id="9", page_name="Someone")),
                      body(ad("2", page_id="9", page_name="Someone")))
    seeds = discover.Seeds(countries=("DK",), queries=(
        discover.Query("regnskab"), discover.Query("fyxer alternative", origin="competitor")))
    rows = {r["id"]: r for r in discover.discover(seeds, client=client(api), today=TODAY)}
    assert rows["fb-1"]["origin"] == "icp-adjacent"
    assert rows["fb-2"]["origin"] == "competitor"


def test_a_seeded_page_beats_a_query_that_returns_the_same_ad():
    """First find wins, and pages are searched first."""
    same = ad("1", page_id="555", page_name="Fyxer")
    api = FakeArchive(body(same), body(same))
    seeds = discover.Seeds(countries=("DK",), pages=(FYXER,), queries=(discover.Query("ai email"),))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert [r["origin"] for r in rows] == ["competitor"]
    assert len(api.calls) == 2


def test_a_batch_mixing_origins_attributes_each_ad_to_its_own_page():
    gosimple = discover.Page("gosimple", "GoSimple", "777", "icp-adjacent", ("GB",))
    api = FakeArchive(body(ad("1", page_id="555", page_name="Fyxer"), ad("2", page_id="777", page_name="GoSimple")))
    seeds = discover.Seeds(countries=("DK",), pages=(FYXER, gosimple))
    rows = {r["id"]: r for r in discover.discover(seeds, client=client(api), today=TODAY)}
    assert rows["fb-1"]["origin"] == "competitor"
    assert rows["fb-2"]["origin"] == "icp-adjacent"
    assert len(api.calls) == 1


def test_an_ad_from_a_page_nobody_asked_for_is_not_given_an_origin():
    api = FakeArchive(body(ad("1", page_id="000", page_name="Stranger")))
    seeds = discover.Seeds(countries=("DK",), pages=(FYXER,))
    assert discover.discover(seeds, client=client(api), today=TODAY) == []


def test_the_channel_is_the_api_page_name_or_the_seeded_name():
    api = FakeArchive(body(ad("1", page_id="555", page_name=""), ad("2", page_id="555", page_name="Fyxer Ltd")))
    seeds = discover.Seeds(countries=("DK",), pages=(FYXER,))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert [r["channel"] for r in rows] == ["Fyxer", "Fyxer Ltd"]


def test_a_page_runs_in_its_own_countries_and_the_record_says_so():
    api = FakeArchive(body(ad("1", page_id="555")), body(ad("2")))
    seeds = discover.Seeds(countries=("DK", "LT"), pages=(FYXER,), queries=(discover.Query("q"),))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert json.loads(api.params(0)["ad_reached_countries"]) == ["GB"]
    assert json.loads(api.params(1)["ad_reached_countries"]) == ["DK", "LT"]
    assert rows[0]["metrics"]["countries"] == ["GB"]
    assert rows[1]["metrics"]["countries"] == ["DK", "LT"]


def test_pages_sharing_a_country_list_share_a_call():
    a = discover.Page("a", "A", "1", "competitor", None)
    b = discover.Page("b", "B", "2", "icp-adjacent", None)
    c = discover.Page("c", "C", "3", "competitor", ("GB",))
    api = FakeArchive(body())
    discover.discover(discover.Seeds(countries=("DK",), pages=(a, b, c)), client=client(api), today=TODAY)
    assert len(api.calls) == 2
    assert json.loads(api.params(0)["search_page_ids"]) == ["1", "2"]
    assert json.loads(api.params(1)["search_page_ids"]) == ["3"]


def test_a_query_carries_its_languages_to_the_request():
    api = FakeArchive(body())
    seeds = discover.Seeds(countries=("LT",), queries=(discover.Query("buhalteris", languages=("lt",)),))
    discover.discover(seeds, client=client(api), today=TODAY)
    assert json.loads(api.params()["languages"]) == ["lt"]


def test_an_exhausted_budget_raises_rather_than_returning_half_a_run():
    api = FakeArchive(body(ad("1")))
    seeds = discover.Seeds(countries=("DK",), queries=(discover.Query("a"), discover.Query("b")))
    with pytest.raises(discover.QuotaExceededError):
        discover.discover(seeds, client=client(api, budget=1), today=TODAY)


def test_no_seeds_means_no_calls():
    api = FakeArchive(body(ad("1")))
    c = client(api)
    assert discover.discover(discover.Seeds(countries=("DK",)), client=c, today=TODAY) == []
    assert api.calls == [] and c.quota.spent == 0


# ---------------------------------------------------------------------------
# No snapshot is ever requested
# ---------------------------------------------------------------------------


def arm_every_socket(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("discovery attempted a network call")

    monkeypatch.setattr(discover, "_http", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


def test_load_seeds_opens_no_socket(tmp_path, monkeypatch):
    arm_every_socket(monkeypatch)
    seeds = discover.load_seeds(write_seeds(tmp_path, ONE_PAGE))
    assert [p.page_id for p in seeds.pages] == ["1007614045762121"]
    assert discover.load_seeds().path == discover.SEEDS_PATH


def test_the_whole_run_completes_with_every_socket_armed(tmp_path, monkeypatch):
    """Every socket in the process explodes. The run must still complete."""
    arm_every_socket(monkeypatch)
    seeds = discover.load_seeds(write_seeds(tmp_path, ONE_PAGE))
    api = FakeArchive(body(ad("1"), ad("2")), body(ad("3", page_id="9")), body(ad("4", page_id="8")))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert [r["id"] for r in rows] == ["fb-1", "fb-2", "fb-3", "fb-4"]


def test_no_transport_call_ever_targets_a_snapshot_page(tmp_path, monkeypatch):
    """The stub hands back snapshot URLs on every ad; none is ever requested."""
    arm_every_socket(monkeypatch)
    seeds = discover.load_seeds(write_seeds(tmp_path, ONE_PAGE))
    api = FakeArchive(body(ad("1", snapshot=True), ad("2", snapshot=True), next_after="c2"),
                      body(ad("3", snapshot=True)))
    rows = discover.discover(seeds, client=client(api), today=TODAY)
    assert rows, "the run found candidates"
    assert api.calls, "the run made calls"
    for url in api.urls:
        assert "ads/library/?id=" not in url
        assert "facebook.com/ads/library" not in url
        assert "render_ad" not in url
        assert urlparse(url).netloc == "graph.facebook.com"
    for row in rows:
        assert row["url"].startswith("https://www.facebook.com/ads/library/?id=")
        assert "ad_snapshot_url" not in json.dumps(row)


def test_the_module_has_no_function_that_fetches_a_snapshot():
    import inspect
    source = inspect.getsource(discover)
    assert "render_ad" not in source
    assert "ads/library" in source  # the URL is written into records
    assert "download" not in source.replace("not a download", "")


# ---------------------------------------------------------------------------
# Seeds - every error names the fix
# ---------------------------------------------------------------------------


def test_a_page_with_an_unknown_origin_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("origin: icp-adjacent", "origin: rival"))
    with pytest.raises(discover.SeedsError, match="competitor or icp-adjacent"):
        discover.load_seeds(path)


def test_a_query_with_an_unknown_origin_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("    countries: [LT]\n", "    countries: [LT]\n    origin: own\n"))
    with pytest.raises(discover.SeedsError, match="origin 'own'"):
        discover.load_seeds(path)


def test_two_pages_sharing_an_id_are_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("queries:", """  - id: balance-dk
    name: Another
    page_id: "2"
    origin: competitor
queries:"""))
    with pytest.raises(discover.SeedsError, match="share the id 'balance-dk'"):
        discover.load_seeds(path)


def test_two_pages_sharing_a_page_id_are_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("queries:", """  - id: balance-again
    name: Another
    page_id: "1007614045762121"
    origin: competitor
queries:"""))
    with pytest.raises(discover.SeedsError, match="share page_id 1007614045762121"):
        discover.load_seeds(path)


def test_a_page_without_a_page_id_is_refused_with_where_to_read_it(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace('page_id: "1007614045762121"', "page_id:"))
    with pytest.raises(discover.SeedsError) as excinfo:
        discover.load_seeds(path)
    message = str(excinfo.value)
    assert "balance-dk" in message and "no page_id" in message
    assert "Ad Library UI" in message


def test_a_page_id_that_is_a_name_or_a_url_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace('page_id: "1007614045762121"', "page_id: Balance"))
    with pytest.raises(discover.SeedsError, match="not a numeric id"):
        discover.load_seeds(path)


def test_an_unquoted_numeric_page_id_still_loads_as_a_string(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace('page_id: "1007614045762121"', "page_id: 1007614045762121"))
    assert discover.load_seeds(path).pages[0].page_id == "1007614045762121"


def test_a_country_that_is_not_a_code_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("countries: [DK, LT]", "countries: [Denmark]"))
    with pytest.raises(discover.SeedsError, match="DK, not Denmark"):
        discover.load_seeds(path)


def test_a_lower_case_code_is_upper_cased(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("countries: [DK, LT]", "countries: [dk, lt]"))
    assert discover.load_seeds(path).countries == ("DK", "LT")


def test_a_page_with_no_countries_anywhere_is_refused(tmp_path):
    document = ONE_PAGE.replace("countries: [DK, LT]\n", "").replace("    countries: [DK]\n", "")
    with pytest.raises(discover.SeedsError, match="ad_reached_countries is required"):
        discover.load_seeds(write_seeds(tmp_path, document))


def test_a_language_that_is_not_a_code_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("languages: [lt]", "languages: [Lithuanian]"))
    with pytest.raises(discover.SeedsError, match="da, not Danish"):
        discover.load_seeds(path)


def test_a_query_over_one_hundred_characters_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("  - regnskab", "  - " + "x" * 101))
    with pytest.raises(discover.SeedsError, match="100"):
        discover.load_seeds(path)


def test_the_same_query_twice_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("  - regnskab", "  - regnskab\n  - Regnskab"))
    with pytest.raises(discover.SeedsError, match="appears twice"):
        discover.load_seeds(path)


def test_a_bare_query_is_icp_adjacent_in_the_default_countries(tmp_path):
    seeds = discover.load_seeds(write_seeds(tmp_path, ONE_PAGE))
    assert seeds.queries[0] == discover.Query("regnskab", "icp-adjacent", None, None)
    assert seeds.queries[1] == discover.Query("buhalteris", "icp-adjacent", ("LT",), ("lt",))


def test_a_misspelt_top_level_block_is_refused_not_ignored(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("queries:", "querys:"))
    with pytest.raises(discover.SeedsError, match="querys"):
        discover.load_seeds(path)


def test_a_blank_own_block_loads_fine(tmp_path):
    seeds = discover.load_seeds(write_seeds(tmp_path, ONE_PAGE))
    assert seeds.own == discover.Own(None, None, None)


def test_a_filled_own_block_is_read_as_strings(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("own:\n  page_id:\n  page_name:\n  ad_account_id:\n",
                                                  'own:\n  page_id: "42"\n  page_name: DoviLoop\n  ad_account_id: act_7\n'))
    assert discover.load_seeds(path).own == discover.Own("42", "DoviLoop", "act_7")


def test_an_own_page_id_that_is_not_numeric_is_refused(tmp_path):
    path = write_seeds(tmp_path, ONE_PAGE.replace("  page_id:\n  page_name:", "  page_id: doviloop\n  page_name:"))
    with pytest.raises(discover.SeedsError, match="own.page_id"):
        discover.load_seeds(path)


def test_a_missing_seeds_file_says_it_is_hand_maintained(tmp_path):
    with pytest.raises(discover.SeedsError, match="hand-maintained"):
        discover.load_seeds(tmp_path / "absent.yaml")


def test_an_empty_seeds_file_is_not_an_error(tmp_path):
    """A repository that has not been seeded yet still loads and finds nothing."""
    seeds = discover.load_seeds(write_seeds(tmp_path, "# nothing yet\n"))
    assert seeds.pages == () and seeds.queries == () and seeds.countries == ()
    assert discover.discover(seeds, client=client(FakeArchive()), today=TODAY) == []


def test_a_seeds_file_that_is_a_list_is_refused(tmp_path):
    with pytest.raises(discover.SeedsError, match="mapping"):
        discover.load_seeds(write_seeds(tmp_path, "- DK\n"))


# ---------------------------------------------------------------------------
# The shipped seeds file
# ---------------------------------------------------------------------------


def test_the_shipped_seeds_file_parses():
    seeds = discover.load_seeds()
    assert seeds.path == discover.SEEDS_PATH
    assert seeds.countries == ("DK", "LT")


@pytest.mark.parametrize("name,page_id", [
    ("Balance - Your AI Powered Accountants", "1007614045762121"),
    ("GoSimple", "1173334875852946"),
])
def test_the_shipped_seeds_file_carries_the_pages_seen_live(name, page_id):
    """Both were in the top five of the `regnskab` DK probe this session."""
    match = [p for p in discover.load_seeds().pages if p.name == name]
    assert match, f"{name} is not in research/seeds.yaml"
    assert match[0].page_id == page_id
    assert match[0].origin == "icp-adjacent"
    assert match[0].countries == ("DK",)


def test_no_page_is_seeded_without_a_real_id():
    """The rule is "never seed a page blind", not "never seed a competitor".

    This asserted there were NO competitor pages at all, which was a fact
    about the day it was written - no competitor's page id was known yet -
    dressed up as a rule. It went red when a live search turned one up
    (Echo You, DK, billing in DKK), which is the test telling us off for
    finding what the engine exists to find.

    What must stay true is that every page in the file carries an id
    somebody actually read off the Ad Library, because a blank or invented
    id costs a call every week and returns nothing.
    """
    for page in discover.load_seeds().pages:
        assert page.page_id, f"{page.id} is seeded with no page_id"
        assert page.page_id.isdigit(), (
            f"{page.id} has page_id {page.page_id!r}; a page id is digits, "
            f"and a name in that field is the mistake this refuses"
        )
        assert page.origin in discover.ORIGINS
        assert page.countries, f"{page.id} names no country to search in"


def test_fyxer_and_jace_stay_commented_out_until_somebody_reads_their_ids():
    """The two reel-engine watches on YouTube. A keyword search for either
    name across five countries returned 2,642 ads and none of theirs, so the
    id has to come from the Ad Library UI - and they may run in no EU country
    at all, in which case the archive does not hold them. Recorded in the
    file rather than seeded blind."""
    text = discover.SEEDS_PATH.read_text(encoding="utf-8")
    assert "# - id: fyxer" in text and "# - id: jace-ai" in text
    assert "#   page_id:\n" in text
    seeded = {p.id for p in discover.load_seeds().pages}
    assert "fyxer" not in seeded and "jace-ai" not in seeded


def test_the_shipped_queries_are_the_markets_own_words():
    queries = {q.text: q for q in discover.load_seeds().queries}
    assert queries["regnskab"].countries == ("DK",) and queries["regnskab"].languages == ("da",)
    assert queries["bogholder"].countries == ("DK",)
    assert queries["buhalterine apskaita"].countries == ("LT",) and queries["buhalterine apskaita"].languages == ("lt",)
    assert queries["buhalteris"].countries == ("LT",)
    assert queries["ai email assistant"].countries == ("DK", "LT")
    assert all(q.origin == "icp-adjacent" for q in queries.values())


def test_the_shipped_own_block_is_blank():
    assert discover.load_seeds().own == discover.Own(None, None, None)


def test_the_shipped_seeds_file_explains_itself():
    text = discover.SEEDS_PATH.read_text(encoding="utf-8")
    assert text.startswith("#"), "the file opens with its explanation"
    for key in ("countries", "page_id", "origin", "queries", "languages", "own", "ad_account_id"):
        assert key in text
    # The refusal posture is explained, and explained about the thing that
    # actually refuses. A blank page_id under `pages` IS refused by name at
    # load; a blank `own:` block is refused by nothing, and the file said the
    # opposite until 2026-09-18 - it credited engine/measure.py with a refusal
    # that module cannot make, because it never opens this file. A bare
    # substring check on "refuses by name" passed throughout, which is why
    # both halves are pinned here rather than one phrase.
    assert "refuses by name at load" in text
    assert "refused by nothing" in text


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def patch_client(monkeypatch, api) -> None:
    """main() builds its own client from the environment; hand it ours.

    The real class is captured first, because the module attribute is what
    the `client()` helper above reads too."""
    real = discover.AdLibraryClient
    monkeypatch.setattr(
        discover, "AdLibraryClient",
        lambda **kw: real("test-token", budget=kw.get("budget", discover.HOURLY_BUDGET_CALLS),
                          transport=api),
    )


def test_json_writes_exactly_one_json_document_to_stdout(tmp_path, monkeypatch, capsys):
    api = FakeArchive(body(ad("1"), ad("2")))
    patch_client(monkeypatch, api)
    code = discover.main(["--seeds", str(write_seeds(tmp_path, ONE_PAGE)), "--json", "--budget", "50"])
    assert code == 0
    out, err = capsys.readouterr()
    rows, end = json.JSONDecoder().raw_decode(out)
    assert out[end:].strip() == "", "nothing follows the one document"
    assert out.endswith("\n")
    assert [r["id"] for r in rows] == ["fb-1", "fb-2"]
    assert out == json.dumps(rows, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert "discovered 2 candidates" in err and "of 50 Ad Library calls" in err


def test_out_writes_the_document_to_a_file_and_stdout_stays_empty(tmp_path, monkeypatch, capsys):
    api = FakeArchive(body(ad("1")))
    patch_client(monkeypatch, api)
    target = tmp_path / "out.json"
    assert discover.main(["--seeds", str(write_seeds(tmp_path, ONE_PAGE)), "--out", str(target)]) == 0
    out, _ = capsys.readouterr()
    assert out == ""
    assert [r["id"] for r in json.loads(target.read_text(encoding="utf-8"))] == ["fb-1"]


def test_days_reaches_the_request_from_the_command_line(tmp_path, monkeypatch):
    api = FakeArchive(body())
    patch_client(monkeypatch, api)
    discover.main(["--seeds", str(write_seeds(tmp_path, ONE_PAGE)), "--days", "14"])
    assert "ad_delivery_date_min" in api.params()


def test_a_discovery_error_is_one_line_and_exit_1(tmp_path, capsys):
    path = write_seeds(tmp_path, ONE_PAGE.replace("origin: icp-adjacent", "origin: rival"))
    assert discover.main(["--seeds", str(path), "--json"]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert err.count("\n") == 1 and "rival" in err and "Traceback" not in err


def test_a_missing_token_is_one_line_and_exit_1(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("META_TOKEN_ISSUED", raising=False)
    assert discover.main(["--seeds", str(write_seeds(tmp_path, ONE_PAGE))]) == 1
    _, err = capsys.readouterr()
    assert "META_ACCESS_TOKEN" in err and err.count("\n") == 1


def test_a_dry_run_prints_the_plan_and_needs_no_token(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    arm_every_socket(monkeypatch)
    assert discover.main(["--seeds", str(write_seeds(tmp_path, ONE_PAGE)), "--dry-run"]) == 0
    out, err = capsys.readouterr()
    assert out == ""
    assert "1 seeded pages in 1 call(s), 2 queries; 3-6 Ad Library calls" in err


# ---------------------------------------------------------------------------
# The token, and the one promise whose failure is silent and permanent
#
# These exist because the promise was BROKEN, in production code, on the
# default transport, with no test covering it. An independent audit on
# 2026-09-19 set META_ACCESS_TOKEN to a 200-character sentinel and got 116 and
# 121 characters of it onto stderr out of main(), and 40 characters into
# research/selection.json - which .github/workflows/research.yml git-adds and
# pushes.
#
# The cause was two decisions that were each defensible alone. This module
# truncates Meta's body to 200 characters so an error stays readable, and it
# kept a LOCAL copy of the redaction that cut whole values only, on the
# argument that "whole-value is what Meta echoes". Our own truncation is what
# turns a whole echo into a partial one, so the two together produce a token
# fragment that the scrubber cannot match.
# ---------------------------------------------------------------------------

# Long enough that our own body[:200] truncation slices it, which is the
# shape that defeated the old whole-value replace.
SENTINEL = "EAA" + "Zq7Kx2Lw9Pv4Nt6Ym1Bd8Rf3Gh5Js0Cn" * 6


def test_a_partial_echo_of_the_token_is_cut_out():
    """Meta echoes the token; we truncate its body; the slice must still go."""
    body = "Invalid OAuth access token: %s" % SENTINEL
    cleaned = discover._redact(body[:200], SENTINEL)
    assert SENTINEL not in cleaned
    # And no run of the token long enough to be worth having survives either.
    for start in range(0, len(SENTINEL) - 24):
        assert SENTINEL[start:start + 24] not in cleaned


def test_both_api_error_shapes_survive_the_scrub():
    """_api_error does NOT scrub - it has no token to scrub with. The cut
    happens upstream in _scrubbed, which is why the truncation and the
    redaction have to agree about partial echoes: this function can make the
    fragment, and that one has to be able to match it.

    Two shapes, and only the second is the one that broke. A well-formed error
    body carries Meta's own message through whole, so a whole-value replace
    was enough for it - which is exactly why the local copy looked correct.
    A body that is not the expected JSON falls back to `body[:200]`, and THAT
    is where our own truncation slices a ~200-character token into a fragment
    no whole-value replace can find.
    """
    formed = discover._api_error(400, json.dumps(
        {"error": {"message": "Bad token %s" % SENTINEL, "code": 190,
                   "type": "OAuthException"}}))
    assert SENTINEL in formed, "the well-formed path no longer carries it whole"

    sliced = discover._api_error(400, "<html>gateway error %s</html>" % SENTINEL)
    assert SENTINEL not in sliced, "the fallback no longer truncates"
    assert SENTINEL[:40] in sliced, "the fallback no longer slices a long token"

    # The scrubber that runs over each of them afterwards removes both.
    for message in (formed, sliced):
        cleaned = discover._redact(message, SENTINEL)
        assert SENTINEL not in cleaned
        for start in range(0, len(SENTINEL) - 24):
            assert SENTINEL[start:start + 24] not in cleaned


def test_a_transport_that_echoes_the_token_cannot_leak_it(monkeypatch):
    """The whole path, through the module's own scrubbing wrapper."""
    def echoes(url, token):
        raise RuntimeError("upstream said: %s" % SENTINEL)

    client = discover.AdLibraryClient(token=SENTINEL, transport=echoes)
    with pytest.raises(discover.ApiError) as caught:
        client.archive(countries=("DK",), search_terms="x")
    assert SENTINEL not in str(caught.value)


def test_a_clean_message_does_not_ride_out_on_a_dirty_chain():
    """The fresh-object rule.

    `error = exc if clean == str(exc) else type(exc)(clean)` re-used the
    original whenever its own message needed no scrubbing - and a clean
    message says nothing about what is chained to it. Here the outer error is
    spotless and the token is on its __context__.
    """
    def dirty():
        try:
            raise ValueError("Invalid isoformat string: %r" % SENTINEL)
        except ValueError:
            raise discover.ApiError("the Ad Library refused the request")

    with pytest.raises(discover.ApiError) as caught:
        discover._scrubbed(SENTINEL, dirty)

    error = caught.value
    assert SENTINEL not in str(error)
    chain = []
    seen = error
    while seen is not None:
        chain.append(str(seen))
        seen = seen.__context__ or seen.__cause__
    assert not any(SENTINEL in link for link in chain), chain


def test_ctrl_c_keeps_its_type_and_still_gets_scrubbed():
    """BaseException is caught - it sails past `except Exception` with its
    message intact - but rebuilding it as an ApiError would make a hung run
    need a second Ctrl-C to die."""
    def interrupted():
        raise KeyboardInterrupt("aborting while holding %s" % SENTINEL)

    with pytest.raises(KeyboardInterrupt) as caught:
        discover._scrubbed(SENTINEL, interrupted)
    assert SENTINEL not in str(caught.value)


def test_an_exit_code_survives_the_scrub():
    """SystemExit(2) rebuilt from a string would exit 1. Args are scrubbed
    element by element so an integer is left alone."""
    def exiting():
        raise SystemExit(2)

    with pytest.raises(SystemExit) as caught:
        discover._scrubbed(SENTINEL, exiting)
    assert caught.value.code == 2


def test_the_body_is_withheld_rather_than_printed_when_the_scrubber_is_gone(monkeypatch):
    """Fail closed. engine/oauth.py is imported lazily, so a broken checkout
    can reach _redact with a token and no scrubber; an unreadable error is
    recoverable and a leaked credential is not."""
    import builtins
    real_import = builtins.__import__

    def no_oauth(name, *args, **kwargs):
        if name == "engine.oauth" or (args and args[2] and "oauth" in args[2]):
            raise ImportError("engine.oauth is not in this checkout")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_oauth)
    cleaned = discover._redact("Bad token %s" % SENTINEL, SENTINEL)
    assert SENTINEL not in cleaned
    assert "withheld" in cleaned


def test_there_is_one_definition_of_the_cut_in_this_repository():
    """A second copy of a security primitive is what caused the leak: the copy
    was made, the original was hardened, and the copy was not. discover
    delegates to engine.oauth now, so a partial-echo rule added there reaches
    here without anybody remembering to copy it."""
    from engine import oauth

    with open(discover.__file__, encoding="utf-8") as handle:
        source = handle.read()
    assert "oauth._redact(text, [token])" in source, (
        "engine/discover.py no longer delegates its redaction; if that is "
        "deliberate, it must carry oauth's partial-run cut itself"
    )
    assert oauth._redact("x %s y" % SENTINEL, [SENTINEL]).find(SENTINEL) == -1
