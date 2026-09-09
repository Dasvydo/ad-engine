"""Pull daily Meta ad numbers and write them into `campaign.ad_stats`.

    python report/pull_ad_stats.py --dry-run            # fixture, writes nothing
    python report/pull_ad_stats.py --date 2026-09-23    # live, needs credentials
    python report/pull_ad_stats.py --since 2026-09-22 --until 2026-09-28

No Meta ad account exists yet, so the live path has never run. The shape of the
Insights response, the field list and the parsing are written against Meta's
documented response for `/act_<id>/insights`, and the fixture is that shape.
The live run is logged as blocked in BLOCKED.md.

Why this is one small script and not an integration: at under EUR 500 a month,
the whole reporting need is "get yesterday's rows into the ledger so the Friday
brief can read them". Anything larger costs more than the media it reports on.

## The seam with Batch B

The ledger's Python client is `campaign_db.py`, owned by Batch B in the
`campaign-ledger` repo. This session cannot see it. So:

* the import is tried, and falls back to `report/ledger_shim.py` on ImportError;
* the call is adapted to whatever signature `snapshot_ad_stats` turns out to
  have, because this side has never seen it (see `_write_row`);
* the row shape uses the exact `campaign.ad_stats` column names and nothing else.

When the ledger lands, put it on the PYTHONPATH. Nothing here needs to change.
"""

from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import sys
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "insights_sample.json"

log = logging.getLogger("ad_stats")

API_VERSION = "v21.0"

# Ad names follow the convention in campaigns/structure.md:
#     teams_q4 | v5-pilot | s05-two-weeks-4x5
# The middle segment is the utm_content value, which is what joins spend back to
# a creative in campaign.content. Nothing else in the Insights response carries it.
AD_NAME_SEPARATOR = "|"

# Meta reports leads under several action_type strings depending on where the
# conversion was defined. Count any of them, once.
LEAD_ACTIONS = {
    "lead",
    "offsite_conversion.fb_pixel_lead",
    "onsite_conversion.lead_grouped",
}

INSIGHTS_FIELDS = (
    "campaign_name",
    "adset_name",
    "ad_name",
    "spend",
    "impressions",
    "clicks",
    "actions",
    "account_currency",
)


# --------------------------------------------------------------------------
# The ledger seam
# --------------------------------------------------------------------------

def _load_snapshot():
    """Try Batch B's client, fall back to the local shim.

    Returns (callable, connected: bool).
    """
    try:
        from campaign_db import snapshot_ad_stats  # type: ignore
    except ImportError:
        from report.ledger_shim import snapshot_ad_stats  # type: ignore

        log.warning(
            "campaign_db not importable, so rows go to report/out/ad_stats.jsonl "
            "instead of campaign.ad_stats. Put Batch B's campaign-ledger on the "
            "PYTHONPATH to connect the real ledger."
        )
        return snapshot_ad_stats, False
    return snapshot_ad_stats, True


def _write_row(snapshot, row: dict) -> None:
    """Call snapshot_ad_stats without knowing its exact signature.

    This side has never seen `campaign_db.py`. Batch B may have written it to
    take a row dict, a list of rows, or keyword arguments per column. Inspect and
    adapt rather than guessing and breaking on the day the ledger lands.
    """
    try:
        sig = inspect.signature(snapshot)
    except (TypeError, ValueError):
        snapshot(row)
        return

    params = [
        p for p in sig.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    ]
    required = [p for p in params if p.default is p.empty and p.kind != p.VAR_KEYWORD]

    # One required parameter: it takes the row (or a list of rows).
    if len(required) <= 1:
        name = required[0].name if required else ""
        if name.endswith("s") and name not in ("stats", "ad_stats"):
            snapshot([row])
        else:
            snapshot(row)
        return

    # Several required parameters: it takes the columns as keywords.
    snapshot(**row)


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------

def build_url(account_id: str, token: str, since: date, until: date) -> str:
    account = account_id if account_id.startswith("act_") else f"act_{account_id}"
    query = urllib.parse.urlencode(
        {
            "fields": ",".join(INSIGHTS_FIELDS),
            "level": "ad",
            "time_increment": "1",  # one row per ad per day, which is the grain we store
            "time_range": json.dumps(
                {"since": since.isoformat(), "until": until.isoformat()}
            ),
            "limit": "500",
            "access_token": token,
        }
    )
    return f"https://graph.facebook.com/{API_VERSION}/{account}/insights?{query}"


def fetch_insights(account_id: str, token: str, since: date, until: date) -> list[dict]:
    """Live call. Never exercised, because no ad account exists. See BLOCKED.md."""
    url = build_url(account_id, token, since, until)
    rows: list[dict] = []
    while url:
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
        if "error" in payload:
            raise RuntimeError(f"Meta Insights error: {payload['error']}")
        rows.extend(payload.get("data", []))
        url = payload.get("paging", {}).get("next")
    return rows


def load_fixture(path: Path = FIXTURE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["data"]


# --------------------------------------------------------------------------
# Transform
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class AdStatRow:
    """One day of numbers for one ad.

    The first eight fields are `campaign.ad_stats`'s columns, exactly, and only
    those are written - see `LEDGER_COLUMNS` and `ledger_row`. `id` is not here:
    the database generates it.

    `utm_content` is deliberately NOT a ledger column. It is the human label
    pulled off the ad name, kept so the dry-run table and the logs can show
    which creative a row came from. Writing it to the database would fail: see
    `content_id_for_ledger`.
    """

    campaign_name: str
    ad_set_name: str
    creative_content_id: str | None
    captured_on: str
    spend_eur: float
    impressions: int
    clicks: int
    leads: int
    utm_content: str = ""


# The columns campaign.ad_stats actually has, in Batch B's order. Anything not
# in this tuple never reaches the ledger, which is why AdStatRow may carry
# local-only fields safely.
LEDGER_COLUMNS = (
    "campaign_name",
    "ad_set_name",
    "creative_content_id",
    "captured_on",
    "spend_eur",
    "impressions",
    "clicks",
    "leads",
)


def ledger_row(row: AdStatRow) -> dict:
    """Project an AdStatRow onto exactly the ledger's columns.

    Replaces a blanket `asdict()`. `_write_row` may call the ledger with
    `snapshot(**row)`, so a stray key here is a TypeError against Batch B's
    signature the first time the real client is on the path.
    """
    return {column: getattr(row, column) for column in LEDGER_COLUMNS}


def creative_content_id(ad_name: str) -> str:
    """Pull the utm_content value out of the ad name.

    `teams_q4 | v5-pilot | s05-two-weeks-4x5` -> `v5-pilot`

    An ad named off-convention still produces a row, because losing a day's spend
    is worse than losing a label. It returns the whole name so the mistake is
    visible in the ledger rather than silently becoming an empty string.
    """
    parts = [p.strip() for p in ad_name.split(AD_NAME_SEPARATOR)]
    if len(parts) >= 2 and parts[1]:
        return parts[1]
    log.warning(
        "ad name %r is off-convention, so spend cannot be joined to a creative. "
        "Expected 'campaign | utm_content | creative-ratio'.",
        ad_name,
    )
    return ad_name.strip()


def content_id_for_ledger(label: str) -> str | None:
    """Return `label` only if it is a real uuid, else None.

    `campaign.ad_stats.creative_content_id` is declared
    `uuid references campaign.content (id)` in Batch B's
    migrations/001_schema.sql:388. An ad-name label like `v5-pilot` is not a
    uuid, so sending it there fails the whole insert with an invalid-input-
    syntax error - and it would fail on the FIRST live write, having passed
    every offline test, because the JSONL shim happily accepts any string.

    Batch B's own docstring on `snapshot_ad_stats` settles what to do instead:
    "creative_content_id is optional ... Leave it None rather than guessing - a
    wrong link makes v_content_perf blame the wrong lane."

    The label is not lost. It stays on `AdStatRow.utm_content`, prints in the
    dry-run table, and is named in the warning below. Joining spend back to a
    specific creative needs a real `campaign.content.id`, which this repo has no
    way to look up - see BLOCKED.md.
    """
    if not label:
        return None
    try:
        uuid.UUID(label)
    except (ValueError, AttributeError, TypeError):
        # Deliberately not a warning. Ad names carry human labels, so this is
        # the NORMAL case on every row of every run, and warning on the normal
        # case teaches people to ignore warnings. transform() logs one summary
        # line per run instead.
        log.debug("creative label %r is not a uuid; creative_content_id is NULL", label)
        return None
    return label


def count_leads(actions: list[dict] | None) -> int:
    if not actions:
        return 0
    total = 0
    for action in actions:
        if action.get("action_type") in LEAD_ACTIONS:
            total += int(float(action.get("value", 0)))
    return total


def to_row(raw: dict, *, strict_currency: bool = True) -> AdStatRow:
    currency = raw.get("account_currency")
    if strict_currency and currency and currency != "EUR":
        # spend_eur is a euro column. Writing USD into it silently would corrupt
        # every funnel number downstream, so refuse rather than convert with a
        # rate nobody recorded.
        raise ValueError(
            f"ad account currency is {currency}, not EUR, and spend_eur is a euro "
            "column. Either set the ad account to EUR or add an explicit, dated "
            "conversion step here."
        )
    label = creative_content_id(raw.get("ad_name", ""))
    return AdStatRow(
        campaign_name=raw["campaign_name"],
        ad_set_name=raw["adset_name"],
        creative_content_id=content_id_for_ledger(label),
        utm_content=label,
        captured_on=raw["date_start"],
        spend_eur=round(float(raw.get("spend", 0)), 2),
        impressions=int(raw.get("impressions", 0)),
        clicks=int(raw.get("clicks", 0)),
        leads=count_leads(raw.get("actions")),
    )


def aggregate(rows: list[AdStatRow]) -> list[AdStatRow]:
    """Collapse ad-level rows onto the ledger's ad-set/day grain, summing.

    Meta is queried at `level=ad` (see INSIGHTS_FIELDS and build_url), so it
    returns one row per ad per day. `campaign.ad_stats` is keyed
    `unique (campaign_name, ad_set_name, captured_on)` and Batch B's
    `snapshot_ad_stats` upserts on exactly that key - a REPLACE, not a sum.

    So without this, two ads in one ad set on one day collide and the second
    write overwrites the first. Nothing errors and nothing warns; the row is
    simply short. Measured on the committed fixture: 8 ad rows collapse to 5
    ad-set/days, and last-write-wins stores 13.97 EUR of a real 22.75 - a 39%
    under-report, which would then be wrong in every cost-per-lead and channel
    funnel number downstream.

    Summing is the only correct reading: `spend_eur`, `impressions`, `clicks`
    and `leads` are all additive over the ads in an ad set.

    `creative_content_id` stays None for a merged group, because a group spans
    creatives and Batch B's docstring is explicit that a wrong link makes
    v_content_perf blame the wrong lane. `utm_content` keeps every distinct
    label so the merge stays visible in the dry-run table and the logs.
    """
    acc: dict[tuple, dict] = {}
    labels: dict[tuple, list[str]] = {}
    order: list[tuple] = []

    for row in rows:
        key = (row.campaign_name, row.ad_set_name, row.captured_on)
        if key not in acc:
            order.append(key)
            acc[key] = {
                "campaign_name": row.campaign_name,
                "ad_set_name": row.ad_set_name,
                "creative_content_id": row.creative_content_id,
                "captured_on": row.captured_on,
                "spend_eur": row.spend_eur,
                "impressions": row.impressions,
                "clicks": row.clicks,
                "leads": row.leads,
            }
            labels[key] = [row.utm_content] if row.utm_content else []
            continue

        a = acc[key]
        a["spend_eur"] = round(a["spend_eur"] + row.spend_eur, 2)
        a["impressions"] += row.impressions
        a["clicks"] += row.clicks
        a["leads"] += row.leads
        # A group spanning creatives cannot name one.
        if a["creative_content_id"] != row.creative_content_id:
            a["creative_content_id"] = None
        if row.utm_content and row.utm_content not in labels[key]:
            labels[key].append(row.utm_content)

    if len(order) != len(rows):
        spanning = sum(1 for k in order if len(labels[k]) > 1)
        log.info(
            "%d ad-level rows collapsed to %d ad-set/day rows, summing spend, "
            "impressions, clicks and leads. %d group(s) span more than one "
            "creative.",
            len(rows), len(order), spanning,
        )

    return [AdStatRow(**acc[k], utm_content="+".join(labels[k])) for k in order]


def transform(raws: list[dict], *, strict_currency: bool = True) -> list[AdStatRow]:
    rows = [to_row(r, strict_currency=strict_currency) for r in raws]
    unlinked = [r for r in rows if r.creative_content_id is None]
    if unlinked:
        labels = sorted({r.utm_content for r in unlinked if r.utm_content})
        log.info(
            "%d of %d rows carry no creative_content_id, so spend is recorded "
            "against its ad set but not joined to a creative. Labels seen: %s. "
            "This is expected while ads are named with human labels rather than "
            "campaign.content uuids.",
            len(unlinked), len(rows), ", ".join(labels) or "(none)",
        )
    return rows


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print_table(rows: list[AdStatRow]) -> None:
    if not rows:
        print("no rows")
        return
    head = f"{'date':11s} {'ad set':22s} {'creative':16s} {'spend':>8s} {'impr':>8s} {'clicks':>7s} {'leads':>6s}"
    print(head)
    print("-" * len(head))
    for r in rows:
        print(
            f"{r.captured_on:11s} {r.ad_set_name[:22]:22s} {(r.utm_content or '-')[:16]:16s} "
            f"{r.spend_eur:8.2f} {r.impressions:8,d} {r.clicks:7,d} {r.leads:6,d}"
        )
    print("-" * len(head))
    print(
        f"{len(rows)} rows  "
        f"spend EUR {sum(r.spend_eur for r in rows):.2f}  "
        f"clicks {sum(r.clicks for r in rows):,}  "
        f"leads {sum(r.leads for r in rows):,}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pull_ad_stats")
    ap.add_argument("--dry-run", action="store_true",
                    help="read the fixture, print the rows, write nothing")
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--date", type=str, help="a single day, YYYY-MM-DD")
    ap.add_argument("--since", type=str)
    ap.add_argument("--until", type=str)
    ap.add_argument("--allow-non-eur", action="store_true",
                    help="write non-EUR spend into spend_eur anyway. Do not.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.dry_run:
        raws = load_fixture(args.fixture)
        log.info("dry run against %s, %d raw rows", args.fixture.name, len(raws))
        rows = aggregate(transform(raws, strict_currency=not args.allow_non_eur))
        _print_table(rows)
        print("\nDRY RUN, nothing written to campaign.ad_stats.")
        return 0

    account = os.environ.get("META_AD_ACCOUNT_ID")
    token = os.environ.get("META_ACCESS_TOKEN")
    if not account or not token:
        log.error(
            "META_AD_ACCOUNT_ID and META_ACCESS_TOKEN are not set, so there is "
            "nothing to call. No Meta ad account exists yet: see BLOCKED.md "
            "entry 6. Use --dry-run to exercise this against the fixture."
        )
        return 2

    if args.date:
        since = until = date.fromisoformat(args.date)
    elif args.since:
        since = date.fromisoformat(args.since)
        until = date.fromisoformat(args.until) if args.until else since
    else:
        since = until = date.today() - timedelta(days=1)   # yesterday, the usual run

    raws = fetch_insights(account, token, since, until)
    rows = aggregate(transform(raws, strict_currency=not args.allow_non_eur))

    snapshot, connected = _load_snapshot()
    for row in rows:
        _write_row(snapshot, ledger_row(row))

    _print_table(rows)
    print(
        f"\nwrote {len(rows)} rows to "
        + ("campaign.ad_stats" if connected else "report/out/ad_stats.jsonl (ledger not connected)")
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE.parent))
    sys.exit(main())
