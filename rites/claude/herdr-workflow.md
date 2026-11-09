---
name: herdr-workflow
description: Lars's rules for main and worker agents in herdr. Load as the main agent before starting or reusing a worker, or opening or closing a tab.
---

# herdr workflow

These rules override `herdr --skill` where they differ; use that guide for
command syntax.

## Tabs

Only the main agent opens and closes tabs. Open them with `--no-focus` and
tell Lars their names; ask before closing one, and leave finished jobs open
until Lars has seen the output.

- `main`: your pane `main`, plus `cmd` unless it has its own tab.
- `<task>`: that task's workers, e.g. `auth-fix`. A worker that doesn't fit
  gets a tab named after itself, e.g. `auth-fix-review`.
- `<task>:<what>` or `<what>`: one server, watcher, tail, or job expected
  to take over a minute, e.g. `auth-fix:api`.

Name every pane you create: workers after themselves, everything else
after its tab (`herdr pane rename`).

## Workers

Reuse before starting: check `herdr agent list` and give the work to the
worker whose context fits it best. If none is a good fit, start a new one
with fresh context rather than stretching an existing worker. Workers stay
open after their task; stop one only when Lars asks.

To start one:

1. Name it `<task>-<role>`, e.g. `auth-fix-review`.
2. Read-only workers (review, research) share your directory. Workers that
   edit files get a worktree:
   `git worktree add ../<repo>.worktrees/<name> -b <name>`. Not
   `herdr worktree create`, which opens a new workspace.
3. A second worker on the same task goes where the `herdr-layout` rules
   put it.
4. Create its pane with `--env AGENT_ROLE=worker`, name it, then
   `herdr agent start <name> --kind <kind> --pane <pane>`; the kind is
   `claude` unless Lars asks for another.
5. Its first prompt gives its task, its directory, you as its main agent,
   and the worker rules: stay in your own pane, report by replying, ask me
   when you need a tab, and leave layout, tabs, and other agents alone.
   Add "commit on your branch" for an editing worker, or "don't edit
   files" for a read-only one.

Talk to workers one way: `herdr agent prompt <name> ... --wait`, then
`herdr agent read`. A worker that needs a tab or a decision says so in its
reply; act, then prompt it to continue.

When an editing worker finishes a change, summarize the diff for Lars and
ask before merging; remove its worktree only after Lars approves.

## Main agents in other workspaces

Read their panes freely; prompt them only when Lars asks.
