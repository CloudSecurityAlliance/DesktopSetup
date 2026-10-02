# AGENTS.md

**Read [`ENGINEERING.md`](ENGINEERING.md) first.** It holds this repository's facts — what the
ten scripts are, why `main` is the release, the `Invoke-Native*` wrappers and the measured
Windows PowerShell 5.1 behaviour behind them, the parity contract, the duplicated six-script
lists, the guard layer, and what `tools/check-all.sh` proves and does not.

That file is agent-neutral on purpose; [`CLAUDE.md`](CLAUDE.md) points at the same one. There is
one copy because this repo has `tools/check-duplication.py` precisely because duplicated content
drifts silently, and that argument applies to its own documentation
([ADR-004](DECISIONS-ADR.md)).

Then [`BUSINESS-CASE.md`](BUSINESS-CASE.md) for why any of it exists, and
[`GOALS.md`](GOALS.md) for what counts as done.

## What this repository actually installs

Getting these names right matters, because an earlier version of this file was a mechanical
`Claude` → `Codex` substitution of `CLAUDE.md` and renamed things that were never Claude —
*"AI coding CLIs (Codex, Codex, Gemini)"*, *"`Codex update`"*, *"Codex Desktop"*. A reader
following it would have been misinformed about what these scripts do, in a public repository
([#115](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/115)).

| What | Installed how |
|---|---|
| **Claude Code** | its own native installer — it auto-updates; do not route it through Homebrew or npm |
| **Codex CLI** (`codex`) | `npm -g @openai/codex` |
| **Gemini CLI** (`gemini`) | `npm -g @google/gemini-cli` |
| **Claude Desktop** | Homebrew cask / winget |
| **ChatGPT Desktop** | Homebrew cask / winget |
| four CSA MCP servers | `uv tool install --python`, from setup scripts in a private gate repo |

`@anthropic-ai/claude-code` **does** appear in these scripts, and only as something to migrate
*away from*: `macos-ai-tools.sh` detects a Claude Code installed via npm or Homebrew and replaces
it with the native installer, preserving settings. So seeing that package name in the source does
not mean npm is how it is installed — it means npm is how it was installed wrongly.

The `claude update` command in the `*-update` scripts belongs to Claude Code specifically.
`codex` and `gemini` are updated through npm with the other globals.

## Where support stops, and why

**Plugin marketplaces and MCP registration are Claude Code only today.** Codex and Gemini both
support OAuth-HTTP MCP transports, but their config formats differ, and nothing here writes
them. That is future work rather than a decision against it — if you are extending this, that is
the gap.

So a change that "adds MCP support" has to say *for which client*, and a step added for one
client still needs its macOS/Windows counterpart.

## Conventions this repo expects of you

- **Commit subjects state the claim the change makes**, not the file that changed.
- **Land work through a PR**, never a direct commit to `main` — and `main` is the release, so
  this is not ceremony.
- **Run `./tools/check-all.sh`** and read its **tail** and exit code. Do not grep for
  `all checks passed`: individual checkers print that string too, and a `head` on the output is
  how `main` stayed red for six commits
  ([#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132)).
- **A new guard needs a self-test** that breaks its own rule on purpose, and should be validated
  against the commit where the real defect lived ([ADR-005](DECISIONS-ADR.md)).
- **Both platforms, or neither.** A behavioural change goes into the `.sh` and the `.ps1`
  together; `check-parity.py` will reject a one-sided one, and declaring it `PLATFORM_ONLY` to
  get past that creates the exact divergence
  [#111](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/111) exists to find.
- **Bump `SCRIPT_VERSION`** on any script you change — `YYYY.MMDDHHMM`, UTC, **minutes**.
- **Editing these files through a shell heredoc mangles backslashes.** They are full of `printf
  '\n\033[1m'`, PowerShell backticks and regex in string literals; it went wrong four times in
  one session. Write the patch to a file and run it. See [FRICTION-002](FRICTION.md).
