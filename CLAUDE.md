# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

DesktopSetup is the Cloud Security Alliance's machine bootstrap. Scripts manage macOS and Windows environments:

**macOS (Bash):**
- `macos-work-tools.sh` — Core work apps (1Password, Slack, Zoom, Chrome, Office, Git, GitHub CLI) + optional dev profile (VS Code, AWS CLI, Wrangler). Post-install: `gh auth login` + Git identity from GitHub profile
- `macos-ai-tools.sh` — AI desktop apps (Claude Desktop, ChatGPT) + Git, GitHub CLI + auth + Git identity from GitHub profile, AI coding CLIs (Claude Code, Codex, Gemini) with migration from wrong install methods. Registers accessible CSA plugin marketplaces with Claude Code (via `gh`-probed access check)
- `macos-update.sh` — Updates everything: Homebrew formulas/casks, npm globals, pip packages, Claude Code (`claude update`), plus syncs CSA plugin marketplaces (adds missing accessible ones, refreshes all registered). Snapshots all versions before updating for rollback.
- `macos-mcp-setup.sh` — Configures MCP servers (Airtable, GitHub, Gmail) for Claude Code, Codex, and Gemini. Discovers tokens from existing config files and environment, validates them against each service's API, and writes to each tool's config.

**Windows (PowerShell):**
- `windows-work-tools.ps1` — Same tool set as macOS work tools, using winget instead of Homebrew
- `windows-ai-tools.ps1` — Same AI tools as macOS (desktop apps + CLIs), using winget + npm. Includes migration support, Git identity from GitHub profile, and CSA plugin marketplace registration.

**Cross-platform:**
- `clone-and-claude.sh` / `clone-and-claude.ps1` — Clone a CSA repo into `~/GitHub/OrgName/RepoName` and print instructions to launch Claude Code

AI skills, MCP server catalogs, and per-project tooling live in separate repositories.

## Repository Structure

```
scripts/
  macos-work-tools.sh       # Work apps + optional dev tools (macOS)
  macos-ai-tools.sh         # AI desktop apps + coding CLIs (macOS)
  macos-update.sh           # Update everything + snapshot for rollback (macOS)
  macos-mcp-setup.sh        # Configure MCP servers for AI CLIs (macOS)
  windows-work-tools.ps1    # Work apps + optional dev tools (Windows)
  windows-ai-tools.ps1      # AI desktop apps + coding CLIs (Windows)
  clone-and-claude.sh       # Clone repo & launch Claude (macOS)
  clone-and-claude.ps1      # Clone repo & launch Claude (Windows)
archives/                   # Previous script versions for reference
docs/                       # Design documents (e.g., Windows AI tools design/process)
.github/
  ISSUE_TEMPLATE/           # Issue templates for contributions
  rulesets/                 # Branch protection rules
```

## Conventions

### macOS Scripts (Bash)
- Target macOS only (checks `uname -s` at startup)
- `macos-work-tools.sh` base layer: Xcode CLI Tools → Homebrew → Node.js/npm
- `macos-ai-tools.sh` base layer: Xcode CLI Tools → Homebrew → Node.js/npm → Python
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
- Both scripts support migration from wrong install methods (same concept as macOS)
- `windows-work-tools.ps1` does **not** include Microsoft Office (unlike the macOS equivalent); core set is Git, GitHub CLI, 1Password, Slack, Zoom, Chrome — same core + dev profile selection as the macOS equivalent (dev adds VS Code, AWS CLI, Wrangler)

### macos-mcp-setup.sh token pipeline
Unique to this script — token handling follows a strict pipeline:
1. **Discover**: reads tokens from existing CLI configs (`~/.claude.json`, `~/.codex/config.toml`, `~/.gemini/settings.json`) and environment variables, using embedded Python 3 snippets
2. **Deduplicate**: parallel arrays (`FOUND_TOKEN_NAMES`, `FOUND_TOKEN_VALUES`) track seen values; duplicates by value are suppressed
3. **Catalog**: surviving tokens are labeled A, B, C… and displayed with `mask_token()` (shows first 8 + `...` + last 4 chars)
4. **Validate**: each token is tested against the service's live API before being written
5. **Write**: validated tokens are written to each CLI's config file

Requires Python 3 (the script calls `abort` if `python3` is not found). Gmail is handled as a special case — no token can be auto-discovered, so the script prints manual OAuth/GCP setup instructions instead.

### Script versioning
All scripts declare `SCRIPT_VERSION="YYYY.MMDDHHSS"` near the top. Update this value when making changes — use the current date/time in that format.

### Shared boilerplate
All scripts (both platforms) duplicate their output helpers, precondition checks, and utility functions. macOS uses `has_command`, `confirm`, `ensure_brew_in_path`; Windows uses `Has-Command`. The two macOS install scripts additionally share `install_xcode_cli_tools`, `install_homebrew`, `install_node`, `setup_gh_auth`, and `setup_git_identity`. The `CSA_MARKETPLACES` array (list of plugin marketplace `ORG/REPO` strings) is duplicated across `macos-ai-tools.sh`, `windows-ai-tools.ps1`, and `macos-update.sh` — update all three when adding a new marketplace, and bump each file's `SCRIPT_VERSION`. **When changing shared logic, update all files that use it.** The marketplace-name → repo mapping is similarly duplicated across the three scripts: as a `plugin_marketplace_repo` bash function in `macos-ai-tools.sh` and `macos-update.sh` (function-based because macOS ships bash 3.2, which doesn't support `declare -A` associative arrays), and as a `$PluginMarketplaceRepos` hashtable in `windows-ai-tools.ps1`. The actual plugin lists, however, are single-source: `scripts/csa-plugins.txt` and `scripts/csa-plugins-internal.txt` are fetched from HEAD at runtime, so list-only changes do **not** require a script edit or `SCRIPT_VERSION` bump.

### Plugin marketplace registration
`macos-ai-tools.sh`, `windows-ai-tools.ps1`, and `macos-update.sh` share the same silent-by-default registration contract:
1. If `claude` or `gh` is missing, or `gh` is not authenticated, return silently — no warning, no action-item line. A user outside CSA-Internal running the installer should not see chatter about repos they can't see.
2. For each entry in `CSA_MARKETPLACES`: skip if already registered (parsed from `claude plugin marketplace list`); probe access with `gh api repos/$repo` and silently skip on non-zero exit; otherwise `claude plugin marketplace add $repo`.
3. Only print output when a marketplace is actually added (success line) or when `add` itself errors (warn line). Inaccessible and already-registered entries produce no output. The warn line includes the captured stderr from `claude plugin marketplace add`, indented under the failed entry, so the schema/auth/network reason is visible (bash: `add_err="$(cmd 2>&1 >/dev/null)"`; PowerShell: `Invoke-NativeCapture`).
4. The updater additionally runs `claude plugin marketplace update` after the add pass to refresh all registered sources — this step always prints its `Refreshing plugin marketplaces` info line since refreshing is the updater's core purpose.

### Plugin install contract
`macos-ai-tools.sh`, `windows-ai-tools.ps1`, and `macos-update.sh` share a silent-by-default plugin-install contract — similar shape to marketplace registration, but driven by list files:
1. Fetch `scripts/csa-plugins.txt` (public) and `scripts/csa-plugins-internal.txt` (CSA-internal) from HEAD via `curl` / `Invoke-RestMethod`. If both fetches fail or `claude`/`curl` is missing, the whole step is a silent no-op.
2. Each entry is `<plugin>@<marketplace>`. Blank lines and `#`-prefixed lines are ignored.
3. Pass 1: ensure each referenced marketplace is registered. Public marketplaces (`claude-plugins-official`, `anthropic-agent-skills`) register unconditionally. CSA marketplaces (`csa-plugins`, `csa-cino-plugins`, `csa-research-plugins`, `csa-training-plugins`, `csa-plugins-official`, `accounting-plugins`) are `gh`-probed first via their underlying repo — inaccessible ones silently skip every plugin from that marketplace, matching the existing CSA-marketplace registration contract.
4. Pass 2: for each plugin whose marketplace is usable, skip if already installed (silent); otherwise `claude plugin install <entry>`.
5. Output: one success line per marketplace registered + one success line per plugin installed + one warn line per failure with the captured stderr indented under it. Already-installed entries and inaccessible CSA entries produce no output.
6. List-only changes (adding or removing a plugin from either `.txt` file) require a single commit to `main` and propagate to existing users on their next installer or `macos-update.sh` run — no script edit or `SCRIPT_VERSION` bump.

### Script execution flow
All macOS scripts follow the same pattern: `main` → preconditions → preflight (show plan) → confirm → action steps → summary. `macos-ai-tools.sh` adds a migration layer: `detect_migrations()` runs during preflight, then `migrate_*()` runs before each tool's install to remove wrong-method installs. `macos-update.sh` takes a pre-update snapshot (to `~/Library/Logs/CSA-DesktopSetup/`) before showing the plan, enabling version rollback if updates break something.

### Validation
No test suite. Use these to check scripts:
```bash
# macOS — syntax check
bash -n scripts/macos-work-tools.sh
bash -n scripts/macos-ai-tools.sh
bash -n scripts/macos-update.sh
bash -n scripts/macos-mcp-setup.sh
bash -n scripts/clone-and-claude.sh

# macOS — static analysis (install: brew install shellcheck)
shellcheck scripts/macos-work-tools.sh
shellcheck scripts/macos-ai-tools.sh
shellcheck scripts/macos-update.sh
shellcheck scripts/macos-mcp-setup.sh
shellcheck scripts/clone-and-claude.sh
```

There is no equivalent linter configured for the PowerShell scripts. PSScriptAnalyzer can be used if available (`Invoke-ScriptAnalyzer -Path scripts/windows-*.ps1`).

### Bootstrap commands
All bootstrap one-liners include a `Cache-Control: no-cache` header to bypass the `raw.githubusercontent.com` CDN edge cache — without it, a stale copy can persist for a few minutes after a fix ships. Keep this header in every documented bootstrap command (README.md included).

```bash
# macOS — Work tools
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"

# macOS — AI tools
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

# macOS — Update everything
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"

# macOS — Configure MCP servers
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-mcp-setup.sh)"

# macOS — Clone repo & start Claude
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
```

```powershell
# Windows — Work tools
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex

# Windows — AI tools
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 -Headers @{'Cache-Control'='no-cache'} | iex

# Windows — Clone repo & start Claude
$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 -Headers @{'Cache-Control'='no-cache'} | iex
```
The macOS `bash -c "$(...)"` form (not pipe) is required to preserve interactive stdin.
