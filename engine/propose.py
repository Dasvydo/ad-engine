"""python -m engine.propose [--segment ID] [--placement P] [--force]
   python -m engine.propose --regate queue/rejected/<segment>.json
   python -m engine.propose --from-selection | --concept a01

Pick the next unused segment, write the ad, gate it, and file it as a job in
queue/proposed/. One auto-rewrite on an editorial failure, then stop and report
- the design's "fails twice, it stops and asks you" rule.

A queue job is durable state, not scratch space: approval.used_ids() reads it
to decide what is already spoken for, and engine/gate.py prints an evidence_key
that hashes the exact text of a claim. So this module never overwrites a job
without --force, never reaches past the proposed stage even then, and never
deletes one it did not write.

TWO FILES, ONE DECISION. A job whose creative_source.kind is "reel" also gets
queue/proposed/<segment>.reel.json beside it - the selection document
reel-engine's own load_selection accepts, so build.yml can hand the sibling
repository a concept instead of a prose brief. It is written only AFTER the
gate passes: an ungated draft has no creative, and a sidecar sitting beside a
parked draft would name a reel nobody approved. When the job was written
without a concept (--segment alone, or a --regate of a draft that predates the
selection), the sidecar carries a synthetic concept built from the job's own
headline and hypothesis, under the job's concept_id when it has one and the
segment id when it does not - so the id in the sidecar is always one a
workflow can read off the job.

WHAT THIS MODULE DOES NOT DO. It resolves no template and shoots no still.
reel-engine's propose picks a staging from the concept's own words and renders
a frame for the approval issue; here the creative is the build step's business
and the template is stamped by engine.write from the placement. The issue goes
up without a still until build.yml has shot one.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine import approval, gate, learn, write
from engine.approval import used_ids  # re-exported: one definition of "used"
from engine.backlog import Segment, load as load_backlog, next_unused
from engine.model import CapacityError, ConfigError

ROOT = Path(__file__).resolve().parents[1]

# The report engine.fanout writes. Read, never written, by this module.
DEFAULT_SELECTION = ROOT / "research" / "selection.json"

# The one creative_source.kind that gets a selection sidecar, per
# docs/CONTRACTS.md. A "still" names a template and a selection path too -
# reel-engine shoots a still from a BUILT reel - but the contract says reel,
# and build.yml's still branch has no spec yet. See the report's notes.
REEL = "reel"

__all__ = [
    "AmbiguousSegment",
    "DEFAULT_SELECTION",
    "SelectionInvalid",
    "cited_patterns",
    "load_concept",
    "load_selection",
    "main",
    "pick",
    "regate",
    "synthetic_concept",
    "used_ids",
]


class SelectionInvalid(ConfigError):
    """A selection report this module will not write an ad from.

    A ConfigError because it is always the operator's to fix and no retry
    helps - a report that is missing, unparseable, or that selects a concept it
    does not itself carry is the same class of fault as an absent key. main()
    already turns one of those into a single line rather than a traceback, so
    the concept path gets that for free.
    """


class AmbiguousSegment(LookupError):
    """One segment, two live jobs. Refused rather than picked between.

    approval.locate() raises LookupError both for "no job" and for "two jobs",
    and the sibling reads either as "nothing is there" - which, on the
    ambiguous one, overwrites one of the two files without --force ever being
    passed. The two cases are told apart here instead.
    """


def _text(value) -> str:
    """A trimmed string, or "" for anything that is not a usable one."""
    return value.strip() if isinstance(value, str) else ""


def load_selection(path: Path | str | None = None) -> list[dict]:
    """The concept records a fan-out run selected, in the report's own order.

    Every fault is raised as SelectionInvalid naming the file, because the
    reader is an operator holding a report that a workflow wrote unattended.
    """
    path = Path(path) if path else DEFAULT_SELECTION
    if not path.exists():
        raise SelectionInvalid(
            "no selection report at %s. Run python -m engine.fanout to write "
            "one, or name an existing report explicitly" % path
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SelectionInvalid("%s is not valid JSON: %s" % (path, exc)) from exc

    if not isinstance(document, dict):
        raise SelectionInvalid(
            "%s must be a JSON object; got %s" % (path, type(document).__name__)
        )

    chosen = document.get("selected")
    records = document.get("concepts")
    if not isinstance(chosen, list) or not isinstance(records, list):
        raise SelectionInvalid(
            "%s must carry a 'selected' list of concept ids and a 'concepts' "
            "list of the records they name; engine.fanout writes both" % path
        )

    by_id = {r.get("id"): r for r in records if isinstance(r, dict)}
    selected: list[dict] = []
    for concept_id in chosen:
        record = by_id.get(concept_id)
        if record is None:
            # A citation pointing at nothing is worse than no citation: it
            # reads as a decision that was never made.
            raise SelectionInvalid(
                "%s selects concept %r but carries no concept with that id. "
                "Re-run python -m engine.fanout; a report that cannot show "
                "what it chose cannot be written from" % (path, concept_id)
            )
        selected.append(record)

    if not selected:
        raise SelectionInvalid(
            "%s selected no concepts, so there is nothing to write. Re-run "
            "python -m engine.fanout" % path
        )
    return selected


def cited_patterns(concept, *, path: Path | str | None = None) -> list[dict]:
    """The pattern records a concept cites, in the order it cites them.

    An id the patterns file no longer holds is dropped rather than raised on:
    engine.concepts already refuses a concept citing a pattern that was never
    measured, so anything missing here is a patterns file regenerated since the
    report was written. That is a thinner prompt, not a reason to refuse to
    write the ad the research chose.
    """
    wanted = [str(p) for p in concept.get("pattern_ids") or []]
    if not wanted:
        return []
    try:
        document = learn.load(path)
    except (FileNotFoundError, learn.PatternsInvalid) as exc:
        raise SelectionInvalid(
            "concept %s cites %s, but its patterns could not be read: %s"
            % (concept.get("id", "(unnamed)"), ", ".join(wanted), exc)
        ) from exc

    by_id = {
        row.get("id"): row
        for row in document.get("patterns", [])
        if isinstance(row, dict)
    }
    return [by_id[pattern_id] for pattern_id in wanted if pattern_id in by_id]


def load_concept(
    concept_id: str,
    *,
    path: Path | str | None = None,
    patterns_path: Path | str | None = None,
) -> tuple[dict, list[dict]]:
    """One selected concept, and the patterns it cites, as one lookup.

    The two are resolved together so the evidence always travels with the hook.
    A hook that arrives without the measurements behind it is indistinguishable
    from a hook somebody made up, which is the one thing this chain exists to
    prevent.
    """
    path = Path(path) if path else DEFAULT_SELECTION
    selected = load_selection(path)
    for record in selected:
        if record.get("id") == concept_id:
            if not _text(record.get("segment")):
                # Checked here rather than left to the caller: a concept with
                # no segment would otherwise fall through to "next unused",
                # and the run would quietly write an ad for somebody else.
                raise SelectionInvalid(
                    "concept %s in %s names no segment, so there is no backlog "
                    "row to write it for. Re-run python -m engine.fanout"
                    % (concept_id, path)
                )
            return record, cited_patterns(record, path=patterns_path)
    raise SelectionInvalid(
        "no selected concept %r in %s. It selected: %s"
        % (concept_id, path, ", ".join(str(r.get("id")) for r in selected))
    )


def pick(segment_id: str | None) -> Segment:
    """The backlog row to write for: the named one, or the next unused one."""
    segments = load_backlog()
    if segment_id:
        for segment in segments:
            if segment.id == segment_id:
                return segment
        raise SystemExit(
            "no segment %r in queue/backlog.md. Available: %s"
            % (segment_id, ", ".join(s.id for s in segments))
        )
    return next_unused(segments, used_ids())


def _existing(segment_id: str):
    """The live job for this segment, or None. Covers all three stages."""
    found = [
        job
        for stage in approval.LIVE_STAGES
        for job in approval.jobs_in(stage)
        if job.segment_id == segment_id
    ]
    if len(found) > 1:
        raise AmbiguousSegment(
            "segment %r has two live jobs, so its stage is undefined and this "
            "run cannot tell which one it would be replacing: %s. Move or "
            "delete one of them by hand."
            % (segment_id, ", ".join(str(job.path) for job in found))
        )
    return found[0] if found else None


def synthetic_concept(job: dict, segment_id: str | None = None) -> dict:
    """A concept record for a job that was written without one.

    The sidecar has to name a concept - reel-engine's load_selection refuses a
    report whose `selected` id it cannot find - so a job written from the
    segment alone still needs one. Everything in it comes off the job itself:
    the headline is the hook, the hypothesis is the angle, the placement is the
    job's. `pattern_ids` is empty because it cites nothing, and `needs_numbers`
    is False because the copy this describes has already passed the claims
    policy - the numbers question was settled by the gate, not left open.

    The id is the job's concept_id when it has one, and the segment id when it
    does not, so `concept_id or segment` reads the right id off either job.
    """
    segment_id = segment_id or _text(job.get("segment")) or _text(job.get("id"))
    return {
        "id": _text(job.get("concept_id")) or segment_id,
        "segment": segment_id,
        "angle": _english(job, "hypothesis"),
        "hook": _english(job, "headline"),
        "pattern_ids": [],
        "placement": job.get("placement"),
        "needs_numbers": False,
    }


def _english(job: dict, field: str) -> str:
    """A job field as English: the `en` of a language map, or a bare string."""
    value = job.get(field)
    if isinstance(value, dict):
        return _text(value.get("en"))
    return _text(value)


def _selection_path(dest: Path, segment_id: str) -> Path:
    """Where the sidecar goes: beside the job, named for the segment.

    Derived from the job's own path rather than from the job's
    creative_source.selection, which is ROOT-relative by contract and would
    escape a redirected queue/ - the one thing a test patching
    approval.QUEUE is redirecting.
    """
    return approval.Job(segment_id, dest, "proposed").reel_selection


def _write_selection(job: dict, dest: Path, segment_id: str,
                     concept: dict | None, *, now=None) -> Path | None:
    """The reel-engine selection beside a gated job, or None for a still.

    Written after the gate and never before it: the sidecar is the instruction
    to render, and an ungated draft has nothing to render.
    """
    source = job.get("creative_source")
    kind = source.get("kind") if isinstance(source, dict) else None
    if kind != REEL:
        return None

    record = concept if concept is not None else synthetic_concept(job, segment_id)
    document = write.reel_selection(record, segment_id, now=now)
    path = _selection_path(dest, segment_id)
    path.write_text(
        json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def _cleanup(dest: Path, preexisting: bool) -> None:
    """Remove this run's leavings: the ungated job file.

    By the time a failure is reported a complete, gate-refused job is already
    on disk, and queue/proposed/ is where every workflow looks for copy to ship.
    Leaving it there is how ungated copy gets shipped.

    It does not go if it pre-dated this run - only --force can even reach that
    case, and overwriting on request is not licence to delete.
    """
    if preexisting:
        print("WARNING: %s existed before this run and --force overwrote it." % dest)
        print("         It now holds ungated copy. Not deleting it. To restore:")
        print("           git checkout -- %s" % dest)
        print("         or fix it in place and re-gate it:")
        print("           python -m engine.propose --regate %s" % dest)
        return
    dest.unlink(missing_ok=True)


def _report(result) -> None:
    print("gate FAILED at the %s layer:" % result.layer)
    for failure in result.failures:
        print("  - %s" % failure)


def regate(path, *, client=None, now=None) -> int:
    """Re-gate one parked draft. On a pass it becomes a proposed job.

    The draft is re-read from disk rather than rewritten, because the whole
    point of parking the exact text is that an evidence_key attesting it still
    hashes it. Regenerating the copy would make that attestation dead on
    arrival.
    """
    path = Path(path)
    if not path.exists():
        raise SystemExit("no such file: %s" % path)

    print("gating %s" % path)
    result = gate.run(path, client=client)

    if not result.ok:
        _report(result)
        print("left in place: %s" % path)
        print("fix or attest, then re-run --regate on the same file.")
        return 1

    segment_id = path.stem
    try:
        live = _existing(segment_id)
    except AmbiguousSegment as exc:
        print("gate passed, but %s" % exc)
        return 1
    if live is not None and live.path.resolve() != path.resolve():
        print("gate passed, but %s already has a job at %s." % (segment_id, live.path))
        print("Promoting %s would give one segment two jobs, and its stage" % path)
        print("would then be undefined. Move or delete one of them.")
        return 1

    dest_dir = approval.queue_dir("proposed")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / ("%s.json" % segment_id)

    # The filename is the segment. A promoted draft whose own fields say
    # otherwise is one approval.load_job() refuses, so it would pass the gate
    # here and be rejected by `approval open` minutes later - and by then it
    # would be sitting in queue/proposed, marking a segment used.
    job = json.loads(path.read_text(encoding="utf-8"))
    for field in ("id", "segment"):
        if _text(job.get(field)) != segment_id:
            print("gate passed, but %s says %s %r while its filename says %r."
                  % (path, field, job.get(field), segment_id))
            print("engine.approval refuses that file, so promoting it would put")
            print("a job in queue/proposed that no `go` tap could ever open.")
            print("Restamp both fields to %r, then re-run --regate." % segment_id)
            return 1

    path.replace(dest)
    print("gate passed -> %s" % dest)

    # The draft was parked before its sidecar was ever written (a structural
    # failure stops short of it), so a promoted draft needs one now or build.yml
    # would meet a reel job with nothing to render from.
    selection = _write_selection(job, dest, segment_id, None, now=now)
    if selection is not None:
        print("selection -> %s" % selection)

    print("run: python -m engine.approval open --segment %s" % segment_id)
    return 0


def main(argv: list[str] | None = None, *, client=None, now=None) -> int:
    """Run, and turn a setup fault into one line instead of a traceback.

    model.client() raises ConfigError when GEMINI_API_KEY is missing, which is
    the likeliest first-run experience there is. Uncaught it reaches the default
    handler, and the traceback goes to unbuffered stderr while the progress
    lines above it are still sitting in a block-buffered stdout - so the failure
    prints BEFORE the work it interrupted. Flushing stdout first restores causal
    order.

    Only ConfigError is caught. A bug still gets its traceback.
    """
    try:
        return _run(argv, client=client, now=now)
    except ConfigError as exc:
        sys.stdout.flush()
        print("stopped: %s" % exc, file=sys.stderr)
        sys.stderr.flush()
        return 1


def _run(argv: list[str] | None = None, *,
         proposed_ids: list[str] | None = None,
         client=None, now=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m engine.propose",
        description="Write, gate and file one ad job from the backlog.",
    )
    ap.add_argument("--segment", default=None,
                    help="segment id; default is next unused")
    ap.add_argument("--placement", default=None, choices=gate.PLACEMENTS,
                    help="force a placement; default is the concept's, then "
                         "%s" % write.DEFAULT_PLACEMENT)
    ap.add_argument("--id-file", default=None, metavar="PATH",
                    help="write the chosen segment id here, for a workflow to "
                         "read; one segment per line, one line per job proposed")
    ap.add_argument("--retries", type=int, default=1,
                    help="editorial rewrites before stopping (default 1)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing proposed job for this segment")
    ap.add_argument("--regate", default=None, metavar="PATH",
                    help="re-gate one parked draft instead of writing a new one")
    ap.add_argument("--concept", default=None, metavar="ID",
                    help="write from this concept in the selection report; its "
                         "segment field picks the backlog row")
    ap.add_argument("--from-selection", action="store_true",
                    help="propose every concept the selection report selected")
    ap.add_argument("--selection", default=None, metavar="PATH",
                    help="selection report to read concepts from "
                         "(default %s)" % DEFAULT_SELECTION)
    args = ap.parse_args(argv)

    if args.regate:
        return regate(Path(args.regate), client=client, now=now)

    if args.retries < 0:
        print("--retries must be zero or more; got %d." % args.retries)
        return 1

    if args.from_selection:
        # One job per selected concept, each proposed through this same path,
        # so a concept-driven job is an ordinary job in every other respect.
        # Only the flag itself is dropped from argv - every other flag the
        # operator passed still applies to each concept - and the worst exit
        # code wins, because three jobs where one failed is a failed run.
        rest = [a for a in (sys.argv[1:] if argv is None else argv)
                if a != "--from-selection"]
        # Every inner run carries the operator's --id-file, and each one used to
        # WRITE it - so the third job overwrote the first two and the workflow
        # reading it opened one approval issue for three committed jobs. The
        # inner runs report their segment here instead, and the file is written
        # once, holding every job proposed.
        segments: list[str] = []
        worst = 0
        # A selection stays committed after the run that consumed it, and
        # propose fires again before the next sweep replaces it. Those later
        # runs meet three segments that already have live jobs, and a live job
        # is a refusal - so without this the second run of every week would go
        # red having filed nothing, which is how an operator learns to stop
        # reading red. A segment already spoken for is done, not failed.
        spoken_for = used_ids()
        # try/finally, because the id file is the ONLY way the workflow learns
        # that anything proposed, and in the sibling it was once written after
        # the loop - so any exception escaping the loop discarded the record of
        # every concept that had already succeeded.
        #
        # MEASURED on reel-engine's run 26, and it cost the first gated reel
        # that engine ever produced. payroll-bureaus passed the gate on its
        # second attempt and was written to queue/proposed/ with its still. The
        # NEXT concept then met a 429 - the free tier's daily cap for the model
        # - which is a plain ConfigError rather than a CapacityError,
        # deliberately, because a daily quota is identical for every concept and
        # there is no point asking again. It escaped the loop, this write never
        # ran, the workflow read a count of 0, staged queue/rejected only, and a
        # job that had PASSED the gate died with the runner.
        #
        # Whatever proposed is reported, however the loop ends. The exception
        # still propagates and the run still fails; it just no longer takes the
        # finished work with it.
        try:
            for record in load_selection(args.selection):
                segment_id = str(record.get("segment") or "")
                if segment_id in spoken_for:
                    print("%s already has a live job; concept %s was proposed by an "
                          "earlier run of this selection."
                          % (segment_id, record.get("id")))
                    continue
                try:
                    worst = max(worst, _run(rest + ["--concept", str(record.get("id"))],
                                            proposed_ids=segments,
                                            client=client, now=now))
                except CapacityError as exc:
                    # A capacity spike is PER CALL, and this loop's whole premise
                    # is that three concepts are three independent jobs. Letting
                    # it escape threw the other two away without ever asking the
                    # model about them - MEASURED on reel-engine's run 25, which
                    # met a 503 on the gate call for concept 1 of 3 and ended
                    # there, having spent a runner on one concept and reported a
                    # failure for three.
                    #
                    # Caught HERE and not in main() so it stays one line rather
                    # than a traceback, and caught as CapacityError and not as
                    # ConfigError so the faults that really are identical for
                    # every concept - a missing key, a rejected key, a daily
                    # quota - still abort the whole run instead of failing three
                    # times slowly.
                    #
                    # The run still ends nonzero: nothing was proposed for this
                    # segment, and it stays in the backlog for the next one.
                    print("%s: %s" % (segment_id, exc))
                    print("moving on to the next concept - a spike is per-call, "
                          "and the concepts after this one have not been asked "
                          "yet.")
                    worst = max(worst, 1)
        finally:
            if args.id_file and segments:
                # One segment per line and no trailing newline, so a single-job
                # run writes exactly what a single run has always written: the
                # bare segment id. An empty list writes nothing at all - the
                # absent file is how the workflow knows there is no issue to
                # open.
                Path(args.id_file).write_text("\n".join(segments),
                                              encoding="utf-8")
        if not segments and worst == 0:
            print("Every selected concept already has a job. Nothing to do.")
        return worst

    concept = patterns = None
    if args.concept:
        concept, patterns = load_concept(args.concept, path=args.selection)
        # The concept names its own segment; queue/backlog.md holds the row.
        args.segment = args.segment or concept["segment"]

    try:
        segment = pick(args.segment)
    except LookupError as exc:
        # Every segment has a live job. Say so and go quiet: a cron that goes
        # red twice a week with a traceback is noise, and the design's answer
        # to an empty backlog is one notice, not a recurring alarm.
        #
        # Nothing is written, so --id-file stays absent - which is how the
        # workflow knows to skip opening an issue rather than committing
        # nothing and failing on an empty `git commit`.
        print("nothing to propose: %s" % exc)
        return 0

    print("segment: %s (rank %d)" % (segment.trade, segment.rank))

    proposed = approval.queue_dir("proposed")
    proposed.mkdir(parents=True, exist_ok=True)
    dest = proposed / ("%s.json" % segment.id)

    # Captured before anything is written. --force is the only way past this,
    # and _cleanup() must know it is looking at someone else's file.
    try:
        live = _existing(segment.id)
    except AmbiguousSegment as exc:
        print("%s" % exc)
        return 1
    preexisting = live is not None

    if live is not None and live.stage != "proposed":
        print("%s already has a job at %s (stage %s)."
              % (segment.id, live.path, live.stage))
        print("--force licenses replacing a proposal. Replacing something")
        print("already built or launched is never what anyone means, so this")
        print("stops regardless. Move that job by hand if you meant it.")
        return 1

    if preexisting and not args.force:
        print("%s already exists." % dest)
        print("That is a live job, not scratch space - overwriting it would")
        print("replace gated copy and invalidate any evidence_key that attests")
        print("its text. Pass --force to overwrite it anyway, or pick a")
        print("different --segment.")
        return 1

    feedback: list[str] | None = None
    job: dict = {}

    for attempt in range(args.retries + 1):
        print("writing (attempt %d)" % (attempt + 1))
        try:
            job = write.generate(
                segment,
                concept=concept,
                patterns=patterns,
                placement=args.placement,
                client=client,
                feedback=feedback,
                now=now,
            )
        except ValueError as exc:
            print("writing FAILED: %s" % exc)
            _cleanup(dest, preexisting)
            print("stopping. Segment stays in the backlog.")
            return 1

        # Authored key order, no sort_keys: a job file is read by a human in a
        # pull request before it is read by anything else.
        dest.write_text(
            json.dumps(job, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print("gating")
        result = gate.run(dest, client=client)
        if result.ok:
            print("gate passed -> %s" % dest)
            break

        _report(result)

        if result.layer == "structural":
            # Keep the exact text. A structural failure is usually one
            # unattested number, and the evidence_key engine/gate.py prints
            # hashes THIS wording - regenerate different copy and that
            # attestation is dead on arrival.
            rejected_dir = approval.queue_dir(approval.REJECTED)
            rejected_dir.mkdir(parents=True, exist_ok=True)
            rejected = rejected_dir / ("%s.json" % segment.id)

            if preexisting:
                # Only --force reaches here. Parking would MOVE a live job out
                # of queue/proposed, so used_ids() would stop seeing it and the
                # next unattended run would re-pick a slot the operator believes
                # is spoken for. --force licenses overwriting in place; it does
                # not license relocating someone else's file.
                _cleanup(dest, preexisting)
                print("Nothing was parked: moving that file out of queue/proposed")
                print("would drop its segment back into the backlog, so the next")
                print("run would re-pick a slot you believe is taken. It stays put.")
                return 1

            if rejected.exists():
                # A parked draft is already waiting on the operator, and a
                # rejected segment deliberately stays in the backlog - so
                # auto-pick lands here again on every run. Overwriting would
                # destroy the exact text they were told to fix or attest.
                _cleanup(dest, preexisting)
                print("%s already exists." % rejected)
                print("A parked draft for this segment is already awaiting")
                print("attention, and its text may already be attested. This")
                print("run's draft was not written over it, and %s has" % dest)
                print("been cleaned up. Re-gate the parked draft:")
                print("  python -m engine.propose --regate %s" % rejected)
                print("or remove it, then re-run.")
                return 1

            dest.replace(rejected)
            print("kept the draft at %s (it does not mark the segment used)"
                  % rejected)
            print("fix the copy, or attest the number in claims/evidence.json")
            print("using the key printed above, then re-gate this same file:")
            print("  python -m engine.propose --regate %s" % rejected)
            return 1

        if attempt == args.retries:
            _cleanup(dest, preexisting)
            print("stopping. Segment stays in the backlog.")
            return 1

        # Rewrite with the reasons in hand, not blind.
        feedback = list(result.failures)

    try:
        selection = _write_selection(job, dest, segment.id, concept, now=now)
    except ValueError as exc:
        # The copy is gated and filed; only the sidecar could not be built,
        # which means the concept record itself is malformed. The job stays -
        # deleting gated copy over a bad field in a report would throw away the
        # expensive half of the run - and the segment is now spoken for, so the
        # fix is a re-gate of the job that is already there.
        print("the job passed the gate and is filed at %s," % dest)
        print("but its reel selection could not be written: %s" % exc)
        print("fix the concept in the selection report, then re-run:")
        print("  python -m engine.propose --regate %s" % dest)
        return 1
    if selection is not None:
        print("selection -> %s" % selection)

    if proposed_ids is not None:
        # An inner run of --from-selection: the caller writes the id file once,
        # for every job, after the last concept.
        proposed_ids.append(segment.id)
    elif args.id_file:
        # A file, not a parsed stdout line: a workflow should not need a regex
        # to learn which segment it just proposed.
        Path(args.id_file).write_text(segment.id, encoding="utf-8")

    print("run: python -m engine.approval open --segment %s" % segment.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
