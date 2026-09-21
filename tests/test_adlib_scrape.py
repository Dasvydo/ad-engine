"""The Ad Library card parser, against text the UI actually rendered.

The fixture is transcribed from a real Ad Library screenshot (Fyxer, Denmark,
2026-09-21). It is text rather than HTML on purpose: the parser reads labels,
because the Ad Library's class names are obfuscated and rotate, and a selector
test would pass against a DOM that no longer exists.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from adlib_scrape import parse_cards

TODAY = date(2026, 9, 21)

FYXER_DK = """
Inactive
Library ID: 2420710038356011
29 May 2026 - 3 Jun 2026
Platforms
2 ads use this creative and text
See summary details
Fyxer
Sponsored
You've got to see it to believe it! Fyxer supercharges your inbox, automating emails, follow-ups, and meeting notes with lightning speed
Your AI Email Assistant
Learn More
Inactive
Library ID: 1727456894897090
6 Feb 2026 - 16 Feb 2026
Platforms
This ad has multiple versions
2 ads use this creative and text
See summary details
Fyxer
Sponsored
Begin your day with emails neatly organized, replies crafted to match your tone and crisp notes from every meeting. Try free today.
Your AI Email Assistant
Learn More
Inactive
Library ID: 1304701714775927
11 Feb 2026 - 23 Feb 2026
Platforms
2 ads use this creative and text
See summary details
Fyxer
Sponsored
Begin your day with emails neatly organized, replies crafted to match your tone and crisp notes from every meeting. Try free today.
Your AI Email Assistant
Learn More
"""


def test_reads_every_card():
    assert len(parse_cards(FYXER_DK, TODAY)) == 3


def test_days_running_is_inclusive():
    """11-23 Feb is thirteen days. An ad that starts and stops on one day ran
    a day, not zero, so the count includes both ends."""
    rows = {r["library_id"]: r for r in parse_cards(FYXER_DK, TODAY)}
    assert rows["1304701714775927"]["days_running"] == 13
    assert rows["1727456894897090"]["days_running"] == 11
    assert rows["2420710038356011"]["days_running"] == 6


def test_status_comes_from_before_the_id_not_after():
    """Regression, 2026-09-21. The Active/Inactive chip renders ABOVE
    "Library ID:", so splitting on that label leaves the chip at the tail of
    the previous chunk. Reading it off the current chunk marked every ad
    active, which would have inverted the whole ranking."""
    assert all(r["active"] is False for r in parse_cards(FYXER_DK, TODAY))

    live = FYXER_DK.replace("Inactive\nLibrary ID: 1304701714775927",
                            "Active\nLibrary ID: 1304701714775927")
    rows = {r["library_id"]: r for r in parse_cards(live, TODAY)}
    assert rows["1304701714775927"]["active"] is True
    assert rows["1727456894897090"]["active"] is False


def test_open_ended_run_is_measured_to_today_and_flagged():
    """A still-running ad has no end date. Its day count is a floor, and
    `still_running` is what stops a reader treating it as a total."""
    running = "\nActive\nLibrary ID: 999\nStarted running on 11 Sep 2026\nPlatforms\nFyxer\nSponsored\nA body long enough to be picked up by the parser.\n"
    row = parse_cards(running, TODAY)[0]
    assert row["still_running"] is True
    assert row["ended"] is None
    assert row["days_running"] == 11


def test_body_copy_is_captured():
    """The body is the field the MCP connector never returns - it hands back
    ad_creative_link_title only. Losing it here defeats the point."""
    rows = {r["library_id"]: r for r in parse_cards(FYXER_DK, TODAY)}
    assert "replies crafted to match your tone" in rows["1304701714775927"]["body"]
    assert "Learn More" not in rows["1304701714775927"]["body"]


def test_creative_reuse_count():
    assert all(r["copies_of_this_creative"] == 2
               for r in parse_cards(FYXER_DK, TODAY))
