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
_RISKY = (
    (re.compile(r"\b\d+\s*(hours?|hrs?|timer|valand)", re.I), "hours_saved"),
    (re.compile(r"\bsaves?\s+\d", re.I), "hours_saved"),
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
