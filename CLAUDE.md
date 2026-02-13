# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

DesktopSetup is the Cloud Security Alliance's machine bootstrap. Two scripts take a bare Mac to a working environment:

- `macos-work-tools.sh` — Core work apps (1Password, Slack, Zoom, Chrome, Office, Git, GitHub CLI) + optional dev profile (VS Code, AWS CLI, Wrangler)
- `macos-ai-tools.sh` — AI coding CLIs (Claude Code, Codex, Gemini) with migration from wrong install methods

AI skills, MCP server catalogs, and per-project tooling live in separate repositories.

## Repository Structure

```
scripts/
  macos-work-tools.sh   # Work apps + optional dev tools
  macos-ai-tools.sh     # AI coding CLIs
archives/               # Previous script versions for reference
.github/
  ISSUE_TEMPLATE/       # Issue templates for contributions
```

## Conventions

### Scripts (`scripts/`)
- Bash, targeting macOS only (checks `uname -s` at startup)
- Both scripts share a base layer: Xcode CLI Tools → Homebrew → Node.js/npm
- Must be idempotent — safe to run multiple times
- Must be interactive by default (show plan, ask for confirmation)
- Support `NONINTERACTIVE=1` for CI/automation
- Use `set -euo pipefail`
- Use colored output helpers: `info()`, `warn()`, `error()`, `success()`
- Never run as root (check `$EUID` at startup)
- Installation strategy: Homebrew for system tools and desktop apps, native installer for Claude Code (auto-updates), npm for AI CLIs (Codex, Gemini) and dev tools (Wrangler)
- `macos-ai-tools.sh` detects and migrates tools installed via the wrong method (e.g., Claude Code via Homebrew → native installer)
- `macos-work-tools.sh` has profile selection: core (everyone) vs core + dev

### Bootstrap commands
```bash
# Work tools
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"

# AI tools
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
```
The `bash -c "$(...)"` form (not pipe) is required to preserve interactive stdin.
