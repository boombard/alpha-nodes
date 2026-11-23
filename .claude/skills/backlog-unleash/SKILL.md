---
name: backlog-unleash
description: Explicit-only (user types /backlog-unleash [task-ids]). Starts one supervised Sonnet Orca worker per ready Backlog.md task (To Do, all dependencies Done), up to 3 unmerged tasks in flight, reviews each result once, and leaves tasks In Review for the human. Kicks off work only; landing is /backlog-converge's job.
disable-model-invocation: true
---

# backlog-unleash

Start work on ready Backlog.md tasks in parallel. You are the **coordinator**
(Opus, on `main`). Each worker is a Sonnet agent in its own Orca child
worktree, implementing one task. This is the front half of a pair:
**`backlog-unleash` starts and reviews work; `backlog-converge` lands it.**
Unleash never rebases, merges or pushes, never marks a task Done, and never
runs converge itself.

Load first: `orchestration` (run `ORCA skills get orchestration`, then follow
it for every Orca command), `orca-cli`. `ORCA` is the resolved Orca executable;
`BL` is `npx -y backlog.md@1.57.4`. Read `documentation/workflow.md` and
`backlog/docs/doc-1 - Implementation-plan.md`.

## Fixed decisions (do not re-litigate)

- **Ready** means status `To Do` and every dependency `Done`. Nothing else
  counts as ready: not `In Progress`, not `In Review`, not "nearly done".
- **Plan tasks are never dispatched.** A ready task labelled `plan` is the
  coordinator's own work. Report it as "coordinator task ready", and do it only
  when the user asks, with their approval of the tasks it creates.
- **WIP cap: 3.** In flight means `In Progress` + `In Review`, because unmerged
  work still costs review attention. Slots = 3 − in flight. If that's 0, report
  and stop.
- **Milestone gate.** If a candidate task belongs to a milestone with no
  `In Progress`, `In Review` or `Done` tasks yet, the previous milestone's demo
  gate must be signed off first. Ask about it explicitly at the confirmation step.
- **Workers:** `--agent claude --model sonnet`,
  `--worktree new-child --name task-<n>`, `--keep-open` so the human can chat
  with them. Each worker follows [worker.md](worker.md).
- **The coordinator owns `backlog/`.** Workers never edit it. All status
  changes, notes and summaries are written by you on `main` and committed
  immediately (`chore(backlog): …`), so `main` stays clean for converge.
- **One feedback round.** After a worker reports done you review once and may
  send one round of fixes. Whatever remains goes to the human, not into a loop.
- **Failures are left alone:** worktree and commits kept, task stays
  `In Progress` with a note. No automatic retry.

## 1. Preconditions

1. `ORCA status --json`: the runtime is reachable.
2. You are on `main` in the main checkout, and `git status --porcelain --untracked-files=no` is empty (untracked files such as `spikes/` don't block).
3. `BL task list --plain` works.

## 2. Ready set

- **With task ids from the user:** each must be ready. Report any that aren't, and why.
- **Otherwise:** list all tasks and compute the ready set yourself from each task's
  `status` and `dependencies` (read the frontmatter; `BL task <id> --plain`).

Drop each of the following, recording why:
- `plan`-labelled tasks: **coordinator task**.
- Tasks that already have an Orca worktree named `task-<n>` (`ORCA worktree list --json`):
  **already started**.
- Anything beyond the free slots, lowest task number first: **over WIP cap**.

Then check the candidates against each other: tasks starting together must have
disjoint **Files** lists. If two overlap, keep the lower-numbered one and drop the
other with the reason **file overlap with task-<m>**.

## 3. Confirm (required gate)

Skip the approval question when the user passed explicit ids or explicitly said to
skip confirmation. The **milestone-gate question is never skipped**: it is the human's
demo sign-off, and it can't be pre-waived.
Otherwise show a table: task, title, milestone, what it unblocks, its Files. Below
it, show the dropped list with reasons, and the milestone-gate question if one
applies. Use AskUserQuestion to approve, drop items, or cap the count. Do nothing
until it's approved.

## 4. Start the wave

1. `ORCA orchestration run-create --environment local --objective "backlog-unleash: <ids>" --json`.
   Use **one Run per wave**.
2. For each approved task, create an Orca task that mirrors its backlog dependencies:
   `task-create --environment local --run <run> --task-title "TASK-<n> <title>" --spec-file <spec> --deps '<json ids of Orca tasks for its deps in this Run, else []>'`.
3. Start the workers together, as the orchestration guide's parallel-start form shows:
   `worker-start --environment local --task <orca task> --worktree new-child --name task-<n> --agent claude --model sonnet --keep-open`.
4. Only for a worker whose `worker-start` succeeded:
   - `BL task edit <n> -s "In Progress"`
   - `BL task edit <n> --notes "Worker: dispatch <id>, worktree task-<n>"`

   On failure, don't relaunch. Report `failedStage` and leave the status alone.
5. Commit `backlog/` on `main`: `chore(backlog): start TASK-<n>[, …]`. End your turn.
   Orca wakes you; never poll.

**Worker spec** (write it to a file and pass `--spec-file`). Resolve every path to an absolute path:

```text
Implement Backlog.md task TASK-<n>: <title>.
Task file: <abs path to backlog/tasks/task-<n> - ….md>
Playbook: <abs path to this skill's worker.md> — read it first and follow it exactly;
it overrides any other skill.
Base branch: main. Commit subjects end with (TASK-<n>).
Do not edit backlog/, rebase, merge, push, or touch other worktrees.
Finish with worker_done as the playbook defines.
```

## 5. When a worker reports done

- **`question`:** answer it from the task, the design docs or `doc-1` if the answer
  follows from them. Otherwise relay it to the user and `reply` with their answer.
- **`worker_done` succeeded:**
  1. Verify that the worktree is clean, has at least 1 commit ahead of `main`, and
     every commit subject carries `(TASK-<n>)`.
  2. Review the diff (`git diff main...task-<n>`) against the task's ACs, Files,
     Interfaces, the Global Constraints and the Review Focus items it owns. Use the
     `code-review` skill at `medium` on that range if the diff is over ~300 lines.
  3. If you find something, send **one** `orchestration send` round with concrete
     fixes, then end your turn. When the worker reports again, do not send a second
     round. Record anything left over in the summary.
  4. Then:
     - `BL task edit <n> -s "In Review"`
     - `BL task edit <n> --final-summary "<worker summary + your review verdict + open points>"`
     - Commit `backlog/`.
- **`worker_done` failed, `escalation`, or `exited`/`lost`:** leave the worktree and
  status alone, add a `--notes` line with the reason, commit, and report it.

The worker stays open (`--keep-open`) for the human.

## 6. Report (when every worker in the wave has settled)

Show a table per task:
- **In Review**: worktree `task-<n>`, commits ahead, your verdict, open points.
- **Failed** or **stalled**: the reason.

Add the dropped list with its reasons. List **Rulings to check**: every decision a
worker or you made that the task didn't dictate, with what it costs if wrong.
Close with: "Review the `task-<n>` worktrees in Orca. Send feedback through me,
or run `/backlog-converge <ids>` to land approved ones."

## Common mistakes

| Mistake | Reality |
|---|---|
| Counting only `In Progress` toward the cap | Unmerged `In Review` work still costs review attention. Cap `In Progress` + `In Review` at 3. |
| Dispatching a `plan` task | Plan tasks are the coordinator's, gated by the human. |
| Letting workers update task status | Workers never touch `backlog/`. Branch edits to it cause merge conflicts. |
| Polling `check` in a loop | End your turn. Orca wakes you. |
| A second and third feedback round | One round. The rest goes to the human. |
| Setting `In Progress` before `worker-start` succeeds | Status follows a successful start only. |
| Leaving `backlog/` edits uncommitted on `main` | Commit them immediately. Converge needs a clean `main`. |
