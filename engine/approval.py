"""The approval seam: given an issue, what stage is it in and what happens next.

A port of reel-engine/engine/approval.py with the stages renamed for what they
mean here. Deliberately thin, and in two halves. The decision half is pure -
queue directory membership, one small table, and the text of a proposal - and
knows nothing about GitHub. The transport half is six methods behind a
protocol, with one implementation today. A Telegram bridge is a second
implementation of that protocol; nothing in the decision half moves.

The queue layout lives here because the directory IS the stage. One definition,
imported by engine.propose and engine.measure, rather than two that can drift.

What changed from the reel loop, and why:

- proposed -> built -> launched. The second `go` does not publish anything: a
  human uploads the creative and the copy in Ads Manager and pastes the ad id
  back (docs/AD-RESEARCH-SCOPE.md 3.11). `launch()` is that paste. It pins the
  ad ids under `ads` and stamps `launched_at`, and it is the only way into
  queue/launched/, because a launched job without an ad id is a record
  engine.measure can never look up.
- A job has two sidecars, not one: the still `<segment>.jpg` the reviewer sees
  on the issue, and `<segment>.reel.json`, the selection reel-engine renders
  from. Both travel with the JSON. The second one ends in `.json`, so every
  directory listing here filters it out: a sidecar is not a job.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from engine import backlog

ROOT = Path(__file__).resolve().parents[1]

# Read through queue_dir(), never cached, so a test can redirect the whole
# module - and engine.propose and engine.measure with it - by patching this one
# name.
QUEUE = ROOT / "queue"

# A job's directory is its status. These three are live: a segment named by any
# of them is spoken for and must not be re-picked from the backlog.
LIVE_STAGES = ("proposed", "built", "launched")

# Not a live stage. A parked draft never passed the gate, so its segment stays
# in the backlog - propose picks it again and refuses to overwrite the draft.
REJECTED = "rejected"

ALL_STAGES = LIVE_STAGES + (REJECTED,)

# The label is a human-readable mirror of the directory. It is never the
# authority: the two `go` taps are indistinguishable in the webhook payload, so
# only the directory can tell a copy approval from a creative approval.
STAGE_LABEL = {"proposed": "stage:copy", "built": "stage:creative"}

GO = "go"
NO = "no"

# The selection reel-engine renders from, written by engine.propose beside the
# job for a `reel` or `still` creative. It ends in .json and lives in the same
# directory, which is why jobs_in() has to know about it.
REEL_SELECTION_SUFFIX = ".reel.json"

# Meta ids - ad, campaign, ad set - are decimal strings in every API reference
# and every Ads Manager column. Anything else pasted into --ad is a typo or a
# name, and pinning it would make every later measurement a 400 by exact
# lookup.
META_ID_RE = re.compile(r"^[0-9]+$")

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def queue_dir(stage: str) -> Path:
    if stage not in ALL_STAGES:
        raise ValueError(
            "unknown stage %r; expected one of %s"
            % (stage, ", ".join(ALL_STAGES))
        )
    return QUEUE / stage


@dataclass(frozen=True)
class Job:
    """One ad, at one stage. The JSON is the job; the directory is the status."""

    segment_id: str
    path: Path
    stage: str

    @property
    def still(self) -> Path:
        """The frame shown on the approval issue. Travels with the JSON."""
        return self.path.with_suffix(".jpg")

    @property
    def reel_selection(self) -> Path:
        """The selection reel-engine renders from. Travels with the JSON.

        with_name rather than with_suffix: a segment id may carry a dot, and
        the sidecar is `<segment>.reel.json` whatever the stem looks like.
        """
        return self.path.with_name(self.segment_id + REEL_SELECTION_SUFFIX)

    @property
    def sidecars(self) -> tuple[Path, Path]:
        """Everything that moves with the job, whether or not it exists yet."""
        return (self.still, self.reel_selection)

    @property
    def label(self) -> str | None:
        return STAGE_LABEL.get(self.stage)


def is_job_file(path: Path) -> bool:
    """A `<segment>.json` that is not a `<segment>.reel.json` sidecar.

    Public because engine.measure lists queue/launched/ with its own glob in
    the reel loop; here that glob would count every reel selection as a
    launched ad. Use jobs_in() instead, or at least this predicate.
    """
    name = path.name
    return name.endswith(".json") and not name.endswith(REEL_SELECTION_SUFFIX)


def jobs_in(stage: str) -> list[Job]:
    """Every job in a stage, in filename order. Sidecars are not jobs."""
    directory = queue_dir(stage)
    if not directory.is_dir():
        return []
    return [
        Job(p.stem, p, stage)
        for p in sorted(directory.glob("*.json"))
        if is_job_file(p)
    ]


def used_ids() -> set[str]:
    """Segments spoken for by a live job.

    queue/rejected/ is excluded on purpose: a parked draft never passed the
    gate, so its segment must stay in the backlog.
    """
    return {job.segment_id for stage in LIVE_STAGES for job in jobs_in(stage)}


def locate(segment_id: str) -> Job:
    """Which stage this segment is in. The first thing every workflow does."""
    found = [
        job
        for stage in LIVE_STAGES
        for job in jobs_in(stage)
        if job.segment_id == segment_id
    ]
    if not found:
        raise LookupError(
            "no job for segment %r in %s"
            % (segment_id, ", ".join("queue/%s" % s for s in LIVE_STAGES))
        )
    if len(found) > 1:
        raise LookupError(
            "segment %r has two jobs, so its stage is undefined and a `go` tap "
            "would be ambiguous: %s"
            % (segment_id, ", ".join(str(job.path) for job in found))
        )
    return found[0]


def load_job(job: Job) -> dict:
    """The job's JSON, refused when the file disagrees with its own name.

    The filename is the segment and the directory is the stage; the `id` and
    `segment` fields inside are the writer's copy of the same fact. When they
    differ, somebody renamed a file by hand or a writer stamped the wrong
    segment, and every later step - the issue title, the measurement row, the
    feedback record - would carry the wrong trade. Named, not guessed past.
    """
    try:
        document = json.loads(job.path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("%s is not JSON (%s)" % (job.path, exc)) from None
    if not isinstance(document, dict):
        raise ValueError(
            "%s holds a JSON %s, not an ad job object"
            % (job.path, type(document).__name__)
        )
    for key in ("id", "segment"):
        if document.get(key) != job.segment_id:
            raise ValueError(
                "%s says %s=%r but its filename says %r. The filename is the "
                "segment; fix the field (or the name) before acting on it."
                % (job.path, key, document.get(key), job.segment_id)
            )
    return document


def _write_job(job: Job, document: dict) -> None:
    # Job files keep their authored key order (docs/CONTRACTS.md, Conventions):
    # no sort_keys, so a launch that fills `ads` and `launched_at` in place
    # produces a two-line diff, not a reshuffle.
    job.path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# --- decision -------------------------------------------------------------


@dataclass(frozen=True)
class Action:
    """What a label means for a job at a given stage."""

    kind: str  # "build" | "launch" | "reject"
    job: Job


def decide(job: Job, label: str) -> Action:
    """The whole control surface, as a table.

    The stage comes from the filesystem, never from a label: `go` on a proposal
    and `go` on a built creative are byte-identical in the webhook payload, so
    the directory is the only thing that can tell them apart.
    """
    if label == NO and job.stage in ("proposed", "built"):
        return Action("reject", job)
    if label == GO and job.stage == "proposed":
        return Action("build", job)
    if label == GO and job.stage == "built":
        return Action("launch", job)
    raise ValueError(
        "no action for label %r on a job in queue/%s. Launching is terminal, "
        "and an unrecognised state is stopped rather than guessed."
        % (label, job.stage)
    )


# --- the marker -----------------------------------------------------------

# An HTML comment: invisible in the rendered issue, and the only thing that
# ties an issue back to a segment. The title is prose and must never be parsed.
MARKER_RE = re.compile(r"<!--\s*doviloop-ad:\s*([A-Za-z0-9._-]+)\s*-->")


def marker(segment_id: str) -> str:
    return "<!-- doviloop-ad: %s -->" % segment_id


def segment_of(issue_body: str) -> str:
    match = MARKER_RE.search(issue_body or "")
    if not match:
        raise ValueError(
            "no doviloop-ad marker in the issue body. This issue was not "
            "opened by engine.approval, so its segment cannot be resolved - "
            "and guessing from the title would act on the wrong ad."
        )
    return match.group(1)


# --- composition ----------------------------------------------------------


def segment_named(segment_id: str) -> backlog.Segment:
    for segment in backlog.load():
        if segment.id == segment_id:
            return segment
    raise LookupError("no segment %r in queue/backlog.md" % segment_id)


def _english(job: dict, field: str) -> str:
    """The `en` text of a {en, da, lt} map; a bare string is taken as is.

    Only English goes on the issue: the writer stamps da and lt with a
    placeholder and a native proofreads them later, off this surface.
    """
    value = job.get(field)
    if isinstance(value, dict):
        value = value.get("en")
    return (value or "").strip() if isinstance(value, str) else ""


def compose_proposal(
    segment: backlog.Segment, job: dict, still_url: str | None
) -> tuple[str, str]:
    """The approval issue: the copy, why this segment, and a look at it.

    Everything a copy decision needs, on one screen, with no repository
    checkout - the reviewer is on a phone. The still is optional because
    propose.yml opens the issue before anything is rendered; build.yml has the
    frame and comments it in later.
    """
    title = "Ad: %s (%s)" % (segment.trade, segment.id)

    lines = [marker(segment.id), ""]

    if still_url and still_url.strip():
        lines += ["![still frame](%s)" % still_url.strip(), ""]

    lines += [
        "## Copy",
        "",
        "**Headline** - %s" % _english(job, "headline"),
        "",
        "**Description** - %s" % _english(job, "description"),
        "",
        "**Primary text**",
        "",
        _english(job, "primary_text"),
        "",
        "**Placement** `%s` - **Offer** `%s` - **CTA** `%s`"
        % (job.get("placement", ""), job.get("offer", ""), job.get("cta", "")),
        "",
        "## Hypothesis",
        "",
        (job.get("hypothesis") or "").strip() or "-",
        "",
    ]

    # Provenance, when the writer left any: which concept, citing which
    # learned patterns. A hand-written job has neither and the section is
    # simply absent rather than a row of blanks.
    provenance = []
    if job.get("concept_id"):
        provenance.append("Concept `%s`" % job["concept_id"])
    pattern_ids = [p for p in (job.get("pattern_ids") or []) if p]
    if pattern_ids:
        provenance.append(
            "patterns %s" % ", ".join("`%s`" % p for p in pattern_ids)
        )
    if provenance:
        lines += ["## Provenance", "", ", ".join(provenance) + ".", ""]

    lines += [
        "## Why this segment",
        "",
        "Rank %d in `queue/backlog.md`. %s answer the same three lookups over "
        "and over: %s."
        % (
            segment.rank,
            segment.trade,
            ", ".join("**%s**" % q for q in segment.questions),
        ),
        "",
        "Backlog note: %s" % (segment.note or "-"),
        "",
        "---",
        "",
        "Add **`go`** to build the creative. Add **`no`** to reject it and "
        "return the segment to the backlog.",
    ]
    return title, "\n".join(lines)


# --- movement -------------------------------------------------------------


def _move(job: Job, to_stage: str) -> Job:
    """Relocate a job and whatever sidecars exist beside it. No checks."""
    dest_dir = queue_dir(to_stage)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / job.path.name

    if dest.exists():
        raise FileExistsError(
            "%s already holds a job for %r" % (dest_dir, job.segment_id)
        )

    job.path.replace(dest)
    moved = Job(job.segment_id, dest, to_stage)
    for source, target in zip(job.sidecars, moved.sidecars):
        if source.exists():
            source.replace(target)
    return moved


def advance(segment_id: str, to_stage: str) -> Job:
    """Move a job to the next stage. The still and the selection travel with it.

    queue/launched/ is not a target here: the only way in is launch(), which
    pins the ad ids. Moving a job there without them would leave a record
    engine.measure reads and can never look up.
    """
    if to_stage not in LIVE_STAGES:
        raise ValueError(
            "cannot advance to %r; expected one of %s"
            % (to_stage, ", ".join(LIVE_STAGES))
        )
    if to_stage == "launched":
        raise ValueError(
            "cannot advance to 'launched' without ad ids; use "
            "`python -m engine.approval launch --segment %s --ad <ad id>`, "
            "which pins them" % segment_id
        )
    return _move(locate(segment_id), to_stage)


# The key engine.measure reads to know when an ad went live.
LAUNCHED_AT = "launched_at"

# The key engine.measure reads for the ad ids it looks up.
ADS = "ads"


def _normalised_ads(ads: dict) -> dict:
    """`ads` as C3 writes it: {"<ad id>": {"campaign_id", "adset_id"}}.

    Both inner keys are always present so a reader can index them without a
    KeyError; an id that was not given is null, never "" and never guessed.
    """
    if not isinstance(ads, dict) or not ads:
        raise ValueError(
            "launch needs at least one ad id; pass --ad <ad id> (the number in "
            "Ads Manager's Ad ID column). A launched job without one is a "
            "record engine.measure can never look up."
        )
    normalised = {}
    for ad_id, ids in ads.items():
        ad_id = str(ad_id).strip()
        if not META_ID_RE.fullmatch(ad_id):
            raise ValueError(
                "ad id %r is not a Meta id (all digits); copy it from Ads "
                "Manager's Ad ID column" % ad_id
            )
        ids = ids or {}
        if not isinstance(ids, dict):
            raise ValueError(
                "ad %s wants a {campaign_id, adset_id} object, got %s"
                % (ad_id, type(ids).__name__)
            )
        entry = {}
        for key in ("campaign_id", "adset_id"):
            value = ids.get(key)
            if value is None or str(value).strip() == "":
                entry[key] = None
                continue
            value = str(value).strip()
            if not META_ID_RE.fullmatch(value):
                raise ValueError(
                    "%s %r for ad %s is not a Meta id (all digits)"
                    % (key, value, ad_id)
                )
            entry[key] = value
        normalised[ad_id] = entry
    return normalised


def _utc_stamp(now: datetime | None) -> str:
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc).strftime(TIMESTAMP_FORMAT)


def launch(segment_id: str, ads: dict, *, now: datetime | None = None) -> Job:
    """Terminal move, with the ad ids written in.

    This is the one place job metadata enters a job JSON after the gate. The
    ad ids are the twin of the reel job's `videos` map: the guess is made
    once, by the human who uploaded the creative, and every later measurement
    is an exact lookup.

    Only from queue/built/. A proposal has no creative to have launched, and a
    job already in queue/launched/ has its ids pinned; either would be a lie
    about what went out. Everything is checked before anything moves, so a
    refusal leaves the queue exactly as it was.

    `launched_at` is recorded because nothing else can recover it later. The
    reel loop learnt this the hard way: git does not store mtimes, so
    actions/checkout stamps every file with the checkout time, and a
    measurement window keyed on mtime slides to "today" for an ad that went
    live a week ago.
    """
    job = locate(segment_id)
    if job.stage != "built":
        raise ValueError(
            "%r is in queue/%s, not queue/built; only a built creative can "
            "be launched. %s"
            % (
                segment_id,
                job.stage,
                "Tap `go` on its issue first (or `approval advance --to built`)."
                if job.stage == "proposed"
                else "Its ad ids are already pinned in the job file.",
            )
        )
    normalised = _normalised_ads(ads)
    document = load_job(job)

    moved = _move(job, "launched")
    document[ADS] = normalised
    document[LAUNCHED_AT] = _utc_stamp(now)
    _write_job(moved, document)
    return moved


def drop(segment_id: str) -> Job:
    """`no`: the job leaves the queue and its segment returns to the backlog.

    Not parked into queue/rejected/ - that directory means "failed the gate,
    fix or attest this exact text, then --regate". A rejected proposal passed
    the gate and was simply not wanted. Git history holds what was removed.
    """
    job = locate(segment_id)
    if job.stage == "launched":
        raise ValueError(
            "%r is already launched; dropping it would delete the record of "
            "an ad that went live (and the ids engine.measure reads)"
            % segment_id
        )
    job.path.unlink()
    for sidecar in job.sidecars:
        sidecar.unlink(missing_ok=True)
    return job


# --- transport ------------------------------------------------------------


class Approvals(Protocol):
    """Everything the workflows need a human-facing surface to do.

    Six methods. A Telegram bridge implements these and nothing above this
    line changes - which is the entire reason the decision half is pure.
    """

    def open(self, *, title: str, body: str, labels: list[str]) -> str: ...
    def comment(self, ref: str, body: str) -> None: ...
    def add_label(self, ref: str, label: str) -> None: ...
    def remove_label(self, ref: str, label: str) -> None: ...
    def close(self, ref: str, comment: str) -> None: ...
    def body_of(self, ref: str) -> str: ...


class GitHubIssues:
    """The one implementation today, over the `gh` CLI.

    `gh` is preinstalled on GitHub runners and authenticated from GH_TOKEN, so
    this needs no library and no PAT. Bodies go through files rather than
    argv: issue text is multi-line and full of backticks and quotes.
    """

    def __init__(self, repo: str | None = None, runner=subprocess.run):
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY")
        self._run = runner

    def _gh(self, *args: str) -> str:
        cmd = ["gh", *args]
        if self.repo:
            cmd += ["--repo", self.repo]
        try:
            proc = self._run(cmd, capture_output=True, text=True)
        except OSError as exc:
            # FileNotFoundError is an OSError, not a RuntimeError, so without
            # this it escapes main()'s handler as a traceback. Runners always
            # have gh; someone running this by hand may not.
            raise RuntimeError(
                "could not run the gh CLI (%s). It is preinstalled on GitHub "
                "runners; locally, install it from https://cli.github.com and "
                "run `gh auth login`." % exc
            ) from exc
        if proc.returncode != 0:
            raise RuntimeError(
                "gh %s failed (exit %s):\n%s"
                % (
                    " ".join(args),
                    proc.returncode,
                    ((proc.stdout or "") + (proc.stderr or "")).strip(),
                )
            )
        return (proc.stdout or "").strip()

    def _with_body_file(self, body: str, build):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8", newline="\n"
        )
        try:
            handle.write(body)
            handle.close()
            return self._gh(*build(handle.name))
        finally:
            os.unlink(handle.name)

    def open(self, *, title: str, body: str, labels: list[str]) -> str:
        def build(path: str) -> list[str]:
            args = ["issue", "create", "--title", title, "--body-file", path]
            for label in labels:
                args += ["--label", label]
            return args

        out = self._with_body_file(body, build)
        match = re.search(r"/issues/(\d+)", out)
        if not match:
            raise RuntimeError(
                "could not read an issue number from gh output: %r" % out
            )
        return match.group(1)

    def comment(self, ref: str, body: str) -> None:
        self._with_body_file(
            body, lambda path: ["issue", "comment", ref, "--body-file", path]
        )

    def add_label(self, ref: str, label: str) -> None:
        self._gh("issue", "edit", ref, "--add-label", label)

    def remove_label(self, ref: str, label: str) -> None:
        self._gh("issue", "edit", ref, "--remove-label", label)

    def close(self, ref: str, comment: str) -> None:
        if comment:
            self.comment(ref, comment)
        self._gh("issue", "close", ref)

    def body_of(self, ref: str) -> str:
        return json.loads(
            self._gh("issue", "view", ref, "--json", "body")
        ).get("body", "")


# --- CLI ------------------------------------------------------------------
#
# The workflows call this and never call `gh` themselves. That is what makes
# swapping the backend a Python change rather than a YAML rewrite.


def _emit(**pairs) -> None:
    """Print for a human, and hand the same pairs to Actions when it is driving."""
    for key, value in pairs.items():
        print("%s=%s" % (key, value))
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            for key, value in pairs.items():
                handle.write("%s=%s\n" % (key, value))


def _read(path: str | None) -> str:
    return Path(path).read_text(encoding="utf-8") if path else ""


def parse_ad_arg(value: str) -> tuple[str, dict]:
    """`ID[:campaign_id[:adset_id]]` -> (ad id, {campaign_id, adset_id}).

    Colons because Meta ids never contain one and because launch.yml builds
    the argument from three dispatch inputs by joining them. A blank segment
    ("123::456") means "not given" for that slot, not an empty id.
    """
    parts = value.split(":")
    if len(parts) > 3:
        raise ValueError(
            "--ad wants ID[:campaign_id[:adset_id]] (at most two colons); "
            "got %r" % value
        )
    ad_id = parts[0].strip()
    if not ad_id:
        raise ValueError("--ad wants ID[:campaign_id[:adset_id]]; got %r" % value)
    ids = {"campaign_id": None, "adset_id": None}
    for key, part in zip(("campaign_id", "adset_id"), parts[1:]):
        ids[key] = part.strip() or None
    return ad_id, ids


def main(argv: list[str] | None = None, backend: Approvals | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="The approval seam: stages, issues and labels."
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("open", help="open the approval issue for a proposal")
    p.add_argument("--segment", required=True)
    p.add_argument(
        "--still-url",
        default=None,
        help="the rendered frame, when there is one; propose.yml has none yet",
    )

    p = sub.add_parser("resolve", help="issue -> segment, confirming the stage")
    p.add_argument("--issue", required=True)
    p.add_argument(
        "--expect",
        default=None,
        choices=list(LIVE_STAGES),
        help="hard-fail unless the job is in this stage",
    )

    p = sub.add_parser("advance", help="move a job to the next stage")
    p.add_argument("--segment", required=True)
    p.add_argument(
        "--to",
        required=True,
        choices=[s for s in LIVE_STAGES if s != "launched"],
        help="launched is reached through `launch`, which pins the ad ids",
    )

    p = sub.add_parser("launch", help="terminal move, with the ad ids pinned")
    p.add_argument("--segment", required=True)
    p.add_argument(
        "--ad",
        action="append",
        required=True,
        metavar="ID[:campaign_id[:adset_id]]",
        help="repeatable; one per ad created from this job",
    )

    p = sub.add_parser(
        "drop", help="remove a job; its segment returns to the backlog"
    )
    p.add_argument("--segment", required=True)

    p = sub.add_parser("comment")
    p.add_argument("--issue", required=True)
    p.add_argument("--body-file", required=True)

    p = sub.add_parser("label")
    p.add_argument("--issue", required=True)
    p.add_argument("--add", default=None)
    p.add_argument("--remove", default=None)

    p = sub.add_parser("close")
    p.add_argument("--issue", required=True)
    p.add_argument("--comment-file", default=None)

    args = ap.parse_args(argv)
    backend = backend or GitHubIssues()

    try:
        if args.cmd == "open":
            job = locate(args.segment)
            if job.stage != "proposed":
                raise ValueError(
                    "%r is in queue/%s; only a proposal opens an issue"
                    % (args.segment, job.stage)
                )
            title, body = compose_proposal(
                segment_named(args.segment), load_job(job), args.still_url
            )
            ref = backend.open(
                title=title, body=body, labels=[STAGE_LABEL["proposed"]]
            )
            _emit(issue=ref, segment=args.segment)
            return 0

        if args.cmd == "resolve":
            segment_id = segment_of(backend.body_of(args.issue))
            job = locate(segment_id)
            if args.expect and job.stage != args.expect:
                raise ValueError(
                    "issue %s resolves to %r, which is in queue/%s, not "
                    "queue/%s. The directory is the authority on stage, so "
                    "this is a corrupt state and is not guessed past."
                    % (args.issue, segment_id, job.stage, args.expect)
                )
            _emit(segment=segment_id, stage=job.stage, path=str(job.path))
            return 0

        if args.cmd == "advance":
            job = advance(args.segment, args.to)
            _emit(segment=job.segment_id, stage=job.stage, path=str(job.path))
            return 0

        if args.cmd == "launch":
            ads: dict = {}
            for value in args.ad:
                ad_id, ids = parse_ad_arg(value)
                if ad_id in ads:
                    raise ValueError(
                        "--ad %s was given twice; one entry per ad" % ad_id
                    )
                ads[ad_id] = ids
            job = launch(args.segment, ads)
            _emit(
                segment=job.segment_id,
                stage=job.stage,
                path=str(job.path),
                ads=",".join(ads),
            )
            return 0

        if args.cmd == "drop":
            job = drop(args.segment)
            _emit(segment=job.segment_id, dropped=str(job.path))
            return 0

        if args.cmd == "comment":
            backend.comment(args.issue, _read(args.body_file))
            return 0

        if args.cmd == "label":
            if args.remove:
                backend.remove_label(args.issue, args.remove)
            if args.add:
                backend.add_label(args.issue, args.add)
            return 0

        if args.cmd == "close":
            backend.close(args.issue, _read(args.comment_file))
            return 0
    except (ValueError, LookupError, FileExistsError, RuntimeError) as exc:
        print("approval %s failed: %s" % (args.cmd, exc), file=sys.stderr)
        return 1

    raise AssertionError("unreachable: argparse rejects unknown subcommands")


if __name__ == "__main__":
    raise SystemExit(main())
