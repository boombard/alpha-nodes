---
name: backlog-unleash
description: Explicit-only (user types /backlog-unleash [task-ids]). Starts one supervised Sonnet Orca worker per ready Backlog.md task (To Do, all dependencies Done), up to 3 unmerged tasks in flight, reviews each result (as many fix rounds as needed, escalating stubborn issues to Opus with the user's approval), and leaves tasks In Review for the human. Kicks off work only; landing is /backlog-converge's job.
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
- **Review until resolved.** After a worker reports done you review, and send as
many rounds of concrete fixes as it takes. Each round after the first re-checks
only what changed since the last round, and tracks each finding as open or
resolved. A finding is **stubborn** when it is still open after 2 consecutive
rounds, or when the worker pushes back and you still think it's a defect. Don't
keep looping on a stubborn finding: see step 5.4.
- **Escalation to Opus needs the user's approval.** Never fix a stubborn finding
yourself, or spawn an Opus worker for it, without an explicit yes.
- **Delegation:** two mechanical jobs go to a Sonnet subagent (Agent tool,
`subagent_type: "general-purpose"`, `model: "sonnet"`, foreground, self-contained
prompt, since it starts cold): computing the ready set (step 2) and the
post-worker checks (step 5.1). Judgment stays with you: the diff review, worker
questions, the milestone gate, dropped-list reasoning and Rulings to check.
- **Failures are left alone:** worktree and commits kept, task stays
`In Progress` with a note. No automatic retry.

## 1. Preconditions

1. `ORCA status --json`: the runtime is reachable.
2. You are on `main` in the main checkout, and `git status --porcelain --untracked-files=no` is empty (untracked files such as `spikes/` don't block).
3. `BL task list --plain` works.

## 2. Ready set

Delegate this to a **Haiku subagent** so the bulk task-file reading stays out of  
your context. Tell it the definitions above (ready, `plan` label, WIP cap, Files
overlap), the user's ids if any, and to **read-only** use `BL task list --plain`,
`BL task <id> --plain` and `ORCA worktree list --json`. It returns: in-flight
count and free slots; the candidates (id, title, milestone, dependencies, what each
unblocks, Files list); the dropped list with reasons; and any milestone-gate
candidates. It never edits anything.

- **With task ids from the user:** each must be ready. The subagent reports any that
aren't, and why.
- **Otherwise:** it computes the ready set from each task's `status` and
`dependencies` (the frontmatter; `BL task <id> --plain`).

Spot-check its answer before you act on it: when the user named the ids (so step 3's
table won't be shown), confirm each id's status and dependencies yourself with
`BL task <id> --plain`. Otherwise the step 3 table is the check.

It drops each of the following, recording why:

- `plan`-labelled tasks: **coordinator task**.
- Tasks that already have an Orca worktree named `task-<n>` (`ORCA worktree list --json`):
**already started**.
- Anything beyond the free slots, lowest task number first: **over WIP cap**.

Then check the candidates against each other: tasks starting together must have
disjoint **Files** lists. If two overlap, keep the lower-numbered one and drop the
other with the reason **file overlap with task-**<m>.

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
  1. **Mechanical checks, delegated** to a Haiku subagent (read-only): the worktree  
   is clean, has at least 1 commit ahead of `main`, every commit subject carries
   `(TASK-<n>)`, and `git diff --name-only main...task-<n>` lists no file outside
   the task's Files list (it names any that are). It returns those facts in a few
   lines and runs nothing that changes the worktree. If a check fails, treat it
   as a finding for the fix round below, not a stop.
  2. Review the diff (`git diff main...task-<n>`) against the task's ACs, Files,
   Interfaces, the Global Constraints, the Review Focus items it owns, and the
   `CLAUDE.md` code-documentation rule (missing or boilerplate docstrings are a finding). Use the
   `code-review` skill at `medium` on that range if the diff is over \~300 lines.
  3. If you find something, send an `orchestration send` round with concrete fixes
   (one numbered finding per item, each naming the file and the expected change),
   then end your turn. When the worker reports again, re-run the mechanical checks
   and review only the delta (`git diff <previous head>..task-<n>`) against your
   open findings, plus anything new it touched. Send another round if any remain
   open. Repeat until none are open.
  4. **Stubborn findings.** If a finding is stubborn (see Fixed decisions), stop the
   loop for it. Use AskUserQuestion to show the finding, the rounds it survived and
   the worker's response, and offer: **escalate to Opus** (you fix it directly in
   the worker's worktree, committing as `fix: <what> (TASK-<n>)`, once the worker is
   idle), **leave it for the human** (record it in the summary), or **one more
   round** with different guidance. Act only on the answer. Other open findings
   continue their normal rounds.
  5. When no findings are open, or the user has chosen to leave the rest:
     - `BL task edit <n> -s "In Review"`
     - `BL task edit <n> --final-summary "<worker summary + review rounds taken + your verdict + open points>"`
     - Commit `backlog/`.
- **`worker_done` failed, `escalation`, or `exited`/`lost`:** leave the worktree and
status alone, add a `--notes` line with the reason, commit, and report it.

The worker stays open (`--keep-open`) for the human.

## 6. Report (when every worker in the wave has settled)

Show a table per task:

- **In Review**: worktree `task-<n>`, commits ahead, your verdict, open points.
- **Failed** or **stalled**: the reason.

Add the dropped list with its reasons. Next think about **Rulings to check**: every decision a  
worker or you made that the task didn't dictate, with what it costs if wrong. There may be no rulings.

For each ruling:

- Think about the ruling. Does it need to be addressed further?
- If it does, think about a proposed solution for that ruling. It could be, for example, sending another round to a task worker, or making modifications to backlog.md.

Then present a set of questions for each ruling to the user, specifying the ruling, along with your recommended proposal.  
Once the questions (if any) have been answered, go ahead with delegation and implementation.

Close with: "Review the `task-<n>` worktrees in Orca. Send feedback through me,
or run `/backlog-converge <ids>` to land approved ones."

## Common mistakes


| Mistake                                                        | Reality                                                                                       |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Counting only `In Progress` toward the cap                     | Unmerged `In Review` work still costs review attention. Cap `In Progress` + `In Review` at 3. |
| Dispatching a `plan` task                                      | Plan tasks are the coordinator's, gated by the human.                                         |
| Letting workers update task status                             | Workers never touch `backlog/`. Branch edits to it cause merge conflicts.                     |
| Polling `check` in a loop                                      | End your turn. Orca wakes you.                                                                |
| Looping forever on the same finding                            | After 2 rounds it's stubborn: ask the user about escalating to Opus.                          |
| Escalating to Opus without asking                              | Escalation needs the user's explicit yes.                                                     |
| Re-reviewing the whole diff every round                        | Review only the delta since the last round, against the open findings.                        |
| Trusting the ready-set subagent when no confirm table is shown | Verify each user-named id with `BL task <id> --plain`.                                        |
| Letting a subagent change anything                             | The ready-set and check subagents are read-only.                                              |
| Setting `In Progress` before `worker-start` succeeds           | Status follows a successful start only.                                                       |
| Leaving `backlog/` edits uncommitted on `main`                 | Commit them immediately. Converge needs a clean `main`.                                       |
