import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.audience import MIN_CUSTOM_AUDIENCE
from engine.preflight import (
    PLACEHOLDER,
    _language_fields,
    audience_blockers,
    claims_gate,
    custom_audience,
    native_copy,
    run,
    skill_claims_sync,
)


def _audience_file(folder, rows):
    path = Path(folder) / "aud.csv"
    path.write_text("email,fn,ln,country\n" + ("a" * 64 + ",,,\n") * rows, encoding="utf-8")
    return path


def test_live_creative_passes_the_claims_gate():
    assert claims_gate().status == "PASS"


def test_placeholder_copy_blocks_the_launch():
    """da and lt are machine quality today. This is meant to be red."""
    c = native_copy()
    assert c.status == "FAIL"
    assert any("da:" in line for line in c.detail)
    assert any("lt:" in line for line in c.detail)


def test_placeholder_is_reported_per_file_and_language():
    c = native_copy()
    assert any(line.startswith("capacity.json") and " da:" in line for line in c.detail)
    assert any(line.startswith("hours.json") and " lt:" in line for line in c.detail)


def test_non_language_dicts_are_not_read_as_copy():
    """creative_source is a dict of strings and is not a language map."""
    spec = {
        "headline": {"en": "More clients, same team", "da": PLACEHOLDER},
        "creative_source": {"video": "reel-engine", "still": "reel-engine"},
    }
    assert set(_language_fields(spec)) == {"headline"}


def test_no_audience_argument_skips_rather_than_passes():
    c = custom_audience(None)
    assert c.status == "SKIP" and any("engine.cli audience" in d for d in c.detail)


def test_audience_below_metas_floor_fails():
    with tempfile.TemporaryDirectory() as tmp:
        c = custom_audience(_audience_file(tmp, 40))
        assert c.status == "FAIL" and "40 rows" in c.summary


def test_audience_at_metas_floor_passes():
    with tempfile.TemporaryDirectory() as tmp:
        assert custom_audience(_audience_file(tmp, MIN_CUSTOM_AUDIENCE)).status == "PASS"


def test_header_row_is_not_counted_as_a_person():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "aud.csv"
        path.write_text("email,fn,ln,country\n", encoding="utf-8")
        assert "0 rows" in custom_audience(path).summary


def test_missing_audience_file_fails_rather_than_skips():
    with tempfile.TemporaryDirectory() as tmp:
        c = custom_audience(Path(tmp) / "never-built.csv")
        assert c.status == "FAIL" and "does not exist" in c.summary


def test_pixel_blocker_fails_by_design():
    """site-retargeting is blocked on a pixel that is not installed. Red is correct."""
    c = audience_blockers()
    assert c.status == "FAIL" and any(d.startswith("site-retargeting:") for d in c.detail)


def test_skill_claims_reference_is_in_sync():
    assert skill_claims_sync().status == "PASS"


def test_preflight_is_red_today_on_copy_and_pixel():
    blocked = [c.name for c in run(None) if c.failed]
    assert blocked == ["native copy", "audience blockers"]


def load_tests(loader, tests, pattern):
    """pytest is not installed here, so unittest runs the same plain functions.

        python -m unittest discover -s tests -t tests
    """
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            tests.addTest(unittest.FunctionTestCase(fn, description=name))
    return tests
