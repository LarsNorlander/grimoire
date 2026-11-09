---
name: herdr-layout
description: Set up or fix Lars's standard herdr layout for the current tab sizes. Run when Lars invokes it, or as the main agent when there is no `cmd` pane.
---

# herdr layout

Make every tab you own match these rules at its current size. Only the main
agent runs this. A tab that already fits is left alone, so a second run
changes nothing.

## Rules

Your tab and pane are `main`; Lars's command pane is `cmd`.

- Wide tab (columns > 2 × rows; cells are about twice as tall as wide):
  `cmd` on the right, a third of the columns, at least 80.
- Tall tab: `cmd` below, a third of the rows, at least 24.
- If `main` would get less than `cmd`, give `cmd` its own tab, also named
  `cmd`.

A second worker on a task shares the task's tab, side by side on a wide tab
or stacked on a tall one, if each half gets at least 80 columns or 24 rows.
Otherwise it gets its own tab, named after itself.

## Steps

1. Measure each tab you own with `herdr pane layout --pane <a pane in it>`.
2. If there is no `cmd` pane, create one: split `main` with
   `--no-focus --ratio (size − cmd) / size` and name it `cmd`. Name your tab
   and pane `main` if they aren't already.
3. Move `cmd` or a second worker if its place no longer fits the rules,
   including between a split and its own tab. `pane move` within a tab
   does nothing. Instead, move the pane to a new tab, then back with
   `--split <direction> --target-pane <id> --ratio <r>`; the emptied tab
   closes by itself. Never move `main`.
4. Reset sizes, because splits keep their ratio when the window resizes:
   `herdr pane resize --pane <first> --direction <d> --amount <new − old ratio>`,
   where `<first>` is the split's first pane (`main`, or the first worker in
   a task tab). The amount is a ratio change, not cells. On a tall tab
   `down` grows the first pane and `up` shrinks it. Check the sizes with
   `herdr pane layout` afterwards.
5. Report one line per tab you changed, e.g. `main: cmd moved below, 24
   rows`, or "Layout already fits" if nothing changed.
