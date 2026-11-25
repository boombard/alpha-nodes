---
name: backlog-converge
description: Explicit-only (user types /backlog-converge [task-ids]). Lands human-approved Backlog.md tasks from their Orca task-<n> worktrees onto main one at a time (rebase, test, fast-forward, remove worktree), marks them Done with ACs/DoD ticked, then reports what is newly unblocked. Destructive (removes worktrees and branches), so never trigger it from casual phrases like "tidy up".
disable-model-invocation: true
---

# backlog-converge

Land approved work onto `main`. You are the **coordinator** (Opus, on `main`). You
own the gates, the user conversation, the `backlog/` edits and the final
verification. The mechanical landing of each task (rebase, mechanical conflict
resolution, checks, ff-merge, worktree removal) is delegated to a **Sonnet
subworker**, one task at a time, to save tokens. This is the back half of the pair
started by `/backlog-unleash`.

Load first: `orchestration` (`ORCA skills get orchestration`), `orca-cli`. `BL` is
`npx -y backlog.md@1.57.4`. Read `documentation/workflow.md`.

## Fixed decisions (do not re-litigate)

- **Only approved tasks land.** Approved means the user named them in this command,
  or confirmed them at step 3. A task must be `In Review`.
- **Landing:** rebase `task-<n>` onto `main`'s tip, then `git merge --ff-only`.
  Linear history: no squash, no PR, **never push**.
- **Sequential**, in dependency order (a task's deps land before it), tie-broken by
  task number. Each rebase builds on the previous landing. Never run two landing
  subworkers at once: they share `main`.
- **Delegation:** landing is done by a subworker spawned with the Agent tool,
  `subagent_type: "general-purpose"`, `model: "sonnet"`, foreground. It cannot talk
  to the user, so it never decides anything the conflict policy reserves for the
  user: it stops and reports back, and you ask.
- **Conflict policy:**
  - The subworker resolves mechanical conflicts: imports, adjacent lines, `uv.lock`
    (regenerate with `uv lock`), `__init__.py` exports, `conftest.py` fixtures
    added on both sides.
  - **The subworker stops and reports; you ask the user** when both sides changed the same logic with competing
    intent, or when the conflict is in `documentation/`, `backlog/`, any `CLAUDE.md`,
    or a `contracts`-labelled task's interfaces.
  - The tests arbitrate. A resolution isn't done until the full suite is green.
- **The coordinator owns `backlog/`.** Status, ACs, DoD and summary are written on
  `main` after landing, and committed.

## 1. Preconditions

1. `ORCA status --json` is reachable. You are in the main checkout on `main`, and
   `git status --porcelain --untracked-files=no` is empty (untracked files such as
   `spikes/` don't block).
2. Detect the checks once: `uv run pytest`, `uv run ruff check`, `uv run pyright`.

## 2. Discover

For each candidate (the user's ids, or every `In Review` task), find worktree
`task-<n>` (`ORCA worktree list --json`) and record:
- branch
- commits ahead of `main`
- whether the tree is clean
- whether every commit subject carries `(TASK-<n>)`
- the worker dispatch from the task's notes

**Landable** = `In Review` + worktree found + clean + at least 1 commit ahead.
Everything else is skipped, with the reason recorded.

## 3. Confirm (required gate)

Skip it only if the user named the ids. Show the landing order, branch, commits
ahead, and the open points from each task's final summary, plus the skipped list.
Use AskUserQuestion to approve, drop or reorder.

## 4. Land, one task at a time

For each approved task, in order:

1. **Quiesce the worker (you).** If its dispatch is live and idle, `worker-release`.
   If it is mid-turn, stop and ask the user: they may still be talking to it.
2. **Spawn the landing subworker** (Agent tool, `model: "sonnet"`, foreground). Its
   prompt must be self-contained, since it starts cold. Give it: the task id, the
   worktree path and branch, the repo root, the check commands from step 1, the
   conflict policy and the no-push rule above, and these steps:
   1. **Rebase in the worktree:** `git -C <path> rebase main`. Resolve mechanical
      conflicts, and commit any resolution as `fix: resolve rebase onto main
      (TASK-<n>)`. On a stop-and-ask conflict: `git -C <path> rebase --abort` and
      return **STOPPED: conflict** with the files and both sides' intent. Do not
      guess.
   2. **Verify in the worktree:** all three checks pass. If they fail, fix only what
      the rebase broke. Anything more: return **STOPPED: post-rebase failure** with
      the failing output, and leave the worktree as is.
   3. **Land:** from the main checkout, `git merge --ff-only task-<n>`, then run the
      checks on `main`.
   4. **Remove** only if `git merge-base --is-ancestor task-<n> main` holds:
      `ORCA worktree rm --worktree name:task-<n> --json`, with no `--force`. Wait
      until `git worktree list` no longer shows it, then `git branch -D task-<n>`
      if the branch still exists. If removal is refused, do not force: return
      **STOPPED: removal refused** with `git -C <path> status --porcelain -uall`.
   5. **Do not** touch `backlog/`, push, or start the next task. Return a short
      report: outcome, commit range `<first>..<last>`, check results, any
      resolutions made (file and one line each), and whether the worktree is gone.
3. **Handle the report (you).**
   - **STOPPED: conflict:** tell the user, skip this task, and continue with the
     next one only if it doesn't depend on this one.
   - **STOPPED: post-rebase failure:** skip with that reason.
   - **STOPPED: removal refused:** show the status output and ask whether to move,
     delete or keep the files. Only "delete" authorises `--force`, and you run it.
   - **Landed:** verify it yourself: `git merge-base --is-ancestor task-<n> main`
     (or the branch is gone and the commits are on `main`) and run the checks on
     `main`. Review any resolutions the subworker made. If a check fails or a
     resolution touched logic, treat it as a stop-and-ask.
4. **Close the task (you)** on `main`:
   - `BL task edit <n> -s Done`
   - `--check-ac` for each AC that the worker's report and your review showed was met
   - check the DoD items
   - append a line to the final summary: `Landed <first>..<last> on main`

   Commit: `chore(backlog): TASK-<n> done`. An AC that was **not** met blocks Done:
   leave the task `In Review`, report it, and continue.

## 5. Newly unblocked

Recompute the ready set: `To Do` tasks whose dependencies are now all `Done`. Report
it, and flag whether any of them start a new milestone (demo gate) or are `plan`
tasks (coordinator work). Use AskUserQuestion to offer running `/backlog-unleash` for
them. Don't start anything without a yes.

## 6. Report

Show a table per task: landed (commit range) / skipped (reason), worktree removed or
kept. Then the newly ready tasks, and a closing line: "`main` is N commits ahead of
origin; nothing was pushed."

## Common mistakes

| Mistake | Reality |
|---|---|
| "The worker's tests passed" / "the subworker said green" | Re-run the checks yourself on `main` after each landing. |
| Letting the subworker resolve a docs/contracts conflict or edit `backlog/` | It stops and reports. You decide and you write `backlog/`. |
| Spawning landing subworkers in parallel | They share `main`. One at a time. |
| Landing an `In Review` task the user didn't approve | `In Review` means waiting for the human. It is not approval. |
| Resolving a conflict in docs or contracts by picking a side | Stop and ask. Those are design decisions. |
| `--force` to finish cleanup | A refusal means files exist only there. Ask. |
| Marking Done with an unmet AC | Leave it `In Review` and report it. |
| Pushing because "local is ahead" | Never push. Report it. |
