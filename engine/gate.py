"""Claims gate. An ad ships only if every factual claim it makes is evidenced.

Mirrors reel-engine's claims discipline. It exists because DoviLoop has no
customers, no case studies and no measured outcomes yet - precisely the state in
which unverifiable claims get written, and precisely the exposure an investor
flagged: a public measurable promise with nothing behind it.

Design notes, so the next person extending this does it the right way:

* The gate is deliberately biased toward false positives. A blocked line that
  was actually fine costs one rewrite. A claim that slips through costs a
  liability, in two jurisdictions, at a company with no liability cap and no
  insurance. When a pattern is arguable, it fires.
* The way to unblock a claim is to add or update an entry in
  claims/evidence.json - state the evidence, list the exact approved wording -
  and flip its status to "verified". It is NOT to weaken a pattern here. A
  pattern edit unblocks every future ad silently; an evidence entry is a
  reviewable record of a decision someone made.
* Detection is weakest in Danish and Lithuanian. There are tokens for both
  below, but they are a backstop, not coverage. A native reviewer is the last
  line for da/lt copy - see the NEEDS_NATIVE_PROOFREAD fields in creative/.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "claims" / "evidence.json"

# Numbers written as words slip past \d, and "save ten hours" is the same claim
# as "save 10 hours".
_NUM = (
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"fifteen|twenty|thirty|forty|fifty|hundreds?|thousands?|dozens?|several|a\s+few)"
)
# Time units in the three languages the creative ships in.
_TIME = r"(?:hours?|hrs?|days?|minutes?|mins?|weeks?|timer|dage|minutter|valand\w*|dien\w*|minu[cč]\w*)"
# The subset a time saving is quoted in; see duration-figure below.
_SHORT_TIME = r"(?:hours?|hrs?|minutes?|mins?|timer|minutter|valand\w*|minu[cč]\w*)"

# (rule name, pattern, claim id it asserts). Every match must resolve to a
# verified entry in claims/evidence.json or the ad does not ship.
_RISKY: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # -- time saved -------------------------------------------------------
    # Bare figure + unit, restricted to the units a time saving is actually quoted
    # in. Wider units (days, weeks, months) are legitimate scene-setting - the
    # brief's own seasonal-surge hook is "you cannot hire for eight weeks" - so
    # they are caught by the saving-verb and per-period rules below instead of on
    # sight. A gate that blocks the brief's recommended hook gets disabled.
    ("duration-figure", re.compile(rf"\b{_NUM}\s*{_SHORT_TIME}\b", re.I), "hours_saved"),
    ("saves-quantity", re.compile(rf"\b(saves?|saved|saving)\s+(?:you\s+|your\s+team\s+)?{_NUM}", re.I), "hours_saved"),
    (
        "time-reclaimed",
        re.compile(
            rf"\b(save|saves|saved|saving|cut|cuts|cutting|free\s+up|frees\s+up|win|gain|gains|reclaim|reclaims|get)\s+"
            rf"(?:\w+\s+){{0,2}}{_TIME}\b",
            re.I,
        ),
        "hours_saved",
    ),
    ("time-back", re.compile(rf"\b{_TIME}\s+back\b|\b{_TIME}\s+(?:a|per|every)\s+(?:day|week|month|year)\b", re.I), "hours_saved"),
    ("half-a-day", re.compile(r"\bhalf\s+(?:a\s+|the\s+)?(?:day|week|morning|afternoon)\b", re.I), "hours_saved"),

    # -- ratios: a time-saving claim expressed without a duration ----------
    ("multiplier", re.compile(rf"\b(?:\d+\s*x|{_NUM}\s*(?:x|times)\s+(?:faster|quicker|slower|more|less|fewer|as\s+many|as\s+much|the))\b", re.I), "multiplier_claim"),
    ("doubling", re.compile(r"\b(?:twice\s+as|double\s+the|triple\s+the|halve\s+(?:your|the)|half\s+the\s+(?:time|work|effort|cost))\b", re.I), "multiplier_claim"),

    # -- counting customers ------------------------------------------------
    ("joined-count", re.compile(rf"\b(trusted\s+by|used\s+by|loved\s+by|chosen\s+by|join|joined\s+by)\s+{_NUM}", re.I), "customer_count"),
    ("firms-using", re.compile(rf"\b{_NUM}\s*(firms?|companies|customers|clients|teams|accountants|brokers|users)\s+(use|uses|trust|trusts|rely|chose|choose)", re.I), "customer_count"),
    ("quantified-cohort", re.compile(r"\b(hundreds|thousands|dozens|scores)\s+of\s+(firms?|companies|customers|clients|teams|accountants|brokers|users|businesses)\b", re.I), "customer_count"),

    # -- social proof with no number in it ---------------------------------
    ("proof-phrase", re.compile(r"\b(trusted|used|loved|chosen|preferred)\s+by\s+(?!you\b)\w+", re.I), "social_proof"),
    ("voice-of-customer", re.compile(r"\b(our\s+(customers|clients|users)\s+(say|report|tell|love)|case\s+stud(y|ies)|testimonial|customer\s+story|success\s+story)\b", re.I), "social_proof"),
    ("star-rating", re.compile(r"\b\d(?:[.,]\d)?\s*(?:stars?\b|/\s*5\b|out\s+of\s+5\b)|\brated\s+\d", re.I), "social_proof"),

    # -- percentages -------------------------------------------------------
    ("percentage", re.compile(r"\d+\s*%|\b\d+\s*(?:percent|procent|proc\.|procent[uų])\b", re.I), "percentage_claim"),

    # -- price -------------------------------------------------------------
    ("currency-figure", re.compile(r"[$€£]\s?\d|\b\d[\d.,]*\s*(?:kr\.?|DKK|EUR|USD|eur[uų]?)\b", re.I), "pricing_claim"),
    ("rate-card", re.compile(r"\b(?:per|a|/)\s*(?:seat|user|month|mo\b|year)\b.{0,20}\d|\d.{0,20}\b(?:per|/)\s*(?:seat|user|month|mo\b)\b", re.I), "pricing_claim"),
    ("free-offer", re.compile(r"\b(free\s+(?:trial|forever|for\s+life|of\s+charge)|no\s+(?:cost|charge)|gratis|nemokam\w*)\b", re.I), "pricing_claim"),

    # -- market position ---------------------------------------------------
    ("superlative", re.compile(r"\b(?:the\s+)?(?:#\s*1|no\.?\s*1|number\s+one|best|leading|market[-\s]leading|industry[-\s]leading)\b(?!\s+(?:practice|guess))", re.I), "market_position"),
    ("first-or-only", re.compile(r"\b(?:world'?s|europe'?s|denmark'?s|lithuania'?s)\s+(?:first|only|best|leading)\b|\bthe\s+only\s+\w+\s+(?:that|which|to|for)\b", re.I), "market_position"),

    # -- comparison against others -----------------------------------------
    ("comparative", re.compile(r"\b(?:faster|quicker|better|cheaper|smarter|more\s+accurate|more\s+reliable)\s+than\b|\bunlike\s+(?:other|most|every)\b|\boutperform\w*\b", re.I), "comparative_claim"),

    # -- accuracy ----------------------------------------------------------
    ("accuracy", re.compile(r"\b(?:error[-\s]free|mistake[-\s]free|flawless|never\s+(?:wrong|makes?\s+a?\s*mistakes?|gets?\s+it\s+wrong)|always\s+(?:right|correct|accurate)|perfect(?:ly)?\s+(?:accurate|written|drafted)|zero\s+(?:errors?|mistakes?))\b", re.I), "accuracy_claim"),

    # -- speed of setup or response ----------------------------------------
    ("instant", re.compile(r"\b(?:instant(?:ly|aneous)?|in\s+seconds|within\s+seconds|in\s+an?\s+instant|overnight)\b", re.I), "speed_claim"),
    ("setup-time", re.compile(rf"\b(?:set\s*up|setup|installed?|live|running|onboarded?|started)\s+(?:in|within)\s+{_NUM}?\s*{_TIME}?\b", re.I), "speed_claim"),

    # -- certification and compliance --------------------------------------
    ("certification", re.compile(r"\b(?:SOC\s*2|ISO\s*27001|ISO\s*9001|HIPAA|certified|accredited|audited|pen[-\s]tested)\b", re.I), "certification_claim"),
    ("gdpr-compliance", re.compile(r"\b(?:GDPR|DSGVO|BDSG)[-\s]?(?:compliant|compliance|certified)\b|\bfully\s+compliant\b", re.I), "certification_claim"),

    # -- guarantees --------------------------------------------------------
    ("guarantee", re.compile(r"\b(?:guarantee[ds]?|guaranteed|risk[-\s]free|money[-\s]back|or\s+(?:it'?s|your\s+money)\s+free|garant\w*)\b", re.I), "guarantee_claim"),
)


@dataclass(frozen=True)
class ClaimVerdict:
    passed: bool
    failures: tuple[str, ...]


def _evidence() -> dict:
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))["claims"]


def rules() -> tuple[tuple[str, str], ...]:
    """(rule name, claim id) for every pattern, so the ruleset is inspectable."""
    return tuple((name, claim_id) for name, _, claim_id in _RISKY)


def check(text: str, where: str = "") -> ClaimVerdict:
    """Scan ad copy for measurable claims and verify each against evidence.

    Reports every distinct offending span, not just the first - a rewrite that
    fixes one match and reships is how the second one gets through.
    """
    ev = _evidence()
    failures: list[str] = []
    prefix = f"{where}: " if where else ""

    for name, pattern, claim_id in _RISKY:
        seen: set[str] = set()
        for match in pattern.finditer(text):
            span = " ".join(match.group(0).split())
            key = span.lower()
            if key in seen:
                continue
            seen.add(key)

            entry = ev.get(claim_id)
            if entry is None:
                failures.append(
                    f"{prefix}{span!r} [{name}] asserts {claim_id!r}, absent from claims/evidence.json"
                )
            elif entry.get("status") != "verified":
                note = entry.get("note", "")
                failures.append(f"{prefix}{span!r} [{name}] -> {claim_id} UNVERIFIED. {note}")

    return ClaimVerdict(not failures, tuple(failures))


def check_creative(spec: dict) -> ClaimVerdict:
    """Check every rendered string in a creative spec, field by field.

    Per-field rather than over one concatenated blob, so a failure names the
    field an editor has to open. Keys starting with "_" and the "hypothesis"
    field are internal reasoning, not copy, and are not scanned.
    """
    fields: list[tuple[str, str]] = []

    def walk(node, path: str) -> None:
        if isinstance(node, str):
            fields.append((path or "<root>", node))
        elif isinstance(node, dict):
            for k, v in node.items():
                if k.startswith("_") or k == "hypothesis":
                    continue
                walk(v, f"{path}.{k}" if path else k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(spec, "")

    failures: list[str] = []
    for path, text in fields:
        failures.extend(check(text, where=path).failures)
    return ClaimVerdict(not failures, tuple(failures))
