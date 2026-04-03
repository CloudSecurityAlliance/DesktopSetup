# CSA DesktopSetup

Automated setup for Cloud Security Alliance development environments on **macOS** and **Windows**. Get from a bare machine to productive in a few commands.

## Quick Start — macOS

### Work tools (everyone)

1Password, Slack, Zoom, Chrome, Microsoft Office, Git, GitHub CLI. Optional dev profile adds VS Code, AWS CLI, and Wrangler.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"
```

### AI tools

Claude Desktop, ChatGPT Desktop, Claude Code, Codex CLI, Gemini CLI.

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

### Prerequisite: enable PowerShell script execution

> **Not your personal machine?** Changing the execution policy is a security setting. If this is a work laptop managed by your IT department, ask them for permission before proceeding. They may already have a policy in place or prefer to make this change for you.

**Step 1 — Check your current policy.** Open PowerShell as Administrator (press the Windows key, type `powershell`, right-click **Windows PowerShell**, and select **Run as administrator**). Then run:

```powershell
Get-ExecutionPolicy
```

Note the value it returns (usually `Restricted` on a fresh install). You'll restore this afterwards.

**Step 2 — Temporarily allow script execution:**

```powershell
Set-ExecutionPolicy RemoteSigned
```

When prompted "Do you want to change the execution policy?", type `Y` and press Enter.

**Step 3 — Run the setup scripts** (see below). Close the Administrator window and open a regular PowerShell window to run them.

**Step 4 — Restore the original policy.** Once you're done running the scripts, open PowerShell as Administrator again and set the policy back to whatever Step 1 reported:

```powershell
Set-ExecutionPolicy Restricted
```

Replace `Restricted` with whatever value you noted in Step 1. If you plan to run PowerShell scripts regularly, you can leave it as `RemoteSigned`.

Then, open a regular PowerShell window and run the scripts below.

### Work tools (everyone)

Git, GitHub CLI, 1Password, Slack, Zoom, Chrome. Optional dev profile adds VS Code, AWS CLI, and Wrangler.

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 | iex
```

### AI tools

Git, GitHub CLI, Python, Node.js, Claude Desktop, ChatGPT Desktop, Claude Code, Codex CLI, Gemini CLI.

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex
```

Both Windows scripts require Windows 10/11 and winget. They install Git and GitHub CLI automatically. The AI tools script detects tools installed via the wrong method (npm or winget for Claude Code, winget for Codex) and migrates them to the correct install method.

## Clone a repo & start Claude

Once the AI tools are installed, use these one-liners to clone any CSA repo and get started with Claude Code. Replace `ORG/REPO` with the actual org and repo name.

### macOS

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
```

### Windows

```powershell
$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 | iex
```

The scripts check prerequisites, clone the repo to `~/GitHub/OrgName/RepoName`, and tell you how to launch Claude Code. Safe to re-run — they skip the clone if the repo already exists and pull latest changes instead.

## What This Repo Contains

### `scripts/`

Setup scripts. Each is self-contained and idempotent (safe to re-run):

- **`macos-work-tools.sh`** — Core work apps + optional developer tools (macOS)
- **`macos-ai-tools.sh`** — AI desktop apps and coding assistants with migration support (macOS)
- **`macos-update.sh`** — Update all installed tools with version snapshots (macOS)
- **`windows-work-tools.ps1`** — Core work apps + optional developer tools (Windows)
- **`windows-ai-tools.ps1`** — AI desktop apps and coding assistants with migration support (Windows)
- **`clone-and-claude.sh`** — Clone a CSA repo and set up for Claude Code (macOS)
- **`clone-and-claude.ps1`** — Clone a CSA repo and set up for Claude Code (Windows)

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

Re-run either script to upgrade — they detect what's already installed and update in place. npm tools can also be updated manually:

```powershell
npm update -g @openai/codex @google/gemini-cli
```

Claude Code updates itself automatically.

## Contributing

Found a problem? Have a suggestion?

[Open an issue](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/new/choose) — we have templates for common requests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
