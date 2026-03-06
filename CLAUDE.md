# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

DesktopSetup is the Cloud Security Alliance's machine bootstrap. Three scripts manage a Mac environment:

- `macos-work-tools.sh` — Core work apps (1Password, Slack, Zoom, Chrome, Office, Git, GitHub CLI) + optional dev profile (VS Code, AWS CLI, Wrangler)
- `macos-ai-tools.sh` — Git, GitHub CLI + auth, AI coding CLIs (Claude Code, Codex, Gemini) with migration from wrong install methods
- `macos-update.sh` — Updates everything: Homebrew formulas/casks, npm globals, pip packages. Snapshots all versions before updating for rollback.

AI skills, MCP server catalogs, and per-project tooling live in separate repositories.

## Repository Structure

```
scripts/
  macos-work-tools.sh   # Work apps + optional dev tools
  macos-ai-tools.sh     # AI coding CLIs
  macos-update.sh       # Update everything + snapshot for rollback
archives/               # Previous script versions for reference
.github/
  ISSUE_TEMPLATE/       # Issue templates for contributions
```

## Conventions

### Scripts (`scripts/`)
- Bash, targeting macOS only (checks `uname -s` at startup)
- The two install scripts share a base layer: Xcode CLI Tools → Homebrew → Node.js/npm
- Must be idempotent — safe to run multiple times
- Must be interactive by default (show plan, ask for confirmation)
- Support `NONINTERACTIVE=1` for CI/automation
- Use `set -euo pipefail`
- Use colored output helpers: `info()`, `warn()`, `error()`, `success()`, `abort()` (abort = error + exit 1)
- Never run as root (check `$EUID` at startup)
- Installation strategy: Homebrew for system tools and desktop apps, native installer for Claude Code (auto-updates), npm for AI CLIs (Codex, Gemini) and dev tools (Wrangler)
- `macos-ai-tools.sh` detects and migrates tools installed via the wrong method (e.g., Claude Code via Homebrew → native installer)
- `macos-work-tools.sh` has profile selection: core (everyone) vs core + dev. Profile is selected interactively; `NONINTERACTIVE=1` always installs core-only (no env var to force dev profile). Uses generic helpers (`install_formula`, `install_cask`, `install_npm_package`) — add new tools by calling these
- `macos-ai-tools.sh` also checks for running AI tool processes (`check_running_tools`) and warns before migrating
- `macos-update.sh` skips Claude Code (auto-updates) but updates Homebrew, npm globals, and pip packages. Respects active virtualenv if set

### Shared boilerplate
All three scripts duplicate their output helpers, precondition checks, and utility functions (`has_command`, `confirm`, `ensure_brew_in_path`). The two install scripts additionally share `install_xcode_cli_tools`, `install_homebrew`, and `install_node`. When changing shared logic, update all files that use it.

### Script execution flow
All three scripts follow the same pattern: `main` → preconditions → preflight (show plan) → confirm → action steps → summary. `macos-ai-tools.sh` adds a migration layer: `detect_migrations()` runs during preflight, then `migrate_*()` runs before each tool's install to remove wrong-method installs. `macos-update.sh` takes a pre-update snapshot (to `~/Library/Logs/CSA-DesktopSetup/`) before showing the plan, enabling version rollback if updates break something.

### Validation
No test suite. Use these to check scripts:
```bash
bash -n scripts/macos-work-tools.sh    # syntax check
bash -n scripts/macos-ai-tools.sh
bash -n scripts/macos-update.sh
shellcheck scripts/macos-work-tools.sh  # static analysis (install: brew install shellcheck)
shellcheck scripts/macos-ai-tools.sh
shellcheck scripts/macos-update.sh
```

### Bootstrap commands
```bash
# Work tools
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"

# AI tools
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"

# Update everything
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"
```
The `bash -c "$(...)"` form (not pipe) is required to preserve interactive stdin.
