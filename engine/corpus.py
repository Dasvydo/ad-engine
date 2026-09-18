"""The analysed-ad corpus: one committed JSON file per analysed ad.

A few hundred ads accumulating a handful a week is a directory of files, not a
database. Keeping them as committed JSON means git history is the audit log -
the same reason queue/ works the way it does - so a bad analysis is undone by
reverting a commit rather than by writing a migration. The Ad Library forgets
a commercial ad about a year after its last impression; the corpus, being
committed, does not, which is one more reason the record is a file per ad.

That only holds while the files stay diff-stable, which is why every record is
written with sorted keys and a trailing newline: re-saving an unchanged record
produces a byte-identical file, and a re-analysis shows up in review as the
fields that actually changed.

A copy of reel-engine/engine/corpus.py with a different REQUIRED_NESTED, not an
import of it: the reel corpus requires a transcript, pacing and a timed
structure, and a text ad has none of those. The two repositories keep their own
corpus; nothing reads across.

Pure filesystem and JSON on purpose. The analyse, learn, score and feedback
steps all import this module, so it has to stay loadable - and testable - with
no API key, no network and no model client anywhere near it.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "research" / "corpus"

SCHEMA = 1

# `meta-ad` and nothing else in this repository. The reel platforms live in
# the sibling's corpus; a record naming one of them here is a record that was
# saved to the wrong repository, and is refused rather than filed.
PLATFORMS = ("meta-ad",)

# "own" is our own launched ads, written back in by engine.feedback with
# `model: "none (authored)"` so that what we shipped - the one place in this
# loop with a real click-through rate - becomes evidence alongside what we
# read. It is part of schema 1 from the first record. Should the enum widen
# again, SCHEMA stays where it is: widening an enum invalidates no record that
# was already written, and the only readers are the modules in this repo, all
# updated together. Removing or renaming a value would be the other thing
# entirely, and would need the bump.
ORIGINS = ("competitor", "icp-adjacent", "own")

REQUIRED_KEYS = (
    "schema",
    "id",
    "platform",
    "url",
    "channel",
    "origin",
    "fetched_at",
    "metrics",
    "analysis",
    "model",
)

# The nested objects the contract fixes, addressed dotted so an error can say
# WHICH object is short a key: "metrics.page_id" points at a line in the file,
# "page_id" leaves the operator to search. Ordered outermost-first, so a parent
# is proved to be an object before anything looks a child up inside it.
#
# `page_id` lives under `metrics` because the top level is closed. `variants`
# and `days_running` are counted by discover over one run's results, not read
# off the archive, and `active` is whether `ad_delivery_stop_time` was absent.
# `analysis.creative.kind` says which analysis path produced the record
# (`text-only`, `local-file`, or `authored` for our own); the rest of the
# creative block follows the prompt.
REQUIRED_NESTED = {
    "metrics": ("eu_total_reach", "days_running", "active", "variants", "page_id"),
    "analysis": (
        "copy",
        "hook",
        "structure",
        "offer",
        "proof",
        "cta",
        "objections",
        "creative",
    ),
    "analysis.copy": ("primary_text", "headline", "description", "link_caption", "words"),
    "analysis.hook": ("words", "text", "device"),
    "analysis.offer": ("type", "text"),
    "analysis.proof": ("type", "text"),
    "analysis.cta": ("type", "text"),
    "analysis.creative": ("kind",),
}

# Checked as lists because a model that returns one object where the contract
# asks for a list of them produces a record that validates key-by-key and then
# makes learn/ count one objection as none and one section as the whole shape.
REQUIRED_LISTS = (
    "analysis.structure",
    "analysis.objections",
)

# The id becomes half the filename, so it is checked rather than escaped: a
# slash would write the record outside the corpus entirely, and a space or a
# colon makes the file awkward to name. Ad Library ids arrive as digit strings
# and are prefixed `fb-` by discover; `fb-own-<segment>-<ad id>` by feedback.
ID_RE = re.compile(r"^[A-Za-z0-9._~-]+$")


class CorpusInvalid(ValueError):
    """A record that is not a complete schema-1 record.

    The message always names the offending key or value, because the caller is
    an operator looking at a directory of near-identical files.
    """


def _describe(record, source: Path | None) -> str:
    """How an error refers to the offending record.

    Its id where there is one, and the file it came from where there is one:
    with a few hundred files in the corpus, an error that does not say which
    one to open is barely an error at all.
    """
    if isinstance(record, dict) and isinstance(record.get("id"), str) and record["id"]:
        label = f"corpus record {record['id']!r}"
    else:
        label = "corpus record with no usable id"
    return f"{label} ({source})" if source is not None else label


def _resolve(record: dict, dotted: str):
    """Walk a dotted path. Only ever called once each parent has been proved
    present and object-shaped, so a KeyError here would be a bug in validate."""
    value = record
    for part in dotted.split("."):
        value = value[part]
    return value


def validate(record: dict, *, source: Path | None = None) -> None:
    """Raise CorpusInvalid unless `record` is a complete schema-1 record.

    Nothing is coerced and nothing is defaulted. A record missing a key is a bug
    in whatever produced it, and filling the key in here would bury that bug in
    a file that looks correct forever afterwards.
    """
    where = _describe(record, source)

    if not isinstance(record, dict):
        raise CorpusInvalid(
            f"{where} is not a JSON object; got {type(record).__name__}"
        )

    for key in REQUIRED_KEYS:
        if key not in record:
            raise CorpusInvalid(f"{where} is missing required key {key!r}")

    # Strict at the top level, permissive inside metrics and analysis. The top
    # level IS the contract, so an unknown key there means the writer and this
    # module disagree about the schema and `schema` should have been bumped;
    # inside analysis the shape follows the analysis prompt, which is expected
    # to grow fields without a schema bump - `outlier_ratio`, and the
    # `own_metrics` and `derived_from` blocks feedback writes, live there for
    # exactly that reason. Under metrics the archive's own lists
    # (`publisher_platforms`, `languages`, `countries`) ride along the same way.
    unexpected = sorted(set(record) - set(REQUIRED_KEYS))
    if unexpected:
        raise CorpusInvalid(
            f"{where} has unexpected key(s) {', '.join(repr(k) for k in unexpected)}; "
            f"schema {SCHEMA} defines exactly: {', '.join(REQUIRED_KEYS)}"
        )

    if record["schema"] != SCHEMA:
        raise CorpusInvalid(
            f"{where} has schema {record['schema']!r}; this module reads schema "
            f"{SCHEMA} only. Migrate the file or bump SCHEMA in engine/corpus.py - "
            f"guessing at an unknown version would mis-read every field after it."
        )

    for key, allowed in (("platform", PLATFORMS), ("origin", ORIGINS)):
        if record[key] not in allowed:
            raise CorpusInvalid(
                f"{where} has {key} {record[key]!r}; expected one of "
                f"{', '.join(allowed)}"
            )

    if not isinstance(record["id"], str) or not ID_RE.match(record["id"]):
        raise CorpusInvalid(
            f"{where} has id {record['id']!r}, which cannot be half a filename; "
            f"expected letters, digits, dot, underscore, tilde or hyphen only"
        )

    for dotted, keys in REQUIRED_NESTED.items():
        value = _resolve(record, dotted)
        if not isinstance(value, dict):
            raise CorpusInvalid(
                f"{where} key {dotted!r} must be a JSON object; got "
                f"{type(value).__name__}"
            )
        for key in keys:
            if key not in value:
                # Reported with the parent path attached, so the message names
                # the key the way the file is laid out.
                missing = f"{dotted}.{key}"
                raise CorpusInvalid(f"{where} is missing required key {missing!r}")

    for dotted in REQUIRED_LISTS:
        value = _resolve(record, dotted)
        if not isinstance(value, list):
            raise CorpusInvalid(
                f"{where} key {dotted!r} must be a list; got {type(value).__name__}"
            )


@dataclass(frozen=True)
class CorpusRecord:
    """One analysed ad, in memory.

    `metrics` and `analysis` stay plain dicts rather than nested dataclasses.
    `analysis` is the shape the analysis prompt returns, and pinning it into
    classes here would mean a second place to edit every time that prompt learns
    a field. What the frozen wrapper protects is the identity - id, platform,
    origin - that the filename and the de-duplication in load_all() depend on.
    """

    id: str
    platform: str
    url: str
    channel: str
    origin: str
    fetched_at: str
    metrics: dict
    analysis: dict
    model: str
    schema: int = SCHEMA

    @classmethod
    def from_dict(cls, record: dict, *, source: Path | None = None) -> CorpusRecord:
        validate(record, source=source)
        return cls(**{key: record[key] for key in REQUIRED_KEYS})

    def to_dict(self) -> dict:
        """The record as it goes to disk. Exactly what from_dict() was given, so
        a load/save cycle leaves the file byte-identical."""
        return asdict(self)


def _as_dict(record: CorpusRecord | dict) -> dict:
    """Both forms are accepted everywhere: the analyse and feedback steps
    assemble a dict, while learn and score hold CorpusRecords."""
    return record.to_dict() if isinstance(record, CorpusRecord) else record


def path_for(record: CorpusRecord | dict, root: Path | None = None) -> Path:
    """Where this record lives: `<platform>-<id>.json`, so `meta-ad-fb-123.json`.
    Validates first, because platform and id are the filename and a record that
    fails validation has no place to be."""
    data = _as_dict(record)
    validate(data)
    root = Path(root) if root else DEFAULT_ROOT
    return root / f"{data['platform']}-{data['id']}.json"


def save(record: CorpusRecord | dict, root: Path | None = None) -> Path:
    """Write the record and return its path.

    sort_keys and the trailing newline are the whole point of the file format:
    they make a re-analysis show up as a readable diff rather than as a
    reordered blob. ensure_ascii stays off so Danish and Lithuanian copy is
    still legible in review, matching the queue/ job files.
    """
    data = _as_dict(record)
    path = path_for(data, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load(path: Path) -> CorpusRecord:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"no corpus record at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Reported apart from the schema failures because the fix is different:
        # this file is not JSON at all, which in practice means a truncated
        # write or a merge conflict marker left in the tree.
        raise CorpusInvalid(f"{path} is not valid JSON: {exc}") from exc
    return CorpusRecord.from_dict(data, source=path)


def load_all(root: Path | None = None) -> list[CorpusRecord]:
    """Every record under `root`, ordered by id.

    Ordered by id rather than by filename so the corpus reads the same however
    the files came to be named, which is what makes learn/ and score/ produce
    the same patterns from the same evidence on every run.
    """
    root = Path(root) if root else DEFAULT_ROOT
    if not root.is_dir():
        raise FileNotFoundError(
            f"no corpus directory at {root}; research/corpus/.gitkeep is what "
            f"keeps it in the tree, so a missing directory means a bad checkout "
            f"rather than an empty corpus"
        )

    records: list[CorpusRecord] = []
    seen: dict[str, Path] = {}
    for path in sorted(root.rglob("*.json")):
        record = load(path)
        if record.id in seen:
            # Not a harmless duplicate: learn/ would median the same ad twice
            # when it weighs the evidence for a pattern, and score/ would let
            # one ad carry a pattern on its own. Name both files instead of
            # dropping whichever sorted second.
            raise CorpusInvalid(
                f"duplicate corpus id {record.id!r} in {seen[record.id]} and "
                f"{path}; one ad is one record, so delete or re-id whichever "
                f"is wrong"
            )
        seen[record.id] = path
        records.append(record)

    return sorted(records, key=lambda r: r.id)
