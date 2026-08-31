"""Meta audience construction.

The central problem: this ICP is ~700-800 firms. No interest-based Meta audience
can find "Danish accounting firms with 10+ staff" - Meta has no such targeting,
and a ~750-company audience is far below what its optimiser needs.

The answer is not to give up on Meta, it is to stop asking Meta to do the
targeting. outreach-engine already produces the exact list. Upload it as a
Custom Audience and Meta becomes account-based air cover over outreach rather
than a prospecting channel in its own right.

  ~750 firms x 2-3 contacts = ~2,000 people, comfortably over Meta's 1,000
  minimum for a usable Custom Audience.

Meta requires every PII field SHA-256 hashed after normalisation. Hashing here
means the raw list never leaves this machine.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

MIN_CUSTOM_AUDIENCE = 1_000   # Meta's floor for delivery
MIN_LOOKALIKE_SEED = 100      # Meta's floor for a lookalike source


def normalise_email(email: str) -> str:
    """Meta's spec: trim, lowercase. No other transformation."""
    return email.strip().lower()


def hash_field(value: str) -> str:
    """SHA-256 hex of a normalised value, as Meta requires."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AudienceBuild:
    path: Path
    rows: int

    @property
    def usable(self) -> bool:
        return self.rows >= MIN_CUSTOM_AUDIENCE

    @property
    def warning(self) -> str:
        if self.usable:
            return ""
        return (
            f"{self.rows} rows is below Meta's {MIN_CUSTOM_AUDIENCE:,} minimum for a "
            f"Custom Audience. Meta will accept the upload and then under-deliver or "
            f"refuse to serve. Widen the source list, or use this as a lookalike seed "
            f"({MIN_LOOKALIKE_SEED} minimum) instead of a direct target."
        )


def from_outreach_csv(src: Path, out: Path) -> AudienceBuild:
    """Turn an outreach-engine campaign CSV into a hashed Meta Custom Audience.

    Reads the columns outreach-engine writes and emits Meta's expected headers.
    Country is included because it materially improves match rate.
    """
    src, out = Path(src), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    rows = 0

    with src.open(encoding="utf-8") as fh, out.open("w", newline="", encoding="utf-8") as wh:
        reader = csv.DictReader(fh)
        writer = csv.writer(wh)
        writer.writerow(["email", "fn", "ln", "country"])

        for row in reader:
            email = normalise_email(row.get("email", ""))
            if not email or email in seen:
                continue
            seen.add(email)
            writer.writerow([
                hash_field(email),
                hash_field(row.get("firstName", "").strip().lower()),
                hash_field(row.get("lastName", "").strip().lower()),
                hash_field(row.get("country", "").strip().lower()),
            ])
            rows += 1

    return AudienceBuild(out, rows)
