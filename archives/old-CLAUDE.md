# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DesktopSetup is a Cloud Security Alliance project that provides idempotent macOS setup scripts for bootstrapping a standardized AI development toolchain. It installs and configures Homebrew, Python (via pyenv), Node.js, AI CLI tools (Claude Code, Gemini CLI, Codex, MCPB), and 1Password.

## Repository Structure

- **`macos-install.sh`** — Main installation script (~720 lines). Installs/updates all tools via Homebrew (primary), npm, or pip. Supports interactive and non-interactive (`NONINTERACTIVE=1`) modes. Each AI tool's package manager is configurable via environment variables (e.g., `CSA_CLAUDE_PKG_MGR`, `CSA_GEMINI_PKG_MGR`).
- **`macos-mcp-claude-desktop.sh`** — Configures MCP servers for Claude Desktop by editing `~/Library/Application Support/Claude/claude_desktop_config.json`. Currently supports Tableau MCP server. Uses Python for JSON manipulation.
- **`ai-agent-skills.md`** — Inventory of AI agent skills for per-project installation (not global). Documents detection criteria, installation methods, and integration strategy for skills like Cloudflare.

## Architecture

Three-layer design:

1. **Machine Setup** (`macos-install.sh`) — Global tool installation, idempotent
2. **AI Configuration** (`macos-mcp-claude-desktop.sh`) — Claude Desktop MCP server setup, creates backups before changes
3. **Project Context** (`ai-agent-skills.md`) — Per-project skill installation guidance, referenced from global `~/.claude/CLAUDE.md`

## Key Design Patterns

- **Idempotency**: Both scripts detect existing installations and skip/upgrade accordingly
- **Conflict avoidance**: `macos-install.sh` skips Homebrew install if a tool binary exists outside Homebrew
- **Safety guards**: Scripts abort on non-macOS, refuse to run as root (except containers), validate JSON before MCP config changes
- **Preflight plan**: In interactive mode, `macos-install.sh` shows a summary of planned actions before executing

## Build/Test/Lint

No build system, test suite, or CI/CD pipeline. These are standalone bash scripts. To validate:
- Run `bash -n macos-install.sh` or `bash -n macos-mcp-claude-desktop.sh` for syntax checking
- Use `shellcheck macos-install.sh` or `shellcheck macos-mcp-claude-desktop.sh` for static analysis

## Script Conventions

- Colored output helpers: `info()`, `warn()`, `error()`, `success()` functions
- Both scripts check `[[ "$OSTYPE" == darwin* ]]` and `[[ $EUID -eq 0 ]]` at startup
- `macos-install.sh` uses `set -euo pipefail`; helper functions return status codes rather than exiting directly
- `macos-mcp-claude-desktop.sh` delegates JSON operations to inline Python via a `json_operation()` function
