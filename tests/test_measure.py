"""Measurement: one call per pinned ad, a ledger that refuses, and a null
wherever Meta gave nothing.

Four properties are worth a test here and the rest is bookkeeping.

**The quota is enforced, not documented.** Every launched ad is one insights
call, charged BEFORE the socket. The tests below count the calls and prove
that the call the budget cannot afford never reaches the transport.

**The token is a header, never a URL and never a message.** A URL can be
logged; a message can be a public Actions log. The tests build a real urllib
request against a fake urlopen, then make the transport raise with the token
in it - whole, as a fragment, and inside a Meta error body - and look for it
in every message and down the exception chain.

**Absent is null, never zero.** The row is contract C6 by value: a full
insights body becomes the contract's own example, a body missing a field
yields null for it, and a rate whose denominator is 0 or missing is null
rather than 0.0. A fabricated zero would sink engine.learn's medians or be
refused by engine.feedback for the wrong reason.

**One unmeasurable ad costs the others nothing.** An ad that has not
delivered, a job whose `ads` map was emptied by hand, a Meta error for one
id: each is a line in `skipped` that names the file and the fix, and every
other ad is measured. A dead token or an exhausted budget is the whole run
misconfigured, and raises.

Every test here is offline. The transport is injected; no test needs a token,
an autouse fixture explodes every socket, and one test parses the module to
prove the only thing that can open one is `_http`.
"""
import ast
import io
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from engine import approval, measure, oauth

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "creative" / "example-job.json"

# A fake credential. Long, distinctive, and obviously not real - the needle
# the leak tests go looking for in every haystack.
TOKEN = "EAAB0FAKEmetaTOKENneverLogMe00112233445566778899aabbcc"

# Contract C6's own moments.
LAUNCHED = "2026-09-29T10:00:00Z"
NOW = "2026-10-06T05:02:00Z"


# ---------------------------------------------------------------------------
# The seam: one callable, one URL and one token in, one JSON document out.
# ---------------------------------------------------------------------------


def ad_id_of(url: str) -> str:
    """The ad id in {GRAPH}/{ad_id}/insights."""
    return urlparse(url).path.rstrip("/").split("/")[-2]


def insights_row(**overrides) -> dict:
    """The insights object for contract C6's example, as Meta would send it:
    every number a string, `actions` a list of typed entries."""
    row = {
        "impressions": "4100",
        "reach": "3300",
        "clicks": "51",
        "ctr": "1.24",
        "cpc": "0.61",
        "cpm": "7.6",
        "spend": "31.2",
        "actions": [
            {"action_type": "link_click", "value": "51"},
            {"action_type": "video_view", "value": "1200"},
            {"action_type": "lead", "value": "4"},
        ],
        "cost_per_action_type": [
            {"action_type": "link_click", "value": "0.61"},
            {"action_type": "lead", "value": "7.8"},
        ],
        "video_play_actions": [{"action_type": "video_view", "value": "1500"}],
        "video_thruplay_watched_actions": [{"action_type": "video_view", "value": "240"}],
        "date_start": "2026-09-29",
        "date_stop": "2026-10-05",
    }
    row.update(overrides)
    return row


def body(*rows) -> dict:
    """One insights response. No rows is what Meta says for an undelivered ad."""
    return {"data": list(rows), "paging": {"cursors": {"before": "b", "after": "a"}}}


# The C6 row the contract prints, by value.
C6_ROW = {
    "segment": "payroll-bureaus",
    "ad_id": "1234",
    "campaign_id": "5678",
    "launched_at": LAUNCHED,
    "measured_at": NOW,
    "date_preset": "maximum",
    "metrics": {
        "impressions": 4100, "reach": 3300, "clicks": 51, "ctr": 1.24, "cpc": 0.61,
        "cpm": 7.6, "spend": 31.2, "plays_3s": 1200, "thruplays": 240,
        "p25": None, "p50": None, "p75": None, "p100": None,
        "results": 4, "cost_per_result": 7.8,
    },
    "derived": {"hook_rate": 0.293, "hold_rate": 0.2},
}


class FakeGraph:
    """A stand-in for measure._http. Records every (url, token) it is handed.

    Bodies are keyed by ad id, read off the URL path. A value that is an
    Exception is raised instead of returned; an id with no body of its own
    gets `default`, which is the C6 example unless a test says otherwise.
    """

    def __init__(self, bodies=None, *, default=None):
        self.bodies = dict(bodies or {})
        self.default = body(insights_row()) if default is None else default
        self.calls: list[tuple[str, str]] = []

    def __call__(self, url: str, token: str) -> dict:
        self.calls.append((url, token))
        reply = self.bodies.get(ad_id_of(url), self.default)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.calls]

    @property
    def ad_ids(self) -> list[str]:
        return [ad_id_of(url) for url in self.urls]

    def params(self, index: int = 0) -> dict:
        return {k: v[0] for k, v in parse_qs(urlparse(self.urls[index]).query).items()}


def client(api, *, budget: int = measure.HOURLY_BUDGET_CALLS, token: str = TOKEN):
    """A client with a stub transport and a fake token. Never touches the wire."""
    return measure.MeasureClient(token, budget=budget, transport=api)


# ---------------------------------------------------------------------------
# Fixtures: no credential, no socket, a redirected queue
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    """Nothing in this file may see a real secret or a real Graph version."""
    for name in (oauth.META_ACCESS_TOKEN, oauth.META_TOKEN_ISSUED, measure.GRAPH_VERSION_ENV):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every socket in the process explodes. A test that dials out fails."""
    def boom(*args, **kwargs):
        raise AssertionError("engine.measure tried to open a socket")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)


@pytest.fixture
def queue(tmp_path, monkeypatch):
    """A throwaway queue/ with all four stages, wired in as the real one.

    Everything reads QUEUE through approval.queue_dir() at call time, so
    patching the module global here redirects approval AND measure together.
    """
    for stage in approval.ALL_STAGES:
        (tmp_path / stage).mkdir()
    monkeypatch.setattr(approval, "QUEUE", tmp_path)
    return tmp_path


def example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


ONE_AD = {"1234": {"campaign_id": "5678", "adset_id": None}}


def launch(queue_root: Path, segment: str, ads=None, *, launched_at=LAUNCHED,
           stage: str = "launched", **overrides) -> Path:
    """A real, gate-passing C3 job as `approval launch` leaves it: ad ids
    pinned under `ads`, `launched_at` stamped, id and segment the filename."""
    job = example()
    job["id"] = job["segment"] = segment
    job["ads"] = dict(ONE_AD) if ads is None else ads
    job["launched_at"] = launched_at
    job.update(overrides)
    dest = queue_root / stage / f"{segment}.json"
    dest.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def credentials(monkeypatch, *, issued_days_ago: float = 1.0):
    """A token and a young issue date in the environment, for the CLI tests."""
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    when = datetime.now(timezone.utc) - timedelta(days=issued_days_ago)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, when.strftime("%Y-%m-%d"))


def assert_no_token(text: str) -> None:
    """Neither the whole value nor any twelve-character run of it."""
    assert TOKEN not in text
    for start in range(len(TOKEN) - oauth.MIN_REDACTED_RUN + 1):
        assert TOKEN[start:start + oauth.MIN_REDACTED_RUN] not in text, text


# ---------------------------------------------------------------------------
# The contract's constants, by value
# ---------------------------------------------------------------------------


def test_the_contract_constants_are_pinned():
    assert measure.GRAPH == "https://graph.facebook.com"
    assert measure.INSIGHT_FIELDS == (
        "impressions", "reach", "clicks", "ctr", "cpc", "cpm", "spend", "actions",
        "cost_per_action_type", "video_play_actions", "video_thruplay_watched_actions",
        "video_p25_watched_actions", "video_p50_watched_actions",
        "video_p75_watched_actions", "video_p100_watched_actions",
    )
    assert measure.DATE_PRESET == "maximum"
    assert measure.HOURLY_BUDGET_CALLS == 200
    assert measure.UNIT_COSTS == {"insights": 1}
    assert measure.MEASUREMENTS_PATH == ROOT / "research" / "measurements.json"
    assert measure.SCHEMA == 1
    assert measure.STAGE == "launched"


def test_the_reads_the_contract_names_are_the_module_constants():
    assert measure.PLAY_ACTION == "video_view"
    assert measure.RESULT_ACTIONS == ("lead", "schedule", "contact", "link_click")
    assert list(C6_ROW["metrics"]) == list(measure.METRIC_KEYS)
    assert list(C6_ROW["derived"]) == list(measure.DERIVED_KEYS)


def test_the_unverified_field_names_say_so_where_they_are_declared():
    """The first live run is the proof; the file must say that beside the list."""
    source = Path(measure.__file__).read_text(encoding="utf-8")
    block = source[:source.index("INSIGHT_FIELDS = (")]
    assert "TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE" in block
    assert "--raw" in block


# ---------------------------------------------------------------------------
# The URL and the header
# ---------------------------------------------------------------------------


def test_the_insights_url_is_the_contract_shape():
    url = measure.insights_url("1234")
    parts = urlparse(url)
    assert parts.scheme == "https" and parts.netloc == "graph.facebook.com"
    assert parts.path == "/1234/insights"
    params = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert params == {
        "fields": ",".join(measure.INSIGHT_FIELDS),
        "date_preset": "maximum",
    }


def test_the_environment_can_insert_a_graph_version(monkeypatch):
    monkeypatch.setenv(measure.GRAPH_VERSION_ENV, "v21.0")
    assert measure.insights_url("1").startswith("https://graph.facebook.com/v21.0/1/insights?")
    monkeypatch.setenv(measure.GRAPH_VERSION_ENV, "21.0")
    assert measure.graph_url() == "https://graph.facebook.com/v21.0"


def test_a_malformed_graph_version_is_refused_with_the_shape(monkeypatch):
    monkeypatch.setenv(measure.GRAPH_VERSION_ENV, "latest")
    with pytest.raises(measure.MeasureError, match="v21.0"):
        measure.graph_url()


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
        return FakeResponse(json.dumps(body(insights_row())))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = measure._http(measure.insights_url("1234"), TOKEN)
    assert result["data"][0]["impressions"] == "4100"
    assert seen["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert seen["headers"]["Accept"] == "application/json"
    assert_no_token(seen["url"])
    assert seen["timeout"] == measure.HTTP_TIMEOUT_SECONDS


def test_the_token_is_never_in_a_url_the_transport_sees(queue):
    launch(queue, "accountants", {"1234": {"campaign_id": None, "adset_id": None},
                                  "4321": {"campaign_id": None, "adset_id": None}})
    api = FakeGraph()
    measure.measure_all(client=client(api), now=NOW)
    assert api.calls, "the transport was called"
    for url, token in api.calls:
        assert_no_token(url)
        assert token == TOKEN


def test_an_http_error_body_reaches_the_operator_and_points_at_the_field_list(monkeypatch):
    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {},
            io.BytesIO(json.dumps({"error": {
                "message": "(#100) impressions_xyz is not valid for fields param.",
                "code": 100, "type": "OAuthException"}}).encode()),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(measure.ApiError, match="not valid for fields") as excinfo:
        measure._http(measure.insights_url("1"), "t")
    assert "code 100" in str(excinfo.value)
    assert "INSIGHT_FIELDS" in str(excinfo.value)


def test_a_non_json_answer_is_named_not_parsed(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout=None: FakeResponse("<html>down</html>"))
    with pytest.raises(measure.ApiError, match="non-JSON"):
        measure._http(measure.insights_url("1"), "t")


def test_a_non_digit_ad_id_never_reaches_a_url():
    """The id goes into a URL path; only digits may."""
    api = FakeGraph()
    c = client(api)
    with pytest.raises(ValueError, match="all digits"):
        c.insights("../me")
    with pytest.raises(ValueError, match="all digits"):
        c.insights("")
    assert api.calls == []
    assert c.quota.spent == 0


# ---------------------------------------------------------------------------
# The quota - charged before the socket
# ---------------------------------------------------------------------------


def test_each_launched_ad_is_one_charge(queue):
    launch(queue, "accountants", {"1": {}, "2": {}})
    launch(queue, "bookkeepers", {"3": {}})
    api = FakeGraph()
    c = client(api)
    run = measure.measure_all(client=c, now=NOW)
    assert api.ad_ids == ["1", "2", "3"]
    assert c.quota.spent == 3
    assert run.calls == 3
    assert len(run.rows) == 3


def test_a_call_that_would_exceed_the_budget_is_refused_before_the_socket(queue):
    """The ledger charges BEFORE the socket, so an unaffordable call costs 0
    and never reaches the transport - and the run raises rather than
    returning half its rows as though it were healthy."""
    launch(queue, "accountants", {"1": {}, "2": {}})
    api = FakeGraph()
    c = client(api, budget=1)
    with pytest.raises(measure.QuotaExceededError) as excinfo:
        measure.measure_all(client=c, now=NOW)
    assert api.ad_ids == ["1"]
    assert c.quota.spent == 1
    assert excinfo.value.needed == 1
    assert excinfo.value.remaining == 0
    assert excinfo.value.budget == 1
    assert excinfo.value.endpoint == "insights"
    assert "ad account" in str(excinfo.value)
    assert_no_token(str(excinfo.value))


def test_a_refused_call_spends_nothing():
    quota = measure.Quota(budget=0)
    with pytest.raises(measure.QuotaExceededError):
        quota.charge("insights")
    assert quota.spent == 0
    assert quota.remaining == 0


def test_affords_reports_without_charging():
    quota = measure.Quota(budget=1)
    assert quota.affords("insights")
    assert quota.spent == 0
    quota.charge("insights")
    assert not quota.affords("insights")


def test_an_unpriced_endpoint_is_refused_rather_than_assumed_free():
    with pytest.raises(ValueError, match="ads_archive"):
        measure.Quota().charge("ads_archive")
    with pytest.raises(ValueError, match="never guess"):
        measure.Quota().cost("act_insights")


def test_a_negative_budget_is_refused():
    with pytest.raises(ValueError, match="negative"):
        measure.Quota(budget=-1)


def test_the_ledger_is_discoverys_shape_and_the_refusal_is_a_measure_error():
    """Copied, not imported: the shape is discovery's, the type is this
    module's, so main() prints it as one line like every other refusal."""
    assert issubclass(measure.QuotaExceededError, measure.MeasureError)
    quota = measure.Quota(budget=2, spent=1)
    assert quota.remaining == 1
    assert quota.charge("insights") == 1
    assert quota.remaining == 0


def test_a_shared_ledger_counts_only_this_runs_calls(queue):
    launch(queue, "accountants", {"1": {}})
    c = measure.MeasureClient(TOKEN, quota=measure.Quota(budget=200, spent=7), transport=FakeGraph())
    run = measure.measure_all(client=c, now=NOW)
    assert c.quota.spent == 8
    assert run.calls == 1


# ---------------------------------------------------------------------------
# Contract C6 - the row, by value
# ---------------------------------------------------------------------------


def test_a_full_insights_body_becomes_the_contract_row_literally():
    """C6 is pinned here by value, so a change to it cannot be accidental."""
    row = measure.measurement(
        segment="payroll-bureaus", ad_id="1234", campaign_id="5678",
        launched_at=LAUNCHED, insights=insights_row(), now=NOW,
    )
    assert row == C6_ROW
    assert list(row) == ["segment", "ad_id", "campaign_id", "launched_at",
                         "measured_at", "date_preset", "metrics", "derived"]


def test_metas_strings_become_numbers_and_numbers_pass_through():
    metrics = measure.metrics_of({"impressions": "4100", "ctr": "1.243902", "spend": 31.2,
                                  "clicks": 7})
    assert metrics["impressions"] == 4100 and isinstance(metrics["impressions"], int)
    assert metrics["ctr"] == 1.243902
    assert metrics["spend"] == 31.2
    assert metrics["clicks"] == 7


def test_missing_fields_are_null_not_zero():
    """An image ad has no video metrics, an ad with no conversion has no
    actions. Neither is 0: 0 would sink a median nobody measured."""
    row = measure.measurement(
        segment="s", ad_id="1", campaign_id=None, launched_at=LAUNCHED,
        insights={"impressions": "4100"}, now=NOW,
    )
    assert row["metrics"] == {
        "impressions": 4100, "reach": None, "clicks": None, "ctr": None, "cpc": None,
        "cpm": None, "spend": None, "plays_3s": None, "thruplays": None,
        "p25": None, "p50": None, "p75": None, "p100": None,
        "results": None, "cost_per_result": None,
    }
    assert row["derived"] == {"hook_rate": None, "hold_rate": None}
    assert row["campaign_id"] is None
    # And every metric key is still present, so a reader can index it.
    assert tuple(row["metrics"]) == measure.METRIC_KEYS


def test_an_empty_insights_object_is_all_null_and_no_zero_anywhere():
    row = measure.measurement(segment="s", ad_id="1", campaign_id=None,
                              launched_at=LAUNCHED, insights={}, now=NOW)
    assert set(row["metrics"].values()) == {None}
    assert set(row["derived"].values()) == {None}


def test_hold_rate_is_null_when_plays_3s_is_zero():
    """0 of 0 plays held is not 0% held; it is unmeasured."""
    insights = insights_row(actions=[{"action_type": "video_view", "value": "0"}])
    metrics = measure.metrics_of(insights)
    assert metrics["plays_3s"] == 0
    derived = measure.derived_of(metrics)
    assert derived["hold_rate"] is None
    # 0 plays out of 4100 real impressions IS a measured rate.
    assert derived["hook_rate"] == 0.0


def test_hook_rate_is_null_when_impressions_are_absent_or_zero():
    assert measure.derived_of({"plays_3s": 10, "impressions": None})["hook_rate"] is None
    assert measure.derived_of({"plays_3s": 10, "impressions": 0})["hook_rate"] is None
    assert measure.derived_of({"plays_3s": None, "impressions": 4100})["hook_rate"] is None


def test_the_derived_rates_are_the_two_divisions_the_contract_names():
    derived = measure.derived_of({"plays_3s": 1200, "impressions": 4100, "thruplays": 240})
    assert derived == {"hook_rate": round(1200 / 4100, 3), "hold_rate": 0.2}


@pytest.mark.parametrize("present, expected_type", [
    (("link_click",), "link_click"),
    (("contact", "link_click"), "contact"),
    (("link_click", "schedule", "contact"), "schedule"),
    (("link_click", "lead", "schedule"), "lead"),
])
def test_results_take_the_first_present_of_lead_schedule_contact_link_click(present, expected_type):
    counts = {"lead": "4", "schedule": "6", "contact": "9", "link_click": "51"}
    costs = {"lead": "7.8", "schedule": "5.2", "contact": "3.5", "link_click": "0.61"}
    insights = insights_row(
        actions=[{"action_type": t, "value": counts[t]} for t in present],
        cost_per_action_type=[{"action_type": t, "value": costs[t]} for t in present],
    )
    metrics = measure.metrics_of(insights)
    assert metrics["results"] == int(counts[expected_type])
    assert metrics["cost_per_result"] == float(costs[expected_type])


def test_no_result_action_means_null_results_and_a_missing_cost_is_null():
    only_plays = insights_row(actions=[{"action_type": "video_view", "value": "9"}],
                              cost_per_action_type=[])
    metrics = measure.metrics_of(only_plays)
    assert metrics["results"] is None and metrics["cost_per_result"] is None

    no_cost = insights_row(actions=[{"action_type": "lead", "value": "4"}],
                           cost_per_action_type=[{"action_type": "link_click", "value": "0.61"}])
    metrics = measure.metrics_of(no_cost)
    assert metrics["results"] == 4
    assert metrics["cost_per_result"] is None


def test_plays_3s_is_the_video_view_action_and_nothing_else():
    """video_play_actions is requested for the first live run to compare
    against; it is never read as plays_3s."""
    insights = insights_row(actions=[{"action_type": "link_click", "value": "51"}])
    assert measure.metrics_of(insights)["plays_3s"] is None
    assert insights["video_play_actions"], "the field is in the body and still unread"


def test_thruplays_and_quartiles_read_the_first_entry_value():
    insights = insights_row(
        video_thruplay_watched_actions=[{"action_type": "video_view", "value": "240"}],
        video_p25_watched_actions=[{"action_type": "video_view", "value": "900"}],
        video_p50_watched_actions=[{"action_type": "video_view", "value": "600"}],
        video_p75_watched_actions=[{"action_type": "video_view", "value": "300"}],
        video_p100_watched_actions=[{"action_type": "video_view", "value": "150"}],
    )
    metrics = measure.metrics_of(insights)
    assert (metrics["thruplays"], metrics["p25"], metrics["p50"], metrics["p75"], metrics["p100"]) == (
        240, 900, 600, 300, 150)
    assert measure.metrics_of(insights_row(video_p25_watched_actions=[]))["p25"] is None
    assert measure.metrics_of(insights_row(video_p25_watched_actions=[{}]))["p25"] is None
    assert measure.metrics_of(insights_row(video_p25_watched_actions="12"))["p25"] is None


def test_booleans_nan_and_junk_are_refused_not_coerced():
    """True is 1 to a median, and NaN poisons one silently."""
    insights = insights_row(impressions=True, reach="nan", clicks="inf", ctr="lots",
                            cpc="", spend=None, actions="not a list",
                            cost_per_action_type=[{"action_type": "lead"}])
    metrics = measure.metrics_of(insights)
    for key in ("impressions", "reach", "clicks", "ctr", "cpc", "spend", "plays_3s",
                "results", "cost_per_result"):
        assert metrics[key] is None, key
    assert measure._number(False) is None
    assert measure._count("3.0") == 3


def test_launched_at_is_normalised_and_an_unreadable_one_is_refused():
    row = measure.measurement(segment="s", ad_id="1", campaign_id=None,
                              launched_at="2026-09-29T12:00:00+02:00",
                              insights={}, now=NOW)
    assert row["launched_at"] == "2026-09-29T10:00:00Z"
    with pytest.raises(ValueError, match="approval launch") as excinfo:
        measure.measurement(segment="s", ad_id="1", campaign_id=None,
                            launched_at="last tuesday", insights={}, now=NOW)
    assert "queue/launched/s.json" in str(excinfo.value)
    with pytest.raises(ValueError, match="launched_at"):
        measure.measurement(segment="s", ad_id="1", campaign_id=None,
                            launched_at=None, insights={}, now=NOW)


def test_measured_at_comes_from_now_in_any_spelling():
    for now in (NOW, "2026-10-06T07:02:00+02:00",
                datetime(2026, 10, 6, 5, 2, tzinfo=timezone.utc),
                datetime(2026, 10, 6, 5, 2)):
        row = measure.measurement(segment="s", ad_id="1", campaign_id=None,
                                  launched_at=LAUNCHED, insights={}, now=now)
        assert row["measured_at"] == NOW


def test_a_row_needs_an_ad_id_and_an_insights_object():
    with pytest.raises(ValueError, match="ad id"):
        measure.measurement(segment="s", ad_id="", campaign_id=None,
                            launched_at=LAUNCHED, insights={}, now=NOW)
    with pytest.raises(ValueError, match="insights"):
        measure.measurement(segment="s", ad_id="1", campaign_id=None,
                            launched_at=LAUNCHED, insights=[insights_row()], now=NOW)


def test_the_row_is_json_serialisable():
    row = measure.measurement(segment="s", ad_id="1", campaign_id="2",
                              launched_at=LAUNCHED, insights=insights_row(), now=NOW)
    assert json.loads(json.dumps(row)) == row


# ---------------------------------------------------------------------------
# The client - one object per ad, or a refusal that says why
# ---------------------------------------------------------------------------


def test_insights_returns_the_one_object_not_the_envelope():
    api = FakeGraph()
    assert client(api).insights("1234") == insights_row()
    assert api.params(0)["date_preset"] == "maximum"


def test_no_insights_row_is_a_named_skip_not_a_row_of_zeros():
    api = FakeGraph({"1234": body()})
    with pytest.raises(measure.UnmeasurableJob) as excinfo:
        client(api).insights("1234")
    message = str(excinfo.value)
    assert "ad 1234" in message
    assert "no insights row" in message
    assert "zeros" in message


def test_two_insight_rows_are_refused_not_taken_on_faith():
    api = FakeGraph({"1234": body(insights_row(), insights_row(impressions="1"))})
    with pytest.raises(measure.UnmeasurableJob, match="2 insights rows") as excinfo:
        client(api).insights("1234")
    assert "engine/measure.py" in str(excinfo.value)


def test_an_answer_without_a_data_list_is_not_the_documented_shape():
    with pytest.raises(measure.ApiError, match="`data` list"):
        client(FakeGraph({"1": {"insights": []}})).insights("1")
    with pytest.raises(measure.ApiError, match="not an object"):
        client(FakeGraph({"1": [insights_row()]})).insights("1")
    with pytest.raises(measure.ApiError, match="not an object"):
        client(FakeGraph({"1": body("a string")})).insights("1")


def test_an_error_object_in_a_200_body_is_not_read_as_no_data():
    api = FakeGraph({"1": {"error": {"message": "Error validating access token",
                                     "type": "OAuthException", "code": 190}}})
    with pytest.raises(measure.ApiError) as excinfo:
        client(api).insights("1")
    message = str(excinfo.value)
    assert "Error validating access token" in message
    assert "META_ACCESS_TOKEN" in message
    assert "engine.oauth --status" in message


def test_a_wrong_ad_id_names_the_job_file_and_the_ads_manager_column():
    api = FakeGraph({"1": {"error": {
        "message": "Unsupported get request. Object with ID '1' does not exist, "
                   "cannot be loaded due to missing permissions, or does not support this operation",
        "type": "GraphMethodException", "code": 100, "error_subcode": 33}}})
    with pytest.raises(measure.ApiError) as excinfo:
        client(api).insights("1")
    message = str(excinfo.value)
    assert "Ad ID column" in message
    assert "queue/launched/" in message
    assert "INSIGHT_FIELDS" not in message


def test_a_permission_error_names_ads_read_on_our_account():
    api = FakeGraph({"1": {"error": {"message": "(#10) Application does not have permission",
                                     "type": "OAuthException", "code": 10}}})
    with pytest.raises(measure.ApiError, match="ads_read"):
        client(api).insights("1")


def test_a_rate_limit_error_carries_the_advice_and_no_retry():
    api = FakeGraph({"1": {"error": {"message": "User request limit reached",
                                     "type": "OAuthException", "code": 80004}}})
    with pytest.raises(measure.ApiError) as excinfo:
        client(api).insights("1")
    assert "Nothing here retries" in str(excinfo.value)


def test_a_missing_token_is_named_without_a_socket():
    with pytest.raises(measure.MissingTokenError) as excinfo:
        measure.MeasureClient(transport=FakeGraph())
    message = str(excinfo.value)
    assert message.startswith("no Meta access token for the Marketing API insights edge (META_ACCESS_TOKEN)")
    assert "docs/SECRETS.md" in message


def test_a_token_passed_in_needs_nothing_from_the_environment():
    assert client(FakeGraph()).quota.remaining == 200


def test_an_expired_stored_token_is_refused_before_any_call(monkeypatch):
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, "2020-01-01")
    api = FakeGraph()
    with pytest.raises(measure.MissingTokenError, match="dead") as excinfo:
        measure.MeasureClient(transport=api)
    assert api.calls == []
    assert_no_token(str(excinfo.value))


# ---------------------------------------------------------------------------
# The token - never in a URL, never in a message, never down the chain
# ---------------------------------------------------------------------------


def test_the_token_is_scrubbed_from_a_provider_error_that_echoes_it():
    """Meta answers a bad token with the token beside the message. It is the
    body an operator needs, so it is kept and the value cut out of it."""
    def failing(url, token):
        raise measure.ApiError(f"Marketing API 400: Invalid OAuth access token - {token} (code 190)")

    with pytest.raises(measure.ApiError) as excinfo:
        client(failing).insights("1")
    message = str(excinfo.value)
    assert_no_token(message)
    assert "Invalid OAuth access token" in message
    assert excinfo.value.__context__ is None and excinfo.value.__cause__ is None


def test_any_exception_from_a_transport_is_scrubbed_whole_and_in_part_and_unchained():
    """http.client echoes a bad header value; a proxy echoes half a token.
    Both are cut, and nothing unscrubbed hangs off the exception."""
    fragment = TOKEN[10:34]

    def failing(url, token):
        raise ValueError(f"Invalid header value b'Bearer {token}\\n' ... {fragment}")

    with pytest.raises(measure.ApiError) as excinfo:
        client(failing).insights("1")
    error = excinfo.value
    assert_no_token(str(error))
    assert_no_token(repr(error))
    assert "ValueError" in str(error)
    assert oauth.REDACTED in str(error)
    assert error.__context__ is None and error.__cause__ is None


def test_a_meta_error_body_that_echoes_the_token_is_scrubbed_in_the_skip_line(queue):
    launch(queue, "accountants", {"1": {}})
    api = FakeGraph({"1": {"error": {
        "message": f"Invalid OAuth access token - Cannot parse access token {TOKEN}",
        "type": "OAuthException", "code": 190}}})
    run = measure.measure_all(client=client(api), now=NOW)
    assert run.rows == []
    assert len(run.skipped) == 1
    assert_no_token(run.skipped[0])
    assert "Cannot parse access token" in run.skipped[0]


def test_no_skip_line_of_a_whole_run_carries_the_token(queue):
    launch(queue, "accountants", {"1": {}, "2": {}, "3": {}})
    api = FakeGraph({
        "1": KeyError(f"broke with {TOKEN} in hand"),
        "2": {"error": {"message": f"token {TOKEN[:30]} refused", "code": 190}},
        "3": measure.ApiError(f"echo {TOKEN}"),
    })
    run = measure.measure_all(client=client(api), now=NOW)
    assert len(run.skipped) == 3
    for line in run.skipped:
        assert_no_token(line)


def test_oauths_own_refusal_arrives_scrubbed_as_a_missing_token(monkeypatch):
    """The token pasted into the DATE variable's box: oauth refuses the date,
    and neither its message nor this module's carries the value."""
    monkeypatch.setenv(oauth.META_ACCESS_TOKEN, TOKEN)
    monkeypatch.setenv(oauth.META_TOKEN_ISSUED, TOKEN)
    with pytest.raises(measure.MissingTokenError) as excinfo:
        measure.MeasureClient(transport=FakeGraph())
    assert_no_token(str(excinfo.value))
    assert "META_TOKEN_ISSUED" in str(excinfo.value)
    assert excinfo.value.__context__ is None and excinfo.value.__cause__ is None


# ---------------------------------------------------------------------------
# One unmeasurable ad costs the others nothing
# ---------------------------------------------------------------------------


def test_one_row_per_job_and_ad_id(queue):
    launch(queue, "accountants", {"1": {"campaign_id": "10", "adset_id": "100"},
                                  "2": {"campaign_id": "20", "adset_id": None}})
    launch(queue, "bookkeepers", {"3": {"campaign_id": None, "adset_id": None}},
           launched_at="2026-09-30T08:00:00Z")
    api = FakeGraph({"2": body(insights_row(impressions="7"))})
    run = measure.measure_all(client=client(api), now=NOW)

    assert run.skipped == []
    assert [(r["segment"], r["ad_id"], r["campaign_id"]) for r in run.rows] == [
        ("accountants", "1", "10"), ("accountants", "2", "20"), ("bookkeepers", "3", None)]
    assert [r["metrics"]["impressions"] for r in run.rows] == [4100, 7, 4100]
    assert [r["launched_at"] for r in run.rows] == [LAUNCHED, LAUNCHED, "2026-09-30T08:00:00Z"]
    assert {r["measured_at"] for r in run.rows} == {NOW}
    assert "adset_id" not in json.dumps(run.rows)


def test_a_job_with_an_empty_ads_map_is_skipped_by_name_and_costs_nothing(queue):
    launch(queue, "accountants", {})
    api = FakeGraph()
    run = measure.measure_all(client=client(api), now=NOW)
    assert run.rows == [] and api.calls == [] and run.calls == 0
    assert len(run.skipped) == 1
    message = run.skipped[0]
    assert message.startswith("accountants: ")
    assert "queue/launched/accountants.json" in message
    assert '"ads"' in message
    assert "Ad ID column" in message


def test_an_ads_map_that_is_not_a_map_is_skipped_by_name(queue):
    launch(queue, "accountants", ["1234"])
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert run.rows == []
    assert "accountants" in run.skipped[0] and '"ads"' in run.skipped[0]


def test_a_failing_ad_is_skipped_by_name_and_the_others_measured(queue):
    launch(queue, "accountants", {"1": {}, "2": {}})
    launch(queue, "bookkeepers", {"3": {}})
    api = FakeGraph({"2": measure.ApiError("Marketing API 500: something broke")})
    run = measure.measure_all(client=client(api), now=NOW)

    assert [(r["segment"], r["ad_id"]) for r in run.rows] == [("accountants", "1"), ("bookkeepers", "3")]
    assert len(run.skipped) == 1
    assert run.skipped[0].startswith("accountants: ")
    assert "ad 2" in run.skipped[0] or "500" in run.skipped[0]
    assert "something broke" in run.skipped[0]
    assert run.calls == 3


def test_an_ad_that_has_not_delivered_is_skipped_by_name_and_the_rest_measured(queue):
    launch(queue, "accountants", {"1": {}, "2": {}})
    api = FakeGraph({"1": body()})
    run = measure.measure_all(client=client(api), now=NOW)
    assert [r["ad_id"] for r in run.rows] == ["2"]
    assert run.skipped[0].startswith("accountants: ad 1: ")
    assert "no insights row" in run.skipped[0]


def test_a_transport_that_blows_up_on_one_ad_is_one_skip(queue):
    launch(queue, "accountants", {"1": {}, "2": {}})
    api = FakeGraph({"1": RuntimeError("connection reset")})
    run = measure.measure_all(client=client(api), now=NOW)
    assert [r["ad_id"] for r in run.rows] == ["2"]
    assert "RuntimeError" in run.skipped[0] and "connection reset" in run.skipped[0]


def test_nothing_launched_makes_no_call_and_asks_for_no_token(queue):
    """Lazy on purpose: no client is built, so no token is read - the
    environment here is empty and MeasureClient() would refuse."""
    run = measure.measure_all(now=NOW)
    assert run == measure.MeasureRun()


def test_jobs_that_fail_every_check_ask_for_no_token_either(queue):
    launch(queue, "accountants", {})
    run = measure.measure_all(now=NOW)
    assert run.rows == [] and run.calls == 0
    assert len(run.skipped) == 1


def test_a_launched_ad_needs_a_token_when_none_is_passed(queue):
    """A dead or missing token is the whole run misconfigured: raised, not
    collected."""
    launch(queue, "accountants")
    with pytest.raises(measure.MissingTokenError, match="META_ACCESS_TOKEN"):
        measure.measure_all(now=NOW)


def test_only_the_launched_stage_is_measured(queue):
    launch(queue, "accountants", stage="proposed")
    launch(queue, "bookkeepers", stage="built")
    launch(queue, "admin-firms", stage="rejected")
    launch(queue, "audit-firms", stage="launched")
    api = FakeGraph()
    run = measure.measure_all(client=client(api), now=NOW)
    assert [r["segment"] for r in run.rows] == ["audit-firms"]
    assert [job.segment_id for job in measure.launched_jobs()] == ["audit-firms"]


def test_a_reel_selection_sidecar_is_not_a_job(queue):
    """<segment>.reel.json travels with the job and ends in .json; a bare
    glob would measure it as a second ad called 'accountants.reel'."""
    launch(queue, "accountants")
    (queue / "launched" / "accountants.reel.json").write_text(
        json.dumps({"schema": 1, "selected": ["a01"]}) + "\n", encoding="utf-8")
    (queue / "launched" / "accountants.jpg").write_bytes(b"not a jpeg")
    api = FakeGraph()
    run = measure.measure_all(client=client(api), now=NOW)
    assert run.skipped == []
    assert [r["segment"] for r in run.rows] == ["accountants"]
    assert api.ad_ids == ["1234"]


def test_an_unreadable_job_is_reported_and_the_rest_measured(queue):
    (queue / "launched" / "broken.json").write_text("{not json", encoding="utf-8")
    launch(queue, "accountants")
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert [r["segment"] for r in run.rows] == ["accountants"]
    assert len(run.skipped) == 1
    assert "broken" in run.skipped[0] and "not JSON" in run.skipped[0]


def test_a_job_whose_fields_disagree_with_its_name_is_reported(queue):
    """The filename is the segment. A renamed file would put the wrong trade
    on every row; approval.load_job refuses it and this run reports it."""
    launch(queue, "accountants", id="bookkeepers")
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert run.rows == []
    assert "accountants" in run.skipped[0] and "filename" in run.skipped[0]


def test_a_hand_edited_non_digit_ad_id_is_skipped_by_name(queue):
    launch(queue, "accountants", {"ad-from-tuesday": {}, "1234": {}})
    api = FakeGraph()
    run = measure.measure_all(client=client(api), now=NOW)
    assert [r["ad_id"] for r in run.rows] == ["1234"]
    assert api.ad_ids == ["1234"]
    assert "ad-from-tuesday" in run.skipped[0]
    assert "queue/launched/accountants.json" in run.skipped[0]
    assert "Ad ID column" in run.skipped[0]


def test_a_non_digit_campaign_id_is_skipped_rather_than_written_as_a_fact(queue):
    launch(queue, "accountants", {"1": {"campaign_id": "Spring push", "adset_id": None}})
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert run.rows == []
    assert "Spring push" in run.skipped[0] and "campaign_id" in run.skipped[0]


def test_an_ads_entry_that_is_not_an_object_is_skipped_by_name(queue):
    launch(queue, "accountants", {"1": "5678"})
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert run.rows == []
    assert "ad 1" in run.skipped[0] and "campaign_id, adset_id" in run.skipped[0]


def test_a_null_or_empty_ads_entry_means_no_campaign_id(queue):
    launch(queue, "accountants", {"1": None, "2": {}})
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert run.skipped == []
    assert [(r["ad_id"], r["campaign_id"]) for r in run.rows] == [("1", None), ("2", None)]


def test_an_unreadable_launched_at_is_skipped_by_name(queue):
    launch(queue, "accountants", launched_at="soon")
    launch(queue, "bookkeepers", launched_at=None)
    api = FakeGraph()
    run = measure.measure_all(client=client(api), now=NOW)
    assert run.rows == [] and api.calls == []
    assert len(run.skipped) == 2
    for line in run.skipped:
        assert "launched_at" in line and "YYYY-MM-DDTHH:MM:SSZ" in line


def test_an_ad_id_pinned_under_two_segments_is_refused_for_both(queue):
    """The mirror of the reel loop's contested upload: two segments sharing
    one ad's numbers would make both histories half somebody else's."""
    launch(queue, "accountants", {"1234": {}, "9": {}})
    launch(queue, "bookkeepers", {"1234": {}})
    api = FakeGraph()
    run = measure.measure_all(client=client(api), now=NOW)
    assert [(r["segment"], r["ad_id"]) for r in run.rows] == [("accountants", "9")]
    assert api.ad_ids == ["9"]
    assert len(run.skipped) == 2
    for line in run.skipped:
        assert "1234" in line and "accountants" in line and "bookkeepers" in line


def test_the_raw_body_rides_along_only_when_asked(queue):
    launch(queue, "accountants")
    plain = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert "raw" not in plain.rows[0]
    with_raw = measure.measure_all(client=client(FakeGraph()), now=NOW, raw=True)
    assert with_raw.rows[0]["raw"] == insights_row()
    assert {k: v for k, v in with_raw.rows[0].items() if k != "raw"} == plain.rows[0]


def test_a_launched_job_is_never_written_by_measurement(queue):
    """Launch is the pin. Nothing here has a reason to touch a job file."""
    path = launch(queue, "accountants")
    before = path.read_bytes()
    measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# Contract C6 - the document
# ---------------------------------------------------------------------------


def row_for(segment: str, ad_id: str) -> dict:
    return measure.measurement(segment=segment, ad_id=ad_id, campaign_id=None,
                               launched_at=LAUNCHED, insights=insights_row(), now=NOW)


def test_the_document_is_sorted_by_segment_then_ad_id():
    rows = [row_for("bookkeepers", "2"), row_for("accountants", "9"),
            row_for("bookkeepers", "1"), row_for("accountants", "10")]
    doc = measure.document(rows, now=NOW)
    assert doc["schema"] == 1
    assert doc["generated_at"] == NOW
    assert [(r["segment"], r["ad_id"]) for r in doc["rows"]] == [
        ("accountants", "10"), ("accountants", "9"), ("bookkeepers", "1"), ("bookkeepers", "2")]
    assert list(doc) == ["schema", "generated_at", "rows"]


def test_the_document_is_written_the_way_every_committed_json_is(tmp_path):
    path = measure.write_measurements([row_for("revisorer-ø", "1")], tmp_path / "m.json", now=NOW)
    text = path.read_text(encoding="utf-8")
    doc = json.loads(text)
    assert text == json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    assert text.endswith("}\n")
    assert "revisorer-ø" in text and "\\u00f8" not in text
    assert list(doc) == ["generated_at", "rows", "schema"]


def test_the_same_inputs_produce_a_byte_identical_file(queue, tmp_path):
    """Deterministic: now= is an input, rows are sorted, nothing reads a clock."""
    launch(queue, "bookkeepers", {"2": {}})
    launch(queue, "accountants", {"1": {}})
    bodies = {"1": body(insights_row(impressions="11")), "2": body(insights_row(impressions="22"))}

    first = measure.write_measurements(
        measure.measure_all(client=client(FakeGraph(bodies)), now=NOW).rows,
        tmp_path / "one.json", now=NOW)
    second = measure.write_measurements(
        measure.measure_all(client=client(FakeGraph(bodies)), now=NOW).rows,
        tmp_path / "two.json", now=NOW)
    assert first.read_bytes() == second.read_bytes()
    assert [r["ad_id"] for r in measure.load(first)["rows"]] == ["1", "2"]


def test_write_creates_the_directory_and_defaults_to_the_contract_path(tmp_path, monkeypatch):
    monkeypatch.setattr(measure, "MEASUREMENTS_PATH", tmp_path / "research" / "measurements.json")
    path = measure.write_measurements([], now=NOW)
    assert path == tmp_path / "research" / "measurements.json"
    assert measure.load(path) == {"schema": 1, "generated_at": NOW, "rows": []}


def test_load_refuses_what_this_module_would_not_have_written(tmp_path):
    with pytest.raises(FileNotFoundError, match="python -m engine.measure"):
        measure.load(tmp_path / "absent.json")

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(measure.MeasureError, match="not JSON"):
        measure.load(bad)

    bad.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(measure.MeasureError, match="JSON list"):
        measure.load(bad)

    bad.write_text(json.dumps({"schema": 2, "generated_at": NOW, "rows": []}), encoding="utf-8")
    with pytest.raises(measure.MeasureError, match="schema 2"):
        measure.load(bad)

    bad.write_text(json.dumps({"schema": 1, "generated_at": NOW, "rows": {}}), encoding="utf-8")
    with pytest.raises(measure.MeasureError, match="rows"):
        measure.load(bad)


def test_generated_at_and_measured_at_are_one_moment_in_a_run(queue, tmp_path):
    launch(queue, "accountants")
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    doc = measure.load(measure.write_measurements(run.rows, tmp_path / "m.json", now=NOW))
    assert doc["generated_at"] == doc["rows"][0]["measured_at"] == NOW


def test_an_unreadable_now_is_refused():
    with pytest.raises(ValueError, match="now"):
        measure.document([], now="last tuesday")


# ---------------------------------------------------------------------------
# The CLI
# ---------------------------------------------------------------------------


def test_dry_run_calls_the_api_prints_the_document_and_writes_nothing(
    queue, tmp_path, monkeypatch, capsys
):
    credentials(monkeypatch)
    launch(queue, "accountants")
    api = FakeGraph()
    monkeypatch.setattr(measure, "_http", api)
    out = tmp_path / "measurements.json"

    code = measure.main(["--dry-run", "--out", str(out)])

    assert code == 0
    assert not out.exists()
    assert api.ad_ids == ["1234"]
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert doc["schema"] == 1
    assert doc["rows"][0]["metrics"] == C6_ROW["metrics"]
    assert "raw" not in doc["rows"][0]
    assert "nothing (dry run)" in captured.err
    assert "1 insights call(s)" in captured.err
    assert_no_token(captured.out + captured.err)


def test_the_cli_writes_the_document_and_reports_the_spend(queue, tmp_path, monkeypatch, capsys):
    credentials(monkeypatch)
    launch(queue, "accountants", {"1": {}, "2": {}})
    monkeypatch.setattr(measure, "_http", FakeGraph())
    out = tmp_path / "measurements.json"

    code = measure.main(["--out", str(out)])

    assert code == 0
    doc = measure.load(out)
    assert [r["ad_id"] for r in doc["rows"]] == ["1", "2"]
    assert doc["generated_at"] == doc["rows"][0]["measured_at"]
    err = capsys.readouterr().err
    assert "measured 2 launched ad(s) in 2 insights call(s); 0 skipped" in err
    assert str(out) in err


def test_raw_is_on_only_by_flag(queue, tmp_path, monkeypatch, capsys):
    credentials(monkeypatch)
    launch(queue, "accountants")
    monkeypatch.setattr(measure, "_http", FakeGraph())
    assert measure.main(["--dry-run", "--raw", "--out", str(tmp_path / "m.json")]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["rows"][0]["raw"] == insights_row()


def test_the_cli_reports_a_skip_and_strict_makes_it_the_exit_code(queue, tmp_path, monkeypatch, capsys):
    credentials(monkeypatch)
    launch(queue, "accountants", {})
    launch(queue, "bookkeepers")
    monkeypatch.setattr(measure, "_http", FakeGraph())
    out = tmp_path / "measurements.json"

    assert measure.main(["--out", str(out)]) == 0
    err = capsys.readouterr().err
    assert "skipped accountants: " in err
    assert "1 skipped" in err
    assert [r["segment"] for r in measure.load(out)["rows"]] == ["bookkeepers"]

    assert measure.main(["--out", str(out), "--strict"]) == 1


def test_a_missing_token_is_one_line_and_exit_1(queue, tmp_path, monkeypatch, capsys):
    launch(queue, "accountants")
    monkeypatch.setattr(measure, "_http", FakeGraph())
    out = tmp_path / "measurements.json"

    code = measure.main(["--out", str(out)])

    assert code == 1
    assert not out.exists()
    captured = capsys.readouterr()
    assert "META_ACCESS_TOKEN" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_an_expired_token_is_one_scrubbed_line_and_exit_1(queue, tmp_path, monkeypatch, capsys):
    credentials(monkeypatch, issued_days_ago=61)
    launch(queue, "accountants")
    api = FakeGraph()
    monkeypatch.setattr(measure, "_http", api)
    assert measure.main(["--out", str(tmp_path / "m.json")]) == 1
    err = capsys.readouterr().err
    assert "dead" in err and "docs/SECRETS.md" in err
    assert_no_token(err)
    assert api.calls == []


def test_the_ageing_warning_reaches_stderr_and_the_run_still_measures(queue, tmp_path, monkeypatch, capsys):
    credentials(monkeypatch, issued_days_ago=45)
    launch(queue, "accountants")
    monkeypatch.setattr(measure, "_http", FakeGraph())
    out = tmp_path / "measurements.json"
    assert measure.main(["--out", str(out)]) == 0
    err = capsys.readouterr().err
    assert "WARNING" in err and "DAYS LEFT" in err
    assert_no_token(err)
    assert len(measure.load(out)["rows"]) == 1


def test_a_run_that_measured_nothing_keeps_the_existing_document(queue, tmp_path, monkeypatch, capsys):
    """Scope rule 6: nothing thin overwrites something good. A morning the
    API is away leaves last week's rows for engine.feedback to read."""
    credentials(monkeypatch)
    launch(queue, "accountants")
    out = tmp_path / "measurements.json"
    measure.write_measurements([row_for("accountants", "1234")], out, now=NOW)
    before = out.read_bytes()
    monkeypatch.setattr(measure, "_http", FakeGraph({"1234": body()}))

    assert measure.main(["--out", str(out)]) == 0
    assert out.read_bytes() == before
    assert "kept as it was" in capsys.readouterr().err


def test_a_first_run_with_nothing_launched_still_writes_an_empty_document(queue, tmp_path, capsys):
    """No file at all would make engine.feedback's read a different error
    from 'nothing measured'; an empty document says exactly that."""
    out = tmp_path / "measurements.json"
    assert measure.main(["--out", str(out)]) == 0
    assert measure.load(out)["rows"] == []
    assert "measured 0 launched ad(s) in 0 insights call(s)" in capsys.readouterr().err


def test_the_cli_writes_to_the_contract_path_by_default(queue, tmp_path, monkeypatch):
    monkeypatch.setattr(measure, "MEASUREMENTS_PATH", tmp_path / "research" / "measurements.json")
    assert measure.main([]) == 0
    assert (tmp_path / "research" / "measurements.json").exists()


# ---------------------------------------------------------------------------
# Offline, and no model
# ---------------------------------------------------------------------------


def test_the_injected_transport_is_the_only_socket(queue, monkeypatch):
    """Make urlopen explode too, then run to completion."""
    def no_sockets(*args, **kwargs):
        raise AssertionError("engine.measure opened a socket")

    monkeypatch.setattr(urllib.request, "urlopen", no_sockets)
    launch(queue, "accountants", {"1": {}, "2": {}})
    run = measure.measure_all(client=client(FakeGraph()), now=NOW)
    assert [r["metrics"]["impressions"] for r in run.rows] == [4100, 4100]


def _imports(nodes) -> set[str]:
    names: set[str] = set()
    for node in nodes:
        for inner in ast.walk(node):
            if isinstance(inner, ast.Import):
                names.update(alias.name for alias in inner.names)
            elif isinstance(inner, ast.ImportFrom):
                module = inner.module or ""
                names.add(module)
                names.update(f"{module}.{alias.name}" for alias in inner.names)
    return names


def test_the_module_imports_no_model_and_can_open_a_socket_only_in_http():
    """Metrics are arithmetic; a model asked for a number would answer
    differently on two runs. And 'the only socket is _http' is a property of
    the code, read off the import graph rather than the prose."""
    tree = ast.parse(Path(measure.__file__).read_text(encoding="utf-8"))
    forbidden = ("engine.model", "engine.script", "engine.discover", "google", "requests",
                 "httpx", "aiohttp", "subprocess", "socket", "ssl", "http", "yaml")
    everywhere = _imports(tree.body)
    for name in everywhere:
        for bad in forbidden:
            assert not (name == bad or name.startswith(bad + ".")), name
    assert not hasattr(measure, "call_model")

    # urllib.request and urllib.error live inside _http and nowhere else;
    # urllib.parse at the top is a string library, not a transport.
    top_level = _imports([node for node in tree.body
                          if isinstance(node, (ast.Import, ast.ImportFrom))])
    assert not any(n.startswith(("urllib.request", "urllib.error")) for n in top_level)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            inside = _imports(node.body)
            if any(n.startswith(("urllib.request", "urllib.error")) for n in inside):
                assert node.name == "_http", node.name


def test_the_module_reads_no_seeds_file():
    """The ad id is the lookup; own.ad_account_id belongs to the batched
    account-level read nobody has verified. Nothing here opens seeds.yaml."""
    assert not hasattr(measure, "SEEDS_PATH")
    assert not hasattr(measure, "load_seeds")
    assert "yaml" not in _imports(ast.parse(Path(measure.__file__).read_text(encoding="utf-8")).body)


def test_the_shipped_seeds_file_does_not_promise_a_refusal_this_module_has_not():
    """research/seeds.yaml told the operator the opposite of the test above.

    Measured: the own: header said "Read by engine/measure.py" and that a
    blank block makes `python -m engine.measure` refuse by name. Nothing here
    opens seeds.yaml, so an operator who left the block blank on that promise
    would read a clean run as proof it was filled in, while engine.feedback
    silently writes page_id "" and channel "own". The file now names its real
    reader and says what a blank block costs: a record's channel, not a call.
    """
    text = (ROOT / "research" / "seeds.yaml").read_text(encoding="utf-8")
    own = text[text.index("# own - "):]
    assert "measure` refuses" not in text and "measure refuses" not in text
    assert "read by measure and feedback only" not in text
    assert "Read by engine/feedback.py" in own
    assert "does NOT open this file" in own


def test_the_token_has_one_owner():
    assert measure.META_ACCESS_TOKEN == oauth.META_ACCESS_TOKEN == "META_ACCESS_TOKEN"


def test_launched_jobs_reads_through_approval(queue, monkeypatch):
    """One definition of the stage, so a redirected QUEUE redirects this too."""
    launch(queue, "accountants")
    jobs = measure.launched_jobs()
    assert [(job.segment_id, job.stage) for job in jobs] == [("accountants", "launched")]
    assert jobs[0].path == queue / "launched" / "accountants.json"
    # An absent queue is no jobs, not an error: a fresh checkout has none.
    monkeypatch.setattr(approval, "QUEUE", queue / "elsewhere")
    assert measure.launched_jobs() == []


# ---------------------------------------------------------------------------
# The token, below Exception
#
# This module always delegated its cut to engine.oauth - it never kept a copy,
# which is why the 2026-09-19 leak was engine/discover.py's and not this
# module's. What it did share with discover was the two narrower gaps: a bare
# type(exc)(clean) with no TypeError fallback, and `except Exception`, which
# KeyboardInterrupt, SystemExit and asyncio.CancelledError sail straight past
# with their messages and their chains intact.
# ---------------------------------------------------------------------------

SENTINEL_TOKEN = "EAA" + "Zq7Kx2Lw9Pv4Nt6Ym1Bd8Rf3Gh5Js0Cn" * 6


def test_ctrl_c_keeps_its_type_and_still_gets_scrubbed():
    """Caught, because `except Exception` misses it - but rebuilt as an
    ApiError it would make a hung run need a second Ctrl-C to die."""
    def interrupted():
        raise KeyboardInterrupt("aborting while holding %s" % SENTINEL_TOKEN)

    with pytest.raises(KeyboardInterrupt) as caught:
        measure._scrubbed(SENTINEL_TOKEN, interrupted)
    assert SENTINEL_TOKEN not in str(caught.value)


def test_an_exit_code_survives_the_scrub():
    """SystemExit(2) rebuilt from a string exits 1. Args are scrubbed element
    by element, so an integer is left alone."""
    def exiting():
        raise SystemExit(2)

    with pytest.raises(SystemExit) as caught:
        measure._scrubbed(SENTINEL_TOKEN, exiting)
    assert caught.value.code == 2


def test_a_subclass_with_its_own_init_does_not_escape_the_scrubber():
    """type(exc)(clean) on a subclass carrying its own signature is a
    TypeError, and an uncaught one HERE escapes with the original as its
    __context__ - the leak this wrapper exists to prevent, arriving through
    the wrapper itself."""
    class Awkward(measure.MeasureError):
        def __init__(self, a, b):
            super().__init__("%s / %s" % (a, b))
            self.a, self.b = a, b

    def awkward():
        raise Awkward("token was %s" % SENTINEL_TOKEN, "second argument")

    with pytest.raises(measure.MeasureError) as caught:
        measure._scrubbed(SENTINEL_TOKEN, awkward)
    assert SENTINEL_TOKEN not in str(caught.value)


def test_a_partial_echo_is_cut_here_too():
    """This module delegates, so oauth's partial-run cut reaches it for free -
    which is the property that made delegation the fix in discover."""
    body = "Invalid OAuth access token: %s" % SENTINEL_TOKEN
    def echoes():
        raise RuntimeError(body[:200])

    with pytest.raises(measure.ApiError) as caught:
        measure._scrubbed(SENTINEL_TOKEN, echoes)
    cleaned = str(caught.value)
    for start in range(0, len(SENTINEL_TOKEN) - 24):
        assert SENTINEL_TOKEN[start:start + 24] not in cleaned
