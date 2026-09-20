"""Launch preflight. Runs docs/META-ADS-RUNBOOK.md Part 6.3 as code.

Part 6.3 is the list a human skips at 23:00 on the night a campaign goes live.
The mechanical half of it is checkable, so it is checked here.

The other half is not, and this command does not pretend otherwise: whether the
copy reads true against claims/evidence.json, whether the frequency cap is set,
whether the pixel is actually collecting and whether outreach is actually
running are all human answers. They stay in the runbook.

Two checks fail today by design. The da/lt copy is still machine quality, and
site-retargeting is blocked on a pixel that is not installed. Both are real
blockers, so both are red.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from engine.audience import MIN_CUSTOM_AUDIENCE
from engine.gate import check_creative

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "NEEDS_NATIVE_PROOFREAD"  # exact marker for copy no native speaker has read
SYNC_SCRIPT = ROOT / "scripts" / "sync_skill_claims.py"

BUILD_HINT = "python -m engine.cli audience <outreach.csv> --out queue/aud-outreach.csv"


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # PASS | FAIL | SKIP
    summary: str
    detail: tuple[str, ...] = ()

    @property
    def failed(self) -> bool:
        return self.status == "FAIL"


def _specs(folder: str) -> list[tuple[Path, dict]]:
    paths = sorted((ROOT / folder).glob("*.json"))
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in paths]


def _language_fields(spec: dict) -> dict[str, dict[str, str]]:
    """Fields carrying per-language copy: a dict keyed by two-letter codes.

    Keyed on the shape rather than a field list, so a new copy field is covered
    the day it is added. `creative_source` and friends are not language maps.
    """
    return {
        key: value
        for key, value in spec.items()
        if isinstance(value, dict)
        and value
        and all(isinstance(k, str) and len(k) == 2 and k.islower() for k in value)
    }


def _load_sync_script() -> ModuleType:
    """Import scripts/sync_skill_claims.py by path - scripts/ is not a package.

    Loaded rather than reimplemented so the renderer has exactly one home.
    """
    spec = importlib.util.spec_from_file_location("sync_skill_claims", SYNC_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def claims_gate() -> Check:
    """1. Every creative passes engine/gate.py."""
    specs = _specs("creative")
    if not specs:
        return Check("claims gate", "FAIL", "creative/ has no specs to check")

    detail = [
        f"{path.name}: {failure}"
        for path, spec in specs
        for failure in check_creative(spec).failures
    ]
    if detail:
        return Check("claims gate", "FAIL", f"{len(detail)} unevidenced claim(s)", tuple(detail))
    return Check(
        "claims gate",
        "PASS",
        f"{len(specs)} spec(s) clean - five regexes, so read the copy yourself too",
    )


def native_copy() -> Check:
    """2. No declared language still carries the proofread placeholder."""
    specs = _specs("creative")
    width = max((len(path.name) for path, _ in specs), default=0)
    detail: list[str] = []
    stale = 0
    stale_en = 0
    declared = 0

    for path, spec in specs:
        by_lang: dict[str, list[str]] = {}
        for field, langs in _language_fields(spec).items():
            for lang, text in langs.items():
                declared += 1
                if text.strip() == PLACEHOLDER:
                    stale += 1
                    if lang == "en":
                        stale_en += 1
                    by_lang.setdefault(lang, []).append(field)
        for lang, fields in sorted(by_lang.items()):
            detail.append(f"{path.name:<{width}}  {lang}: {', '.join(sorted(fields))}")

    # English is the day-one language, so it alone decides the verdict.
    #
    # This used to FAIL on any placeholder in any language, which was right until
    # 2026-09-17. The founder then decided the outreach audience runs as ONE combined
    # ad set on the English page - the list clears Meta's 1,000 floor only with both
    # countries together, so it cannot be language-split (audiences/outreach-list.json,
    # `decision`). That put the Danish and Lithuanian proofread off the critical path:
    # it gates the four /da and /lt ad sets, which the pixel is holding anyway.
    # A red preflight that contradicts the recorded plan is a preflight people learn
    # to ignore, so it now reports the state without blocking on it.
    if stale_en:
        detail.append("English is the day-one language - this blocks every ad set")
        return Check(
            "native copy",
            "FAIL",
            f"{stale_en} English field(s) still {PLACEHOLDER}",
            tuple(detail),
        )
    if stale:
        detail.append("English is complete, so the day-one English ad sets can ship")
        detail.append("Gates only the /da and /lt ad sets - see docs/FUNNEL-HANDOFF.md")
        return Check(
            "native copy",
            "PASS",
            f"English clean; {stale} of {declared} non-English fields await a native read",
            tuple(detail),
        )
    return Check("native copy", "PASS", f"{declared} language fields, none placeholder")


def custom_audience(path: Path | None) -> Check:
    """3. The built audience file clears Meta's delivery floor."""
    if path is None:
        return Check(
            "custom audience",
            "SKIP",
            "no --audience given, nothing counted",
            (f"build it: {BUILD_HINT}", "then: python -m engine.cli preflight --audience <that file>"),
        )

    path = Path(path)
    if not path.exists():
        return Check(
            "custom audience",
            "FAIL",
            f"{path} does not exist",
            (f"build it: {BUILD_HINT}",),
        )

    rows = _data_rows(path)
    if rows < MIN_CUSTOM_AUDIENCE:
        return Check(
            "custom audience",
            "FAIL",
            f"{rows:,} rows, under Meta's {MIN_CUSTOM_AUDIENCE:,} floor",
            (
                "Meta accepts the upload and then under-delivers or refuses to serve",
                "widen the source list - do NOT split the audience to make a slice fit",
            ),
        )
    return Check(
        "custom audience",
        "PASS",
        f"{rows:,} rows, over Meta's {MIN_CUSTOM_AUDIENCE:,} floor",
        ("upload it whole: both countries, all three verticals, one ad set",),
    )


def audience_blockers() -> Check:
    """4. Any audience spec carrying blocked_on is a launch blocker.

    site-retargeting fails here until the pixel is live on doviloop.dev, and it
    keeps failing for as long as the pixel has nothing in it. That is the
    correct reading, not a bug in this check.
    """
    blocked = [(path, spec) for path, spec in _specs("audiences") if spec.get("blocked_on")]
    if blocked:
        return Check(
            "audience blockers",
            "FAIL",
            f"{len(blocked)} of {len(_specs('audiences'))} audience(s) blocked",
            tuple(f"{spec['id']}: {spec['blocked_on'][:100]}..." for _, spec in blocked),
        )
    return Check("audience blockers", "PASS", "no audience carries blocked_on")


def skill_claims_sync() -> Check:
    """5. The skill's generated claims copy still matches claims/evidence.json."""
    sync = _load_sync_script()
    target = sync.TARGET.relative_to(ROOT)
    fix = ("run: python scripts/sync_skill_claims.py",)

    if not sync.TARGET.exists():
        return Check("skill claims", "FAIL", f"{target} is missing", fix)
    if sync.TARGET.read_text(encoding="utf-8") != sync.render():
        return Check("skill claims", "FAIL", f"{target} is stale", fix)
    return Check("skill claims", "PASS", f"{target} matches evidence.json")


def _data_rows(path: Path) -> int:
    """Count people in a built audience file. Line 1 is the header Meta wants."""
    with path.open(newline="", encoding="utf-8") as fh:
        return sum(
            1
            for i, row in enumerate(csv.reader(fh))
            if i and any(cell.strip() for cell in row)
        )


def run(audience: Path | None = None) -> tuple[Check, ...]:
    """The whole checklist, in the order Part 6.3 lists it."""
    return (
        claims_gate(),
        native_copy(),
        custom_audience(audience),
        audience_blockers(),
        skill_claims_sync(),
    )
