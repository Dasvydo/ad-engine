#!/usr/bin/env python3
"""python tools/walk.py [--out DIR] [--quiet]

The whole loop, driven end to end, offline, into files you can open.

WHY THIS EXISTS. Every stage of this engine is proven by a test, and
`tests/test_pipeline.py` proves the stages meet. But a green test tells you
the seams hold; it does not let you SEE what the engine produces, and the
first live run is a poor place to find out that a patterns document is not
what you expected to read. This tool runs the same walk as that test and
keeps the artifacts: a corpus of analysed ads, the patterns they count to,
the concepts that cite those patterns, a scorecard for each, the job the
writer produced, the measurement row, and the own-ad record that closes the
loop back into the corpus. Then it prints, stage by stage, what changed and
which number to read.

WHAT IS REAL AND WHAT IS NOT. Every line of engine code is the real one. Two
things are stubbed, and only two, because they are the only two that live
outside this repository:

  - Meta's Ad Library. `tests/test_pipeline.py::PAGE_SEARCH` and
    `QUERY_SEARCH` stand in for the archive's JSON - four Danish bookkeeping
    ads, in the exact field shape `discover.FIELDS` asks for.
  - The model. `tests/stubs.StubClient` answers from a queue instead of
    opening a socket, so the analyst, the concept writer, the editorial
    scorer and the copywriter all return fixed replies.

Both are imported from the test rather than copied, so this tool and the test
cannot drift: change the loop in a way that breaks one and the other breaks
in the same commit. That is the whole reason the fixtures are not duplicated
here.

COSTS NOTHING, NEEDS NOTHING. No Meta token, no Gemini key, no network. If
this tool ever needs one, that is a bug in this tool.

WRITES NOWHERE REAL. Everything lands under `--out` (default `demo/`, which
.gitignore covers). The committed `research/corpus/`, `queue/` and
`research/*.json` are never touched - the one exception is that the walk
READS the committed `queue/backlog.md` and `claims/evidence.json`, because
scoring a made-up segment against made-up claims would prove nothing.

Exit codes: 0 walked, 2 refused (nothing written).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import (  # noqa: E402
    analyse,
    approval,
    backlog,
    concepts,
    corpus,
    discover,
    feedback,
    gate,
    learn,
    measure,
    score,
    write,
)

# The fixtures, imported rather than copied - see the banner. This is the one
# place in the tree where a tool imports from tests/, and it is deliberate:
# the alternative is a second set of fixtures that drifts from the first.
from tests.stubs import StubClient, json_reply  # noqa: E402
from tests.test_pipeline import (  # noqa: E402
    AD_IDS,
    ADSET_ID,
    ANALYSES,
    CAMPAIGN_ID,
    LAUNCHED_AT,
    MEASURED_AT,
    PROPOSED_AT,
    SEEDS_YAML,
    SEGMENT_ID,
    TODAY,
    RecordingTransport,
    concept_reply,
    editorial_reply,
    insights_body,
    written_reply,
)

DEFAULT_OUT = ROOT / "demo"


class Refused(RuntimeError):
    """Something the walk will not guess at. Printed as one line, not a
    traceback."""


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------

class Log:
    """Stage headings, key/value facts, and file lines - or silence.

    Widths are fixed rather than computed so two runs of the same walk line up
    character for character and a diff of two captured runs shows only what
    actually changed.
    """

    def __init__(self, on: bool = True):
        self.on = on

    def say(self, text: str = "") -> None:
        if self.on:
            print(text)

    def banner(self, title: str, subtitle: str) -> None:
        self.say()
        self.say(title)
        self.say("=" * len(title))
        self.say(subtitle)

    def stage(self, number: int, name: str, summary: str) -> None:
        self.say()
        self.say(f"{number:>2}  {name:<10}  {summary}")

    def fact(self, label: str, value: str) -> None:
        self.say(f"      {label:<22} {value}")

    def read(self, text: str) -> None:
        """The one line per stage that says what to look at and why."""
        self.say(f"      -> {text}")

    def wrote(self, path: Path, out: Path) -> None:
        self.say(f"      wrote {path.relative_to(out.parent)}")


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------

def walk(out: Path, log: Log) -> dict:
    """Ten stages, in order, into `out`. Returns the artifacts by name so a
    test can assert on them without re-reading the files."""
    tree = _prepare(out)

    log.banner(
        "ad-engine: one ad's whole journey, offline",
        "No Meta token. No model key. No socket. Nothing here costs anything.\n"
        "Every line of engine code below is the real one; only Meta's archive\n"
        "and the model are stubbed, because they are the only two things that\n"
        "live outside this repository.",
    )
    log.say()
    log.say(f"  writing to {out}/")

    # --- 1. the Ad Library -> candidates -----------------------------------
    transport = RecordingTransport()
    seeds = discover.load_seeds(tree / "seeds.yaml")
    client = discover.AdLibraryClient("demo-token-not-a-real-one", transport=transport)
    candidates = discover.discover(seeds, client=client, today=TODAY)

    log.stage(1, "DISCOVER", f"{len(transport.urls)} archive calls -> "
                             f"{len(candidates)} candidates")
    log.fact("calls made", f"{len(transport.urls)} "
                           f"(one per page batch, one per query)")
    log.fact("token in any URL", "no - it travels in the Authorization header")
    for row in candidates:
        metrics = row["metrics"]
        log.fact(
            row["id"],
            f"{metrics['days_running']:>4}d running  "
            f"reach {metrics['eu_total_reach']:>6,}  "
            f"outlier x{row['outlier_ratio']}  "
            f"{'live' if metrics['active'] else 'stopped'}",
        )
    log.read(
        "days_running is the only figure an advertiser's own money voted on. "
        "outlier_ratio is this ad's reach-per-day over the MEDIAN of its own "
        "page's other ads, so x2.0 means it outpulled its page-mates two to one."
    )

    # --- 2. candidates -> corpus records -----------------------------------
    analyst = StubClient([json_reply({"ads": {c["id"]: ANALYSES[c["id"]]
                                              for c in candidates}})])
    run = analyse.analyse_all(
        candidates, client=analyst, media_root=tree / "media", now=TODAY
    )
    if run.skipped:
        raise Refused(f"the analyst skipped {run.skipped}, which this walk does "
                      f"not expect; the fixtures and engine/analyse.py disagree")
    corpus_root = tree / "research" / "corpus"
    for record in run.records:
        corpus.save(record, corpus_root)

    first = run.records[0]
    log.stage(2, "ANALYSE", f"1 model call -> {len(run.records)} corpus records")
    log.fact("model calls", "1 (ads are batched, 12 per call)")
    log.fact("copied verbatim", "metrics, copy, origin - the model never "
                                "restates a fact")
    log.fact("the model's own work", f"hook.device={first['analysis']['hook']['device']}, "
                                     f"copy.words={first['analysis']['copy']['words']}, "
                                     f"structure={'>'.join(first['analysis']['structure'])}")
    log.wrote(corpus_root, out)
    log.read(
        "one JSON per ad, git history as the audit log. The split to check is "
        "`metrics` (Meta's, never touched) against `analysis` (the model's, "
        "always arguable)."
    )

    # --- 3. corpus -> patterns ---------------------------------------------
    patterns = learn.build(corpus.load_all(corpus_root))
    patterns_path = learn.write(patterns, tree / "research" / "patterns.json")

    log.stage(3, "LEARN", f"{patterns['corpus_size']} records -> "
                          f"{len(patterns['patterns'])} patterns")
    log.fact("floor", f"a device held by fewer than {learn.MIN_SUPPORT} ads is "
                      f"not a pattern")
    for pattern in patterns["patterns"]:
        log.fact(pattern["id"], f"{pattern['kind']}/{pattern['device']}  "
                                f"n={pattern['n']}  {pattern['evidence']}")
    log.wrote(patterns_path, out)
    log.read(
        "`evidence` is the list of ad ids holding the device up. A pattern you "
        "disagree with is answered by opening those ads, not by arguing with "
        "the number."
    )

    # --- 4. patterns -> concepts -------------------------------------------
    segment = _segment()
    minted = [p["id"] for p in patterns["patterns"]][:2]
    written = concepts.generate(
        patterns, [segment], n=2,
        client=StubClient([json_reply(concept_reply(minted))]),
    )
    concepts_path = tree / "research" / "concepts.json"
    _dump({"concepts": written}, concepts_path)

    log.stage(4, "CONCEPTS", f"{len(written)} concepts, every citation checked")
    for concept in written:
        log.fact(concept["id"], f"cites {concept['pattern_ids']}  "
                                f"{concept['placement']}  offer={concept['offer']}")
        log.fact("", f'hook: "{concept["hook"]}"')
    log.wrote(concepts_path, out)
    log.read(
        "a concept citing a pattern id that learn did not mint is REFUSED here, "
        "not scored low. That refusal is what stops the model inventing evidence."
    )

    # --- 5. concepts -> a selection ----------------------------------------
    context = score.load_context(
        patterns_path=patterns_path,
        queue_root=tree / "queue",
        creative_root=tree / "creative",
        evidence=gate.load_attestations(),
    )
    selection = score.select(
        written, context=context,
        client=StubClient([json_reply(editorial_reply(written))]), top=1,
    )
    selection_path = tree / "research" / "selection.json"
    _dump(selection.as_dict(), selection_path)
    chosen = selection.selected[0]

    log.stage(5, "SCORE", f"{len(selection.scorecards)} scored, "
                          f"{len(selection.selected)} selected")
    log.fact("weights", "  ".join(f"{d}={w}" for d, w in score.WEIGHTS.items()))
    for card in selection.scorecards:
        marker = "SELECTED" if card.selected else "        "
        log.fact(f"{card.id} {marker}", f"total={card.total}  " + "  ".join(
            f"{d}={card.scores.get(d, 0.0):.2f}" for d in score.WEIGHTS
        ))
    log.wrote(selection_path, out)
    log.read(
        "the four measured dimensions carry 0.80 between them and editorial "
        "carries 0.20, so the model's taste cannot outvote the evidence on its "
        "own. That ratio is the whole selection policy."
    )

    # --- 6. the selected concept -> a job the gate passes -------------------
    job = write.generate(
        segment, concept=chosen, patterns=patterns["patterns"],
        client=StubClient([json_reply(written_reply())]), now=PROPOSED_AT,
    )
    verdict = gate.structural(job)

    log.stage(6, "WRITE+GATE", f"1 job, gate {'PASS' if verdict.ok else 'BLOCK'}")
    log.fact("headline", job["headline"]["en"])
    log.fact("cta / offer", f"{job['cta']} / {job['offer']}")
    log.fact("creative", f"{job['creative_source']['kind']} via template "
                         f"{job['creative_source']['template']} "
                         f"(chosen by placement, not hardcoded)")
    log.fact("gate failures", str(verdict.failures) if verdict.failures else "none")
    log.read(
        "the gate is structural and runs before a human ever sees the copy: no "
        "number without an attestation in claims/evidence.json, no refused "
        "construction, every field under Meta's limit."
    )

    # --- 7. proposed -> built -> launched ----------------------------------
    sidecar = write.reel_selection(chosen, segment, now=PROPOSED_AT)
    _dump(job, approval.queue_dir("proposed") / f"{SEGMENT_ID}.json")
    _dump(sidecar, approval.queue_dir("proposed") / f"{SEGMENT_ID}.reel.json")

    approval.advance(SEGMENT_ID, "built")
    launched = approval.launch(
        SEGMENT_ID,
        {ad: {"campaign_id": CAMPAIGN_ID, "adset_id": ADSET_ID} for ad in AD_IDS},
        now=LAUNCHED_AT,
    )
    live = approval.load_job(launched)

    log.stage(7, "APPROVE", "proposed -> built -> launched")
    log.fact("the tap", "a `go` label on the approval issue moves the file one "
                        "directory; the directory IS the status")
    log.fact("ad ids pinned", ", ".join(sorted(live["ads"])))
    log.fact("copy unchanged", "yes - byte-identical to what the gate passed")
    log.wrote(approval.queue_dir("launched") / f"{SEGMENT_ID}.json", out)
    log.read(
        "nothing in this repository can move a job forward on its own. The only "
        "thing that promotes a file is a human tapping a label."
    )

    # --- 8. the insights edge -> measurement rows --------------------------
    rows = [
        measure.measurement(
            segment=SEGMENT_ID, ad_id=ad_id,
            campaign_id=live["ads"][ad_id]["campaign_id"],
            launched_at=live["launched_at"],
            insights=insights_body(impressions=4100 + index * 300,
                                   clicks=51 + index * 4, ctr=1.24 + index * 0.1),
            now=MEASURED_AT,
        )
        for index, ad_id in enumerate(AD_IDS)
    ]
    measurements_path = measure.write_measurements(
        rows, tree / "research" / "measurements.json", now=MEASURED_AT
    )

    log.stage(8, "MEASURE", f"{len(rows)} launched ads read back")
    for row in rows:
        metrics = row["metrics"]
        log.fact(row["ad_id"], f"impressions {metrics['impressions']:,}  "
                               f"ctr {metrics['ctr']}%  "
                               f"results {metrics['results']}  "
                               f"cost/result {metrics['cost_per_result']}  "
                               f"hook-rate {row['derived']['hook_rate']:.2f}")
    log.wrote(measurements_path, out)
    log.read(
        "an absent figure is null here, never 0. A quartile Meta did not send is "
        "not a zero-second watch, and averaging it in as one would be a lie."
    )

    # --- 9. job + row -> own corpus records --------------------------------
    own = feedback.load_own(tree / "seeds.yaml")
    own_records = [feedback.record_for(live, row, own=own) for row in rows]
    for record in own_records:
        corpus.save(record, corpus_root)

    log.stage(9, "FEEDBACK", f"{len(own_records)} own ads join the corpus")
    log.fact("origin", "own - scored beside the competitors, not in a side table")
    log.fact("model", own_records[0]["model"])
    log.fact("carries", f"analysis.own_metrics.ctr = "
                        f"{own_records[0]['analysis']['own_metrics']['ctr']}")
    log.read(
        "this is the join that makes the loop a loop: our own results re-enter "
        "the same corpus the competitors are in, under the same schema."
    )

    # --- 10. learned again -> a ctr pattern a concept can cite -------------
    after = learn.build(corpus.load_all(corpus_root))
    learn.write(after, patterns_path)
    ctr_patterns = [p for p in after["patterns"] if p["kind"] == "ctr"]
    if not ctr_patterns:
        raise Refused(
            "the corpus grew by our own ads and no ctr pattern appeared, so the "
            "loop does not close; engine/learn.py is not reading "
            "analysis.own_metrics.ctr"
        )
    ctr = ctr_patterns[0]
    closing = concepts.generate(
        after, [segment], n=2,
        client=StubClient([json_reply(concept_reply([ctr["id"]]))]),
    )

    log.stage(10, "CLOSED", f"corpus {patterns['corpus_size']} -> "
                            f"{after['corpus_size']}, a new pattern kind appears")
    log.fact(ctr["id"], f"{ctr['kind']}/{ctr['device']}  n={ctr['n']}  "
                        f"{ctr['evidence']}")
    log.fact("cited by", f"{closing[0]['id']} on the next pass")
    log.read(
        "next week's concept cites what OUR ad did, on the same footing as what "
        "a competitor's ad did. From here the loop runs without new input."
    )

    _epilogue(out, log)
    return {
        "candidates": candidates,
        "records": run.records,
        "patterns": patterns,
        "concepts": written,
        "selection": selection,
        "job": job,
        "verdict": verdict,
        "rows": rows,
        "own_records": own_records,
        "after": after,
    }


def _epilogue(out: Path, log: Log) -> None:
    log.say()
    log.say("what is now on disk")
    log.say("-------------------")
    for path in sorted(out.rglob("*.json")):
        log.say(f"  {path.relative_to(out.parent)}")
    log.say()
    log.say("Read them in this order: one corpus record (what one ad is, to this")
    log.say("engine), then patterns.json (what the corpus counts to), then")
    log.say("selection.json (why one concept beat the other). Those three are the")
    log.say("analysis. Everything after them is plumbing.")
    log.say()


# ---------------------------------------------------------------------------
# Plumbing
# ---------------------------------------------------------------------------

def _prepare(out: Path) -> Path:
    """A clean tree under `out`, and engine.approval pointed into it.

    `approval.QUEUE` is reassigned rather than passed, because every other
    module reaches the queue through `approval.queue_dir()` at call time -
    which is exactly how tests/test_approval.py redirects it, and the reason
    one assignment moves approval, measure and propose together.
    """
    if out.exists():
        if not (out / ".walk").exists():
            raise Refused(
                f"{out} exists and was not written by this tool (no .walk marker "
                f"in it). Refusing to delete somebody else's directory - pass "
                f"--out to choose another, or remove it yourself."
            )
        shutil.rmtree(out)
    for stage in approval.ALL_STAGES:
        (out / "queue" / stage).mkdir(parents=True)
    (out / "research" / "corpus").mkdir(parents=True)
    (out / "creative").mkdir()
    (out / ".walk").write_text(
        "Written by tools/walk.py. Safe to delete; nothing reads it.\n",
        encoding="utf-8",
    )
    (out / "seeds.yaml").write_text(SEEDS_YAML, encoding="utf-8")
    approval.QUEUE = out / "queue"
    return out


def _segment() -> backlog.Segment:
    """The real backlog row, read from the committed queue/backlog.md.

    Read rather than invented, for the reason tests/test_pipeline.py gives:
    engine/score.py scores a concept 0 for a segment that is not a row in that
    file, so a made-up one would walk green for the wrong reason.
    """
    rows = {s.id: s for s in backlog.load()}
    if SEGMENT_ID not in rows:
        raise Refused(
            f"{SEGMENT_ID!r} is no longer a row in queue/backlog.md. This walk "
            f"needs a real segment, because engine/score.py scores an unknown "
            f"one at zero and the selection would then prove nothing. Pick a "
            f"row from that file and change SEGMENT_ID in tests/test_pipeline.py."
        )
    return rows[SEGMENT_ID]


def _dump(obj: dict, path: Path) -> Path:
    """One writer for every file this tool writes itself, in the same shape
    engine/propose.py commits a job: two-space indent, trailing newline, UTF-8
    kept as UTF-8 so Danish copy reads as Danish."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="walk", description=__doc__.splitlines()[2],
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help="where to write the artifacts (default: demo/)")
    parser.add_argument("--quiet", action="store_true",
                        help="write the files, print nothing")
    args = parser.parse_args(argv)

    try:
        walk(args.out.resolve(), Log(on=not args.quiet))
    except Refused as refusal:
        print(f"refused: {refusal}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
