import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report import ledger_shim
from report.pull_ad_stats import (
    AdStatRow,
    _write_row,
    build_url,
    count_leads,
    creative_content_id,
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
    integration failure on the day the ledger lands."""
    row = transform(load_fixture())[0]
    assert set(vars(row)) == set(ledger_shim.COLUMNS)


# --- the ledger seam ------------------------------------------------------

def test_shim_writes_a_row(tmp_path):
    row = vars(transform(load_fixture())[0])
    out = tmp_path / "ad_stats.jsonl"
    ledger_shim.snapshot_ad_stats(row, path=out)
    assert out.read_text(encoding="utf-8").count("\n") == 1


def test_shim_refuses_a_column_that_is_not_in_the_table(tmp_path):
    row = dict(vars(transform(load_fixture())[0]), ctr=0.02)
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

    _write_row(snapshot, vars(transform(load_fixture())[0]))
    assert seen["campaign_name"] == "teams_q4_retargeting"
    assert seen["creative_content_id"] == "v5-pilot"


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
