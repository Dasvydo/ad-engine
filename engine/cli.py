"""ad-engine CLI.

    python -m engine.cli audience <outreach.csv> --out queue/aud.csv
    python -m engine.cli check [<creative>]
    python -m engine.cli plan
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine.audience import from_outreach_csv
from engine.gate import check_creative, check_landing

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ad-engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audience", help="hash an outreach CSV into a Meta Custom Audience")
    a.add_argument("src", type=Path)
    a.add_argument("--out", type=Path, default=Path("queue/aud-outreach.csv"))

    c = sub.add_parser("check", help="run the claims gate over creative")
    c.add_argument("creative", nargs="?", type=Path)
    c.add_argument(
        "--landing",
        type=Path,
        metavar="DIR",
        help="also gate the landing page copy, e.g. ../campaign-site/src/content. "
        "The ad and the page behind the click are one unit; see docs/FUNNEL-HANDOFF.md",
    )

    sub.add_parser("plan", help="show audiences in priority order with blockers")

    args = p.parse_args(argv)

    if args.cmd == "audience":
        build = from_outreach_csv(args.src, args.out)
        print(f"{build.rows:,} rows -> {build.path}")
        if not build.usable:
            print(f"\nWARNING: {build.warning}")
            return 1
        return 0

    if args.cmd == "check":
        paths = [args.creative] if args.creative else sorted((ROOT / "creative").glob("*.json"))
        failed = False
        for path in paths:
            spec = json.loads(Path(path).read_text(encoding="utf-8"))
            verdict = check_creative(spec)
            print(("PASS  " if verdict.passed else "BLOCK "), Path(path).name)
            for f in verdict.failures:
                print("        ", f)
                failed = True

        if args.landing:
            if not args.landing.is_dir():
                print(f"\nlanding copy: {args.landing} is not a directory")
                return 1
            print(f"\nlanding copy ({args.landing})")
            print("  Advisory, and it does not change the exit code. The page is allowed to")
            print("  state a modelled figure because it carries the disclosure in the same")
            print("  eyeline. An ad carries none, so nothing below may be echoed into one.")
            print()
            for name, verdict in check_landing(args.landing).items():
                print(("  CLEAN " if verdict.passed else "  CLAIMS"), name)
                for f in verdict.failures:
                    print("          ", f)
            print("\n  Strings are joined across neighbours, so a hit can be two unrelated")
            print("  fields rather than one sentence. Look before rewriting.")

        return 1 if failed else 0

    # Sorted by priority, not by filename. With two audiences sharing priority 2
    # the alphabetical order read as if the ranking had been ignored.
    specs = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "audiences").glob("*.json")]
    for spec in sorted(specs, key=lambda s: (s["priority"], s["id"])):
        print(f"[{spec['priority']}] {spec['id']:20s} {spec['type']}")
        print(f"      {spec['rationale'][:100]}...")
        if spec.get("decision"):
            print(f"      DECIDED: {spec['decision'][:100]}...")
        if spec.get("blocked_on"):
            print(f"      BLOCKED: {spec['blocked_on'][:100]}...")
        if spec.get("warning"):
            print(f"      WARNING: {spec['warning'][:100]}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
