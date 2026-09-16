"""ad-engine CLI.

    python -m engine.cli audience <outreach.csv> --out queue/aud.csv
    python -m engine.cli check [<creative>]
    python -m engine.cli plan
    python -m engine.cli preflight [--audience <built.csv>]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import preflight
from engine.audience import from_outreach_csv
from engine.gate import check_creative

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ad-engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audience", help="hash an outreach CSV into a Meta Custom Audience")
    a.add_argument("src", type=Path)
    a.add_argument("--out", type=Path, default=Path("queue/aud-outreach.csv"))

    c = sub.add_parser("check", help="run the claims gate over creative")
    c.add_argument("creative", nargs="?", type=Path)

    sub.add_parser("plan", help="show audiences in priority order with blockers")

    f = sub.add_parser("preflight", help="run the runbook Part 6.3 launch checklist")
    f.add_argument("--audience", type=Path, help="a built audience CSV to size-check")

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
        return 1 if failed else 0

    if args.cmd == "preflight":
        checks = preflight.run(args.audience)
        width = max(len(c.name) for c in checks)
        print("preflight - docs/META-ADS-RUNBOOK.md Part 6.3\n")
        for c in checks:
            print(f"{c.status}  {c.name:<{width}}  {c.summary}")
            for line in c.detail:
                print(f"{'':6}{line}")
        tally = "  ".join(f"{s} {sum(c.status == s for c in checks)}" for s in ("PASS", "FAIL", "SKIP"))
        blocked = [c.name for c in checks if c.failed]
        print(f"\n{tally}")
        print(f"BLOCKED by: {', '.join(blocked)}" if blocked else "Mechanical checks clear.")
        print("Not checked here: the copy itself against evidence.json, frequency cap,")
        print("budget, pixel collecting, outreach actually running.")
        return 1 if blocked else 0

    for path in sorted((ROOT / "audiences").glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        print(f"[{spec['priority']}] {spec['id']:20s} {spec['type']}")
        print(f"      {spec['rationale'][:100]}...")
        if spec.get("blocked_on"):
            print(f"      BLOCKED: {spec['blocked_on'][:100]}...")
        if spec.get("warning"):
            print(f"      WARNING: {spec['warning'][:100]}...")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
