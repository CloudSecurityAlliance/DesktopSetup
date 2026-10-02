# CLAUDE.md

**Read [`ENGINEERING.md`](ENGINEERING.md) first.** It holds this repository's facts — what the
ten scripts are, why `main` is the release, the `Invoke-Native*` wrappers and the measured 5.1
behaviour behind them, the parity contract, the duplicated six-script lists, the guard layer,
and what `tools/check-all.sh` proves and does not.

That file is agent-neutral on purpose; [`AGENTS.md`](AGENTS.md) points at the same one. There is
one copy because this repo has `tools/check-duplication.py` precisely because duplicated content
drifts silently, and that argument applies to its own documentation
([ADR-004](DECISIONS-ADR.md)).

Then [`BUSINESS-CASE.md`](BUSINESS-CASE.md) for why any of it exists, and
[`GOALS.md`](GOALS.md) for what counts as done.

## Specific to Claude Code

- **`/check-all` is not a thing; run `./tools/check-all.sh`.** It mirrors CI exactly. Read its
  **tail** and its exit code — do not grep for `all checks passed`, which individual checkers
  also print, and do not pipe through `head`. That is how `main` stayed red for six commits
  ([#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132)).
- **This repo installs the thing you are running in.** `scripts/*-ai-tools.*` install Claude
  Code via its native installer (it auto-updates; do not route it through Homebrew or npm), and
  register CSA plugin marketplaces and the `csa-mcp` server against the user's own GitHub
  identity.
- **Claude Desktop holds the MCP server entry points open on Windows.** That is why
  `Check-RunningTools` exists and why a `uv tool install --force` is refused while a client is
  running — the rebuild is not atomic and leaves a husk. Identify clients by **path**: a live
  Claude Code process once reported its name as `claude.exe.old.1790878548618.45752`, because
  its own updater had renamed its running image.
- **`scripts/csa-claude-connectors.py`** disables chosen claude.ai connectors so the CSA Google
  MCP servers are used instead. Report-only unless `--apply`.
- **Editing these scripts from a Claude Code session on Windows:** patching them through a Bash
  heredoc mangles backslashes, four times in one session — these files are full of `printf
  '\n\033[1m'`, PowerShell backticks and regex in string literals. Write the patch to a file and
  run it, or avoid backslashes entirely (`chr(10)`). See [FRICTION-002](FRICTION.md).

## Conventions this repo expects of you

- **Commit subjects state the claim the change makes**, not the file that changed.
- **Land work through a PR**, never a direct commit to `main` — and `main` is the release, so
  this is not ceremony.
- **A new guard needs a self-test** that breaks its own rule on purpose, and should be validated
  against the commit where the real defect lived ([ADR-005](DECISIONS-ADR.md)).
- **Both platforms, or neither.** A behavioural change goes into the `.sh` and the `.ps1`
  together; `check-parity.py` will reject a one-sided one, and declaring it `PLATFORM_ONLY` to
  get past that creates the exact divergence
  [#111](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/111) exists to find.
- **Bump `SCRIPT_VERSION`** on any script you change — `YYYY.MMDDHHMM`, UTC, **minutes**.
