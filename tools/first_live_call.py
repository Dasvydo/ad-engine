#!/usr/bin/env python3
"""The first live call, as one command. Read-only, one request, no writes.

    export META_ACCESS_TOKEN=...
    python tools/first_live_call.py                 # one page-id call, DK
    python tools/first_live_call.py --query regnskab --country DK
    python tools/first_live_call.py --rate-limit    # probe the hourly ceiling

WHY THIS EXISTS. Three things in this repository are marked
`TODO(integration): UNVERIFIED AGAINST A LIVE RESPONSE`, and all three are
answered by one real response:

  1. THE FIELD SET. `engine/discover.py`'s FIELDS was built from Meta's
     reference page and the DSA guides, and nobody here has seen what a
     commercial EU ad actually returns. A field that is documented and absent
     is a parser reading None forever; a field that is present and undocumented
     is evidence we are not collecting.
  2. THE RATE LIMIT. `HOURLY_BUDGET_CALLS = 200` is the figure every secondary
     guide reports and Meta's own reference does not print - it names the
     error, code 613, and not the number. The budget is a parameter precisely
     so a measured figure replaces it in one line.
  3. THE TOKEN LIFETIME. Not published for this use. Sixty days is assumed
     from the sibling repository's Instagram experience.

This script answers 1 and, with --rate-limit, 2. Nothing answers 3 except the
calendar.

WHAT IT DELIBERATELY DOES NOT DO. It writes no corpus record, no patterns and
no report - a first call that also committed files would make "did the call
work" and "did the pipeline work" the same question, and they are not. It
makes ONE request by default, because the first thing you want to know about a
new credential is whether one call works, not whether fifty do.

It prints no token. The value travels in an Authorization header, and every
error is reported without the URL that carried it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import discover  # noqa: E402


def _fetch(client: discover.AdLibraryClient, **kwargs) -> list[dict]:
    """One archive call, with the module's own transport and quota."""
    return client.archive(max_pages=1, **kwargs)


def report_fields(ads: list[dict]) -> int:
    """What came back, against what engine/discover.py asks for."""
    asked = list(discover.FIELDS)
    seen: dict[str, int] = {}
    for ad in ads:
        for key in ad:
            seen[key] = seen.get(key, 0) + 1

    print("\nFIELDS - what %d ad(s) actually carried" % len(ads))
    print("  %-34s %-9s %s" % ("field", "in n ads", "verdict"))
    for field in asked:
        n = seen.get(field, 0)
        if n == len(ads) and n:
            verdict = "always present"
        elif n:
            verdict = "SOMETIMES present - a parser must tolerate its absence"
        else:
            verdict = "NEVER RETURNED - asked for and not given"
        print("  %-34s %-9s %s" % (field, "%d/%d" % (n, len(ads)), verdict))

    extra = sorted(set(seen) - set(asked))
    if extra:
        print("\n  UNDOCUMENTED, returned but never asked for - evidence we are")
        print("  not collecting. Add to engine/discover.py FIELDS to keep it:")
        for field in extra:
            print("    %-32s in %d/%d" % (field, seen[field], len(ads)))
    else:
        print("\n  No undocumented field came back.")

    missing = [f for f in asked if not seen.get(f)]
    if missing:
        print("\n  VERDICT: %d documented field(s) never arrived. Before trusting a"
              % len(missing))
        print("  sweep, decide for each whether it is absent for THESE ads (a")
        print("  political-only field on a commercial ad) or absent always (a")
        print("  field to drop from FIELDS so the request stops asking).")
        return 1
    print("\n  VERDICT: every documented field arrived. The TODO(integration)")
    print("  block in engine/discover.py can record this run and close.")
    return 0


def report_shape(ads: list[dict]) -> None:
    """One whole ad, verbatim. The thing worth pasting into a commit."""
    if not ads:
        return
    print("\nONE WHOLE AD, as returned - paste this into the commit that closes")
    print("the TODO, so the next reader sees the evidence and not a summary:\n")
    print(json.dumps(ads[0], indent=2, sort_keys=True, ensure_ascii=False))


def probe_rate_limit(client: discover.AdLibraryClient, countries) -> int:
    """Call until Meta refuses, and report where it did.

    Costs real calls on purpose: the number is the whole point, and it is the
    one figure in docs/COST.md that is a secondary source rather than a
    measurement. Stops at the module's own budget so a probe cannot spend an
    afternoon's allowance.
    """
    print("\nRATE LIMIT - calling until refused, ceiling %d (the documented"
          % discover.HOURLY_BUDGET_CALLS)
    print("assumption). A refusal before that is the real number.\n")
    made = 0
    try:
        while made < discover.HOURLY_BUDGET_CALLS:
            _fetch(client, countries=countries, search_terms="regnskab", limit=1)
            made += 1
            if made % 10 == 0:
                print("  %d calls, still answering" % made)
    except discover.QuotaExceededError:
        print("  stopped at %d by OUR OWN ledger, not by Meta. The real ceiling"
              % made)
        print("  is at or above that. Raise --budget to probe further.")
        return 0
    except discover.ApiError as exc:
        print("  REFUSED after %d call(s): %s" % (made, exc))
        print("\n  That is the measured hourly ceiling. Put it in")
        print("  engine/discover.py HOURLY_BUDGET_CALLS and in docs/COST.md,")
        print("  and mark that row measured rather than reported.")
        return 0
    print("  %d calls and never refused. The 200 assumption is a floor, not a"
          % made)
    print("  ceiling. Record that rather than raising the budget on a hunch.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python tools/first_live_call.py",
        description="One real Ad Library call, and what it says about the "
                    "assumptions this repository was built on.",
    )
    parser.add_argument("--query", default=None,
                        help="search text; default is a page-id call against "
                             "the first seeded page")
    parser.add_argument("--country", action="append", default=None,
                        metavar="ISO2", help="repeatable; default DK")
    parser.add_argument("--budget", type=int,
                        default=discover.HOURLY_BUDGET_CALLS,
                        help="calls this run may spend (default %d)"
                             % discover.HOURLY_BUDGET_CALLS)
    parser.add_argument("--rate-limit", action="store_true",
                        help="call until refused, to MEASURE the ceiling. "
                             "Spends real calls; that is the point")
    args = parser.parse_args(argv)

    countries = tuple(args.country or ("DK",))

    try:
        client = discover.AdLibraryClient(budget=args.budget)
    except discover.DiscoveryError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.rate_limit:
        return probe_rate_limit(client, countries)

    try:
        if args.query:
            print("one call: search_terms=%r, countries=%s"
                  % (args.query, ", ".join(countries)))
            ads = _fetch(client, countries=countries, search_terms=args.query)
        else:
            seeds = discover.load_seeds()
            if not seeds.pages:
                print("research/seeds.yaml seeds no page; pass --query instead",
                      file=sys.stderr)
                return 1
            page = seeds.pages[0]
            countries = page.countries or countries
            print("one call: page_ids=[%s] (%s), countries=%s"
                  % (page.page_id, page.name, ", ".join(countries)))
            ads = _fetch(client, countries=countries, page_ids=[page.page_id])
    except discover.DiscoveryError as exc:
        # The operator's fault or Meta's, never a traceback. The message
        # carries Meta's own words and never the URL that carried the token.
        print("\nthe call did not succeed: %s" % exc, file=sys.stderr)
        return 1

    print("\n%d ad(s) came back; spent %d of %d call(s)."
          % (len(ads), client.quota.spent, args.budget))
    if not ads:
        print("\nZero ads is an ANSWER, not an error: this page ran nothing")
        print("that reached those countries inside the archive's window. Try")
        print("--query, or another seeded page, before doubting the token.")
        return 0

    code = report_fields(ads)
    report_shape(ads)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
