# User Preferences

## Bash Tool Usage

- **Never chain `cd` with other commands** — Don't use `cd /path && git status` or `cd /path && ./gradlew test`. Instead, run `cd` as a separate Bash call first, then run the command in a follow-up call. This ensures commands like `git status` match permission allows correctly, rather than being treated as an unrecognized `cd`-prefixed command that triggers a manual approval prompt every time.

## Scripting Conventions

- **Unix philosophy** — Do one thing well. Use stdin/stdout/stderr for composability. Use exit codes for success/failure.
- **Language choice** — Bash/sh for simple linear scripts. Python for anything with branching logic, data parsing, or complexity.
- **No external dependencies** — System-installed interpreters and stdlib only.
- **Naming** — Lowercase, hyphen-separated, verb-first for actions (e.g., `monitor-mysql-restore`). No file extensions — the shebang determines the interpreter.
- **Shebang required** — `#!/usr/bin/env bash` or `#!/usr/bin/env python3`. Make executable.
- **System versions** — bash 3.2 (no associative arrays, `mapfile`, `|&`), Python 3.9 (no `match/case`, `tomllib`).
