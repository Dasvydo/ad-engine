#!/usr/bin/env bash
# Push the current branch, surviving a push that landed while we were working.
#
# WHY THIS EXISTS. Every committing workflow here ends in `git push`, and a
# bare push fails outright when the remote moved in between:
#
#   ! [rejected]  main -> main (fetch first)
#
# That is not a hypothetical. On 2026-09-15 a research run discovered 192
# candidates, analysed them, wrote its selection and committed it - and the
# push was rejected because a capture-goldens run had landed seven seconds
# earlier. The runner was then torn down and the whole sweep was lost,
# including the YouTube quota it had already spent. The job went red with a git
# hint as its only explanation, which reads like nothing the pipeline did.
#
# The crons are spaced an hour apart so they do not collide on their own, but
# any `go` tap during a scheduled run, or any two manual dispatches, will.
#
# WHAT IT DOES. Rebases onto the remote and tries again, a bounded number of
# times. Rebase rather than merge: these jobs append committed OUTPUTS - a
# corpus record, a measurement row, a job file - and replaying them on top of
# whatever else landed is exactly right. Nothing here edits a file another
# workflow is also editing, so a conflict means something genuinely unexpected
# and stops rather than being resolved blindly.
#
# WHAT IT DELIBERATELY DOES NOT DO. No --force, ever, under any failure. These
# workflows push to the default branch; a force push there would discard
# somebody else's commit to make a cron green, which is the worst possible
# trade. A conflict or an exhausted retry exits nonzero and the job goes red
# with a real reason.
set -euo pipefail

ATTEMPTS="${PUSH_ATTEMPTS:-4}"

# Named explicitly rather than relying on an upstream being configured.
# actions/checkout leaves a branch checked out for the workflows here, but
# `git push` with no argument fails outright on a detached HEAD, and that is a
# confusing way to discover a checkout changed shape.
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" = "HEAD" ]; then
  echo "::error::Detached HEAD - nothing to push to. The checkout step did not"
  echo "::error::leave a branch, so this job has no branch to update."
  exit 1
fi

for attempt in $(seq 1 "$ATTEMPTS"); do
  if git push origin "$BRANCH"; then
    [ "$attempt" -gt 1 ] && echo "::notice::Pushed on attempt $attempt of $ATTEMPTS, after another workflow landed first."
    exit 0
  fi

  if [ "$attempt" -eq "$ATTEMPTS" ]; then
    echo "::error::Push rejected $ATTEMPTS times. Something is pushing to this"
    echo "::error::branch faster than this job can rebase onto it. What this"
    echo "::error::job produced is committed locally and will be lost with the"
    echo "::error::runner - re-run it once the other workflow has finished."
    exit 1
  fi

  echo "::notice::Push rejected; the remote moved while this job was working."
  echo "::notice::Rebasing and retrying (attempt $attempt of $ATTEMPTS)."

  # A rebase that cannot apply cleanly is left aborted, so the working tree is
  # not half-rebased when the job exits. Two workflows writing the same file is
  # a design problem to look at, not something to resolve automatically at
  # 05:00 on a Monday.
  if ! git pull --rebase origin "$BRANCH"; then
    git rebase --abort || true
    echo "::error::Rebase onto the updated branch hit a conflict, so this job"
    echo "::error::stopped rather than guessing. Two workflows wrote the same"
    echo "::error::file; the run that lost the race is this one, and what it"
    echo "::error::produced is in its log above."
    exit 1
  fi
done
