# Instructions: Write windows-ai-tools.ps1

## Your Task

Write `scripts/windows-ai-tools.ps1` — a PowerShell bootstrap script that installs and maintains the CSA AI coding environment on Windows 10/11. It is the Windows equivalent of `scripts/macos-ai-tools.sh`. Read that script first to understand the structure, tone, and conventions you are mirroring.

## Bootstrap Invocation

The script is invoked by the user running this in PowerShell:

```powershell
irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex
```

This is the native PowerShell idiom and preserves interactive stdin correctly.

## Resolve This Before Writing Detection Logic

**You do not yet know where the Claude Code native installer places its binary on Windows.** Before writing the Claude Code detection logic, fetch and read the installer script to find the install path:

```powershell
irm https://claude.ai/install.ps1
```

Look for the target directory where it places the `claude` binary. That path is the anchor for detecting a correct installation vs a wrong-method installation.

## PowerShell Conventions

### Error handling
```powershell
$ErrorActionPreference = 'Stop'
```
Equivalent of `set -euo pipefail`.

### Output helpers
Use colored `Write-Host` output consistently:
```powershell
function Write-Info    { Write-Host "==> $args" -ForegroundColor Cyan }
function Write-Success { Write-Host "==> $args" -ForegroundColor Green }
function Write-Warn    { Write-Host "Warning: $args" -ForegroundColor Yellow }
function Write-Err     { Write-Host "Error: $args" -ForegroundColor Red }
function Abort         { Write-Err $args; exit 1 }
```

### Command detection
```powershell
function Has-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}
```

### Confirmation prompt
```powershell
function Confirm-Step($message) {
    if ($env:NONINTERACTIVE) { return $true }
    $reply = Read-Host "$message [Y/n]"
    return ($reply -eq '' -or $reply -match '^[Yy]')
}
```

### PATH refresh
Run this after every install so subsequent steps can find newly installed tools in the same session:
```powershell
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH","User")
```

### Non-interactive mode
Honour both `$env:NONINTERACTIVE` and `$env:CI`. If either is set, skip all prompts and accept all defaults.

## Preconditions (check at startup, abort if not met)

1. **Windows 10 or 11** — check `[System.Environment]::OSVersion`
2. **Not running as Administrator** — elevated sessions change install paths in ways that break user-space tool detection. Check `[Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()`.
3. **Execution policy** — `irm | iex` requires at least `RemoteSigned`. If policy is `Restricted` or `AllSigned`, abort with the fix: `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`
4. **Git for Windows** — Claude Code requires Git Bash. Check `Has-Command git`. If missing, abort with: `winget install Git.Git`
5. **winget** — check `Has-Command winget`. It ships with Windows 10/11 but may be missing on very old installs.

## Running Process Check

Before doing anything else, check whether any AI tools are currently running and warn the user:

```powershell
$running = @()
if (Get-Process -Name claude  -ErrorAction SilentlyContinue) { $running += "Claude Code" }
if (Get-Process -Name codex   -ErrorAction SilentlyContinue) { $running += "Codex CLI" }
if (Get-Process -Name gemini  -ErrorAction SilentlyContinue) { $running += "Gemini CLI" }
```

If any are running, warn that they will stay on the old version and ask whether to continue.

## Migration Detection

Set these flags before running preflight. They control what the preflight plan displays and what the install functions do.

```powershell
$claudeMigration = ""   # "npm" or "winget" if installed wrong
$codexMigration  = ""   # "winget" or "choco" if installed wrong
$geminiMigration = ""   # "winget" or "choco" if installed wrong
```

### Claude Code — correct method is native installer
```powershell
# Wrong: npm
if (npm list -g @anthropic-ai/claude-code 2>$null) { $claudeMigration = "npm" }
# Wrong: winget (Anthropic.ClaudeCode exists in winget as of 2026-03)
if (winget list --id Anthropic.ClaudeCode 2>$null | Select-String "Anthropic.ClaudeCode") { $claudeMigration = "winget" }
```

### Codex — correct method is npm
```powershell
winget list --id OpenAI.Codex 2>$null && $codexMigration = "winget"
# Also check: choco list --local-only codex
```

### Gemini — correct method is npm
```powershell
winget list --id Google.GeminiCLI 2>$null && $geminiMigration = "winget"
```

## Preflight Plan

Display the plan before touching anything. Follow the macOS script's format: one line per tool showing current state and intended action. Example:

```
==> Installation plan:

  Python ............ installed (3.14.3) [correct]
  Node.js ........... installed (22.18.0) [update available: 22.22.0]
  Claude Code ....... migrate npm → native installer (settings preserved)
  Codex CLI ......... installed (0.23.0)
  Gemini CLI ........ installed (0.1.22)
```

Then ask: `Proceed with installation? [Y/n]`

## Install Functions

### Install-Python

**Correct install**: `$env:LOCALAPPDATA\Python\bin\python.exe`
**Wrong install / Store stub**: `$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe` — this is not a real Python, it opens the Store

Detection logic:
- If `$env:LOCALAPPDATA\Python\bin\python.exe` exists → already correct, report version and return
- If `$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe` exists but not the above → stub only, proceed to install
- If Python is found on PATH but not at the correct path → warn that it was installed via an unsupported method, instruct the user to install the new Python install manager, then **continue** (do not abort — other tools can still be installed)

To install:
```powershell
Write-Info "Opening Windows Store — please install the Python install manager and complete setup"
Write-Info "Accept the long path support prompt when asked"
Start-Process "ms-windows-store://pdp/?ProductId=9nq7512cxl7t"
Write-Host "Press Enter once Python installation is complete..."
Read-Host
```
Then verify `$env:LOCALAPPDATA\Python\bin\python.exe` exists. If still missing, warn and continue.

**Python is never auto-migrated.** Only install if not present at the correct path.

### Install-Node

```powershell
if (Has-Command node) {
    # Check if managed by winget and update
    winget upgrade --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
} else {
    winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
}
```
Refresh PATH after install.

### Install-Claude

```powershell
if ($claudeMigration -eq "npm") {
    Write-Info "Removing Claude Code from npm (migrating to native installer)"
    npm uninstall -g @anthropic-ai/claude-code
} elseif ($claudeMigration -eq "winget") {
    Write-Info "Removing Claude Code from winget (migrating to native installer)"
    winget uninstall --id Anthropic.ClaudeCode --accept-source-agreements
}
Write-Info "Installing/updating Claude Code (native installer)"
irm https://claude.ai/install.ps1 | iex
```
Refresh PATH after install. Config in `~/.claude/` is never touched.

### Install-Codex

```powershell
if ($codexMigration -eq "winget") {
    winget uninstall --id OpenAI.Codex
}
if (Has-Command codex) {
    npm update -g @openai/codex
} else {
    npm install -g @openai/codex
}
```

### Install-Gemini

```powershell
if ($geminiMigration -eq "winget") {
    winget uninstall --id Google.GeminiCLI
}
if (Has-Command gemini) {
    npm update -g @google/gemini-cli
} else {
    npm install -g @google/gemini-cli
}
```

## Summary

After all installs, display versions of everything installed, same style as the macOS script. Include next-steps hints: how to run each tool, how to update npm tools manually, note that Claude Code auto-updates.

## Verified State on Reference Machine (as of 2026-02-24)

These were the actual installed states when this document was written, confirmed by running detection commands:

| Tool | Installed via | Path | Correct? |
|------|--------------|------|----------|
| Python 3.14.3 | New install manager | `$LOCALAPPDATA\Python\bin\python.exe` | Yes |
| Node.js 22.18.0 | winget (OpenJS.NodeJS.22) | `C:\Program Files\nodejs\node.exe` | Yes |
| Claude Code 2.1.55 | npm | `$APPDATA\npm\claude` | No — needs migration |
| Codex 0.23.0 | npm | `$APPDATA\npm\codex` | Yes |
| Gemini 0.1.22 | npm | `$APPDATA\npm\gemini` | Yes |

The script should correctly detect and migrate Claude Code on this machine, and leave everything else in place.
