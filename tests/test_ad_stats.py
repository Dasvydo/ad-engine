import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report import ledger_shim
from report.pull_ad_stats import (
    AdStatRow,
    aggregate,
    LEDGER_COLUMNS,
    _write_row,
    build_url,
    content_id_for_ledger,
    count_leads,
    creative_content_id,
    ledger_row,
    load_fixture,
    to_row,
    transform,
)


# --- joining spend back to a creative -------------------------------------

def test_ad_name_convention_yields_the_utm_content_value():
    assert creative_content_id("teams_q4 | v5-pilot | s05-two-weeks-4x5") == "v5-pilot"


def test_off_convention_ad_name_still_produces_a_row():
    """Losing a day of spend is worse than losing a label, so it degrades
    to the whole name rather than dropping the row or emitting ''."""
    assert creative_content_id("teams_q4_v3_outlook_static") == "teams_q4_v3_outlook_static"


# --- leads ----------------------------------------------------------------

def test_leads_count_every_meta_lead_action_type():
    actions = [
        {"action_type": "link_click", "value": "9"},
        {"action_type": "offsite_conversion.fb_pixel_lead", "value": "1"},
        {"action_type": "lead", "value": "2"},
    ]
    assert count_leads(actions) == 3


def test_no_actions_is_zero_leads_not_none():
    assert count_leads(None) == 0 and count_leads([]) == 0


# --- currency -------------------------------------------------------------

def test_non_eur_account_is_refused():
    """spend_eur is a euro column. Writing USD into it silently would corrupt
    every funnel figure downstream."""
    raw = {
        "campaign_name": "c", "adset_name": "a", "ad_name": "c | v1 | s1",
        "spend": "5.00", "impressions": "10", "clicks": "1",
        "account_currency": "USD", "date_start": "2026-09-23",
    }
    with pytest.raises(ValueError, match="USD"):
        to_row(raw)
    assert to_row(raw, strict_currency=False).spend_eur == 5.0


# --- the fixture ----------------------------------------------------------

def test_fixture_transforms_clean():
    rows = transform(load_fixture())
    assert len(rows) == 8
    assert all(isinstance(r, AdStatRow) for r in rows)
    assert round(sum(r.spend_eur for r in rows), 2) == 22.75
    assert sum(r.clicks for r in rows) == 53
    assert sum(r.leads for r in rows) == 2


def test_rows_use_the_exact_ad_stats_columns():
    """Batch B owns campaign.ad_stats. A renamed field here is a silent
    integration failure on the day the ledger lands.

    Checked through ledger_row(), not vars(): AdStatRow deliberately carries
    utm_content, which is a local label and not a column.
    """
    row = transform(load_fixture())[0]
    assert set(ledger_row(row)) == set(ledger_shim.COLUMNS)
    assert set(LEDGER_COLUMNS) == set(ledger_shim.COLUMNS)


# --- the ledger seam ------------------------------------------------------

def test_shim_writes_a_row(tmp_path):
    row = ledger_row(transform(load_fixture())[0])
    out = tmp_path / "ad_stats.jsonl"
    ledger_shim.snapshot_ad_stats(row, path=out)
    assert out.read_text(encoding="utf-8").count("\n") == 1


def test_shim_refuses_a_column_that_is_not_in_the_table(tmp_path):
    row = dict(ledger_row(transform(load_fixture())[0]), ctr=0.02)
    with pytest.raises(ValueError, match="ctr"):
        ledger_shim.snapshot_ad_stats(row, path=tmp_path / "x.jsonl")


def test_write_row_adapts_to_a_single_row_signature():
    seen = []
    _write_row(lambda row: seen.append(row), {"campaign_name": "c"})
    assert seen == [{"campaign_name": "c"}]


def test_write_row_adapts_to_a_kwargs_signature():
    """Batch B may have written snapshot_ad_stats to take the columns as
    keywords. This side has never seen that file, so it adapts."""
    seen = {}

    def snapshot(campaign_name, ad_set_name, creative_content_id,
                 captured_on, spend_eur, impressions, clicks, leads):
        seen.update(locals())

    _write_row(snapshot, ledger_row(transform(load_fixture())[0]))
    assert seen["campaign_name"] == "teams_q4_retargeting"
    # NOT "v5-pilot". The column is uuid; see test_the_ledger_never_receives_a_
    # non_uuid_creative_id below.
    assert seen["creative_content_id"] is None


def test_the_ledger_never_receives_a_non_uuid_creative_id():
    """The defect this guards against would have failed on the FIRST live write.

    campaign.ad_stats.creative_content_id is `uuid references campaign.content
    (id)`. Ad names carry a human label like `v5-pilot`, which Postgres rejects
    as invalid uuid syntax - but the offline JSONL shim accepts any string, so
    every test passed and the failure was reserved for production.
    """
    for row in transform(load_fixture()):
        assert row.creative_content_id is None or uuid.UUID(row.creative_content_id)


def test_a_real_uuid_in_the_ad_name_is_passed_through():
    """If an ad is ever named with a genuine content id, keep it."""
    real = "3f2504e0-4f89-11d3-9a0c-0305e82c3301"
    assert content_id_for_ledger(real) == real


def test_a_label_that_is_not_a_uuid_becomes_none():
    assert content_id_for_ledger("v5-pilot") is None
    assert content_id_for_ledger("") is None


def test_the_creative_label_is_kept_even_though_it_is_not_written():
    """Dropping the id must not mean losing the information."""
    rows = transform(load_fixture())
    assert rows[0].utm_content == "v5-pilot"


def test_ledger_row_emits_exactly_the_ledger_columns():
    """A stray key would be a TypeError against Batch B's kwargs signature."""
    row = transform(load_fixture())[0]
    assert tuple(ledger_row(row)) == LEDGER_COLUMNS
    assert "utm_content" not in ledger_row(row)


# --- the ad-set/day grain ---------------------------------------------------

def test_aggregation_preserves_every_euro():
    """The defect this guards against loses spend silently.

    Meta is queried at level=ad; campaign.ad_stats is unique on
    (campaign_name, ad_set_name, captured_on) and snapshot_ad_stats upserts on
    that key, replacing rather than summing. Writing ad-level rows straight
    through means the last ad in each ad set overwrites its siblings.

    Asserting the TOTAL, not the row count: a count-only test passes happily
    while every number is short.
    """
    rows = transform(load_fixture())
    agg = aggregate(rows)
    assert sum(r.spend_eur for r in agg) == pytest.approx(sum(r.spend_eur for r in rows))
    for field in ("impressions", "clicks", "leads"):
        assert sum(getattr(r, field) for r in agg) == sum(getattr(r, field) for r in rows)


def test_aggregation_collapses_to_the_ledger_grain():
    agg = aggregate(transform(load_fixture()))
    keys = [(r.campaign_name, r.ad_set_name, r.captured_on) for r in agg]
    assert len(keys) == len(set(keys)), "two rows share the ledger's natural key"


def test_the_fixture_actually_exercises_a_collision():
    """A guard on the guard. If the fixture ever loses its duplicate ad sets,
    the tests above would still pass while testing nothing."""
    rows = transform(load_fixture())
    agg = aggregate(rows)
    assert len(agg) < len(rows), "fixture no longer contains an ad-set collision"


def test_a_merged_group_has_no_creative_link():
    """A group spanning creatives cannot name one, or v_content_perf blames the
    wrong lane."""
    for r in aggregate(transform(load_fixture())):
        if "+" in r.utm_content:
            assert r.creative_content_id is None


def test_a_merged_group_keeps_every_label():
    agg = aggregate(transform(load_fixture()))
    merged = [r for r in agg if "+" in r.utm_content]
    assert merged, "expected at least one merged group in the fixture"
    for r in merged:
        parts = r.utm_content.split("+")
        assert len(parts) == len(set(parts)), "labels should be de-duplicated"


def test_aggregate_is_idempotent():
    once = aggregate(transform(load_fixture()))
    twice = aggregate(once)
    assert [ledger_row(r) for r in once] == [ledger_row(r) for r in twice]


def test_write_row_adapts_to_a_list_signature():
    seen = []
    _write_row(lambda rows: seen.extend(rows), {"campaign_name": "c"})
    assert seen == [{"campaign_name": "c"}]


# --- the live call, which has never run -----------------------------------

def test_live_url_is_built_for_daily_ad_level_rows():
    from datetime import date

    url = build_url("123456", "TOKEN-NOT-A-REAL-SECRET", date(2026, 9, 23), date(2026, 9, 24))
    assert "act_123456/insights" in url
    assert "level=ad" in url
    assert "time_increment=1" in url          # one row per ad per day is the stored grain
    assert "2026-09-23" in url and "2026-09-24" in url
