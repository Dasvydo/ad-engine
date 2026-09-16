"""Regenerate the skill's claims reference from claims/evidence.json.

The skill has to work in Claude Desktop, where there is no repo to read, so it
carries its own copy of the claims list. Two copies means one can go stale.
Run this whenever claims/evidence.json changes:

    python scripts/sync_skill_claims.py          # write
    python scripts/sync_skill_claims.py --check  # CI-friendly, non-zero if stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "claims" / "evidence.json"
TARGET = ROOT / ".claude" / "skills" / "meta-ads" / "references" / "claims.md"

# Copy that passes engine/gate.py's regexes but is still an unverifiable claim.
# Measured 2026-09-16 by running engine.gate.check over each.
GATE_BLIND_SPOTS = [
    "Save ten hours a month",
    "Cut your reply time in half",
    "Most firms see faster turnaround",
    "Save hours every week",
]


def render() -> str:
    claims = json.loads(EVIDENCE.read_text(encoding="utf-8"))["claims"]
    verified = {k: v for k, v in claims.items() if v.get("status") == "verified"}
    blocked = {k: v for k, v in claims.items() if v.get("status") != "verified"}

    out = [
        "# Claims — what DoviLoop may and may not say in an ad",
        "",
        "> GENERATED from `claims/evidence.json` by `scripts/sync_skill_claims.py`.",
        "> Do not hand-edit. Re-run the script after changing evidence.json.",
        "",
        "## The rule",
        "",
        "Every factual assertion in ad copy must resolve to a `verified` entry below.",
        "If it does not, it does not ship. There is no 'probably fine'.",
        "",
        f"## ✅ Verified — safe to claim ({len(verified)})",
        "",
    ]
    for key, entry in verified.items():
        out.append(f"### `{key}`")
        out.append(f"{entry['evidence']}")
        out.append("")
        out.append("Safe phrasings:")
        out += [f"- {p}" for p in entry.get("safe_phrasings", [])]
        out.append("")

    out += [f"## ⛔ Blocked — never claim ({len(blocked)})", ""]
    for key, entry in blocked.items():
        out.append(f"### `{key}`")
        out.append(f"**Why blocked:** {entry['evidence']}")
        if entry.get("note"):
            out.append("")
            out.append(f"**Note:** {entry['note']}")
        out.append("")

    out += [
        "## ⚠️ The gate does not catch everything",
        "",
        "`engine/gate.py` is five regexes looking for digits. These all pass it",
        "clean and are all still unverifiable claims. Catching them is *your* job,",
        "not the script's:",
        "",
    ]
    out += [f"- {s!r}" for s in GATE_BLIND_SPOTS]
    out += [
        "",
        "The pattern: the gate hunts for a **digit**. A claim spelled out in words,",
        "or phrased as a vague comparative, is invisible to it. Reason about the",
        "*claim*, not the digit.",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"STALE: {TARGET.relative_to(ROOT)} does not match evidence.json")
            return 1
        print("ok: skill claims reference is in sync")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
