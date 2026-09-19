"""The workflow files carry findings that are expensive to rediscover.

Ported from reel-engine/tests/test_workflows.py, which learned each of them the
hard way, and re-pointed at what is different here: two taps instead of three,
a creative that is rendered in a SIBLING repository rather than in this one, a
Meta token in place of a YouTube key, and a launch that carries an ad id a human
typed.

The three the sibling paid for in production:

  Without `if: github.event.label.name == ...`, adding `no` starts a build.
  Without a `permissions` block, GITHUB_TOKEN cannot write.
  With the default concurrency, a `no` tap silently cancels a render.

And two this repository adds:

  The one thing in this loop that opens a browser is build.yml, inside the
  reel-engine checkout. A `playwright install` anywhere else is pure cost on
  every run, forever, for a browser nothing opens.
  `--budget 150` leaves 50 Ad Library calls of the hour for the re-run that a
  red Monday asks for. A sweep that spends the whole hour cannot be re-run
  until the next one.
"""
import ast
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SIBLING = ROOT.parent / "reel-engine"

# The four that open, label or close an approval issue. They need issues:write.
NAMES = ["propose.yml", "build.yml", "launch.yml", "reject.yml"]

# The two that fire on `issues.labeled`. launch.yml is deliberately NOT one of
# them: the second half of a launch carries a number - the Ad ID column in Ads
# Manager - and no label can carry a number, so it is a dispatch with a form.
LABEL_TRIGGERED = ["build.yml", "reject.yml"]

# Every workflow that commits to the default branch, for the rules that bind
# all of them. research.yml and measure.yml commit files and open nothing, so
# they are deliberately NOT in NAMES - granting them issues:write to satisfy a
# test would be the test making the workflows worse. They still have to parse,
# still have to serialise, still have to cap their minutes and still may not
# call `gh`.
#
# Note what went wrong in the sibling and is being avoided here: research.yml
# was for a while absent from BOTH lists, which reads like a decision and was
# not one - it simply meant a scheduled workflow that pushes to the default
# branch was bound by no rule in the file at all. A workflow left out of a
# parametrized list fails nothing, which is the only kind of gap in a test
# suite that is invisible. test_the_hand_kept_lists_name_files_that_exist
# catches a rename; test_every_committing_workflow_is_under_these_rules catches
# the omission.
ALL_WORKFLOWS = ["research.yml", "propose.yml", "build.yml", "launch.yml",
                 "reject.yml", "measure.yml"]

# Discovered, not hand-kept, and deliberately a different list. The rules above
# are about what one named workflow does, so naming them is right. The timeout
# rule is about what ANY job costs when it hangs, and a list would only ever
# bind the files somebody remembered to add. tests.yml is already outside
# ALL_WORKFLOWS - it commits nothing and opens nothing - and it can hang
# exactly like the rest.
EVERY_WORKFLOW = sorted(path.name for path in WORKFLOWS.glob("*.yml"))

# What "this workflow writes to the branch" looks like in a run: body. Both
# forms, because the bare `git push` is replaced by a script that rebases and
# retries, and matching only the old spelling would quietly drop every
# committing workflow out of the rules below - the same silent-omission failure
# test_every_committing_workflow_is_under_these_rules exists to catch.
PUSHES = re.compile(r"git push|push_with_retry\.sh")


def parsed(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def text_of(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def triggers(workflow: dict) -> dict:
    """`on` is the YAML 1.1 boolean True, so PyYAML keys it as True, not "on"."""
    return workflow.get("on", workflow.get(True))


def steps_of(name: str, job: str | None = None) -> list:
    jobs = parsed(name)["jobs"]
    return jobs[job or next(iter(jobs))]["steps"]


def step_with(name: str, step_id: str) -> dict:
    return next(s for s in steps_of(name) if s.get("id") == step_id)


def scripts_of(name: str) -> list:
    """Every `run:` body in the file. NOT the raw text.

    That distinction is not free. The sibling's version of this started as a
    substring search over the whole file, which is the obvious way to write it
    and quietly wrong: the first workflow added afterwards MENTIONED `git push`
    in a comment explaining why it would never do one, and was duly ordered to
    declare contents: write for a push it does not make. Four files here carry
    a comment saying they install no browser; a test that cannot tell a command
    from a comment about that command would fail all four.
    """
    return [
        step.get("run") or ""
        for job in (parsed(name).get("jobs") or {}).values()
        for step in (job.get("steps") or [])
    ]


def commands_in(script: str) -> str:
    """One run body with its comment lines removed - what actually executes.

    commands_of() is the whole file, which is right for "this workflow never
    does X" and wrong for "this step passes this flag": propose.yml carries
    `echo "::error::--segment ID"` in another step, and that would satisfy a
    substring search as happily as a comment does.
    """
    return "\n".join(line for line in script.splitlines()
                     if not line.strip().startswith("#"))


def commands_of(name: str) -> str:
    """Every run body with its comment lines removed - what actually executes."""
    return "\n".join(commands_in(script) for script in scripts_of(name))


# --------------------------------------------------------------------------
# The rules that bind every file.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", EVERY_WORKFLOW)
def test_it_parses(name):
    assert isinstance(parsed(name), dict)


def test_the_hand_kept_lists_name_files_that_exist():
    """A rename would otherwise go stale as a dozen confusing failures."""
    for listed in (ALL_WORKFLOWS, NAMES, LABEL_TRIGGERED):
        missing = sorted(set(listed) - set(EVERY_WORKFLOW))
        assert not missing, "a list names files not on disk: %s" % missing


def test_every_workflow_the_contract_names_is_on_disk():
    """The seven in docs/CONTRACTS.md's Workflows table, by name.

    A workflow that was never written fails nothing anywhere else: there is no
    file to parse, no job to cap and no permission to check, so every
    parametrized rule in here simply has one fewer case.
    """
    assert EVERY_WORKFLOW == sorted(
        ["tests.yml", "research.yml", "propose.yml", "build.yml",
         "launch.yml", "reject.yml", "measure.yml"])


def test_every_committing_workflow_is_under_these_rules():
    """The other half of the rename check: a file on disk that nothing names.

    ALL_WORKFLOWS is hand-kept because the rules it drives are about what a
    named workflow does, and that is right. What it cannot do by itself is
    notice an omission - a new workflow that pushes to the default branch and
    is in no list fails nothing here, so the gap looks exactly like a pass.

    So the membership itself is derived: anything that runs `git push` writes
    to the branch every other job checks out, which is the whole reason the
    permissions, concurrency and `gh` rules exist. tests.yml pushes nothing and
    holds `contents: read`, so it stays outside and outside is visible.
    """
    pushes = sorted(
        name for name in EVERY_WORKFLOW
        if any(PUSHES.search(script) for script in scripts_of(name))
    )
    unbound = sorted(set(pushes) - set(ALL_WORKFLOWS))
    assert not unbound, (
        "%s push to the default branch but are in no list in this file, so "
        "none of the rules below bind them" % unbound)
    assert set(pushes) == set(ALL_WORKFLOWS), (
        "ALL_WORKFLOWS names %s, but the files that actually push are %s"
        % (sorted(ALL_WORKFLOWS), pushes))


def test_no_workflow_pushes_without_surviving_a_lost_race():
    """A bare `git push` throws away everything the run just did.

    MEASURED in the sibling repository, on 2026-09-15: a research run
    discovered 192 candidates, spent the quota, committed its selection - and
    the push was rejected because another workflow had landed seven seconds
    earlier. The runner was torn down and the sweep was gone, with git's own
    "fetch first" hint as the job's only explanation.

    The crons here are an hour apart so they do not collide by themselves, but
    a `go` tap during a scheduled run does, and so does any second dispatch.
    Every push therefore goes through tools/push_with_retry.sh, which rebases
    and tries again, and never force-pushes.
    """
    for name in EVERY_WORKFLOW:
        for script in scripts_of(name):
            if "git push" in script:
                assert "push_with_retry.sh" in script, (
                    "%s pushes with a bare `git push`. A run that loses a race "
                    "to the branch will be discarded whole, with the Ad Library "
                    "calls it already spent. Use tools/push_with_retry.sh."
                    % name)


@pytest.mark.parametrize("name", EVERY_WORKFLOW)
def test_every_job_caps_the_minutes_it_can_burn(name):
    """GitHub's default is 360 minutes: 18% of the 2,000-minute month on one
    hung job, and the minute budget is this repository's central invariant.

    Nothing else stops one. A headless Chromium that never exits, a Gemini
    request that never returns and a stalled Graph API read all look identical
    to a job still working, so the runner holds until the default expires.
    Every other limit in docs/COST.md fails closed with a 429 or a 403; this is
    the one that fails by spending.

    Parametrized over what is on disk rather than over a list, so an eighth
    workflow cannot land without a cap.
    """
    for job_name, job in parsed(name)["jobs"].items():
        timeout = job.get("timeout-minutes")
        assert timeout is not None, (
            "%s job %r declares no timeout-minutes, so it inherits GitHub's "
            "360-minute default" % (name, job_name))
        assert isinstance(timeout, int) and not isinstance(timeout, bool), (
            "%s job %r must give timeout-minutes a plain number of minutes; "
            "got %r" % (name, job_name, timeout))
        assert 0 < timeout < 360, (
            "%s job %r sets timeout-minutes: %r, which is not below the "
            "360-minute default and so caps nothing" % (name, job_name, timeout))


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_every_workflow_can_write_the_files_it_commits(name):
    assert parsed(name)["permissions"]["contents"] == "write"


def test_the_suite_workflow_reports_and_writes_nothing():
    """tests.yml is the one file on the other side of that line, and it should
    stay there. It commits nothing, opens no issue and closes none."""
    assert parsed("tests.yml")["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("name", NAMES)
def test_the_issue_workflows_can_write_issues(name):
    assert parsed(name)["permissions"]["issues"] == "write"


def test_research_is_not_granted_issue_access_it_does_not_use():
    """Least privilege, stated as a test so nobody grants it to pass one.

    research.yml commits three files and opens no issue. The obvious way to
    bring it under test_the_issue_workflows_can_write_issues would be to add
    issues:write - a test making the thing it tests worse. The handoff to a
    human is propose.yml reading the committed report, which needs no new
    permission anywhere because propose already has issues:write.
    """
    assert "issues" not in parsed("research.yml")["permissions"]


def test_measure_is_not_granted_issue_access_it_does_not_use():
    """The same call, made again rather than inherited, for the same reason.

    measure.yml runs engine.measure and engine.feedback and commits what they
    wrote. It opens no issue and closes none: a measurement is read back off
    our own ad account, not approved, so there is nothing in this workflow for
    a human to tap. Adding issues:write would widen, for the sake of a green
    parametrize, the permissions of a scheduled job that carries an access
    token.
    """
    assert "issues" not in parsed("measure.yml")["permissions"]


def _concurrency(workflow: dict) -> dict:
    """Wherever it is declared. research, propose and measure are cron-driven
    with no siblings racing them, so they keep a workflow-level group."""
    if "concurrency" in workflow:
        return workflow["concurrency"]
    groups = [j["concurrency"] for j in workflow["jobs"].values()
              if "concurrency" in j]
    assert groups, "no concurrency declared at workflow or job level"
    return groups[0]


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_concurrency_never_cancels(name):
    """The default queue keeps only one pending run, so a second tap would
    silently cancel work already under way - a sweep that has charged its Ad
    Library calls, or a build most of the way through an encode."""
    assert _concurrency(parsed(name))["cancel-in-progress"] is False


def test_only_the_suite_cancels_a_run_that_is_already_going():
    """And it should, which is why the rule above is scoped to the committing
    six. A test run holds nothing: push twice in a minute and the first run is
    answering a question nobody is asking any more."""
    assert _concurrency(parsed("tests.yml"))["cancel-in-progress"] is True


@pytest.mark.parametrize("name", LABEL_TRIGGERED)
def test_label_triggered_concurrency_is_declared_on_the_job(name):
    """Observed in the sibling, not theorised: a `no` tap cancelled a render.

    Every label event starts a run of every label-triggered workflow - the
    `if:` gates the job, not the trigger. A workflow-level group is acquired by
    the RUN, so the runs that were only ever going to skip still queue in it,
    and GitHub cancels the older pending run when another arrives. A skipped
    job never acquires the slot, so the group keeps serialising the work that
    actually touches this issue without the no-ops competing for it.
    """
    workflow = parsed(name)
    assert "concurrency" not in workflow, (
        "%s declares concurrency at workflow level; a run that skips its job "
        "would still hold the group and can cancel a real one" % name)
    for job_name, job in workflow["jobs"].items():
        assert "concurrency" in job, "%s job %r has no concurrency" % (name, job_name)
        assert job["concurrency"]["group"] == "ad-${{ github.event.issue.number }}", (
            "%s job %r must share the per-issue group so build and reject "
            "cannot both commit to queue/ at once" % (name, job_name))


def test_a_launch_shares_the_group_with_the_taps_on_the_same_issue():
    """launch.yml is a dispatch, so it cannot key off the event's issue - it
    keys off the issue number in its own form instead. Same group, same
    serialisation: a `no` tapped while a launch is running would otherwise be
    deleting the job file the launch is moving."""
    job = next(iter(parsed("launch.yml")["jobs"].values()))
    assert job["concurrency"]["group"] == "ad-${{ inputs.issue }}"
    assert job["concurrency"]["cancel-in-progress"] is False


@pytest.mark.parametrize("name", LABEL_TRIGGERED)
def test_every_label_triggered_job_guards_on_the_label_name(name):
    """Without this, adding `no` also starts a build."""
    workflow = parsed(name)
    assert list(triggers(workflow)["issues"]["types"]) == ["labeled"]
    for job_name, job in workflow["jobs"].items():
        condition = job.get("if", "")
        assert "github.event.label.name" in condition, (
            "%s job %r has no label guard" % (name, job_name))


def test_build_and_launch_discriminate_the_stages():
    """The two taps that move an ad are not the same event, and the difference
    is not in the payload.

    `go` on a proposal means "build the creative"; the ad id arriving later
    means "it is live". build.yml uses the stage label as a cheap pre-filter so
    the wrong tap does not boot a runner, and `approval resolve --expect
    proposed` as the authority - the directory is what knows the stage.
    launch.yml has no label at all: `approval launch` refuses anything that is
    not in queue/built/, which is the same discrimination made by the module
    instead of by the YAML.
    """
    build = text_of("build.yml")
    assert "stage:copy" in build and "--expect proposed" in build

    launch = text_of("launch.yml")
    assert "approval launch" in commands_of("launch.yml")
    assert "--expect" not in commands_of("launch.yml"), (
        "launch resolves no issue to a stage; it is handed a segment and an "
        "ad id, and the stage check belongs to engine/approval.py")
    assert "queue/built" in launch, (
        "nothing in launch.yml says which stage a launch may start from")


def test_reject_fires_on_no_and_not_on_go():
    reject = parsed("reject.yml")
    condition = next(iter(reject["jobs"].values()))["if"]
    assert "'no'" in condition
    assert "'go'" not in condition


def test_nothing_calls_gh_directly():
    """The seam only holds if the transport is swappable in Python. A `gh` call
    in YAML is a Telegram bridge's problem later.

    engine/approval.py's GitHubIssues shells out to `gh` itself, behind a
    `runner=` a test replaces; that is the one place it is allowed to live.
    """
    for name in EVERY_WORKFLOW:
        for line in text_of(name).splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not stripped.startswith("gh "), (
                "%s calls gh directly: %s" % (name, stripped))


@pytest.mark.parametrize("name", EVERY_WORKFLOW)
def test_no_expression_is_interpolated_into_a_run_body(name):
    """Values arrive through `env:`, never spliced into the script text.

    A `${{ }}` in a run body is substituted by the runner BEFORE bash sees the
    line, so the result is whatever the value happened to contain - a quote, a
    newline, a `;` - pasted into a shell script as code. An object that is not
    a string arrives as the literal `[object Object]`, which is a value no
    guard in the script can recognise and no error message ever explains.

    Every workflow here already does it the other way (`MAX_ADS: ${{
    inputs.max_ads }}` and then `"$MAX_ADS"`), and the reason it is worth a
    test rather than a habit is that the safe form and the unsafe form look
    almost identical in review, on a line that reads as obviously correct.

    `if:` and `with:` are untouched by this: they are expression contexts by
    definition, evaluated as values, and never handed to a shell.
    """
    for job_name, job in parsed(name)["jobs"].items():
        for step in job["steps"]:
            run = str(step.get("run", ""))
            offenders = [line for line in run.splitlines() if "${{" in line]
            assert not offenders, (
                "%s job %r step %r splices an expression into its script; "
                "pass it through env: instead: %s"
                % (name, job_name, step.get("name", step.get("id")), offenders))


@pytest.mark.parametrize("name", EVERY_WORKFLOW)
def test_nothing_commits_the_whole_research_directory(name):
    """`git add research` would commit somebody else's creative.

    research/media/ is where an operator hand-saves a competitor's video or
    image so the model can watch it. .gitignore covers .mp4, .mov, .m4v and
    .webm; engine/analyse.py also accepts .jpg, .jpeg, .png and .webp, so the
    ignore list does NOT cover everything the pipeline reads, and the two
    workflows that write under research/ name their outputs instead. The gap is
    easy to close the wrong way - adding four globs to .gitignore looks like
    the fix and only narrows the hole - so the rule lives where the add
    happens.
    """
    for line in text_of(name).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert stripped.rstrip("/") != "git add research", (
            "%s adds the whole of research/, which would commit whatever is "
            "sitting in research/media/: %s" % (name, stripped))


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_a_pushing_job_reports_the_minutes_it_spent(name):
    """The minute budget is the central invariant, and every committing job is
    where it drifts.

    timeout-minutes caps the worst case. This is the other half: what the job
    ACTUALLY costs, in the run summary, every time. docs/COST.md's per-job
    figures are estimates and say so; these are the measurements that replace
    them. The sibling required this of scheduled jobs only; here it binds every
    job that pushes, because the label-triggered ones are the expensive ones -
    build.yml downloads a browser and encodes a video.

    First step and last step, specifically: a stamp taken after the install
    would exclude the largest cost of the cheapest job, and a report that is
    not `if: always()` would go missing on exactly the failing runs whose
    minutes still get billed.
    """
    for job_name, job in parsed(name)["jobs"].items():
        steps = job["steps"]
        assert "JOB_STARTED=" in str(steps[0].get("run", "")), (
            "%s job %r does not stamp JOB_STARTED in its first step, so any "
            "elapsed time it reports excludes the install" % (name, job_name))

        last = steps[-1]
        assert "JOB_STARTED" in str(last.get("run", "")), (
            "%s job %r does not report its elapsed minutes last" % (name, job_name))
        assert "GITHUB_STEP_SUMMARY" in str(last.get("run", "")), (
            "%s job %r computes its minutes and never shows them" % (name, job_name))
        assert last.get("if") == "always()", (
            "%s job %r skips its own cost report on the runs that fail, which "
            "are billed the same as the ones that work" % (name, job_name))


@pytest.mark.parametrize("name", ALL_WORKFLOWS)
def test_a_pushing_job_checks_out_a_branch_not_a_detached_head(name):
    """`issues` events check out github.sha detached, so `git push` would fail
    with a message about not being on a branch - which reads like a broken
    workflow rather than a checkout that never had a branch.

    A schedule and a workflow_dispatch both leave a branch checked out, so
    those files take the plain checkout. tools/push_with_retry.sh is the
    runtime guard either way: it names the detached HEAD rather than letting
    git's hint explain it.
    """
    workflow = parsed(name)
    job = next(iter(workflow["jobs"].values()))
    checkout = next(
        step for step in job["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout")
    )
    if "issues" in (triggers(workflow) or {}):
        assert "ref" in checkout.get("with", {}), (
            "%s checks out a detached HEAD but pushes" % name)


# --------------------------------------------------------------------------
# The browser. One repository renders, and it is not this one.
# --------------------------------------------------------------------------


def test_only_the_build_installs_a_browser():
    """Nothing in ad-engine renders, so a Chromium anywhere but build.yml is a
    download paid for on every run for a browser nothing opens.

    Four files carry a COMMENT saying they install no browser, which is the
    point of them, so this reads the commands rather than the text - the same
    distinction scripts_of() exists for.
    """
    for name in EVERY_WORKFLOW:
        if name == "build.yml":
            continue
        assert "playwright" not in commands_of(name), (
            "%s installs a browser. Nothing in this repository renders: the "
            "video and the still are shot by reel-engine, inside build.yml's "
            "sibling checkout." % name)


def test_the_suite_installs_no_browser():
    """Named on its own because reel-engine's tests.yml DOES install one, and
    copying that file across without thinking is the obvious mistake.

    There it is load-bearing: six committed golden frames are compared byte for
    byte and cannot be rendered without a Chromium, which is also why that file
    pins runs-on by name. There are no golden frames here and nothing to
    rasterise, so both the browser and the pinned image are cost with no
    corresponding check.
    """
    assert "playwright" not in commands_of("tests.yml")
    assert "python -m pytest" in commands_of("tests.yml")


def test_the_browser_is_installed_only_on_the_reel_path():
    """A copy-only ad shoots nothing, so it must not pay for a browser."""
    step = next(s for s in steps_of("build.yml")
                if "playwright" in str(s.get("run", "")))
    assert step.get("if") == "steps.creative.outputs.kind == 'reel'", (
        "build.yml downloads Chromium for every ad, including the ones with no "
        "video to shoot")


# --------------------------------------------------------------------------
# research.yml - the weekly sweep.
# --------------------------------------------------------------------------


def _cron_fields(name: str) -> list:
    return [entry["cron"].split() for entry in triggers(parsed(name))["schedule"]]


def test_a_pinned_number_is_read_from_the_command_not_from_its_comment(
        tmp_path, monkeypatch):
    """The two tests below pin a number the workflow also spells out in prose.

    Measured, not feared: `args=(--budget 200)` under an untouched
    `# --budget 150, not the module default of 200.` and `args=(--retries 1 ...)`
    under an untouched `# --retries 2, ...` both left this whole file green,
    because those tests read the raw run body and the comment alone satisfied
    the substring. So the pins this module advertises bound nothing.

    This runs those two tests against exactly those mutations and requires
    them to go red. It is a guard on the reading, not on the numbers: if
    either test goes back to step_with(...)["run"], the pin is decorative
    again and this fails.
    """
    # Read from the real directory throughout: WORKFLOWS is redirected below,
    # and the second pass would otherwise look for its workflow in tmp_path.
    on_disk = WORKFLOWS
    for name, real, mutated, pinned in (
            ("research.yml", "--budget 150", "--budget 200",
             test_the_scheduled_sweep_stays_under_the_hour_it_shares),
            ("propose.yml", "--retries 2", "--retries 1",
             test_propose_still_falls_back_to_the_backlog)):
        text = (on_disk / name).read_text(encoding="utf-8")
        broken = text.replace("args=(%s" % real, "args=(%s" % mutated)
        assert broken != text, (
            "%s no longer opens its args array with %s, so this guard mutates "
            "nothing - re-point it at how the flag is spelled now"
            % (name, real))
        assert real in broken, (
            "%s no longer names %s in a comment, so the raw body would catch "
            "this on its own and this guard has nothing left to prove"
            % (name, real))
        (tmp_path / name).write_text(broken, encoding="utf-8")
        monkeypatch.setattr(sys.modules[__name__], "WORKFLOWS", tmp_path)
        with pytest.raises(AssertionError):
            pinned()


def test_the_scheduled_sweep_stays_under_the_hour_it_shares():
    """--budget 150, not the module default of 200.

    200 calls an hour is the reported Ad Library allowance and what
    engine/discover.py's ledger defaults to. The ledger is charged BEFORE the
    socket opens and refuses what it cannot afford, so the budget decides
    whether a run can happen at all - and a sweep that spends the whole hour
    leaves the same-hour re-run, which is the ordinary response to a red
    Monday, with nothing to spend.

    150 leaves 50, which is four times what the shipped research/seeds.yaml
    costs at its ceiling (6 searches, 12 calls at two pages each).
    """
    # The commands, not the comment above them. This read the raw body until
    # a scratch copy showed why that was worth nothing: research.yml's comment
    # spells the flag out, so `args=(--budget 200)` under an untouched
    # `# --budget 150, ...` left the whole file green.
    run = commands_in(step_with("research.yml", "research")["run"])
    assert "--budget 150" in run, (
        "the sweep does not cap its Ad Library spend at 150 calls, so a re-run "
        "in the same hour may be refused before it starts")


def test_the_sweep_passes_its_dispatch_inputs_through_env():
    step = step_with("research.yml", "research")
    assert step["env"]["MAX_ADS"] == "${{ inputs.max_ads }}"
    assert step["env"]["DRY_RUN"] == "${{ inputs.dry_run }}"
    assert "--max-ads" in step["run"] and "--dry-run" in step["run"]


def test_the_sweep_commits_what_it_produced_before_it_goes_red():
    """A nonzero exit means "a stage could not run", never "nothing was
    produced". A discovery that was refused still leaves a corpus that learned
    and concepts that scored, and engine/fanout.py writes
    research/selection.json on every live run including a failed one.
    """
    steps = steps_of("research.yml")
    assert step_with("research.yml", "research").get("continue-on-error") is True

    committed = next(i for i, s in enumerate(steps)
                     if "git commit" in str(s.get("run", "")))
    raised = next(i for i, s in enumerate(steps)
                  if "outcome == 'failure'" in str(s.get("if", "")))
    assert committed < raised, (
        "the failure must be re-raised after the sweep's outputs are committed")


def test_the_sweep_commits_its_outputs_by_name():
    step = next(s for s in steps_of("research.yml")
                if "git commit" in str(s.get("run", "")))
    for produced in ("research/corpus", "research/patterns.json",
                     "research/selection.json"):
        assert produced in step["run"], "the commit step never names %s" % produced
    staged = [line for line in step["run"].splitlines()
              if not line.strip().startswith("#")]
    assert "research/media" not in "\n".join(staged)
    assert "git diff --cached --quiet" in step["run"], (
        "a dry run and a week that discovered nothing both leave an empty "
        "index, and `git commit` fails on one")


# --------------------------------------------------------------------------
# propose.yml - the selection reaching a human.
# --------------------------------------------------------------------------


def test_propose_runs_on_a_schedule_and_on_demand():
    on = triggers(parsed("propose.yml"))
    assert "schedule" in on
    assert len(on["schedule"]) == 2, (
        "the design is twice a week; got %r" % on["schedule"])
    assert "workflow_dispatch" in on


def test_the_scheduled_run_proposes_what_the_research_selected():
    """The gap this closes cost nothing to run and everything to trust.

    In the sibling, research.yml wrote a selection report every Monday,
    committed it, and stopped; propose took the next unused backlog row and
    never opened the report. Both halves worked; the research simply never
    reached a human, so the front end was decorative on the shipped schedule.
    """
    run = step_with("propose.yml", "propose")["run"]
    assert "--from-selection" in run, (
        "the scheduled path never proposes the selected concepts")
    assert "research/selection.json" in run


def test_propose_still_falls_back_to_the_backlog():
    """The backlog path is the one that works on a fresh checkout and must not
    regress: a repository with no report, a week whose research was a dry run,
    an operator naming a segment by hand. The report is a preference, never a
    requirement."""
    # Commands only: the block above these flags names `--segment` and
    # `--retries 2` in prose, and reading the raw body let `--retries 1` ship
    # green underneath it.
    run = commands_in(step_with("propose.yml", "propose")["run"])
    assert "-f research/selection.json" in run, (
        "propose must TEST for the report; assuming it would break every run "
        "that has none")
    assert "--segment" in run, "an operator can no longer name a row"
    assert "--id-file" in run
    assert "--retries 2" in run, (
        "the gate refuses a first draft routinely, and the module default of 1 "
        "gives each concept a single rewrite - the first attempt that knows "
        "what it got wrong is also the last")


def test_the_approval_step_opens_one_issue_per_proposed_segment():
    """--from-selection proposes a job per selected concept and writes their
    ids one per line. A step that read that file as a single value would open
    one issue and leave the other ads invisible - the same defect as never
    reading the report, one layer down.
    """
    step = next(s for s in steps_of("propose.yml")
                if "approval open" in str(s.get("run", "")))
    run = step["run"]
    assert "while IFS= read -r" in run, (
        "the ids must be read line by line, not as one value")
    # Invocations, not mentions: the step also names the command in the message
    # it prints when an issue could not be opened.
    invoked = [line for line in run.splitlines()
               if "engine.approval open" in line and "echo" not in line]
    assert len(invoked) == 1, (
        "one call, inside the loop - not one per hard-coded segment; got %r"
        % invoked)
    assert '|| [ -n "$segment" ]' in run, (
        "a one-concept run writes a single line that may carry no trailing "
        "newline; without this guard `read` drops it and the single-proposal "
        "path opens no issue at all")
    # Commands, not the comment that explains their absence, which is the
    # distinction scripts_of() exists for.
    assert "--still-url" not in commands_of("propose.yml"), (
        "there is no still at this point in the loop: nothing in this "
        "repository renders, and build.yml shoots the frame one tap later")


def test_the_jobs_are_committed_before_any_issue_invites_a_tap():
    """The issue asks a human to tap `go` on a job file. A tap that landed on a
    file only the runner had would advance a stage that exists nowhere else, so
    the commit goes first."""
    steps = steps_of("propose.yml")
    pushed = next(i for i, s in enumerate(steps)
                  if PUSHES.search(str(s.get("run", ""))))
    opened = next(i for i, s in enumerate(steps)
                  if "approval open" in str(s.get("run", "")))
    assert pushed < opened


def test_a_concept_that_fails_does_not_discard_the_ones_that_proposed():
    """One report is three jobs, so partial failure is the ordinary case.

    --from-selection returns the worst exit code of the concepts it ran. A step
    that failed on it would abandon two good proposals - already written and
    gated - over a third that never passed. Record the failure, finish the work
    that succeeded, then go red.
    """
    steps = steps_of("propose.yml")
    assert step_with("propose.yml", "propose").get("continue-on-error") is True

    raised = next(i for i, s in enumerate(steps)
                  if "steps.propose.outcome == 'failure'" in str(s.get("if", "")))
    opened = next(i for i, s in enumerate(steps)
                  if "approval open" in str(s.get("run", "")))
    assert opened < raised, (
        "the failure must be re-raised after the surviving jobs are committed "
        "and their issues are open")


def test_a_run_that_proposed_nothing_stages_only_the_parked_drafts():
    """engine/propose.py writes a draft into queue/proposed/ and MOVES it to
    queue/rejected/ when the gate refuses it structurally. A run killed between
    those two leaves a refused draft in the directory that means "gated, and
    waiting for a human to tap go" - and `git add queue` would commit it as
    though it had passed.
    """
    step = step_with("propose.yml", "commit")
    assert "git add queue/rejected" in step["run"]
    assert step["env"]["COUNT"] == "${{ steps.propose.outputs.count }}"
    assert step.get("if") == "always()", (
        "a run where every concept failed the gate still produces the drafts "
        "and the reasons they were refused for, which are worth committing")


# --------------------------------------------------------------------------
# build.yml - the creative, shot in the sibling.
# --------------------------------------------------------------------------


def _build_step(name_fragment: str) -> dict:
    return next(s for s in steps_of("build.yml")
                if name_fragment in str(s.get("name", "")))


def test_the_build_checks_the_sibling_out_where_the_repository_expects_it():
    """../reel-engine, which is the layout every sibling-aware path here
    assumes - tools/sync_backlog.py's DEFAULT_SOURCE is exactly that - and the
    layout a developer has on their own machine.

    actions/checkout cannot write outside $GITHUB_WORKSPACE, so the sibling
    arrives inside it and is moved one level up immediately. That move is the
    thing to keep if this file is ever rewritten: a checkout left under the
    workspace would be committed by the next `git add`.
    """
    checkout = next(s for s in steps_of("build.yml")
                    if s.get("uses", "").startswith("actions/checkout")
                    and s.get("with", {}).get("repository"))
    assert checkout["with"]["repository"] == "Dasvydo/reel-engine"
    assert checkout["with"]["token"] == "${{ secrets.REEL_ENGINE_TOKEN }}", (
        "GITHUB_TOKEN cannot read another repository")
    assert checkout["with"]["path"] == "_reel-engine"
    assert checkout["if"] == "steps.creative.outputs.kind == 'reel'"

    move = _build_step("Move the sibling")
    assert 'dirname "$GITHUB_WORKSPACE"' in move["run"]
    assert "REEL_ENGINE=" in move["run"]


def test_the_build_runs_the_siblings_renderer_with_the_jobs_own_choices():
    """Everything the render needs was decided by engine/write.py and written
    into the job: the template for the placement, and the selection sidecar
    holding the concept. Re-deriving either in YAML would be a second opinion
    that can drift from the first.
    """
    run = step_with("build.yml", "reel")["run"]
    assert "python -m engine.propose" in run
    for flag in ("--concept", "--selection", "--template", "--still", "--render"):
        assert flag in run, "the sibling is called without %s" % flag
    assert 'cd "$REEL_ENGINE"' in run, (
        "reel-engine's propose has to run with the sibling as its working "
        "directory; its ROOT is where it writes the MP4")
    assert '"$GITHUB_WORKSPACE/$SELECTION"' in run, (
        "the selection must be an ABSOLUTE path: a relative one resolves "
        "inside reel-engine, where this repository's queue does not exist")
    env = step_with("build.yml", "reel")["env"]
    assert env["GEMINI_API_KEY"] == "${{ secrets.GEMINI_API_KEY }}", (
        "reel-engine writes the reel's script before rendering it")


def test_the_render_shoots_the_document_the_creative_reader_read():
    """$CONCEPT was read out of creative_source.selection by the step above.
    Rebuilding that path in bash is the second opinion this file's own header
    says it exists to prevent: a job naming one sidecar and a render shooting
    another agree today only because both spellings happen to match, and the
    concept would then be looked up in a document nobody validated.
    """
    step = step_with("build.yml", "reel")
    assert step["env"]["SELECTION"] == "${{ steps.creative.outputs.selection }}", (
        "the reel step must take the selection off the creative reader's "
        "output, which is the path the concept was read from")
    run = step["run"]
    assert "$SEGMENT.reel.json" not in run, (
        "the sidecar's name is re-derived in shell; the job already carries it")


def test_a_failed_render_blocks_the_issue_instead_of_advancing_it():
    """The copy stays in queue/proposed/, `stage:copy` does not move, and `go`
    comes off so a retry is one tap. Removing a label to allow a human retry is
    the opposite of a workflow adding one to chain itself, which never fires.
    """
    assert step_with("build.yml", "reel").get("continue-on-error") is True
    blocked = _build_step("Block the issue")
    assert blocked["if"] == "steps.reel.outcome == 'failure'"
    assert "approval comment" in blocked["run"]
    assert "--remove go" in blocked["run"]
    assert "approval advance" not in blocked["run"]
    assert blocked["run"].rstrip().endswith("exit 1")


def test_the_artifacts_are_kept_for_fourteen_days_and_no_longer():
    """Artifact storage is a free-tier ceiling that actually binds: a 1080x1920
    MP4 is ~10-15MB against the 500MB a private repository gets. 14 days only
    has to outlive the gap between approving the copy and uploading the ad in
    Ads Manager - and the still is not lost with it, because it is committed to
    queue/built/.
    """
    upload = next(s for s in steps_of("build.yml")
                  if str(s.get("uses", "")).startswith("actions/upload-artifact"))
    assert upload["with"]["retention-days"] == 14
    assert upload["with"]["if-no-files-found"] == "error"
    assert ".mp4" in upload["with"]["path"] and ".jpg" in upload["with"]["path"]
    assert upload["if"] == (
        "steps.creative.outputs.kind == 'reel' && steps.reel.outcome == 'success'")


def test_the_still_travels_with_the_job_into_queue_built():
    """The issue's image has to keep working once the job leaves
    queue/proposed/, and an artifact expires in 14 days."""
    step = _build_step("Advance the job")
    run = step["run"]
    assert "approval advance --segment \"$SEGMENT\" --to built" in run
    assert 'cp "$SEGMENT.jpg" "queue/built/$SEGMENT.jpg"' in run
    assert run.index("--to built") < run.index("queue/built/$SEGMENT.jpg"), (
        "the still is copied after the advance, so it lands beside the job "
        "rather than chasing it")
    assert "git add queue" in run and "push_with_retry.sh" in run


def test_the_issue_is_told_how_to_launch_what_was_just_built():
    """An artifact link with no instructions is a file nobody knows what to do
    with. The comment carries the Ads Manager steps and the exact launch
    dispatch, because the ad id is the one fact this repository cannot work out
    for itself.
    """
    run = _build_step("Advance the job")["run"]
    assert "Ads Manager" in run
    assert "launch" in run and "ad_id" in run
    assert "actions/runs" in run, "the artifact is never linked"
    assert "copy-only ad" in run, (
        "a job with no video says nothing about why there is no artifact")
    assert "NEEDS_NATIVE_PROOFREAD" in run, (
        "the comment invites somebody to paste da and lt copy that no native "
        "has signed off")


def test_the_label_swap_takes_the_stage_off_as_well_as_the_tap():
    """`go` and `stage:copy` are what this workflow guards on, and BOTH have to
    go: leaving stage:copy behind means the next `go` - the one that is meant
    to mean something else entirely - shoots the same reel again.

    Two calls, because `approval label` takes one --add and one --remove. A
    single call with two --remove flags would silently keep only the last,
    which is the kind of mistake that reads as correct.
    """
    run = _build_step("Advance the job")["run"]
    lines = [line.strip() for line in run.splitlines()
             if not line.strip().startswith("#")]
    calls = [line for line in lines
             if "approval label" in line and "echo" not in line]
    joined = " ".join(lines)
    assert len(calls) == 2, "expected two label calls; got %r" % calls
    assert "--remove go --add stage:creative" in joined
    assert "--remove stage:copy" in joined


def test_a_copy_only_ad_never_reaches_for_the_sibling():
    """creative_source.kind decides, and everything the sibling needs is gated
    on it: the token guard, the checkout, the install, the render and the
    upload. The job still advances, still commits and still gets its Ads
    Manager comment, because a static ad is uploaded by hand exactly like a
    video one.
    """
    guarded = [s for s in steps_of("build.yml")
               if str(s.get("if", "")).startswith("steps.creative.outputs.kind == 'reel'")]
    names = [str(s.get("name", s.get("uses", ""))) for s in guarded]
    assert len(guarded) >= 5, (
        "only %d steps are gated on the creative kind: %r" % (len(guarded), names))

    # By name, one at a time, because a count is exactly the assertion that
    # passes while the one step that matters is ungated. The render step ran
    # unconditionally in the first draft of this workflow: a copy-only ad `cd`d
    # into an unset $REEL_ENGINE, the step failed, and the issue was BLOCKED
    # with a shell error for an ad that never wanted a video.
    for step in (step_with("build.yml", "reel"),
                 next(s for s in steps_of("build.yml") if "playwright" in str(s.get("run", ""))),
                 next(s for s in steps_of("build.yml")
                      if s.get("with", {}).get("repository") == "Dasvydo/reel-engine")):
        assert step["if"] == "steps.creative.outputs.kind == 'reel'", (
            "%r runs for a copy-only ad" % step.get("name", step.get("id")))

    unconditional = _build_step("Advance the job")
    assert "if" not in unconditional, (
        "the advance, the commit and the comment run for every ad, whatever "
        "its creative")


def test_the_backlog_drift_check_runs_only_where_the_sibling_exists():
    """`tools/sync_backlog.py --check` compares queue/backlog.md against
    reel-engine's. build.yml is the only job that has both copies on disk;
    anywhere else the tool exits 2 refusing a source it cannot find, which is
    not drift and would read like one.

    A WARNING, never a failure: a table that drifted is worth knowing about,
    and an approved ad must not be held up by it.
    """
    for name in EVERY_WORKFLOW:
        if name == "build.yml":
            continue
        # Invocations, not mentions: propose.yml's "nothing proposed" notice
        # tells the operator to run the sync tool by hand, which is exactly the
        # advice it should be giving.
        invoked = [line.strip() for line in commands_of(name).splitlines()
                   if "sync_backlog" in line and not line.strip().startswith("echo")]
        assert not invoked, (
            "%s runs the backlog drift check without a sibling checkout, where "
            "it can only ever refuse: %r" % (name, invoked))

    step = next(s for s in steps_of("build.yml")
                if "sync_backlog" in str(s.get("run", "")))
    assert step.get("continue-on-error") is True
    assert step["if"] == "steps.creative.outputs.kind == 'reel'"
    assert "::warning::" in step["run"]
    assert "::error::" not in step["run"]


# --------------------------------------------------------------------------
# build.yml's creative reader, run for real. It is pure file reading - no
# socket, no key, no model - so the test executes the step's own script rather
# than asserting on its text.
# --------------------------------------------------------------------------


def _creative_script() -> str:
    run = step_with("build.yml", "creative")["run"]
    _, _, rest = run.partition("<<'PY'\n")
    body, _, _ = rest.rpartition("\nPY")
    assert body, "the creative step no longer embeds a python heredoc"
    return body


def _run_creative(tmp_path, monkeypatch, job: dict, sidecar=None,
                  segment="payroll-bureaus") -> dict:
    import json

    proposed = tmp_path / "queue" / "proposed"
    proposed.mkdir(parents=True, exist_ok=True)
    (proposed / ("%s.json" % segment)).write_text(
        json.dumps(job, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if sidecar is not None:
        (proposed / ("%s.reel.json" % segment)).write_text(
            json.dumps(sidecar, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")

    output = tmp_path / "github_output"
    output.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SEGMENT", segment)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    exec(compile(_creative_script(), "<build.yml creative>", "exec"),
         {"__name__": "__main__"})
    return dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines() if line
    )


def _example_job(**overrides) -> dict:
    import json

    job = json.loads((ROOT / "creative" / "example-job.json").read_text(
        encoding="utf-8"))
    job["id"] = job["segment"] = "payroll-bureaus"
    job["creative_source"]["selection"] = "queue/proposed/payroll-bureaus.reel.json"
    job.update(overrides)
    return job


SIDECAR = {
    "schema": 1,
    "generated_at": "2026-09-18T00:00:00Z",
    "source": "ad-engine",
    "selected": ["a01"],
    "concepts": [{"id": "a01", "segment": "payroll-bureaus", "angle": "a",
                  "hook": "h", "pattern_ids": [], "format": "vertical reel, 9:16",
                  "needs_numbers": False}],
}


def test_the_creative_reader_takes_the_kind_template_and_concept_off_the_job(
        tmp_path, monkeypatch):
    """The worked example in creative/example-job.json is a reel job, so this
    runs the real step over the real file shape the writer emits."""
    out = _run_creative(tmp_path, monkeypatch, _example_job(), SIDECAR)
    assert out == {
        "kind": "reel",
        "template": "reel-c",
        "selection": "queue/proposed/payroll-bureaus.reel.json",
        "concept": "a01",
    }


def test_the_creative_reader_asks_for_nothing_on_a_copy_only_job(
        tmp_path, monkeypatch):
    """kind `none` means no sibling, no browser and no concept to shoot, and
    the reader must not go looking for a sidecar that was never written."""
    job = _example_job()
    job["creative_source"] = {"kind": "none"}
    out = _run_creative(tmp_path, monkeypatch, job)
    assert out["kind"] == "none"
    assert out["concept"] == "" and out["template"] == ""


def test_the_creative_reader_refuses_a_kind_the_gate_would_never_have_filed(
        tmp_path, monkeypatch):
    """engine/gate.py refuses an unknown creative_source.kind before a job is
    ever filed, so reaching one here means the file was edited by hand.
    Falling through to the copy-only path would ship an ad whose video nobody
    shot.
    """
    job = _example_job()
    job["creative_source"] = {"kind": "carousel"}
    with pytest.raises(SystemExit) as caught:
        _run_creative(tmp_path, monkeypatch, job)
    assert "carousel" in str(caught.value)
    assert "reel, still, none" in str(caught.value)


def test_the_creative_reader_refuses_a_reel_with_no_template(
        tmp_path, monkeypatch):
    """reel-engine would fall back to its own default template and shoot a
    shape nobody approved."""
    job = _example_job()
    job["creative_source"] = {
        "kind": "reel", "repo": "reel-engine", "template": "",
        "selection": "queue/proposed/payroll-bureaus.reel.json"}
    with pytest.raises(SystemExit) as caught:
        _run_creative(tmp_path, monkeypatch, job, SIDECAR)
    assert "template" in str(caught.value)


def test_the_creative_reader_refuses_a_selection_that_selects_nothing(
        tmp_path, monkeypatch):
    sidecar = dict(SIDECAR, selected=[])
    with pytest.raises(SystemExit) as caught:
        _run_creative(tmp_path, monkeypatch, _example_job(), sidecar)
    assert "selects no concept" in str(caught.value)


def test_the_creative_reader_refuses_a_selection_that_leaves_the_repository(
        tmp_path, monkeypatch):
    """The render joins this value onto $GITHUB_WORKSPACE, so an absolute or
    climbing path reads fine in this step and then misses in the sibling -
    after the checkout and the Chromium install. Refused here instead.
    """
    job = _example_job()
    job["creative_source"] = dict(job["creative_source"],
                                  selection="/tmp/payroll-bureaus.reel.json")
    with pytest.raises(SystemExit) as caught:
        _run_creative(tmp_path, monkeypatch, job, SIDECAR)
    assert "not a path inside this repository" in str(caught.value)


def test_the_creative_reader_never_forges_an_output_line(
        tmp_path, monkeypatch):
    """$GITHUB_OUTPUT is line-oriented, so a value carrying a newline would
    write output lines nobody asked for. Refused rather than escaped: a
    template name with a line break in it is a corrupt job file either way.
    """
    job = _example_job()
    job["creative_source"] = dict(job["creative_source"], template="reel-c\nkind=none")
    with pytest.raises(SystemExit) as caught:
        _run_creative(tmp_path, monkeypatch, job, SIDECAR)
    assert "line break" in str(caught.value)


# --------------------------------------------------------------------------
# launch.yml - the ad id a human typed.
# --------------------------------------------------------------------------


def test_launch_takes_the_four_things_only_a_human_has():
    on = triggers(parsed("launch.yml"))
    assert "schedule" not in on, (
        "a launch is never unattended: it carries an ad id somebody copied out "
        "of Ads Manager")
    inputs = on["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"segment", "ad_id", "campaign_id", "issue"}
    assert inputs["segment"]["required"] is True
    assert inputs["ad_id"]["required"] is True
    assert inputs["campaign_id"]["required"] is False


def test_launch_pins_the_ad_id_and_commits_it():
    run = step_with("launch.yml", "launch")["run"]
    joined = re.sub(r"\s+", " ", " ".join(
        line.strip() for line in run.replace("\\\n", " ").splitlines()
        if not line.strip().startswith("#")))
    assert 'approval launch --segment "$SEGMENT" --ad "$AD_ID:$CAMPAIGN_ID"' in joined, (
        "the ad id and the campaign id travel as one --ad value; a blank "
        "trailing slot is parsed as a null campaign id rather than as an empty "
        "string")
    assert "git add queue" in run and "push_with_retry.sh" in run
    assert 'if [ -z "$SEGMENT" ] || [ -z "$AD_ID" ]' in run, (
        "a required input can still arrive empty through the API, and a blank "
        "segment should be a sentence rather than a LookupError")


def test_launch_closes_the_issue_after_the_pin_is_committed():
    steps = steps_of("launch.yml")
    pinned = next(i for i, s in enumerate(steps)
                  if "approval launch" in str(s.get("run", "")))
    closed = next(i for i, s in enumerate(steps)
                  if "approval close" in str(s.get("run", "")))
    assert pinned < closed, (
        "an issue closed before the pin is committed would say the ad is "
        "recorded when it is not")
    run = steps[closed]["run"]
    assert 'if [ -z "$ISSUE" ]' in run, (
        "a missing issue number must cost a tidy-up, never the pin")


# --------------------------------------------------------------------------
# measure.yml - the loop closing.
# --------------------------------------------------------------------------


def test_measure_runs_on_a_schedule_and_on_demand():
    on = triggers(parsed("measure.yml"))
    assert "schedule" in on
    assert len(on["schedule"]) == 1
    assert "workflow_dispatch" in on


def test_the_measurement_lands_before_the_research_that_consumes_it():
    """The ordering IS the feature, and nothing else enforces it.

    engine.feedback writes our measured ads into research/corpus/ as records
    with origin "own". engine.fanout - what research.yml runs - loads the whole
    corpus and derives that week's patterns from it, and propose.yml writes
    what those patterns select. So the corpus has to be current BEFORE the
    sweep reads it: measure at 05:00, research at 06:00, propose at 09:00.

    Swap the two hours and nothing fails. The record still lands, it is simply
    read next Monday instead of this one, and every click-through rate we learn
    about our own ads reaches the concepts a week after it was true. A silent
    week of lag is not something a run summary can show, so it is pinned here.
    """
    measure = _cron_fields("measure.yml")
    research = _cron_fields("research.yml")
    assert len(measure) == 1, "measure is meant to be weekly; got %r" % measure
    assert len(research) == 1

    minute, hour, dom, month, dow = measure[0]
    r_minute, r_hour, r_dom, r_month, r_dow = research[0]

    assert (dom, month, dow) == (r_dom, r_month, r_dow), (
        "measure and research must fall on the same day for the ordering to "
        "mean anything; measure %r vs research %r" % (measure[0], research[0]))
    assert (int(hour), int(minute)) < (int(r_hour), int(r_minute)), (
        "measure runs at %s:%s and research at %s:%s, so the sweep reads a "
        "corpus that is a week behind the ads we launched"
        % (hour, minute, r_hour, r_minute))


def test_the_proposals_land_after_the_sweep_that_chooses_them():
    research = _cron_fields("research.yml")[0]
    for cron in _cron_fields("propose.yml"):
        if cron[2:] != research[2:]:
            continue  # the Thursday run has no sweep of its own to wait for
        assert (int(cron[1]), int(cron[0])) > (int(research[1]), int(research[0])), (
            "propose runs at %s:%s on the same day as the sweep at %s:%s, so "
            "it would read last week's selection" % (cron[1], cron[0],
                                                     research[1], research[0]))


def test_measure_runs_both_halves_of_the_loop_in_order():
    """MEASURE then FEED BACK. feedback reads what measure wrote.

    Run them the other way and NOTHING fails: both stages exit 0, the document
    is written, and the corpus records built seconds earlier carry last week's
    numbers - a whole week of readback that never reaches the learner, under a
    green tick.
    """
    steps = steps_of("measure.yml")
    measure = next(i for i, s in enumerate(steps)
                   if "python -m engine.measure" in str(s.get("run", "")))
    feedback = next(i for i, s in enumerate(steps)
                    if "python -m engine.feedback" in str(s.get("run", "")))
    assert measure < feedback


def test_a_stage_that_fails_does_not_discard_what_the_other_produced():
    """Nine measured ads must not be lost to a tenth Meta holds no row for.

    Same rule as research.yml's sweep and propose.yml's loop: a nonzero exit
    means "a stage could not run", not "nothing was produced". Both halves are
    continue-on-error, everything they wrote is committed, and the job goes red
    afterwards.
    """
    steps = steps_of("measure.yml")
    for step_id in ("measure", "feedback"):
        step = step_with("measure.yml", step_id)
        assert step.get("continue-on-error") is True, (
            "the %s step fails the job before the commit" % step_id)

    committed = next(i for i, s in enumerate(steps)
                     if "git commit" in str(s.get("run", "")))
    raised = next(i for i, s in enumerate(steps)
                  if "outcome == 'failure'" in str(s.get("if", "")))
    assert committed < raised, (
        "the failure must be re-raised after the measurements are committed")


def test_measure_commits_the_outputs_by_name():
    """Both modules' outputs, and nothing else. queue/ is deliberately absent:
    engine.measure reads the launched jobs and writes none of them - the ad id
    was pinned by launch.yml, by a human, once - so anything found under queue/
    during this run belongs to another workflow.
    """
    step = next(s for s in steps_of("measure.yml")
                if "git commit" in str(s.get("run", "")))
    run = step["run"]
    for produced in ("research/measurements.json", "research/corpus"):
        assert produced in run, "the commit step never names %s" % produced
    staged = [line for line in run.splitlines()
              if not line.strip().startswith("#")]
    assert "research/media" not in "\n".join(staged)
    assert "git add queue" not in "\n".join(staged)
    assert "git diff --cached --quiet" in run, (
        "a rehearsal, a week with nothing launched and a week whose rows read "
        "back unchanged all leave an empty index, and `git commit` fails on one")


def test_the_feedback_step_is_handed_no_credential_at_all():
    """engine.feedback reads three files and counts words - no model, no
    network - which tests/test_feedback.py proves by AST-parsing the module. A
    credential in this step's env would be a credential this step could spend,
    and the whole reason the loop closes for free is that its second half costs
    nothing.
    """
    step = step_with("measure.yml", "feedback")
    for name in step.get("env", {}):
        assert "API_KEY" not in name and "TOKEN" not in name, (
            "the feedback step is given %s, which it has no use for" % name)


def test_the_rehearsal_leaves_the_tree_byte_identical():
    """`dry_run` has to be inert in BOTH halves. Measuring without writing the
    document while still letting engine.feedback write corpus records would
    teach next week's concepts numbers that are not on disk.
    """
    on = triggers(parsed("measure.yml"))
    assert "dry_run" in on["workflow_dispatch"]["inputs"]
    for step_id in ("measure", "feedback"):
        step = step_with("measure.yml", step_id)
        assert "--dry-run" in step["run"], (
            "the %s step writes even on a rehearsal" % step_id)
        assert step["env"]["DRY_RUN"] == "${{ inputs.dry_run }}", (
            "the input must arrive through env:, not spliced into the script")


# --------------------------------------------------------------------------
# Credentials. Every one of them is required where it is used, named where it
# is missing, and read under the name engine/oauth.py owns.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["research.yml", "propose.yml", "build.yml"])
def test_the_model_key_is_required_not_optional(name):
    """A missing key must fail the workflow with a message naming it, never
    skip a step and report success. build.yml needs it because reel-engine
    writes the reel's script before rendering it - the same free key, in the
    sibling's checkout."""
    text = text_of(name)
    assert "secrets.GEMINI_API_KEY" in text
    assert "GEMINI_API_KEY is not set" in text
    assert "docs/SECRETS.md" in text


@pytest.mark.parametrize("name", ["research.yml", "measure.yml"])
def test_the_meta_token_is_required_not_optional(name):
    """The twin of the rule above, and a different credential: the Ad Library
    API and the Marketing API insights edge are both read with
    META_ACCESS_TOKEN, and GEMINI_API_KEY is not interchangeable with it.

    META_TOKEN_ISSUED is a repository VARIABLE, not a secret, and that is not a
    detail: it is a date. A secret is write-only once saved, so an operator
    rotating the token could not see whether the date beside it had ever been
    updated - and a stale date is a countdown that never fires.
    """
    text = text_of(name)
    assert "secrets.META_ACCESS_TOKEN" in text
    assert "META_ACCESS_TOKEN is not set" in text
    assert "vars.META_TOKEN_ISSUED" in text
    assert "secrets.META_TOKEN_ISSUED" not in text
    assert "docs/SECRETS.md" in text


def test_the_sibling_checkout_needs_a_token_of_its_own():
    """GITHUB_TOKEN is scoped to this repository, so cloning Dasvydo/reel-engine
    needs a credential that reaches it. A missing one must fail loudly on the
    reel path rather than silently shipping a copy-only ad."""
    text = text_of("build.yml")
    assert "secrets.REEL_ENGINE_TOKEN" in text
    assert "REEL_ENGINE_TOKEN is not set" in text
    guard = next(s for s in steps_of("build.yml")
                 if "REEL_ENGINE_TOKEN is not set" in str(s.get("run", "")))
    assert guard["if"] == "steps.creative.outputs.kind == 'reel'", (
        "a copy-only ad would be blocked on a secret it never uses")
    steps = steps_of("build.yml")
    checkout = next(i for i, s in enumerate(steps)
                    if s.get("with", {}).get("repository") == "Dasvydo/reel-engine")
    assert steps.index(guard) < checkout, (
        "the guard must run before the checkout it explains")


@pytest.mark.parametrize("name", ["research.yml", "measure.yml"])
def test_every_meta_credential_arrives_by_its_real_name_through_env(name):
    """The names come from engine/oauth.py, not from memory. A typo in one of
    two names is a stage that fails forever with a message about a credential
    that is right there."""
    from engine import oauth

    steps = [s for s in steps_of(name) if s.get("env")]
    token_step = next(s for s in steps
                      if "engine.oauth --status" in str(s.get("run", "")))
    for secret in oauth.SECRET_NAMES:
        assert token_step["env"].get(secret) == "${{ secrets.%s }}" % secret
    for variable in oauth.VARIABLE_NAMES:
        assert token_step["env"].get(variable) == "${{ vars.%s }}" % variable, (
            "%s must read %s as a repository VARIABLE; a secret cannot be read "
            "back by the operator who has to keep it honest" % (name, variable))


@pytest.mark.parametrize("name", ["research.yml", "measure.yml"])
def test_the_token_countdown_runs_and_is_a_warning_not_a_fault(name):
    """Meta's token dies 60 days after issue and cannot be refreshed after.

    `python -m engine.oauth --status` is offline, prints which names are set
    and the value of none of them, and exits 1 from day 40 of 60 and again once
    the token is dead. Day 40 leaves twenty days - at this weekly cadence, at
    least two more runs that shout before anything breaks - so the nonzero exit
    is a warning and must not, on its own, fail the job. A run that went red for
    it would be red for three good weeks running, which is how a red cron stops
    meaning anything.
    """
    step = next(s for s in steps_of(name)
                if "engine.oauth --status" in str(s.get("run", "")))
    assert "|| code=$?" in step["run"], (
        "the countdown's exit code is propagated rather than caught, so a "
        "token with twenty days left fails the run")
    assert "::warning::" in step["run"], "the countdown is caught and swallowed"
    assert step.get("continue-on-error") is True
    raised = [s for s in steps_of(name) if "outcome == 'failure'" in str(s.get("if", ""))]
    for s in raised:
        assert "steps.token.outcome" not in s["if"], (
            "a token inside its warning window fails the run")


@pytest.mark.parametrize("name", ["research.yml", "measure.yml"])
def test_the_countdown_reaches_the_run_summary(name):
    """A warning nobody opens the log to see is not a warning. The summary is
    the page an operator actually looks at on a Monday, and it is where a token
    with twenty days left has to be visible while there is still time to rotate
    it."""
    step = next(s for s in steps_of(name)
                if "GITHUB_STEP_SUMMARY" in str(s.get("run", ""))
                and "oauth.txt" in str(s.get("run", "")))
    assert step.get("if") == "always()"


# --------------------------------------------------------------------------
# The commands themselves. A flag that does not exist is a job that fails at
# 05:00 with an argparse usage line, and nothing else in this suite would
# notice.
# --------------------------------------------------------------------------


SUBSTITUTIONS = {
    "ISSUE": "1",
    "SEGMENT": "payroll-bureaus",
    "segment": "payroll-bureaus",
    "AD_ID": "120210000000000001",
    "CAMPAIGN_ID": "120210000000000002",
    "MAX_ADS": "24",
}


def _approval_commands(runner_temp: Path) -> list:
    """Every `python -m engine.approval ...` a workflow actually runs.

    Joined across line continuations, stripped of a leading `if `, cut at the
    first redirection or separator, and with shell variables replaced by values
    of the right shape. Lines that merely MENTION the command - the error
    messages telling an operator how to run it by hand - are echoes, and
    commands_of() has already dropped the comments.
    """
    substitutions = dict(SUBSTITUTIONS, RUNNER_TEMP=str(runner_temp))
    found = []
    for name in EVERY_WORKFLOW:
        script = commands_of(name).replace("\\\n", " ")
        for line in script.splitlines():
            stripped = line.strip()
            if stripped.startswith("if "):
                stripped = stripped[3:].strip()
            if not stripped.startswith("python -m engine.approval"):
                continue
            for cut in ("<", ";", "&&", "||", "|"):
                stripped = stripped.split(cut)[0]
            command = re.sub(r"\$\{?(\w+)\}?",
                             lambda m: substitutions.get(m.group(1), "x"),
                             stripped)
            # [3:] drops `python -m engine.approval`, leaving the argv the
            # module's own parser is handed.
            found.append((name, shlex.split(command)[3:]))
    return found


def test_the_workflows_call_approval_with_flags_it_declares(tmp_path, monkeypatch):
    """Run against the real argparse, not against a list of flags written here.

    A usage error exits 2 - an unknown flag, a missing required one, a
    subcommand that does not exist - and that is what this catches. A refusal
    from the module itself (no such job, wrong stage) exits 1 and is fine: the
    point is only that the command line parses. Nothing reaches GitHub: the
    backend is a stand-in and the queue is a temporary directory, so a `drop`
    in here cannot remove a real job.

    What this does NOT catch is a command that parses and means the wrong
    thing: `--remove go --remove stage:copy` is accepted and argparse silently
    keeps the last. test_the_label_swap_takes_the_stage_off_as_well_as_the_tap
    is the rule for that one.
    """
    from engine import approval

    queue = tmp_path / "queue"
    for stage in approval.ALL_STAGES:
        (queue / stage).mkdir(parents=True)
    monkeypatch.setattr(approval, "QUEUE", queue)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    commands = _approval_commands(tmp_path)
    assert len(commands) >= 8, (
        "only %d approval commands were found across the workflows, which "
        "means the extraction stopped matching rather than that the workflows "
        "stopped calling it" % len(commands))

    class Fake:
        """The six-method protocol engine/approval.py's GitHubIssues answers."""

        def open(self, **kw):
            return "1"

        def comment(self, ref, body):
            pass

        def add_label(self, ref, label):
            pass

        def remove_label(self, ref, label):
            pass

        def close(self, ref, comment=None):
            pass

        def body_of(self, ref):
            return approval.marker("payroll-bureaus")

    for name, argv in commands:
        # engine/approval.py reads a --body-file before it talks to the
        # backend, so a path that does not exist would raise FileNotFoundError
        # and say nothing about whether the flags parse.
        for argument in argv:
            if argument.endswith(".md"):
                Path(argument).write_text("body\n", encoding="utf-8")
        code = approval.main(argv, backend=Fake())
        assert code != 2, "%s: %r is not a command engine.approval accepts" % (
            name, argv)


def test_the_flag_check_would_notice_a_flag_that_went_away(tmp_path, monkeypatch):
    """A decoy, because the test above passes just as happily when the
    extraction has silently stopped finding anything."""
    from engine import approval

    queue = tmp_path / "queue"
    for stage in approval.ALL_STAGES:
        (queue / stage).mkdir(parents=True)
    monkeypatch.setattr(approval, "QUEUE", queue)
    with pytest.raises(SystemExit) as caught:
        approval.main(["label", "--issue", "1", "--swap", "go"], backend=object())
    assert caught.value.code == 2


@pytest.mark.skipif(not (ROOT / "engine" / "propose.py").exists(),
                    reason="engine/propose.py is not written yet")
def test_propose_is_called_with_flags_it_declares():
    """The flags docs/CONTRACTS.md fixes for engine/propose.py, read off the
    module's own argparse rather than trusted."""
    source = (ROOT / "engine" / "propose.py").read_text(encoding="utf-8")
    declared = set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', source))
    used = set(re.findall(r"(--[a-z-]+)", commands_of("propose.yml")))
    # Only the flags this workflow passes to engine.propose, not every flag in
    # the file (the approval calls have their own).
    for flag in ("--retries", "--id-file", "--from-selection", "--segment"):
        assert flag in used, "propose.yml no longer passes %s" % flag
        assert flag in declared, (
            "propose.yml passes %s and engine/propose.py does not declare it"
            % flag)


@pytest.mark.skipif(not (SIBLING / "engine" / "propose.py").exists(),
                    reason="../reel-engine is not checked out")
def test_the_sibling_declares_every_flag_the_build_passes_it():
    """build.yml calls another repository's CLI, so nothing in this repository's
    own test suite would catch a flag that was renamed over there. This runs
    only where the sibling is on disk - which is a developer's machine and
    build.yml's own runner.
    """
    source = (SIBLING / "engine" / "propose.py").read_text(encoding="utf-8")
    declared = set(re.findall(r'add_argument\(\s*"(--[a-z-]+)"', source))
    run = step_with("build.yml", "reel")["run"]
    passed = set(re.findall(r"(--[a-z-]+)", run))
    missing = sorted(passed - declared)
    assert not missing, (
        "build.yml passes %s to reel-engine's engine.propose, which declares "
        "no such flag" % missing)


# --------------------------------------------------------------------------
# tools/push_with_retry.sh
# --------------------------------------------------------------------------


SCRIPT = ROOT / "tools" / "push_with_retry.sh"


def test_the_push_script_is_executable_and_is_bash():
    assert SCRIPT.exists()
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash")
    assert os.access(SCRIPT, os.X_OK), (
        "the workflows call it as `bash tools/push_with_retry.sh`, so this is "
        "belt and braces - but a script that is not executable is a script "
        "somebody will eventually try to run directly")


def test_the_push_script_never_force_pushes():
    """These jobs push to the default branch. A force push there would discard
    somebody else's commit to make a cron green, which is the worst trade
    available - and it is the obvious thing to reach for when a rebase fails.
    """
    body = SCRIPT.read_text(encoding="utf-8")
    for line in body.splitlines():
        if line.strip().startswith("#"):
            continue
        assert "--force" not in line and " -f " not in line, (
            "push_with_retry.sh force-pushes: %s" % line)
    assert "git rebase --abort" in body, (
        "a rebase that cannot apply cleanly must leave the tree unrebased "
        "rather than half-rebased")
    assert "rev-parse --abbrev-ref HEAD" in body, (
        "the branch must be named explicitly: `git push` with no argument "
        "fails outright on a detached HEAD, which is a confusing way to "
        "discover a checkout changed shape")


def test_the_push_script_is_bash_that_parses():
    result = subprocess.run(["bash", "-n", str(SCRIPT)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not (SIBLING / "tools" / "push_with_retry.sh").exists(),
                    reason="../reel-engine is not checked out")
def test_the_push_script_is_the_siblings_byte_for_byte():
    """Copied rather than rewritten, because what it survives was MEASURED
    there: a research run that had already spent its quota, pushed, and lost
    to a run that landed seven seconds earlier. Two copies that drift are two
    behaviours under one name.
    """
    assert SCRIPT.read_bytes() == (SIBLING / "tools" / "push_with_retry.sh").read_bytes()


# --------------------------------------------------------------------------
# Hygiene.
# --------------------------------------------------------------------------


def test_every_run_body_is_valid_bash():
    """A quoting mistake in a heredoc or an unbalanced `if` is a job that fails
    on its first real trigger, at 05:00, with a syntax error and nothing
    else."""
    for name in EVERY_WORKFLOW:
        for job_name, job in parsed(name)["jobs"].items():
            for step in job["steps"]:
                script = step.get("run")
                if not script:
                    continue
                result = subprocess.run(
                    ["bash", "-n", "-"], input=script,
                    capture_output=True, text=True)
                assert result.returncode == 0, (
                    "%s job %r step %r is not valid bash:\n%s"
                    % (name, job_name, step.get("name", step.get("id")),
                       result.stderr))


def test_the_embedded_python_is_valid_python():
    """The creative reader is the only python in any workflow here, and a
    SyntaxError in it would be discovered by the first `go` tap."""
    ast.parse(_creative_script())
    bodies = [s for name in EVERY_WORKFLOW for s in scripts_of(name)
              if "python - <<" in s]
    assert len(bodies) == 1, (
        "more than one workflow embeds a python script; each one is code that "
        "no linter reads and no test imports: %d found" % len(bodies))


def test_every_step_that_can_fail_quietly_sets_pipefail():
    """`a | tee b` exits with tee's status, so a python command that died would
    leave the step green. Every multi-line script that pipes sets it.
    """
    for name in EVERY_WORKFLOW:
        for step in (s for job in parsed(name)["jobs"].values()
                     for s in job["steps"]):
            script = str(step.get("run", ""))
            if "| tee" not in script:
                continue
            assert "pipefail" in script, (
                "%s step %r pipes into tee without pipefail, so a failing "
                "command reads as a passing step"
                % (name, step.get("name", step.get("id"))))


def test_the_workflows_are_pure_ascii():
    """A smart quote pasted into a shell string is a different byte from the
    one the script meant, and YAML will carry it silently."""
    for name in EVERY_WORKFLOW:
        text = text_of(name)
        bad = [(i + 1, line) for i, line in enumerate(text.splitlines())
               if not line.isascii()]
        assert not bad, "%s carries non-ASCII: %r" % (name, bad[:3])


def test_python_is_asked_for_by_version_everywhere():
    for name in EVERY_WORKFLOW:
        setups = [s for s in (st for job in parsed(name)["jobs"].values()
                              for st in job["steps"])
                  if str(s.get("uses", "")).startswith("actions/setup-python")]
        assert setups, "%s never sets up python" % name
        for step in setups:
            assert step["with"]["python-version"] == "3.11", (
                "%s runs on %r; the modules are written against 3.11"
                % (name, step["with"].get("python-version")))


def test_nothing_reaches_for_a_snapshot_page_or_a_creative_download():
    """The rule that makes this repository's discovery honest, checked where a
    workflow could quietly break it with a curl. docs/AD-RESEARCH-SCOPE.md 3.3:
    a creative is watched only when a human saved it by hand.
    """
    for name in EVERY_WORKFLOW:
        commands = commands_of(name)
        for forbidden in ("ads/library", "snapshot", "yt-dlp", "ffmpeg -i"):
            assert forbidden not in commands, (
                "%s reaches for %r" % (name, forbidden))


def test_the_runner_is_linux_everywhere():
    """docs/COST.md's arithmetic is the 2,000 Linux minutes. macOS bills at 10x
    and Windows at 2x, so one `runs-on` is the whole month."""
    for name in EVERY_WORKFLOW:
        for job_name, job in parsed(name)["jobs"].items():
            assert str(job["runs-on"]).startswith("ubuntu"), (
                "%s job %r runs on %r, which is not billed at 1x"
                % (name, job_name, job["runs-on"]))


def test_the_graph_version_override_reaches_the_step_that_would_use_it():
    """An override nothing maps into the runner is an override that does not
    exist, and docs/SECRETS.md documented this one as a repository VARIABLE
    before any workflow passed it - so setting it would have changed nothing
    and the operator would have had no way to tell.

    engine/discover.py and engine/measure.py both read META_GRAPH_VERSION from
    the environment and insert it into the Graph URL when a field they read
    turns out to need a version. Both steps that open a Graph call therefore
    map it. It is `vars.` and not `secrets.` because a version string is not a
    credential, and a variable is visible on the settings page beside the token
    it qualifies.
    """
    for name, step_id in (("research.yml", "research"), ("measure.yml", "measure")):
        env = step_with(name, step_id).get("env") or {}
        assert "META_GRAPH_VERSION" in env, (
            "%s's %s step opens a Graph call but cannot see the version "
            "override docs/SECRETS.md tells an operator to set" % (name, step_id))
        assert env["META_GRAPH_VERSION"] == "${{ vars.META_GRAPH_VERSION }}", (
            "%s passes META_GRAPH_VERSION as %r; a version string is a "
            "variable, not a secret" % (name, env["META_GRAPH_VERSION"]))


def test_the_feedback_step_is_handed_no_credential_at_all():
    """engine/feedback.py reads two files and counts words. It calls no model
    and opens no socket - tests/test_feedback.py AST-parses it to prove that -
    so a token or a key on its step would be a credential handed to a process
    that has nowhere to send it.
    """
    env = step_with("measure.yml", "feedback").get("env") or {}
    for name in ("META_ACCESS_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        assert name not in env, (
            "measure.yml's feedback step is handed %s, which it cannot use" % name)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"] + sys.argv[1:]))
