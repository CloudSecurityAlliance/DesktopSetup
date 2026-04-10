# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

DesktopSetup is the Cloud Security Alliance's machine bootstrap. Scripts manage macOS and Windows environments:

**macOS (Bash):**
- `macos-work-tools.sh` — Core work apps (1Password, Slack, Zoom, Chrome, Office, Git, GitHub CLI) + optional dev profile (VS Code, AWS CLI, Wrangler). Post-install: `gh auth login` + Git identity from GitHub profile
- `macos-ai-tools.sh` — AI desktop apps (Claude Desktop, ChatGPT) + Git, GitHub CLI + auth + Git identity from GitHub profile, AI coding CLIs (Claude Code, Codex, Gemini) with migration from wrong install methods
- `macos-update.sh` — Updates everything: Homebrew formulas/casks, npm globals, pip packages. Snapshots all versions before updating for rollback.
- `macos-mcp-setup.sh` — Configures MCP servers (Airtable, GitHub, Gmail) for Claude Code, Codex, and Gemini. Discovers tokens from existing config files and environment, validates them against each service's API, and writes to each tool's config.

**Windows (PowerShell):**
- `windows-work-tools.ps1` — Same tool set as macOS work tools, using winget instead of Homebrew
- `windows-ai-tools.ps1` — Same AI tools as macOS (desktop apps + CLIs), using winget + npm. Includes migration support.

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
- Support `NONINTERACTIVE=1` for CI/automation
- Use `set -euo pipefail`
- Use colored output helpers: `info()`, `warn()`, `error()`, `success()`, `abort()` (abort = error + exit 1)
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
- `windows-work-tools.ps1` does **not** include Microsoft Office (unlike the macOS equivalent); installs Git, GitHub CLI, 1Password, Slack, Zoom, Chrome only

### Script versioning
All scripts declare `SCRIPT_VERSION="YYYY.MMDDHHSS"` near the top. Update this value when making changes — use the current date/time in that format.

### Shared boilerplate
All scripts (both platforms) duplicate their output helpers, precondition checks, and utility functions. macOS uses `has_command`, `confirm`, `ensure_brew_in_path`; Windows uses `Has-Command`. The two macOS install scripts additionally share `install_xcode_cli_tools`, `install_homebrew`, `install_node`, `setup_gh_auth`, and `setup_git_identity`. **When changing shared logic, update all files that use it.**

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
```bash
# macOS — Work tools
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"

# macOS — AI tools
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

# macOS — Update everything
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"

# macOS — Configure MCP servers
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-mcp-setup.sh)"

# macOS — Clone repo & start Claude
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
```

```powershell
# Windows — Work tools
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 | iex

# Windows — AI tools
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex

# Windows — Clone repo & start Claude
$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 | iex
```
The macOS `bash -c "$(...)"` form (not pipe) is required to preserve interactive stdin.
