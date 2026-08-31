"""Validate campaign/structure.json against the rest of the repo.

The point of declaring the account structure as JSON is that it can be checked.
A structure file that drifts from the audiences, the creative and the claims
gate is worse than no structure file, because it looks authoritative.

What this refuses to let through:

* an ad set pointing at an audience that does not exist, or at the wrong
  priority for it;
* an ad pointing at creative that does not exist;
* an ad whose creative fails the claims gate;
* an ad in a language whose copy is still NEEDS_NATIVE_PROOFREAD and which is
  not marked blocked - drafted Danish and Lithuanian are not shippable, and the
  gate reads both poorly, so this is the only thing standing between a draft
  translation and a live ad;
* an ad set whose audience is blocked upstream but whose launch gate does not
  say so;
* anything not PAUSED. Nothing in this repo launches itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from engine.gate import check_creative

ROOT = Path(__file__).resolve().parent.parent
STRUCTURE = ROOT / "campaign" / "structure.json"

PLACEHOLDER = "NEEDS_NATIVE_PROOFREAD"
LOCALISED_FIELDS = ("primary_text", "headline", "description")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load(directory: str) -> dict[str, dict]:
    return {
        spec["id"]: spec
        for spec in (
            json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / directory).glob("*.json"))
        )
    }


def load_structure(path: Path | None = None) -> dict:
    return json.loads((path or STRUCTURE).read_text(encoding="utf-8"))


def iter_adsets(structure: dict):
    for campaign in structure.get("campaigns", []):
        for adset in campaign.get("adsets", []):
            yield campaign, adset


def validate(structure: dict | None = None) -> Report:
    structure = structure if structure is not None else load_structure()
    audiences = _load("audiences")
    creatives = _load("creative")
    rep = Report()

    seen_ids: set[str] = set()

    def unique(kind: str, ident: str) -> None:
        if ident in seen_ids:
            rep.errors.append(f"duplicate {kind} id {ident!r}")
        seen_ids.add(ident)

    launch_daily = 0.0
    all_daily = 0.0

    for campaign in structure.get("campaigns", []):
        unique("campaign", campaign["id"])

    for campaign, adset in iter_adsets(structure):
        unique("adset", adset["id"])
        where = f"{campaign['id']}/{adset['id']}"

        if campaign.get("status") != "PAUSED":
            rep.errors.append(f"{campaign['id']}: status is {campaign.get('status')!r}, must be PAUSED")
        if adset.get("status") != "PAUSED":
            rep.errors.append(f"{where}: status is {adset.get('status')!r}, must be PAUSED")

        aud = audiences.get(adset.get("audience_ref", ""))
        if aud is None:
            rep.errors.append(f"{where}: audience_ref {adset.get('audience_ref')!r} has no audiences/*.json")
        else:
            if aud.get("priority") != adset.get("priority"):
                rep.errors.append(
                    f"{where}: priority {adset.get('priority')} disagrees with "
                    f"audiences/{aud['id']}.json ({aud.get('priority')})"
                )
            blockers = adset.get("launch_gate", {}).get("blockers", [])
            if aud.get("blocked_on") and not blockers:
                rep.errors.append(
                    f"{where}: audience {aud['id']} is blocked upstream "
                    f"({aud['blocked_on'][:60]}...) but launch_gate lists no blockers"
                )
            if aud.get("warning") and not adset.get("warning"):
                rep.warnings.append(f"{where}: audience {aud['id']} carries a warning the ad set does not repeat")

        budget = float(adset.get("daily_budget_eur", 0))
        all_daily += budget
        if not adset.get("launch_gate", {}).get("blockers"):
            launch_daily += budget

        adset_ad_ids = {ad["id"] for ad in adset.get("ads", [])}
        for ad in adset.get("ads", []):
            unique("ad", ad["id"])
            ad_where = f"{where}/{ad['id']}"

            if ad.get("status") != "PAUSED":
                rep.errors.append(f"{ad_where}: status is {ad.get('status')!r}, must be PAUSED")

            replaces = ad.get("replaces")
            if replaces and replaces not in adset_ad_ids:
                rep.errors.append(f"{ad_where}: replaces {replaces!r}, which is not an ad in this ad set")

            spec = creatives.get(ad.get("creative_ref", ""))
            if spec is None:
                rep.errors.append(f"{ad_where}: creative_ref {ad.get('creative_ref')!r} has no creative/*.json")
                continue

            verdict = check_creative(spec)
            if not verdict.passed:
                for failure in verdict.failures:
                    rep.errors.append(f"{ad_where}: CLAIMS GATE creative/{spec['id']}.json {failure}")

            locale = ad.get("locale", "")
            unready = [
                f for f in LOCALISED_FIELDS
                if isinstance(spec.get(f), dict) and spec[f].get(locale, "").strip() == PLACEHOLDER
            ]
            if unready and not ad.get("blockers"):
                rep.errors.append(
                    f"{ad_where}: locale {locale!r} copy is still {PLACEHOLDER} in "
                    f"creative/{spec['id']}.json ({', '.join(unready)}) but the ad lists no blockers. "
                    f"Drafted is not native-checked."
                )
            if not unready and locale not in ("en",) and ad.get("blockers"):
                rep.warnings.append(
                    f"{ad_where}: copy is no longer {PLACEHOLDER} but the ad still lists blockers - "
                    f"clear them if a native reviewer has signed off"
                )

    summary = structure.get("budget_summary", {})
    for key, actual in (("at_launch_daily_eur", launch_daily), ("all_four_daily_eur", all_daily)):
        declared = summary.get(key)
        if declared is not None and abs(float(declared) - actual) > 1e-9:
            rep.errors.append(f"budget_summary.{key} says {declared} but the ad sets total {actual:g}")
    monthly = summary.get("monthly_at_launch_eur")
    if monthly is not None and abs(float(monthly) - launch_daily * 30) > 1e-9:
        rep.errors.append(
            f"budget_summary.monthly_at_launch_eur says {monthly} but "
            f"{launch_daily:g}/day over 30 days is {launch_daily * 30:g}"
        )

    return rep


def render(structure: dict | None = None) -> str:
    """The structure as a tree, blockers first-class."""
    structure = structure if structure is not None else load_structure()
    out: list[str] = []
    for campaign in structure.get("campaigns", []):
        out.append(f"{campaign['id']}  [{campaign['status']}]  {campaign['objective']}")
        out.append(f"    {campaign['name']}")
        for adset in campaign.get("adsets", []):
            blockers = adset.get("launch_gate", {}).get("blockers", [])
            flag = "BLOCKED" if blockers else "ready"
            out.append(
                f"  [{adset['priority']}] {adset['id']:24s} EUR {adset.get('daily_budget_eur', 0)}/day"
                f"  {adset['optimization_goal']:12s} {flag}"
            )
            for b in blockers:
                out.append(f"        BLOCKED: {b}")
            for ad in adset.get("ads", []):
                mark = "  x" if ad.get("blockers") else "  ."
                out.append(f"      {mark} {ad['id']:28s} {ad['creative_ref']:9s} {ad['locale']:3s} {ad['format']}")
                for b in ad.get("blockers", []):
                    out.append(f"            {b}")
        out.append("")
    return "\n".join(out)
