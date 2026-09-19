#!/usr/bin/env bash
# One-time repository setup, as a script rather than a click-path.
#
# WHY THIS EXISTS. docs/SECRETS.md describes four labels, three secrets and one
# variable that every workflow here depends on, and a missing one fails at a
# different place each time: a missing label fails the step that adds it, a
# missing secret fails the guard at the top of the run, a missing VARIABLE
# fails nothing at all and quietly disables the token countdown. Setting them
# by hand is about twenty minutes of clicking through two settings pages, and
# the failure mode of clicking is pasting the date into Secrets instead of
# Variables - which cannot be seen afterwards, because a secret is write-only
# once saved.
#
# So: run this instead. It is idempotent, it prints what it did, and it says
# what it could NOT do rather than pretending the setup is complete.
#
#   bash tools/setup_github.sh            # create what is missing, report the rest
#   bash tools/setup_github.sh --check    # change nothing; report what is missing
#
# It needs the `gh` CLI, authenticated as somebody with admin on the
# repository. It never prints a secret's value, and it reads every value from
# a prompt rather than from an argument, so nothing lands in your shell
# history.
set -euo pipefail

REPO="${REPO:-Dasvydo/ad-engine}"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

command -v gh >/dev/null || {
  echo "gh is not installed. https://cli.github.com, then: gh auth login" >&2
  exit 1
}

say() { printf '  %s\n' "$*"; }
missing=0

# --------------------------------------------------------------------------
# Labels. The two taps are `go`, twice; `no` rejects; the two stage labels
# mirror the queue directory and are never the authority on stage - only the
# directory can tell the two identical `go` payloads apart.
# --------------------------------------------------------------------------
echo "Labels"
add_label() {
  local name="$1" colour="$2" desc="$3"
  if gh label list --repo "$REPO" --json name --jq '.[].name' 2>/dev/null | grep -qx "$name"; then
    say "ok       $name"
    return
  fi
  missing=$((missing + 1))
  if [ "$CHECK" = 1 ]; then say "MISSING  $name"; return; fi
  gh label create "$name" --repo "$REPO" --color "$colour" --description "$desc" >/dev/null
  say "created  $name"
}
add_label go             "0e8a16" "You approve. Added by a human, twice - once per tap"
add_label no             "b60205" "You reject. Closes the issue and returns the segment to the backlog"
add_label stage:copy     "1d76db" "Awaiting copy approval. Mirrors queue/proposed/"
add_label stage:creative "5319e7" "Awaiting launch. Mirrors queue/built/"

# --------------------------------------------------------------------------
# Secrets. Never echoed, never passed as an argument. `gh secret set` reads
# stdin, so the value never reaches the process table or the history file.
# --------------------------------------------------------------------------
echo
echo "Secrets"
have_secret() { gh secret list --repo "$REPO" --json name --jq '.[].name' 2>/dev/null | grep -qx "$1"; }
add_secret() {
  local name="$1" what="$2"
  if have_secret "$name"; then say "ok       $name"; return; fi
  missing=$((missing + 1))
  if [ "$CHECK" = 1 ]; then say "MISSING  $name  - $what"; return; fi
  say "$name is not set. $what"
  printf '  paste it (input hidden, blank to skip): '
  read -rs value; echo
  if [ -z "$value" ]; then say "skipped  $name"; return; fi
  printf '%s' "$value" | gh secret set "$name" --repo "$REPO" >/dev/null
  say "set      $name"
  unset value
}
add_secret GEMINI_API_KEY \
  "free, no card: aistudio.google.com. Read by research.yml, propose.yml, and build.yml on a reel job."
add_secret META_ACCESS_TOKEN \
  "Meta developer app with the Ad Library API product added, after identity verification at facebook.com/ID."
add_secret REEL_ENGINE_TOKEN \
  "a fine-grained PAT, Contents: read, scoped to Dasvydo/reel-engine ONLY. build.yml checks that repo out to render the creative."

# --------------------------------------------------------------------------
# The variable. This is the one that is silently wrong when it is set in the
# wrong tab: a date is not a credential, and the countdown needs it VISIBLE so
# a rotation can be checked against it. Set as a secret, it warns nobody ever.
# --------------------------------------------------------------------------
echo
echo "Variable (NOT a secret - a different tab, on purpose)"
if gh variable list --repo "$REPO" --json name --jq '.[].name' 2>/dev/null | grep -qx META_TOKEN_ISSUED; then
  say "ok       META_TOKEN_ISSUED = $(gh variable get META_TOKEN_ISSUED --repo "$REPO" 2>/dev/null || echo '?')"
else
  missing=$((missing + 1))
  if [ "$CHECK" = 1 ]; then
    say "MISSING  META_TOKEN_ISSUED - the day META_ACCESS_TOKEN was issued, YYYY-MM-DD"
  else
    say "META_TOKEN_ISSUED is the day META_ACCESS_TOKEN was issued, as YYYY-MM-DD."
    say "Set it in the SAME visit as the token, or the countdown runs from the wrong day."
    printf '  date (blank to skip): '
    read -r issued
    if [ -n "$issued" ]; then
      gh variable set META_TOKEN_ISSUED --repo "$REPO" --body "$issued" >/dev/null
      say "set      META_TOKEN_ISSUED = $issued"
    else
      say "skipped  META_TOKEN_ISSUED"
    fi
  fi
fi

# --------------------------------------------------------------------------
# What no script can do.
# --------------------------------------------------------------------------
echo
echo "Not settable from here - open these yourself"
say "Spending limit \$0: github.com/settings/billing - this is what turns the"
say "  \$0.00 claim in docs/COST.md from a claim into a guarantee. With it at"
say "  zero an Actions overage STOPS runs instead of billing for them."
say "Gemini key's Cloud project must have NO billing account attached, or the"
say "  free tier silently bills at paid rates with no 429 and no warning."

echo
if [ "$missing" = 0 ]; then
  echo "Everything this script can check is set."
else
  echo "$missing item(s) still missing. Re-run without --check to set them."
  [ "$CHECK" = 1 ] && exit 1
fi
