# CSA DesktopSetup

Automated setup for Cloud Security Alliance development environments on **macOS** and **Windows**. Get from a bare machine to running AI coding assistants in a few commands.

## Quick Start — AI tools

Installs Claude Desktop, ChatGPT Desktop, Claude Code, Codex CLI, and Gemini CLI. The install scripts walk you through GitHub login (`gh auth login`) and configure your Git identity from your GitHub profile. They also detect tools installed via the wrong method (e.g., Claude Code via Homebrew or npm) and migrate them to the correct installer.

### macOS

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
```

The macOS script shares a base layer (Xcode CLI Tools, Homebrew, Node.js/npm, Python) and installs it if not already present.

### Windows

Windows requires one-time PowerShell setup before running any script in this repo.

> **Not your personal machine?** Changing the execution policy is a security setting. If this is a work laptop managed by your IT department, ask them for permission before proceeding.

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

**Step 3 — Run the AI tools script.** Close the Administrator window and open a regular PowerShell window:

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex
```

The Windows AI tools script also installs Git, GitHub CLI, Python, and Node.js (via winget) alongside the AI apps and CLIs. Requires Windows 10/11 and winget.

**Step 4 — Restore the original policy.** Once you're done running scripts, re-open PowerShell as Administrator and set the policy back to whatever Step 1 reported:

```powershell
Set-ExecutionPolicy Restricted
```

Replace `Restricted` with the value from Step 1. If you plan to run PowerShell scripts regularly, you can leave it as `RemoteSigned`.

## MCP servers (macOS)

Connect your AI coding CLIs to Airtable, GitHub, and Gmail. Scans your existing config files and environment for tokens, validates each against the service's API, deduplicates them into a labeled catalog (A, B, C…), and writes the right token to each tool. Also detects and removes old npm/stdio-based MCP entries that no longer work.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-mcp-setup.sh)"
```

## Clone a repo & start Claude

Once AI tools are installed, use these one-liners to clone any CSA repo and launch Claude Code. Replace `ORG/REPO` with the actual org and repo name.

### macOS

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.sh)" -- ORG/REPO
```

### Windows

```powershell
$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 | iex
```

The scripts check prerequisites, clone the repo to `~/GitHub/OrgName/RepoName`, and tell you how to launch Claude Code. Safe to re-run — they skip the clone if the repo already exists and pull latest changes instead.

## Updating

### macOS

Run the update script to update everything at once (Homebrew formulas/casks, npm globals, pip packages, and Claude Code). Saves a snapshot of all installed versions before updating so you can roll back if anything breaks:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-update.sh)"
```

Or update individual package managers manually:

```bash
brew update && brew upgrade     # Homebrew formulas and casks
npm update -g                   # npm global packages (Codex, Gemini, Wrangler)
pip install --upgrade pip       # pip itself
claude update                   # Claude Code
```

Snapshots are saved to `~/Library/Logs/CSA-DesktopSetup/` with timestamps.

### Windows

Re-run either install script to upgrade — they detect what's already installed and update in place. npm tools can also be updated manually:

```powershell
npm update -g @openai/codex @google/gemini-cli
```

Claude Code updates itself automatically.

---

## Work tools (productivity apps)

Optional — install these alongside AI tools for a complete work setup. Covers productivity, communication, browser, and (optionally) general developer tools.

### macOS

**Installs:** 1Password, Slack, Zoom, Chrome, Microsoft Office, Git, GitHub CLI. Optional dev profile adds VS Code, AWS CLI, and Wrangler.

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-work-tools.sh)"
```

### Windows

**Installs:** Git, GitHub CLI, 1Password, Slack, Zoom, Chrome. Optional dev profile adds VS Code, AWS CLI, and Wrangler. Requires the PowerShell execution policy from the Windows AI tools section above.

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 | iex
```

## Repository contents

### `scripts/`

Each script is self-contained and idempotent (safe to re-run):

- **`macos-ai-tools.sh`** — AI desktop apps and coding assistants with migration support (macOS)
- **`macos-mcp-setup.sh`** — Discover, validate, and write MCP server tokens (Airtable, GitHub, Gmail) for Claude Code, Codex, and Gemini; cleans up legacy npm/stdio entries (macOS)
- **`macos-update.sh`** — Update all installed tools with version snapshots (macOS)
- **`macos-work-tools.sh`** — Core work apps + optional developer tools (macOS)
- **`windows-ai-tools.ps1`** — AI desktop apps and coding assistants with migration support (Windows)
- **`windows-work-tools.ps1`** — Core work apps + optional developer tools (Windows)
- **`clone-and-claude.sh`** — Clone a CSA repo and set up for Claude Code (macOS)
- **`clone-and-claude.ps1`** — Clone a CSA repo and set up for Claude Code (Windows)

### `docs/`

Design documents and implementation notes for the scripts.

### `archives/`

Previous versions of scripts preserved for reference.

## Contributing

Found a problem? Have a suggestion?

[Open an issue](https://github.com/CloudSecurityAlliance/DesktopSetup/issues/new/choose) — we have templates for common requests.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
