#!/usr/bin/env python3
"""Read a page's ads out of the Meta Ad Library UI, ranked by how long each ran.

WHY THIS EXISTS. `engine/discover.py` is the real path and it needs
META_ACCESS_TOKEN, which needs identity verification at facebook.com/ID, which
takes days. This reads the same public archive through the browser instead, so
the founder is not blocked on Meta's queue.

WHY IT RUNS ON YOUR MACHINE AND NOT IN CI. Meta returns 403 to a datacenter or
headless client: the page frame renders, the ad data never arrives. Verified
2026-09-21 - six scroll passes, body text stuck at 553 characters. The fix is
not a better user agent, it is being an ordinary logged-in browser on an
ordinary connection. So this ATTACHES to a Chrome you already have open. It
never sees a password, never logs in, never stores a cookie.

    1. Quit Chrome completely.
    2. Start it with a debug port:
       macOS   /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
                 --remote-debugging-port=9222
       Linux   google-chrome --remote-debugging-port=9222
    3. Log into Facebook in that window, as normal.
    4. pip install playwright && playwright install chromium
    5. python tools/adlib_scrape.py --page-id 484462831408750 --country DK

⚠️ Automated reading of the Ad Library sits against Meta's terms of service.
That is the operator's call, not this script's. The default pacing is
deliberately slow and there is no retry-on-block: if Meta says no, it stops.
Nothing here disguises the client or evades a control.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime

CARD = re.compile(r"Library ID:\s*(\d+)")
# "11 Feb 2026 - 23 Feb 2026" or the open-ended "Started running on 11 Feb 2026"
RANGE = re.compile(r"(\d{1,2} \w{3} \d{4})\s*[-–]\s*(\d{1,2} \w{3} \d{4})")
STARTED = re.compile(r"Started running on (\d{1,2} \w{3} \d{4})")
USES = re.compile(r"(\d+)\s+ads use this creative and text")


def _date(s: str):
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_cards(body: str, today) -> list[dict]:
    """Split the results text on 'Library ID:' and read each block.

    Text, not selectors, on purpose: the Ad Library's class names are
    obfuscated and rotate. The labels do not.
    """
    rows, parts = [], body.split("Library ID:")
    for i, part in enumerate(parts[1:], start=1):
        m = re.match(r"\s*(\d+)", part)
        if not m:
            continue
        block = part[: 2000]
        # The Active/Inactive chip is rendered ABOVE "Library ID:", so it lands
        # at the tail of the PREVIOUS split chunk, not the head of this one.
        # Reading it off `block` marks every ad active. Caught by the fixture
        # test on 2026-09-21; do not "simplify" this back.
        preceding = parts[i - 1][-40:]
        started = ended = None
        if r_ := RANGE.search(block):
            started, ended = _date(r_.group(1)), _date(r_.group(2))
        elif s_ := STARTED.search(block):
            started, ended = _date(s_.group(1)), None

        days = None
        if started:
            # Inclusive: an ad that started and stopped the same day ran a day.
            days = ((ended or today) - started).days + 1

        # Body copy is whatever follows "Sponsored" on the card.
        body_copy = ""
        if "Sponsored" in block:
            after = block.split("Sponsored", 1)[1]
            for line in (l.strip() for l in after.split("\n")):
                if len(line) > 25 and "Learn More" not in line:
                    body_copy = line
                    break

        rows.append({
            "library_id": m.group(1),
            "active": "Inactive" not in preceding,
            "started": started.isoformat() if started else None,
            "ended": ended.isoformat() if ended else None,
            "days_running": days,
            "still_running": ended is None and started is not None,
            "copies_of_this_creative": int(u.group(1)) if (u := USES.search(block)) else 1,
            "body": body_copy,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--page-id", required=True, help="Advertiser page id, from the Ad Library URL")
    ap.add_argument("--country", default="DK", help="ISO-2. Must be an EU country for reach data")
    ap.add_argument("--cdp", default="http://localhost:9222", help="Your Chrome's debug endpoint")
    ap.add_argument("--max-scrolls", type=int, default=40)
    ap.add_argument("--pause-ms", type=int, default=2500, help="Between scrolls. Do not lower it")
    ap.add_argument("--out", default="adlib.csv")
    a = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright", file=sys.stderr)
        return 2

    url = (f"https://www.facebook.com/ads/library/?active_status=all&ad_type=all"
           f"&country={a.country}&view_all_page_id={a.page_id}")
    today = datetime.now().date()

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(a.cdp)
        except Exception as exc:
            print(f"Could not attach to Chrome at {a.cdp}.\n"
                  f"Start it with --remote-debugging-port=9222 and log in first.\n{exc}",
                  file=sys.stderr)
            return 2

        page = browser.contexts[0].new_page()
        page.goto(url, timeout=90_000, wait_until="domcontentloaded")
        page.wait_for_timeout(a.pause_ms)

        seen, stalled = 0, 0
        for i in range(a.max_scrolls):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(a.pause_ms)
            found = len(CARD.findall(page.inner_text("body")))
            if found == seen:
                stalled += 1
                if stalled >= 3:          # three quiet passes means the end
                    break
            else:
                stalled = 0
            seen = found
            print(f"  scroll {i+1}: {found} ads", file=sys.stderr)

        body = page.inner_text("body")
        page.close()

    if not CARD.search(body):
        print("No ads parsed. Either the page has none in this country, or Meta "
              "served a block page - check the browser window.", file=sys.stderr)
        return 1

    rows = parse_cards(body, today)
    # Longest-running first: that is the one the advertiser's own money voted on.
    rows.sort(key=lambda r: (r["days_running"] or 0), reverse=True)

    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(a.out.replace(".csv", ".json"), "w") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)

    print(f"\n{len(rows)} ads -> {a.out}\n")
    print(f"{'days':>5}  {'copies':>6}  {'id':<18}  body")
    for r in rows[:15]:
        flag = "*" if r["still_running"] else " "
        print(f"{str(r['days_running'] or '?'):>5}{flag} {r['copies_of_this_creative']:>6}  "
              f"{r['library_id']:<18}  {r['body'][:60]}")
    print("\n* = still running, so its day count is a floor, not a total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
