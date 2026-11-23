# Development workflow

Solo developer. An Opus coordinator runs on `main` and Sonnet workers run in Orca child
worktrees. The backlog lives in the repo (Backlog.md). There is no Linear.

## Backlog

- Tasks, milestones and the plan doc live in `backlog/`, which is plain Markdown + YAML
  frontmatter. The CLI is pinned: `npx -y backlog.md@1.57.4 <cmd>`.
  - `task list --plain`: all tasks
  - `task <id> --plain`: one task
  - `task edit <id> -s "In Progress"`: change status
  - `board`: kanban view
  - `browser`: web UI
- Statuses: `To Do` → `In Progress` (worker dispatched) → `In Review` (worker done,
  coordinator reviewed, awaiting human) → `Done` (merged to `main`).
- The plan overview, global constraints and review focus are in `backlog/docs/doc-1 - Implementation-plan.md`.

## Task rules

- One task = one reviewable diff:
  - it crosses one module boundary
  - about 150–500 lines including tests, written test-first
  - concrete acceptance: the named tests pass and the whole suite is green
- Every task lists **Files** (create/modify/test) and an **Interfaces** block (Consumes/Produces, exact signatures).
- Tasks that can run at the same time must touch disjoint files.
- Each milestone opens with a `contracts` task (shared models, protocols, toy fixtures).
  The rest of the milestone fans out against it.
- Split a task that needs more than one design decision. Merge a task that only makes sense alongside a sibling.
- Plan in rolling waves: only the next one or two milestones are detailed (see the `plan` tasks).

## Coordinator loop (Opus on `main`, `/orchestration`)

1. **Ready set.** List tasks in `To Do` whose dependencies are all `Done`.
2. **Dispatch** up to **3** at once, one Orca worker each (Sonnet, `--worktree new-child`).
   - The spec is the task file path plus: "follow the Steps; stay inside Files; on a missing
     interface, `ask` instead of inventing one; finish with `worker_done` including test output".
   - Mirror the backlog dependencies with `task-create --deps` so Orca's DAG matches.
   - Set the task `In Progress`.
3. **Review.** When a worker reports done, the coordinator reviews the diff against the task
   (ACs, Interfaces, Global Constraints, Review Focus) and sends **one** round of feedback via
   `orchestration send` if needed. Then it sets the task `In Review` and tells the human.
4. **Human review in Orca.** Feedback goes to the coordinator, which relays it to the worker.
5. **Merge.** Merge in dependency order into `main`. After each merge:
   - rebase in-flight worker branches
   - run the full suite
   - resolve conflicts with the tests as arbiter

   Then set the task `Done`, checking ACs and DoD in the task file (`task edit <id> --check-ac N`).
6. **Repeat** from 1. At a milestone's last task, stop for the **demo gate** described in
   the milestone file. The human signs off before the next milestone's tasks are dispatched.

## Prompts for the coordinator

Start the coordinator as a Claude (Opus) chat in the Orca workspace on `main`, after this
branch has been merged to `main`.

**Shortcut skills** (project skills in `.claude/skills/`; they implement the loop above):
- `/backlog-unleash [task-ids]`: dispatch ready tasks (WIP cap 3), give one review round,
  and leave them `In Review`.
- `/backlog-converge [task-ids]`: land approved `In Review` tasks onto `main` (rebase,
  checks, ff-only, remove worktree, mark Done), then offer to unleash what's newly unblocked.

The longer prompts below do the same things by hand.

**Start or continue a tranche**
```text
/orchestration
You are the alpha-nodes coordinator on main. Read CLAUDE.md, documentation/workflow.md and
backlog/docs/doc-1 - Implementation-plan.md. Follow the coordinator loop in workflow.md:
find the ready set (To Do tasks whose dependencies are all Done), and dispatch up to 3 as Orca
workers (agent claude, model sonnet, --worktree new-child --name task-<id>, --keep-open), one
task each, mirroring backlog dependencies with --deps. Mark each In Progress. When a worker
finishes, review its diff against the task's ACs, Interfaces, Global Constraints and Review
Focus, send at most one round of feedback, then mark it In Review and tell me which worktree
to look at. Do not merge until I approve.
```

**Relay feedback**
```text
Feedback on task-<id>: <what to change>. Send it to that worker, then tell me when it's addressed.
```

**Merge approved work**
```text
task-<id> (and task-<id>) are approved. Merge them into main in dependency order. For each:
merge the branch, run uv run pytest, ruff check and pyright, and resolve conflicts with the tests
as arbiter (ask me if a conflict needs a design decision). Tick its ACs and DoD and mark it Done
in the backlog, then commit. After that, rebase in-flight worker branches onto main and dispatch
newly unblocked tasks (max 3 in flight). Stop at a milestone demo gate.
```

**Milestone gate passed, plan the next one**
```text
The M<n> demo gate is approved. Do the next plan task (task-<id>): create the detailed tasks for
that milestone per its description, show them to me, and wait for approval before dispatching.
```

**Resume after a restart**
```text
/orchestration
Resume as the alpha-nodes coordinator. Reconcile orca orchestration worker-list and
task-list with the backlog statuses, report what's in flight, in review and ready, and wait.
```

## Why not Linear

Agents read and update the task files directly, status changes show up in the same diffs
that get reviewed, and there's no MCP dependency. If collaborators or a mobile board
are ever needed, Linear can mirror the backlog.
