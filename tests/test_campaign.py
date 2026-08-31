"""The campaign structure is only worth declaring if it is checked against the
rest of the repo. These tests check the checker."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.campaign import load_structure, validate


@pytest.fixture
def structure():
    return copy.deepcopy(load_structure())


def _first_ad(structure):
    return structure["campaigns"][0]["adsets"][0]["ads"][0]


def test_declared_structure_is_valid():
    report = validate()
    assert report.ok, report.errors


def test_nothing_in_the_declared_structure_is_live():
    """No campaign, ad set or ad may ship enabled from this repo. A human launches."""
    structure = load_structure()
    for campaign in structure["campaigns"]:
        assert campaign["status"] == "PAUSED"
        for adset in campaign["adsets"]:
            assert adset["status"] == "PAUSED"
            for ad in adset["ads"]:
                assert ad["status"] == "PAUSED"


def test_an_enabled_ad_is_rejected(structure):
    _first_ad(structure)["status"] = "ACTIVE"
    assert not validate(structure).ok


def test_unknown_creative_ref_is_rejected(structure):
    _first_ad(structure)["creative_ref"] = "does-not-exist"
    assert any("creative_ref" in e for e in validate(structure).errors)


def test_unknown_audience_ref_is_rejected(structure):
    structure["campaigns"][0]["adsets"][0]["audience_ref"] = "nope"
    assert any("audience_ref" in e for e in validate(structure).errors)


def test_priority_must_agree_with_the_audience_file(structure):
    structure["campaigns"][0]["adsets"][0]["priority"] = 9
    assert any("priority" in e for e in validate(structure).errors)


def test_blocked_audience_must_surface_a_blocker(structure):
    retarget = structure["campaigns"][1]["adsets"][0]
    assert retarget["id"] == "as-site-retargeting"
    retarget["launch_gate"]["blockers"] = []
    assert any("blocked upstream" in e for e in validate(structure).errors)


def test_unproofread_locale_without_a_blocker_is_rejected(structure):
    """Drafted Danish is not native-checked, and the gate reads Danish poorly.
    This assertion is the only thing between a draft translation and a live ad."""
    danish = next(
        ad
        for _, adset in [(c, a) for c in structure["campaigns"] for a in c["adsets"]]
        for ad in adset["ads"]
        if ad["locale"] == "da"
    )
    danish["blockers"] = []
    assert any("NEEDS_NATIVE_PROOFREAD" in e for e in validate(structure).errors)


def test_replaces_must_point_at_a_sibling_ad(structure):
    danish = next(ad for ad in structure["campaigns"][1]["adsets"][1]["ads"] if ad.get("replaces"))
    danish["replaces"] = "ad-that-does-not-exist"
    assert any("replaces" in e for e in validate(structure).errors)


def test_budget_summary_must_match_the_ad_sets(structure):
    structure["campaigns"][0]["adsets"][0]["daily_budget_eur"] = 500
    errors = validate(structure).errors
    assert any("budget_summary" in e for e in errors)


def test_launch_budget_excludes_blocked_ad_sets():
    """The blocked retargeting ad set must not be counted in day-one spend."""
    structure = load_structure()
    summary = structure["budget_summary"]
    assert summary["at_launch_daily_eur"] < summary["all_four_daily_eur"]
