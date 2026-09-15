# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

DesktopSetup is the Cloud Security Alliance's machine bootstrap. Scripts manage macOS and Windows environments:

**macOS (Bash):**
- `macos-work-tools.sh` — Core work apps (1Password, Slack, Zoom, Chrome, Office, Git, GitHub CLI) + optional dev profile (VS Code, AWS CLI, Wrangler). Post-install: `gh auth login` + Git identity from GitHub profile
- `macos-ai-tools.sh` — AI desktop apps (Claude Desktop, ChatGPT) + Git, GitHub CLI + auth + Git identity from GitHub profile, AI coding CLIs (Claude Code, Codex, Gemini) with migration from wrong install methods. Registers accessible CSA plugin marketplaces with Claude Code (via `gh`-probed access check) and the CSA MCP server (`csa-mcp`) for users with CSA-Internal access
- `macos-update.sh` — Updates everything: Homebrew formulas/casks, npm globals, pip packages, Claude Code (`claude update`), plus syncs CSA plugin marketplaces (adds missing accessible ones, refreshes all registered) and registers the CSA MCP server if missing. Snapshots all versions before updating for rollback.
- `macos-plugins.sh` — Standalone plugin install/update. Just the plugin-related work from `macos-update.sh` (register CSA marketplaces, install default plugins, refresh marketplaces, register CSA MCP server) without the Homebrew/npm/pip steps. Use when you just want to get current on plugins without the full update cycle.

**Windows (PowerShell):**
- `windows-work-tools.ps1` — Same tool set as macOS work tools, using winget instead of Homebrew
- `windows-ai-tools.ps1` — Same AI tools as macOS (desktop apps + CLIs), using winget + npm. Includes migration support, Git identity from GitHub profile, CSA plugin marketplace registration, and CSA MCP server registration.
- `windows-update.ps1` — Updates everything, Windows counterpart to `macos-update.sh`: `winget upgrade --all`, npm globals, pip itself plus every outdated package, `claude update`, then the marketplace/plugin/MCP sync. Snapshots installed versions to `%LOCALAPPDATA%\CSA-DesktopSetup\` before touching anything, for rollback.
- `windows-plugins.ps1` — Standalone plugin install/update, Windows counterpart to `macos-plugins.sh`. Runs just the plugin workflow without touching winget apps.

**Cross-platform:**
- `clone-and-claude.sh` / `clone-and-claude.ps1` — Clone a CSA repo into `~/GitHub/OrgName/RepoName` and print instructions to launch Claude Code

AI skills, MCP server catalogs, and per-project tooling live in separate repositories.

## Repository Structure

```
scripts/
  macos-work-tools.sh       # Work apps + optional dev tools (macOS)
  macos-ai-tools.sh         # AI desktop apps + coding CLIs (macOS)
  macos-update.sh           # Update everything + snapshot for rollback (macOS)
  macos-plugins.sh          # Standalone plugin install/update (macOS)
  windows-work-tools.ps1    # Work apps + optional dev tools (Windows)
  windows-ai-tools.ps1      # AI desktop apps + coding CLIs (Windows)
  windows-update.ps1        # Update everything + snapshot for rollback (Windows)
  windows-plugins.ps1       # Standalone plugin install/update (Windows)
  clone-and-claude.sh       # Clone repo & launch Claude (macOS)
  clone-and-claude.ps1      # Clone repo & launch Claude (Windows)
  csa-plugins.txt           # Public default plugin list (fetched from HEAD at runtime)
  csa-plugins-internal.txt  # CSA-internal default plugin list (fetched from HEAD at runtime)
tools/
  check-all.sh              # Everything CI runs, locally, in one command
  check-*.py                # Repo-specific static checks — all seven also run in CI
  sweep-csa-sources.sh      # Weekly drift sweep (network + gh, NOT in check-all.sh)
tests/
  test_*.py                 # Standalone executables — run one directly with python3
  NativeWrappers.Tests.ps1  # Pester; the only suite needing real 5.1 to mean anything
archives/                   # Previous script versions for reference
docs/
  periodic-sweep.md         # Weekly sweep runbook — what drifts and where to fix it
  mcp-servers.md            # Historical MCP config reference (third-party servers)
TODO.md                     # Audit findings, priority-grouped; cites functions, never line numbers
.github/
  ISSUE_TEMPLATE/           # Issue templates for contributions
  rulesets/                 # Branch protection rules
```

## Conventions

### macOS Scripts (Bash)
- Target macOS only (checks `uname -s` at startup)
- `macos-work-tools.sh` base layer: Xcode CLI Tools → Homebrew → Node.js/npm
- `macos-ai-tools.sh` base layer: Xcode CLI Tools → Homebrew → Node.js/npm → uv → Python
- **Python comes from uv, with Homebrew as the fallback** (CINO-Platform-Engineering DEC-012). `install_uv` runs before `install_python`; `install_python` provisions `CSA_PYTHON_PREFERRED` via `uv python install` and only falls back to `brew install python` if uv is missing or fails. **But it provisions nothing at all when the machine already has a floor-clearing Python** — `install_python` returns early on any `find_usable_python` hit, deliberately, so an existing install is never churned. So the honest claim is *clean machines converge on `CSA_PYTHON_PREFERRED`*, not *every machine runs the same version*: a Mac that already had `brew install python` keeps 3.14, and the cross-platform version split is closed for new machines only. Both floors are taken from the consumer that asks for most, never picked: `CSA_PYTHON_MIN=3.10` from CSA-Document-Pipeline's `requires-python`, and the Node floor of 22 from Wrangler's `engines.node`. **uv creates no PATH shims for interpreters it manages** (measured, uv 0.12.10), so `find_usable_python` / `Find-UsablePython` probe PATH first and then ask `uv python find` directly — PATH probing alone would miss a good uv Python and install a second one.
- Must be idempotent — safe to run multiple times
- Must be interactive by default (show plan, ask for confirmation)
- Support `NONINTERACTIVE=1` for CI/automation — also auto-detected when `$CI` is set or stdin is not a TTY
- Use `set -euo pipefail`
- Use colored output helpers: `info()`, `warn()`, `error()`, `success()`, `abort()` (abort = error + exit 1); colors are stripped automatically when stdout is not a TTY (`[[ -t 1 ]]` guard)
- Never run as root (check `$EUID` at startup) — exception: root is allowed inside containers (`.dockerenv` / `/run/.containerenv`) for CI use
- Installation strategy: Homebrew for system tools and desktop apps, native installer for Claude Code (auto-updates), npm for AI CLIs (Codex, Gemini) and dev tools (Wrangler)
- `macos-ai-tools.sh` detects and migrates tools installed via the wrong method (e.g., Claude Code via Homebrew → native installer)
- `macos-work-tools.sh` has profile selection: core (everyone) vs core + dev. Profile is selected interactively; `NONINTERACTIVE=1` always installs core-only (no env var to force dev profile). Uses generic helpers (`install_formula`, `install_cask`, `install_npm_package`) — add new tools by calling these
- `macos-ai-tools.sh` also checks for running AI tool processes (`check_running_tools`) and warns before migrating
- `macos-update.sh` runs `claude update` in addition to Homebrew, npm globals, and pip packages. Respects active virtualenv if set

### Windows Scripts (PowerShell)
- Target Windows 10/11, require winget
- Use `$ErrorActionPreference = 'Stop'`
- Same output helper pattern: `Write-Info`, `Write-Success`, `Write-Warn`, `Write-Err`, `Abort`
- Same utility function pattern: `Has-Command` instead of `has_command`
- Installation strategy: winget for system tools and desktop apps, npm for AI CLIs
- `windows-ai-tools.ps1` base layer: winget → Git, GitHub CLI, Node.js, Python (installed if missing); `windows-work-tools.ps1` installs Node.js (core, via `OpenJS.NodeJS.LTS`) but not Python
- Both scripts support migration from wrong install methods (same concept as macOS)
- Core set matches macOS: Git, GitHub CLI, 1Password, Slack, Zoom, Chrome, Microsoft Office (`Microsoft.Office`, which winget lists as "Microsoft 365 Apps for enterprise"), with the same core + dev profile selection (dev adds VS Code, AWS CLI, Wrangler). Office used to be macOS-only; that exception is closed. On a machine with a managed M365 deployment winget reports it as already installed and skips it

### Script versioning
All scripts declare a version string near the top — `SCRIPT_VERSION="YYYY.MMDDHHSS"` in the bash scripts, `$ScriptVersion = "YYYY.MMDDHHSS"` in the PowerShell scripts. Update this value when making changes — use the current date/time in that format.

### Shared boilerplate
**These are checked now, not just documented.** `.github/workflows/lint.yml` runs on every PR: `bash -n` + shellcheck on the `.sh` files, and — because GitHub runners have `pwsh` and the authoring machine does not — a **parse check and PSScriptAnalyzer on the `.ps1` files**, which had never been verified anywhere before. Plus seven repo-specific checks in `tools/` (`check-duplication.py`, `check-parity.py`, `check-powershell-native.py`, `check-pipeline-assignments.py`, `check-paste-safety.py`, `check-shell-tail-conditionals.py`, `check-todo-citations.py`), of which these are worth explaining:

- **`check-duplication.py`** — a function duplicated across scripts must be byte-identical in behaviour (comments and whitespace ignored). Names that are *meant* to differ live in its `PER_SCRIPT` map with a reason, so allowing a difference is a deliberate act. This turns the instruction below from a discipline into a check; when it was first run, twelve functions had already drifted.
- **`check-parity.py`** — the complement: it catches what `check-duplication.py` structurally cannot, a function that is **absent**. Every macOS script must have a Windows counterpart, and the two `main()` step lists must match once mapped through its `EQUIV` table (`setup_git_identity` ↔ `Setup-GitIdentity`). Compared as sets, since the platforms order their base layers differently. A step on one side only goes in `PLATFORM_ONLY` or `PER_PAIR` with a reason — Xcode tools and Homebrew are macOS-only, `Set-LongPathSupport` is Windows-only — and an allowlist entry that matches nothing is itself reported, because an exception for a step that no longer exists has stopped checking without failing. Run against the scripts as they stood before #69 it reports exactly three problems, which are exactly the three gaps that shipped: no `windows-update.ps1`, no internal setup in `windows-plugins.ps1`, no Git identity in `windows-work-tools.ps1`. It exists because the scripts are silent by default, so *absent* and *nothing to do* look identical at the terminal and an omission never gets reported. **When you add a step to either platform's `main()`, this check will make you say what its counterpart is.**
- **`check-todo-citations.py`** — `TODO.md` cites findings by function name (`` (`macos-update.sh`, `update_pip`) ``), never by line number, and every cited function must still exist. The original `file:line` citations had all rotted within seven months, C2 by 243 lines — onto unrelated code about the same topic, which is worse than an obviously wrong citation. Re-anchoring them is also how H5 turned out to be fixed while still marked open.
- **`check-powershell-native.py`** — a native command (`winget`, `npm`, `gh`, `claude`, `git`, `icacls`, …) invoked in a script that sets `$ErrorActionPreference = 'Stop'` must go through a wrapper that sets `'Continue'`, or a `try/catch`. When first run this found 14 unguarded calls, 13 of them in `windows-work-tools.ps1`, including every `winget install/upgrade` and `npm install -g`; npm writes deprecation warnings to stderr routinely, so that script terminated on a *successful* run.

  **The full behaviour, measured on 5.1.26100** — in the shape these scripts actually run in, `& ([ScriptBlock]::Create(…))` invoked from a `'Stop'` session, which is how one script here runs another:

  | form | result |
  |---|---|
  | bare call | kills the script **and its caller** |
  | `\| Out-Null` | kills the script and its caller |
  | `$x = cmd` (assignment) | kills the script and its caller |
  | `cmd 2>$null` | kills the script and its caller |
  | `cmd *> $null` | kills the script and its caller |
  | `$x = cmd 2>&1 \| Out-String` | kills the script and its caller |
  | any of the above, after `EAP = 'Continue'` | **all six survive** |

  So **no form of redirection helps** — `2>$null` hides the text, not the termination — and a bare call is no safer than a redirected one. The trap that makes this hard to believe: standalone, the same error is only *statement*-terminating, so the script carries on and every form above looks survivable in isolation. Inside `& ([ScriptBlock]::Create(…))` the whole invocation is **one statement in the caller**, so an error that merely ends a statement in the callee ends the entire call in the caller. Measure it the way it is deployed or not at all. (This table exists because the note it replaced had the conclusion backwards, twice — once in each direction.)

  The check also **self-tests before it reports**: an inline fixture it must fail on, run first, because two separate bugs here (a `\w*` that swallowed command names, a six-line `try {` window that exempted exactly the region where the wrappers live) each turned it into a check that printed *"all native calls are guarded"* no matter what. A clean bill of health from a check that cannot fail is worse than no check, because it is believed.

**Run everything locally with `./tools/check-all.sh`** — it mirrors CI exactly.

### Debug mode

`CSA_DEBUG=1` makes any script write a timestamped, mode-0600 log to `$HOME` —
`desktopsetup-YYYYMMDD-HHMMSS.log` — while still printing to the screen. An environment
variable rather than a flag because the documented invocation is `curl … | bash` / `irm … |
iex`, which passes no argument vector at all (`NONINTERACTIVE` already works this way).

Two different mechanisms, for a reason:

- **PowerShell:** the five `Invoke-Native*` wrappers log. Nothing at the call sites changed,
  because `check-powershell-native.py` already guarantees every native command goes through
  one — the wrappers were already the choke point.
- **bash:** `exec > >(csa_redact | tee -a "$CSA_LOG") 2>&1`, process-wide. There is no
  equivalent choke point here (bash has no `NativeCommandError` problem, so there are no
  wrappers), and retrofitting one onto ~1000 lines of direct calls would capture only the
  calls someone remembered. The redirection captures everything, including code written
  before anyone thought about logging. Verified on bash 3.2.57: no output is lost, on a clean
  exit, an `exit N`, or an uncaught failure under `set -e`.

`CSA_LOG` is **exported**, so the CSA-internal setup — fetched and run as a separate process —
appends to the *same* file instead of opening a second one. One file per run: the person
debugging is being asked to send a log, and "send both of them, and mind the timestamps" is
how half a report goes missing. The bash redactor is line-buffered (`sed -l`, or `-u` on GNU)
so the parent's output does not sit in the pipe while the child writes to the file ahead of it.

Credential shapes are redacted **keeping the key** — `client_secret: <redacted>` still says
which line failed, `<redacted>` does not — and ANSI colour is stripped from the file only. The
patterns are verified by extracting the live code from each script and running the same cases
through it; that check found two real defects, `${keep}` leaking as literal text and the JSON
form `"client_secret": "…"` not matching at all. The OAuth client fetch is excluded from
logging *by construction* rather than by pattern, because a base64 blob has no shape to match.

### What local `pwsh` proves, and what it does not

`brew install powershell` gives PowerShell **7**; the Windows scripts run under **Windows
PowerShell 5.1**. They differ on precisely the behaviour the `Invoke-Native*` wrappers exist
for. Measured, not assumed:

| | stderr on a **successful** command | non-zero exit |
|---|---|---|
| **Windows PowerShell 5.1** | **terminates** ← the bug | terminates |
| pwsh 7, `$PSNativeCommandUseErrorActionPreference=$false` *(default)* | survives | survives |
| pwsh 7, same flag `$true` | **survives** | terminates |

In 5.1, *stderr output* becomes a terminating `NativeCommandError` under
`$ErrorActionPreference='Stop'` whatever the exit code. In pwsh 7 that is not an error condition
under **any** setting — the flag only makes a non-zero *exit code* respect the preference.

**So local pwsh will tell you the wrappers are unnecessary, and it will be wrong.** Do not
remove them on the strength of a green run on macOS. `tests/NativeWrappers.Tests.ps1` records
this table and tests what *is* testable everywhere: the wrappers' return values, `$LASTEXITCODE`
preservation, and that they restore `$ErrorActionPreference`. CI additionally runs the suite
under real 5.1 on `windows-latest`, which is the only place the difference is exercised.

Local pwsh is genuinely useful for: instant parse checking, PSScriptAnalyzer, and Pester tests of
pure logic. It is not a substitute for running the installers on Windows.

**What has now actually been run on Windows, and what has not.** On 2026-09-15, on Windows 11
26200 under **real Windows PowerShell 5.1** (5.1.26100.9444), these were exercised against the
live machine: `windows-update.ps1`'s `Test-Preconditions`, `Save-Snapshot` (real file written,
verified BOM-free and one-record-per-line), `Show-Preflight` (including the live plugin
comparison, which hits the network), `Show-Summary`, and the `pip list --outdated --format=json`
parse; plus `windows-work-tools.ps1`'s `Setup-GitIdentity`. The technique was to strip the
trailing `Main` invocation and dot-source the script, so the real shipping code ran without the
mutating half. **Still never run: any installer end to end, and any actual upgrade** —
`winget upgrade --all`, `npm update -g`, `claude update`. So the parts that decide *what* to do
are tested on the target runtime; the parts that *do* it are not.

All scripts (both platforms) duplicate their output helpers, precondition checks, and utility functions. macOS uses `has_command`, `confirm`, `ensure_brew_in_path`; Windows uses `Has-Command`. The two macOS install scripts additionally share `install_xcode_cli_tools`, `install_homebrew`, `install_node`, `setup_gh_auth`, and `setup_git_identity`. The `CSA_MARKETPLACES` array (list of plugin marketplace `ORG/REPO` strings) is duplicated across **six** scripts: `macos-ai-tools.sh`, `macos-update.sh`, `macos-plugins.sh`, `windows-ai-tools.ps1`, `windows-update.ps1`, `windows-plugins.ps1` — update all six when adding a new marketplace, and bump each file's `SCRIPT_VERSION`. **When changing shared logic, update all files that use it.** The marketplace-name → repo mapping is similarly duplicated across all six scripts: as a `plugin_marketplace_repo` bash function in the three `.sh` files (function-based because macOS ships bash 3.2, which doesn't support `declare -A` associative arrays), and as a `$PluginMarketplaceRepos` hashtable in the three `.ps1` files. The same six files also share the CSA MCP server registration logic (`setup_csa_mcp_server` / `Register-CSAMcpServer`) and the constants `CSA_MCP_NAME`, `CSA_MCP_URL`, `CSA_MCP_GATE_REPO` — keep these in sync too. The actual plugin lists, however, are single-source: `scripts/csa-plugins.txt` and `scripts/csa-plugins-internal.txt` are fetched from HEAD at runtime, so list-only changes do **not** require a script edit or `SCRIPT_VERSION` bump.

### What a Windows authoring machine proves, and what it does not

Sibling to the `pwsh` note above, and the same lesson from the other direction. This repo was
authored on a Mac; the test suite first ran on Windows on 2026-09-15 and ten of eleven checks
failed — none of them because the scripts were wrong. Measured on Windows 11 26200 with Git
for Windows:

| | macOS / Linux | Windows |
|---|---|---|
| `Path.read_text()` default encoding | UTF-8 | **cp1252** — dies on bytes `0x81 0x8D 0x8F 0x90 0x9D` |
| `Path.chmod(0o755)` | mode `0o755` | mode **`0o666`** — Python cannot set the exec bit |
| `test -x stub` under Git Bash | true | **false** — yet the stub still runs (see below) |
| bare `"bash"` via `subprocess` | `/bin/bash` | **`System32\bash.exe`**, the WSL launcher |
| `shutil.which("bash")` | `/bin/bash` | `…\Git\usr\bin\bash.EXE` — *disagrees with the line above* |
| `pty.fork()` | works | **absent** — no `termios`, and `winpty` refuses a piped stdin |

Four consequences worth keeping:

- **Pin every `read_text`/`write_text` to `encoding="utf-8"`.** Not `errors="replace"`: that
  decodes cp1252 without raising and silently substitutes U+FFFD, so `check-duplication.py`
  would compare two functions *after* corrupting both identically — they differ in a non-ASCII
  character and still compare equal. A check that cannot fail, again. cp1252 only chokes on
  five byte values, so a file passes or fails on whether it happens to contain one; three
  checks here were passing by luck, not correctness.
- **Resolve `bash` absolutely, and never as a bare name.** `shutil.which` and `CreateProcess`
  resolve `"bash"` to *different binaries* on Windows, and the one `CreateProcess` picks is the
  WSL launcher, which exits 1 with a UTF-16LE "no installed distributions" message. That reads
  as the test failing, not as bash being missing. `tests/*.py` share a `_posix_bash()` helper
  that prefers Git Bash and refuses anything under `System32`; `CSA_TEST_BASH` overrides it.
- **The stub-executable technique still works.** The tests intercept `npm`/`gh`/`claude` by
  putting shebang'd stubs on a stub-only PATH. Windows cannot mark them executable and `test -x`
  agrees, but MSYS2 resolves and runs them anyway by sniffing the `#!`. So no Windows-specific
  test suite is needed — measure before assuming a POSIX technique is unavailable, because the
  obvious reading of `chmod` here is wrong.
- **`tests/test_prompt_visibility.py` is the one genuine casualty**, and it exits **77**
  ("skipped") rather than pretending to pass. It needs a real pty on *both* ends — three
  cheaper harnesses each produced a false negative, so a Windows substitute would risk being a
  fourth. `check-all.sh` counts 77 separately and says so in its summary, because a check that
  did not run must never be reported as one that passed. CI still runs it on every PR.

**So a green run on Windows is worth slightly less than a green run on macOS** — one fewer
check — and `check-all.sh` tells you so explicitly rather than leaving you to remember it.

### Plugin marketplace registration
`macos-ai-tools.sh`, `macos-update.sh`, `macos-plugins.sh`, `windows-ai-tools.ps1`, `windows-update.ps1`, and `windows-plugins.ps1` share the same silent-by-default registration contract:
1. If `claude` or `gh` is missing, or `gh` is not authenticated, return silently — no warning, no action-item line. A user outside CSA-Internal running the installer should not see chatter about repos they can't see.
2. For each entry in `CSA_MARKETPLACES`: skip if already registered (parsed from `claude plugin marketplace list`); probe access with `gh api repos/$repo` and silently skip on non-zero exit; otherwise `claude plugin marketplace add $repo`.
3. Only print output when a marketplace is actually added (success line) or when `add` itself errors (warn line). Inaccessible and already-registered entries produce no output. The warn line includes the captured stderr from `claude plugin marketplace add`, indented under the failed entry, so the schema/auth/network reason is visible (bash: `add_err="$(cmd 2>&1 >/dev/null)"`; PowerShell: `Invoke-NativeCapture`).
4. The updater additionally runs `claude plugin marketplace update` after the add pass to refresh all registered sources — this step always prints its `Refreshing plugin marketplaces` info line since refreshing is the updater's core purpose.

### Plugin install contract
The plugin-install contract is shared across all six scripts — `macos-ai-tools.sh`, `macos-update.sh`, `macos-plugins.sh`, `windows-ai-tools.ps1`, `windows-update.ps1`, and `windows-plugins.ps1` — silent-by-default, driven by list files:
1. Fetch `scripts/csa-plugins.txt` (public) and `scripts/csa-plugins-internal.txt` (CSA-internal) from HEAD via `curl` / `Invoke-RestMethod`. If both fetches fail or `claude`/`curl` is missing, the whole step is a silent no-op.
2. Each entry is `<plugin>@<marketplace>`. Blank lines and `#`-prefixed lines are ignored.
3. Pass 1: ensure each referenced marketplace is registered. Public marketplaces (`claude-plugins-official`, `anthropic-agent-skills`) register unconditionally. CSA marketplaces (`csa-plugins`, `csa-cino-plugins`, `csa-research-plugins`, `csa-training-plugins`, `csa-plugins-official`, `accounting-plugins`) are `gh`-probed first via their underlying repo — inaccessible ones silently skip every plugin from that marketplace, matching the existing CSA-marketplace registration contract. Any registrations that happened print a `Registered plugin marketplaces:` success block right after this pass.
4. Pass 2: collect plugins to install (in a usable marketplace, not already installed, deduped across the two list files). This pass only builds a list; it does not hit the network.
5. Pass 3: announce `Installing N plugin(s):` and then install each one with a per-item `  + <plugin>` line on success or `  ! <plugin>` + indented stderr on failure. Progressive output so the user sees forward motion during a long install.
6. Output: silent when nothing needs to happen. Only actual registrations, actual installs, and per-item failures print. A trailing `Plugin install finished with N failure(s)` warn appears if any install failed.
7. Preflight preview: each script's plan-display phase also calls `install_plugins_preview` / `Show-PluginsPreview`, which fetches the list files and compares against `claude plugin list` to print a one-liner like `Plugins  install up to 2 new (38 already present)`. No `gh`-probes, so the count is an upper bound — CSA plugins the user can't access get filtered at actual install time.
8. List-only changes (adding or removing a plugin from either `.txt` file) require a single commit to `main` and propagate to existing users on their next installer or `macos-update.sh` run — no script edit or `SCRIPT_VERSION` bump.

### CSA MCP server registration
`macos-ai-tools.sh`, `macos-update.sh`, `macos-plugins.sh`, `windows-ai-tools.ps1`, `windows-update.ps1`, and `windows-plugins.ps1` register the CSA MCP server (`csa-mcp` → `https://cloudsecurityalliance.org/mcp`, HTTP transport, OAuth 2.1 + PKCE) with Claude Code. The server answers unauthenticated callers, so the gate is not about access — registration is silent-by-default and gated behind a `gh`-probe of `CloudSecurityAlliance-Internal/CSA-Plugins` (a CSA-membership proxy that mirrors the plugin-marketplace contract) because this public bootstrap should only auto-wire CSA tooling into CSA-eligible accounts:
1. If `claude` or `gh` is missing, or `gh` is unauthenticated, return silently — no chatter for users without a CSA-Internal-eligible GitHub account.
2. If `csa-mcp` is already registered (parsed from `claude mcp list`, matching `^csa-mcp[: ]`), return silently. Re-running `claude mcp add` for an existing entry would either error or — if it succeeded — invalidate the user's authenticated OAuth session, so we never clobber.
3. Otherwise, `gh api repos/CloudSecurityAlliance-Internal/CSA-Plugins` is called as the gate. Non-zero exit → silent skip. Zero exit → run `claude mcp add --transport http --scope user csa-mcp https://cloudsecurityalliance.org/mcp`.
4. **Output is silent unless registration actually happened.** On success, print a `Registered Claude Code MCP server: csa-mcp` line followed by `Run /mcp inside Claude Code to authenticate with the CSA MCP server.` (the OAuth flow is browser-driven and must be initiated by the user). On `add` failure, print a warn line with the captured stderr indented underneath, matching the marketplace-add error format.
5. Currently Claude Code only. Codex and Gemini support OAuth-HTTP MCP transports too but their config formats differ; adding them is future work.

### Local CSA MCP servers (`setup_csa_internal_tools`)
Separate mechanism from the hosted `csa-mcp` above, and a **third** place the lists drift. All **six** scripts run `setup_csa_internal_tools` / `Invoke-CSAInternalSetup` — `macos-ai-tools.sh`, `macos-plugins.sh`, `macos-update.sh`, `windows-ai-tools.ps1`, `windows-update.ps1`, `windows-plugins.ps1`. `windows-plugins.ps1` used to lack it entirely, so a Windows user running the standalone plugin script silently got no local MCP servers; closed in #65. The function `gh`-probes the gate repo and then fetches one setup script per server from `CloudSecurityAlliance-Internal/CSA-Plugins/internal-setup/`, executing each with `CSA_NESTED=1`. The servers live in their own public repos (`csa-google-workspace`, `csa-skilljar`, and `csa-zendesk` when it is ready); the setup scripts live in the private gate repo because they carry CSA's OAuth client. A server is wired up by appending its `<name>-setup.sh` to the `setups=()` array — in all six scripts, with a `SCRIPT_VERSION` bump each. The loop uses `continue`, not `return`, so a setup script that is absent (unmerged, renamed) cannot silently disable the servers listed after it.

### Periodic source sweep (weekly, manual for now)
Nothing in CSA notifies this repo when new tooling appears, so **run `./tools/sweep-csa-sources.sh` weekly** — by hand, on a machine whose `gh` has CSA-Internal read access. **Nothing runs it automatically yet.** Long term this belongs on the planned **Operations360** platform (the operations sibling to `CINO-Customer-360` / `Work360-*`), which does not exist as of 2026-09-01. A Claude cloud routine was tried and is parked disabled: the cloud sandbox ships no `gh` binary at all, and fixing it needs a CSA-Internal PAT stored in cloud config — a credential decision, not a technical one. Details in the runbook. It probes the CSA orgs and reports four kinds of drift against four different extension points: unregistered plugin **marketplaces** (`CSA_MARKETPLACES`, 6 scripts), published **plugins** nobody installs (`scripts/csa-plugins*.txt`, list-only change), **MCP servers** that are ready to wire (`setups=()`, 6 scripts), and **version floors** that no longer match what upstream asks for — `CSA_PYTHON_MIN` against CSA-Document-Pipeline's `requires-python`, and the Node floor against the highest `engines.node` among the npm packages we install. The floors are *derived* values, so they are the one thing here that can rot without anyone touching this repo. Exit `0` no drift, `1` drift, `2` could not complete — `2` means "I learned nothing", never "no drift".

Deliberately **not** in `check-all.sh`: it needs the network and a `gh` token with CSA-Internal access, and a check that cannot pass in CI is a check that gets deleted.

**Do not make its probing parallel.** An early version used `xargs -P 12` and reported three repos as having no `marketplace.json` when all three do — a probe that fails under load is indistinguishable from a repo that genuinely lacks the file, so the sweep under-reports and the failure looks exactly like success. It probes sequentially and separates 404 from other errors for that reason. Full rationale, the MCP-description heuristic's known blind spot, and what to do with each finding: [`docs/periodic-sweep.md`](docs/periodic-sweep.md).

### Script execution flow
All macOS scripts follow the same pattern: `main` → preconditions → preflight (show plan) → confirm → action steps → summary. `macos-ai-tools.sh` adds a migration layer: `detect_migrations()` runs during preflight, then `migrate_*()` runs before each tool's install to remove wrong-method installs. `macos-update.sh` takes a pre-update snapshot (to `~/Library/Logs/CSA-DesktopSetup/`) before showing the plan, enabling version rollback if updates break something.

### Validation
**Run `./tools/check-all.sh`** — it mirrors CI. There *is* a test suite now (this section used to say there wasn't):

- `tests/test_prompt_visibility.py` — debug mode must not swallow interactive prompts (uses a real pty; three simpler harnesses each produced a false negative). **The only check that cannot run on Windows** — it exits 77 ("skipped") there rather than pretend to pass; see the Windows note above
- `tests/test_npm_output_filter.py` — npm's install-scripts noise is dropped without hiding npm's failures, and keeps the `grep -v` version as a control so the test can still detect the regression
- `tests/test_version_floors.py` — the interpreter/runtime floors reject what the OS ships (asserts the real `/usr/bin/python3` on macOS, stubs the selection logic so it behaves identically on CI's Linux)
- `tests/test_venv_replacement.py` — replacing the shared venv never leaves the machine worse than it found it; keeps the move-first ordering as a control
- `tests/test_headless.py` — a headless run must not block on a prompt (DEC-013 tier 2)
- `tests/test_survives_tool_failure.py` — one failing tool must not kill the installer (#51)
- `tests/NativeWrappers.Tests.ps1` — the five `Invoke-Native*` wrappers' contract, run under pwsh 7 locally and under real Windows PowerShell 5.1 in CI

Every one of these extracts the code under test out of the shipping script rather than copying it, so a test cannot drift from what runs.

`check-all.sh` ends by asserting **the checks did not change the working tree** — `git status --porcelain --untracked-files=all` compared before and after, so it passes mid-edit and fails only on what the run itself did. Every assertion in the suite once passed while `test_version_floors.py` installed a 167 MB Python into the repo on each Windows run (#67); `git status` found it, not the suite. CI runs the same guard at the end of the `duplication` and `powershell` jobs. Known limit: a file already modified before the run and modified again shows the same porcelain line both times. The lower-level checks:
```bash
# macOS — syntax check
bash -n scripts/macos-work-tools.sh
bash -n scripts/macos-ai-tools.sh
bash -n scripts/macos-update.sh
bash -n scripts/macos-plugins.sh
bash -n scripts/clone-and-claude.sh

# macOS — static analysis (install: brew install shellcheck)
shellcheck scripts/macos-work-tools.sh
shellcheck scripts/macos-ai-tools.sh
shellcheck scripts/macos-update.sh
shellcheck scripts/macos-plugins.sh
shellcheck scripts/clone-and-claude.sh
```

Every test is a standalone executable, so a single one runs on its own — that is the fast loop while iterating:

```bash
python3 tests/test_version_floors.py       # or any one file in tests/ or tools/
```

On Windows the shell-driving tests need a POSIX bash and find Git Bash themselves; set
`CSA_TEST_BASH=/path/to/bash` to point them elsewhere. They must never be handed a bare
`bash` — that resolves to the WSL launcher. Details in the Windows note above.

The PowerShell half needs three things installed before `check-all.sh` covers it; without
them those steps print `skipped`, which is easy to misread as `passed`:

```bash
brew install shellcheck powershell
pwsh -NoProfile -c 'Install-Module PSScriptAnalyzer -Scope CurrentUser'
pwsh -NoProfile -c 'Install-Module Pester -RequiredVersion 5.7.1 -Scope CurrentUser'
```

**Pester is pinned to 5.7.1, deliberately.** Pester 6.1.0's manifest claims Windows
PowerShell 5.1 support, but under real 5.1 it aborts the entire run with "a 'break' or
'continue' statement … escaped from your code" — its own message cites pester/Pester#2669 —
with no `break` anywhere in the suite. Both CI jobs and `check-all.sh` pin the same version
so the test framework is not itself a source of divergence between them. Do not bump it
casually; being current matters less than matching CI.

### Bootstrap commands
All bootstrap one-liners include a `Cache-Control: no-cache` header to bypass the `raw.githubusercontent.com` CDN edge cache — without it, a stale copy can persist for a few minutes after a fix ships. Keep this header in every documented bootstrap command (README.md included).

```bash
# macOS — Work tools
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"

# macOS — AI tools
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

# macOS — Update everything
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"

# macOS — Plugin install/update only (no brew/npm/pip)
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-plugins.sh)"

# macOS — Clone repo & start Claude
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
```

```powershell
# Windows — Work tools
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex

# Windows — AI tools
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex

# Windows — Update everything
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-update.ps1 -Headers @{'Cache-Control'='no-cache'} | iex

# Windows — Plugin install/update only (no winget apps)
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-plugins.ps1 -Headers @{'Cache-Control'='no-cache'} | iex

# Windows — Clone repo & start Claude
$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```
The macOS `bash -c "$(...)"` form (not pipe) is required to preserve interactive stdin.
