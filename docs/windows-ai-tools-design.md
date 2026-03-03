# Windows AI Tools Script — Design Rationale

This document captures the reasoning behind the design of `scripts/windows-ai-tools.ps1`, the Windows equivalent of `scripts/macos-ai-tools.sh`.

## Goal

A single PowerShell script that installs and maintains the CSA AI coding environment on Windows 10/11, following the same principles as the macOS script: idempotent, interactive by default, detects wrong-method installs and migrates them safely.

## Bootstrap Invocation

The macOS scripts use `bash -c "$(...)"` rather than a pipe, to preserve interactive stdin. The Windows equivalent is:

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex
```

`irm` (Invoke-RestMethod) is native PowerShell and already the pattern used by Claude Code's own installer (`irm https://claude.ai/install.ps1 | iex`). PowerShell handles interactive stdin through the pipe correctly, so the `irm | iex` form works where the bash pipe equivalent does not.

## Why This Script Exists Separately from the macOS Script

The macOS AI tools script does not install Python — it has no need to. On Windows, Python is required because Claude Code skills are heavily Python-based, and unlike macOS (where Python ships with the system or Xcode tools), Windows has no guaranteed Python baseline.

## Package Manager Strategy

The macOS AI tools script uses Homebrew solely as a Node.js delivery mechanism — not for Claude Code, Codex, or Gemini directly. Applying the same lens to Windows: we don't need a general-purpose package manager, just a way to get Node.js.

- **winget** — used only to install Node.js. Ships with Windows 10/11, requires no bootstrap, and is fully automatable with `--accept-package-agreements --accept-source-agreements`.
- **npm** — used for Codex and Gemini, same as macOS.
- **Native installers** — used for Claude Code (Anthropic's installer) and Python (new Python install manager).

Chocolatey and Scoop are not used. They require their own bootstrap and add complexity without benefit given the narrow set of tools we're installing.

## Tool-by-Tool Decisions

### Node.js

- **Correct method**: `winget install OpenJS.NodeJS.LTS`
- **Detection**: `node --version` to check presence; `winget list --id OpenJS.NodeJS` to confirm it's winget-managed
- **Verified on reference machine**: Node.js 22.18.0 via winget (`OpenJS.NodeJS.22`) — correct, with 22.22.0 available as an update

### Claude Code

- **Correct method**: Native installer — `irm https://claude.ai/install.ps1 | iex`
- **Why not npm**: The npm package (`@anthropic-ai/claude-code`) is the legacy install method. The native installer is a self-contained binary with a more reliable auto-updater and no Node.js dependency.
- **Detection of wrong method**: `npm list -g @anthropic-ai/claude-code` or `winget list --id Anthropic.ClaudeCode` (confirmed in winget as of 2026-03, version 2.1.63)
- **Migration**: `npm uninstall -g @anthropic-ai/claude-code` or `winget uninstall --id Anthropic.ClaudeCode`, then run native installer
- **Config safety**: `~/.claude/` is never touched — config is fully separate from the binary location
- **Verified on reference machine**: Claude Code 2.1.55 installed via npm at `AppData\Roaming\npm\claude` — needs migration

### Codex CLI

- **Correct method**: `npm install -g @openai/codex`
- **Detection**: `npm list -g @openai/codex`
- **Wrong methods to detect**: winget, Chocolatey
- **Verified on reference machine**: Codex 0.23.0 via npm — correct

### Gemini CLI

- **Correct method**: `npm install -g @google/gemini-cli`
- **Detection**: `npm list -g @google/gemini-cli`
- **Wrong methods to detect**: winget, Chocolatey
- **Verified on reference machine**: Gemini 0.1.22 via npm — correct

### Python

This is where Windows diverges most significantly from macOS.

**Why not `winget install Python.Python.3.13`?**

It works and is automatable, but uses the traditional installer which:
- Does not fix the Windows 260-character path limit (a real problem for deep venvs and `node_modules` trees)
- Does not handle multiple Python versions cleanly
- Is being explicitly phased out by the Python project in favour of the new install manager

**Why the new Python install manager?**

Python.org's new install manager (Windows Store app ID `9nq7512cxl7t`) is the stated long-term direction:
- Prompts to fix the 260-character path limit at install time
- Handles multiple Python version management cleanly
- Installs to user space (`$env:LOCALAPPDATA\Python\`) — no admin rights needed

**It is interactive by design.** The install manager has a TUI configuration helper that requires human input for system-level decisions (path limit, version selection). This is handled the same way the macOS script handles Xcode CLI Tools — open the Store to the right app, tell the user to follow the prompts, then poll until Python is available:

```powershell
Start-Process "ms-windows-store://pdp/?ProductId=9nq7512cxl7t"
Write-Host "Please complete the Python install manager setup, then press Enter to continue..."
```

**Detection anchor**: The new install manager puts Python at `$env:LOCALAPPDATA\Python\bin\python.exe`. This path is the signal that Python was installed correctly. The Windows Store also registers a stub at `$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe` — this stub must not be confused with a real Python installation.

**Migration policy — Python is not auto-migrated.** If Python is found but not at the expected path, the script warns and instructs the user to install via the new install manager manually, then re-run the script. The risk of silent auto-migration is too high: existing virtual environments would break, pip packages installed in the old location would be orphaned, and PATH changes require a reboot.

**Verified on reference machine**: Python 3.14.3 via new install manager at `$LOCALAPPDATA\Python\bin\python.exe` — correct.

## Wrong-Method Detection: More Fragmented Than macOS

On macOS, Homebrew is the only likely wrong-method package manager. On Windows the landscape is wider:

| Wrong method | Detection |
|---|---|
| npm global | `npm list -g <package>` |
| winget | `winget list --id <package>` |
| Chocolatey | `choco list --local-only <package>` |
| Direct download / unknown path | `Get-Command <tool>` resolves to unexpected path |

The script checks npm and winget. Chocolatey is checked where practical. Unknown-path installs are caught by checking whether `Get-Command` resolves to an expected location.

## Safety Principles

Carried over directly from the macOS script:

1. **Config is never touched** — `~/.claude/`, `~/.codex/`, `~/.gemini/` are preserved across all migrations
2. **Preflight plan first** — show what will change and ask for confirmation before modifying anything
3. **Check for running processes** — warn if claude/codex/gemini processes are running before migrating
4. **Non-interactive mode** — `$env:NONINTERACTIVE = "1"` skips all prompts for CI/automation
5. **Warn, don't abort on optional steps** — Codex and Gemini failures warn and continue; Node.js failure aborts
6. **Python never auto-migrated** — too high a risk of breaking existing environments

## Windows-Specific Considerations

**Execution policy**: `irm | iex` requires at least `RemoteSigned` execution policy. The script checks on startup and aborts with a clear message and fix instructions if the policy is `Restricted` or `AllSigned`.

**Admin rights**: The script targets user-space installs throughout to avoid requiring elevation — winget installs to user scope by default, npm globals go to `AppData\Roaming\npm`, the Python install manager uses `AppData\Local\Python`, and the Claude Code native installer uses `AppData\Local`. The macOS script refuses to run as root; the Windows script should similarly refuse to run from an elevated (Administrator) prompt, for the same reasons.

**PATH refresh**: Windows PATH changes from installers don't take effect in the current PowerShell session. After each install the script refreshes the session PATH:
```powershell
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH","User")
```

**Git requirement**: Claude Code on Windows requires Git for Windows (Git Bash). The script checks for `git` during preconditions and aborts with instructions (`winget install Git.Git`) if not found, rather than letting Claude Code's installer fail with a less obvious error.

## Script Structure

Mirrors `macos-ai-tools.sh`:

```
main
  → preconditions (Windows 10/11, not elevated, execution policy, git present)
  → Check-RunningTools
  → Detect-Migrations
  → Show-Preflight (installation plan)
  → confirm
  → Install-Python    (interactive if not already correct)
  → Install-Node      (winget, automatable)
  → Install-Claude    (native installer, migrate from npm if needed)
  → Install-Codex     (npm)
  → Install-Gemini    (npm)
  → Show-Summary
```
