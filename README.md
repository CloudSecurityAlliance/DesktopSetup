# CSA DesktopSetup

Automated setup for Cloud Security Alliance development environments. Get from a bare machine to productive in a few commands.

## Quick Start — macOS

### Work tools (everyone)

1Password, Slack, Zoom, Chrome, Microsoft Office, Git, GitHub CLI. Optional dev profile adds VS Code, AWS CLI, and Wrangler.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"
```

### AI tools

Claude Code, Codex CLI, Gemini CLI.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
```

### Update everything

Homebrew formulas/casks, npm global packages, pip packages. Saves a snapshot of all installed versions before updating so you can roll back if anything breaks.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"
```

All three macOS scripts are interactive — they show you what they plan to do and ask for confirmation. The install scripts share a base layer (Xcode CLI Tools, Homebrew, Node.js/npm) and install it if not already present.

## Quick Start — Windows

### AI tools

Python, Node.js, Claude Code, Codex CLI, Gemini CLI. Run in PowerShell:

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex
```

Requires Windows 10/11, winget, and Git for Windows. The script detects tools installed via the wrong method (npm or winget for Claude Code, winget for Codex) and migrates them to the correct install method.

## What This Repo Contains

### `scripts/`

Setup scripts. Each is self-contained and idempotent (safe to re-run):

- **`macos-work-tools.sh`** — Core work apps + optional developer tools (macOS)
- **`macos-ai-tools.sh`** — AI coding assistants with migration support (macOS)
- **`macos-update.sh`** — Update all installed tools with version snapshots (macOS)
- **`windows-ai-tools.ps1`** — AI coding assistants with migration support (Windows)

### `docs/`

Design documents and implementation notes for the scripts.

### `archives/`

Previous versions of scripts preserved for reference.

## Updating

### macOS

Run the update script to update everything at once (snapshots versions first):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"
```

Or update individual package managers manually:

```bash
brew update && brew upgrade     # Homebrew formulas and casks
npm update -g                   # npm global packages (Codex, Gemini, Wrangler)
pip install --upgrade pip       # pip itself (Claude Code auto-updates)
```

Snapshots are saved to `~/Library/Logs/CSA-DesktopSetup/` with timestamps.

### Windows

Re-run the AI tools script to upgrade — it detects what's already installed and updates in place. npm tools can also be updated manually:

```powershell
npm update -g @openai/codex @google/gemini-cli
```

Claude Code updates itself automatically.

## Contributing

Found a problem? Have a suggestion?

[Open an issue](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/new/choose) — we have templates for common requests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
