# AGENTS.md

Tightened for modern AI: 2026-11-10.

Instructions for every AI agent working in this repository. `CLAUDE.md` and `GEMINI.md` are
one-line pointers to this file: **do not edit them.** Put every instruction here, and label one
that applies to a single tool with that tool's name
([DEC-033](https://github.com/CloudSecurityAlliance-Internal/CINO-Engineering/blob/main/DECISIONS.md#dec-033-agentsmd-is-the-instruction-file-claudemd-and-geminimd-are-one-line-pointers-never-full-files)).

**Read [`ENGINEERING.md`](ENGINEERING.md) before changing anything.** It holds this repository's
facts, once, for every agent ([ADR-004](DECISIONS-ADR.md)); this file holds the rules and the
traps.

## Rules

- **Land work through a PR; never commit to `main`.** `main` is the release: every install
  one-liner fetches `HEAD` ([ADR-001](DECISIONS-ADR.md)).
- **Commit subjects state the claim the change makes**, not the file that changed.
- **Before pushing, run `./tools/check-all.sh` (it mirrors CI) and read its tail and its exit
  code.** Don't grep for `all checks passed`, which individual checkers also print, and don't
  pipe it through `head`: that is how `main` stayed red for six commits
  ([#132](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/132)).
- **Both platforms, or neither.** A behavioural change goes into the `.sh` and the `.ps1`
  together. `check-parity.py` rejects a one-sided one, and declaring it `PLATFORM_ONLY` to get
  past that creates the divergence
  [#111](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/111) exists to find.
- **Bump `SCRIPT_VERSION` on any script you change:** the UTC time, ISO 8601 to the **minute**,
  e.g. `2026-10-26T05:04Z`
  ([ENGINEERING.md → Script versioning](ENGINEERING.md#script-versioning)).
- **A new guard needs a self-test** that breaks its own rule on purpose, validated against the
  commit where the real defect lived ([ADR-005](DECISIONS-ADR.md)).
- **A change that adds MCP support says which client it is for**, and a step added for one
  client still needs its macOS/Windows counterpart.

## Traps

- **Don't patch these scripts through a shell heredoc.** The quoting layers silently mangle
  their backslashes (`printf '\n\033[1m'`, PowerShell backticks, regex in string literals).
  Write the patch to a file and run it, or avoid backslashes entirely (`chr(10)`)
  ([FRICTION-002](FRICTION.md)).
- **This repo installs Claude Code itself, with its native installer, which auto-updates.**
  Never route it through Homebrew or npm. `@anthropic-ai/claude-code` appears in the scripts only
  as an old install to migrate *away from*. `claude update` in the `*-update` scripts is Claude
  Code's; `codex` and `gemini` update as npm globals.
- **On Windows, Claude Desktop holds the MCP servers' entry points open.** That is why
  `Check-RunningTools` exists and a `uv tool install --force` is refused while a client runs:
  the rebuild is not atomic and leaves a husk. **Identify a client by its path, never its
  process name:** Claude Code's updater renames its running image, e.g.
  `claude.exe.old.1790878548618.45752` ([TODO.md](TODO.md) H1, item 2).
- **`scripts/csa-claude-connectors.py` is report-only unless `--apply`.**
- **Which clients get CSA tooling depends on who registers it.** The local CSA MCP servers are
  registered with Claude Code, Claude Desktop, Codex and Gemini by the private gate repo's setup
  scripts, which these scripts fetch and run
  ([ENGINEERING.md → The CSA contracts](ENGINEERING.md#the-csa-contracts)). This repo's own code
  registers only the CSA plugin marketplaces and the hosted `csa-mcp` server, and only with
  Claude Code, against the user's own GitHub identity. Each client's MCP config format:
  [`docs/mcp-servers.md`](docs/mcp-servers.md). Wider coverage:
  [#176](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/176).
- **Claude Code:** there is no `/check-all` command; run `./tools/check-all.sh`.

## Reference

- [`ENGINEERING.md`](ENGINEERING.md): the scripts, why `main` is the release, Windows
  PowerShell 5.1 and the `Invoke-Native*` wrappers, the parity contract, the duplicated
  six-script lists, the guard layer, and what `check-all.sh` proves and does not. Its first
  table says which section to read when.
- [`BUSINESS-CASE.md`](BUSINESS-CASE.md): why any of it exists. [`GOALS.md`](GOALS.md): what
  counts as done.
