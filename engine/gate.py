"""Claims gate. An ad ships only if every factual claim it makes is evidenced.

Mirrors reel-engine's claims discipline. It exists because DoviLoop has no
customers, no case studies and no measured outcomes yet - precisely the state in
which unverifiable claims get written, and precisely the exposure an investor
flagged: a public measurable promise with nothing behind it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "claims" / "evidence.json"

# Patterns that assert something measurable. Each must be backed or removed.
#
# Word order matters and the first version of this tuple got it wrong. It blocked
# "Saves 430 USD" but passed "430 USD saved per month" - which is the exact string
# the campaign landing page renders. The gate was catching the phrasings nobody
# writes and passing the two the funnel actually puts in front of a buyer. The
# money and multiple patterns below exist for that reason; see
# docs/FUNNEL-HANDOFF.md, "the gate hole".
_CURRENCY = r"(?:usd|eur|dkk|kr|euros?|dollars?)"
_SAVE = r"(?:saved|saving|saves|save)"
_SPELLED = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|dozens?)"

_RISKY = (
    (re.compile(r"\b\d+\s*(hours?|hrs?|timer|valand)", re.I), "hours_saved"),
    (re.compile(r"\bsaves?\s+\d", re.I), "hours_saved"),
    # Worded time claims carry no digit at all, so no numeric pattern sees them.
    (re.compile(r"\b(cuts?|cutting|halves?|halved|slash(?:es|ed)?)\b[^.\n]{0,30}\b(time|hours?|workload)\b", re.I), "hours_saved"),
    (re.compile(r"\b(in|by)\s+half\b", re.I), "hours_saved"),
    (re.compile(r"\bhalf\s+the\s+(time|work|hours)\b", re.I), "hours_saved"),
    # Spelled-out quantities. scripts/sync_skill_claims.py documented "Save ten
    # hours a month" and "Save hours every week" as blind spots on 2026-09-16, and
    # they were: every pattern above needs a digit or a currency, and neither
    # string has one. Merged from the ads-integration branch 2026-09-18.
    # Must read as a SAVING, not merely as a duration. The first version of this
    # matched any spelled number plus a time unit, which blocked "two weeks" -
    # the pilot length in creative/copy/v5-pilot.json and the whole subject of
    # creative/static/specs/s05-two-weeks.json. A two-week pilot is a fact about
    # what the firm gets, not a claim about time they get back. Caught by
    # tests/test_copy.py on the merge of claude/campaign-build-status-9j9194,
    # which is the argument for that branch's copy corpus existing at all.
    (re.compile(rf"\b(?:{_SAVE}|back|frees?\s+up|freed\s+up)\b[^.\n]{{0,25}}\b{_SPELLED}\s+(?:hours?|hrs?|minutes?|days?|weeks?)\b", re.I), "hours_saved"),
    (re.compile(rf"\b{_SPELLED}\s+(hours?|hrs?|minutes?)\b[^.\n]{{0,25}}\b(saved|back|freed)\b", re.I), "hours_saved"),
    (re.compile(r"\bsaves?\b[^.\n]{0,15}\b(hours?|time|minutes?)\b", re.I), "hours_saved"),
    # Money saved, in either word order.
    (re.compile(rf"\b\d[\d.,]*\s*(?:{_CURRENCY}|€|\$)\b[^.\n]{{0,40}}\b{_SAVE}\b", re.I), "money_saved"),
    (re.compile(rf"\b{_SAVE}\b[^.\n]{{0,40}}\b\d[\d.,]*\s*(?:{_CURRENCY}|€|\$)\b", re.I), "money_saved"),
    (re.compile(rf"[€$]\s*\d[\d.,]*[^.\n]{{0,40}}\b{_SAVE}\b", re.I), "money_saved"),
    (re.compile(rf"\b{_SAVE}\b[^.\n]{{0,40}}[€$]\s*\d", re.I), "money_saved"),
    # "Worth 4,300 USD a month" carries no save-word. Narrow on purpose: a bare
    # price ("89 USD per month") is a fact about the offer, not a claim about an
    # outcome, and must stay shippable.
    (re.compile(rf"\b(worth|values?|valued)\b[^.\n]{{0,20}}\b\d[\d.,]*\s*(?:{_CURRENCY}|€|\$)", re.I), "money_saved"),
    (re.compile(rf"\b(worth|values?|valued)\b[^.\n]{{0,20}}[€$]\s*\d", re.I), "money_saved"),
    # Return multiples. The negative lookahead keeps pixel dimensions (1200x628)
    # out of it; only a bare "12x" reads as a claim.
    (re.compile(r"\b\d+(?:[.,]\d+)?\s*x\b(?!\s*\d)", re.I), "roi_multiple"),
    (re.compile(r"\bpays? for itself\b", re.I), "roi_multiple"),
    (re.compile(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|twelve)\s+times\s+over\b", re.I), "roi_multiple"),
    (re.compile(r"\b(trusted by|used by|join)\s+\d", re.I), "customer_count"),
    (re.compile(r"\b\d+\s*(firms?|companies|customers|clients)\s+(use|trust)", re.I), "customer_count"),
    (re.compile(r"\d+\s*%", re.I), "percentage_claim"),
    # ROI-shaped claims. Added 2026-09-06 after Dovy confirmed the 9x / 400 EUR /
    # 40-day figures are a model, not a measurement. Before this, "9x ROI" would
    # have passed the gate unnoticed. A multiple ("9x"), a payback period, or a
    # money-saved figure all resolve to roi_model, which is UNVERIFIED and only
    # passes when the ad itself says it is a model or a worked example.
    (re.compile(r"\b\d+(?:\.\d+)?\s?x\b(?!\d)", re.I), "roi_model"),
    (re.compile(r"\bpayback\b|\bpays? (?:for )?itself\b|\breturn on investment\b|\bROI\b", re.I), "roi_model"),
    (re.compile(r"\b(?:saves?|saved|saving)\b[^.\n]{0,40}?(?:eur|usd|dkk|kr\.?|€|\$)\s?\d", re.I), "roi_model"),
    (re.compile(r"(?:eur|usd|dkk|kr\.?|€|\$)\s?\d[\d,.]*[^.\n]{0,40}?\b(?:saved|savings?)\b", re.I), "roi_model"),
)


@dataclass(frozen=True)
class ClaimVerdict:
    passed: bool
    failures: tuple[str, ...]


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))["claims"]


def _framed(text: str, entry: dict) -> bool:
    """True when the ad carries one of the entry's allowed framing phrases.

    Only entries that explicitly list `allowed_if_framed_as` can ever pass this
    way. An UNVERIFIED entry without that list stays blocked no matter what the
    ad says around it, so this does not loosen hours_saved, customer_count or
    percentage_claim.
    """
    phrases = entry.get("allowed_if_framed_as") or []
    low = text.lower()
    return any(ph.lower() in low for ph in phrases)


def check(text: str) -> ClaimVerdict:
    """Scan ad copy for measurable claims and verify each against evidence."""
    ev = _evidence()
    failures: list[str] = []

    for pattern, claim_id in _RISKY:
        match = pattern.search(text)
        if not match:
            continue
        entry = ev.get(claim_id)
        if entry is None:
            failures.append(
                f"{match.group(0)!r} asserts {claim_id!r}, absent from claims/evidence.json"
            )
        elif entry.get("status") != "verified":
            if _framed(text, entry):
                # Dovy's rule of 2026-09-06: a modelled figure may appear only
                # when the same ad says, in words, that it is a model or a
                # worked example. That framing phrase has to be in the ad
                # itself, not in a note, because the reader never sees notes.
                continue
            failures.append(f"{match.group(0)!r} -> {claim_id} UNVERIFIED. {entry.get('note','')}")

    return ClaimVerdict(not failures, tuple(failures))


# Matches a TypeScript/JS string literal in any of the three quote styles.
_TS_STRING = re.compile(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"|`((?:[^`\\]|\\.)*)`", re.S)


def check_landing(content_dir: Path) -> dict[str, ClaimVerdict]:
    """Gate the landing page's copy, not only the ad's.

    To a reader - and to an advertising regulator - the ad and the page behind
    the click are one unit. Gating only the ad leaves every measurable claim on
    the other side of the click unexamined, which is where this funnel's actual
    numbers live.

    The literals are joined with a space rather than a newline on purpose. The
    page assembles its claims from fragments: the amount sits in one field
    ('430'), the unit in a second ('\u00a0USD') and the verb in a third ('saved per
    month, for each person'). A per-literal scan sees three innocent strings and
    no claim at all. Joining them back restores what the reader is actually
    shown. It can also glue two unrelated neighbours into a false positive -
    which is the right way round for a gate, because the cost is a human
    glancing at a line.
    """
    out: dict[str, ClaimVerdict] = {}
    for path in sorted(content_dir.glob("*.ts")):
        if path.stem in {"index", "types"}:
            continue
        src = path.read_text(encoding="utf-8")
        literals = [
            _unescape(next(g for g in m.groups() if g is not None))
            for m in _TS_STRING.finditer(src)
        ]
        out[path.name] = check(" ".join(literals))
    return out


_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\(.)")


def _unescape(s: str) -> str:
    """Resolve the escapes a .ts literal carries, without touching real UTF-8.

    Needed, not cosmetic. The landing page writes its non-breaking spaces as
    '\\u00a0', so the amount and its unit read as '430' and '\\u00a0USD' in source.
    Left encoded, no currency pattern can span them and the file passes for the
    wrong reason. codecs' 'unicode_escape' would fix that and mangle every
    Danish and Lithuanian character on the way past, because it decodes through
    latin-1.
    """

    def sub(m: re.Match[str]) -> str:
        if m.group(1):
            return chr(int(m.group(1), 16))
        return {"n": " ", "t": " ", "r": " "}.get(m.group(2), m.group(2))

    return _ESCAPE.sub(sub, s)


def check_creative(spec: dict) -> ClaimVerdict:
    """Check every rendered string in a creative spec."""
    blobs: list[str] = []

    def walk(node):
        if isinstance(node, str):
            blobs.append(node)
        elif isinstance(node, dict):
            for k, v in node.items():
                if not k.startswith("_") and k != "hypothesis":
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(spec)
    return check("\n".join(blobs))
