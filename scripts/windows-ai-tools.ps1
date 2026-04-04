# Cloud Security Alliance — Windows AI Tools Setup
#
# Installs:
#   1. Git (via winget, includes Git Bash)
#   2. GitHub CLI (gh, via winget) + authentication
#   3. Python (via winget)
#   4. Node.js LTS (via winget)
#   5. 1Password CLI (via winget)
#   6. Claude Desktop (via winget, auto-updates)
#   7. ChatGPT Desktop (via winget, auto-updates)
#   8. Claude Code (native installer, auto-updates)
#   9. OpenAI Codex CLI (via npm)
#  10. Google Gemini CLI (via npm)
#
# Usage:
#   irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex

$ErrorActionPreference = 'Stop'

# ── Output helpers ──────────────────────────────────────────────────

function Write-Info    { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Green }
function Write-Warn    { param([string]$Message) Write-Host "Warning: $Message" -ForegroundColor Yellow }
function Write-Err     { param([string]$Message) Write-Host "Error: $Message" -ForegroundColor Red }
function Abort         { param([string]$Message) Write-Err $Message; exit 1 }

# ── Utility functions ───────────────────────────────────────────────

function Has-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-ToolVersion {
    param([string]$Command, [string[]]$Arguments)
    if (Has-Command $Command) {
        try {
            $output = & $Command @Arguments 2>$null
            if ($output) { return ($output | Select-Object -First 1) }
        } catch {}
    }
    return $null
}

function Confirm-Step {
    param([string]$Message)
    if ($env:NONINTERACTIVE -eq '1') { return $true }
    $reply = Read-Host "$Message [Y/n]"
    return ($reply -eq '' -or $reply -match '^[Yy]')
}

function Refresh-Path {
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH = "$machinePath;$userPath"
}

# ── Preconditions ───────────────────────────────────────────────────

function Test-Preconditions {
    # Windows 10 or 11
    $osVersion = [System.Environment]::OSVersion.Version
    if ($osVersion.Major -lt 10) {
        Abort "This script requires Windows 10 or later."
    }

    # Not running as Administrator
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Abort "Don't run this as Administrator. Run from a normal PowerShell prompt."
    }

    # Execution policy
    $policy = Get-ExecutionPolicy -Scope CurrentUser
    if ($policy -eq 'Restricted' -or $policy -eq 'AllSigned') {
        Abort "Execution policy is '$policy'. Fix with: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser"
    }

    # winget
    if (-not (Has-Command winget)) {
        Abort "winget is required but not found. Install App Installer from the Microsoft Store."
    }

    # Git is installed by this script (Install-Git step)
}

# ── Non-interactive detection ───────────────────────────────────────

function Detect-NonInteractive {
    if ($env:NONINTERACTIVE -eq '1') { return }

    if ($env:CI) {
        Write-Warn "Non-interactive mode: `$CI is set."
        $env:NONINTERACTIVE = "1"
    } elseif (-not [Environment]::UserInteractive) {
        Write-Warn "Non-interactive mode: session is not interactive."
        $env:NONINTERACTIVE = "1"
    }
}

# ── Running process check ──────────────────────────────────────────

function Check-RunningTools {
    $running = @()
    if (Get-Process -Name claude -ErrorAction SilentlyContinue) { $running += "Claude Code" }
    if (Get-Process -Name codex  -ErrorAction SilentlyContinue) { $running += "Codex CLI" }
    if (Get-Process -Name gemini -ErrorAction SilentlyContinue) { $running += "Gemini CLI" }

    if ($running.Count -gt 0) {
        Write-Warn "These tools are currently running: $($running -join ', ')"
        Write-Host "  It's safe to continue, but running sessions will stay on the old version."
        Write-Host "  For a clean migration, close them first and re-run this script."
        Write-Host ""
        if (-not (Confirm-Step "Continue anyway?")) {
            Abort "Aborted. Close running tools and try again."
        }
    }
}

# ── Migration detection ────────────────────────────────────────────
# Detect tools installed via the wrong method so we can migrate them.
# Config files (~/.claude, ~/.codex, ~/.gemini) are always preserved.

$script:claudeMigration = @()  # collect ALL wrong methods (could be both npm and winget)
$script:codexMigration  = ""   # "winget" if installed wrong

function Detect-Migrations {
    # Claude: should be native installer, not npm or winget
    if (Has-Command npm) {
        $npmList = npm list -g @anthropic-ai/claude-code 2>$null
        if ($npmList -and ($npmList | Select-String '@anthropic-ai/claude-code')) {
            $script:claudeMigration += "npm"
        }
    }
    $wingetCheck = winget list --id Anthropic.ClaudeCode --accept-source-agreements 2>$null
    if ($wingetCheck -and ($wingetCheck | Select-String 'Anthropic.ClaudeCode')) {
        $script:claudeMigration += "winget"
    }

    # Codex: should be npm, not winget
    $codexWinget = winget list --id OpenAI.Codex --accept-source-agreements 2>$null
    if ($codexWinget -and ($codexWinget | Select-String 'OpenAI.Codex')) {
        $script:codexMigration = "winget"
    }

    # Gemini: npm only, no wrong-method detection needed (not in winget)
}

# ── Python Store stub detection ────────────────────────────────────

function Test-PythonStoreStub {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) { return $false }
    return $pythonCmd.Source -like '*WindowsApps*'
}

# ── Preflight ───────────────────────────────────────────────────────

function Show-Preflight {
    Detect-Migrations

    Write-Host ""
    Write-Info "Installation plan:"
    Write-Host ""

    # Git
    if (Has-Command git) {
        $gitVer = Get-ToolVersion git '--version'
        Write-Host "  Git ............... installed ($gitVer)"
    } else {
        Write-Host "  Git ............... install via winget"
    }

    # GitHub CLI
    if (Has-Command gh) {
        $ghVer = Get-ToolVersion gh '--version'
        Write-Host "  GitHub CLI ........ installed ($ghVer)"
    } else {
        Write-Host "  GitHub CLI ........ install via winget"
    }

    # Python
    if ((Has-Command python) -and -not (Test-PythonStoreStub)) {
        $pyVer = Get-ToolVersion python '--version'
        Write-Host "  Python ............ installed ($pyVer)"
    } elseif (Has-Command python3) {
        $pyVer = Get-ToolVersion python3 '--version'
        Write-Host "  Python ............ installed ($pyVer)"
    } else {
        Write-Host "  Python ............ install via winget"
    }

    # Node.js
    if (Has-Command node) {
        $nodeVer = Get-ToolVersion node '--version'
        Write-Host "  Node.js ........... installed ($nodeVer)"
    } else {
        Write-Host "  Node.js ........... install via winget"
    }

    # 1Password CLI
    if (Has-Command op) {
        $opVer = Get-ToolVersion op '--version'
        Write-Host "  1Password CLI ..... installed ($opVer)"
    } else {
        Write-Host "  1Password CLI ..... install via winget"
    }

    # Claude Desktop
    $claudeDesktop = winget list --id Anthropic.Claude --accept-source-agreements 2>$null
    if ($claudeDesktop -and ($claudeDesktop | Select-String 'Anthropic.Claude')) {
        Write-Host "  Claude Desktop .... installed (winget)"
    } else {
        Write-Host "  Claude Desktop .... install via winget"
    }

    # ChatGPT Desktop
    $chatgptDesktop = winget list --id OpenAI.ChatGPT --accept-source-agreements 2>$null
    if ($chatgptDesktop -and ($chatgptDesktop | Select-String 'OpenAI.ChatGPT')) {
        Write-Host "  ChatGPT Desktop ... installed (winget)"
    } else {
        Write-Host "  ChatGPT Desktop ... install via winget"
    }

    # Claude Code
    if ($script:claudeMigration.Count -gt 0) {
        $methods = $script:claudeMigration -join ' + '
        Write-Host "  Claude Code ....... migrate from $methods -> native installer (settings preserved)"
    } elseif (Has-Command claude) {
        $claudeVer = Get-ToolVersion claude '--version'
        Write-Host "  Claude Code ....... installed ($claudeVer)"
    } else {
        Write-Host "  Claude Code ....... install (native installer, auto-updates)"
    }

    # Codex
    if ($script:codexMigration) {
        Write-Host "  Codex CLI ......... migrate from winget -> npm (settings preserved)"
    } elseif (Has-Command codex) {
        $codexVer = Get-ToolVersion codex '--version'
        Write-Host "  Codex CLI ......... installed ($codexVer)"
    } else {
        Write-Host "  Codex CLI ......... install via npm"
    }

    # Gemini
    if (Has-Command gemini) {
        $geminiVer = Get-ToolVersion gemini '--version'
        Write-Host "  Gemini CLI ........ installed ($geminiVer)"
    } else {
        Write-Host "  Gemini CLI ........ install via npm"
    }

    Write-Host ""
}

# ── Migration steps ─────────────────────────────────────────────────
# Remove tools installed via the wrong method before reinstalling.
# Config files in $HOME are never touched.

function Migrate-Claude {
    foreach ($method in $script:claudeMigration) {
        if ($method -eq "npm") {
            Write-Info "Removing Claude Code from npm (migrating to native installer)"
            try { npm uninstall -g @anthropic-ai/claude-code } catch { Write-Warn "npm uninstall claude-code failed; continuing" }
        } elseif ($method -eq "winget") {
            Write-Info "Removing Claude Code from winget (migrating to native installer)"
            try { winget uninstall --id Anthropic.ClaudeCode --accept-source-agreements } catch { Write-Warn "winget uninstall claude-code failed; continuing" }
        }
    }
}

function Migrate-Codex {
    if ($script:codexMigration -eq "winget") {
        Write-Info "Removing Codex CLI from winget (migrating to npm)"
        try { winget uninstall --id OpenAI.Codex --accept-source-agreements } catch { Write-Warn "winget uninstall codex failed; continuing" }
    }
}

# ── Install steps ──────────────────────────────────────────────────

function Install-Git {
    if (Has-Command git) {
        # Check if managed by winget and try to upgrade
        $wingetGit = winget list --id Git.Git --accept-source-agreements 2>$null
        if ($wingetGit -and ($wingetGit | Select-String 'Git.Git')) {
            Write-Info "Upgrading Git via winget"
            winget upgrade --id Git.Git --accept-package-agreements --accept-source-agreements
            # winget upgrade returns non-zero if already up to date — that's fine
        } else {
            $gitVer = Get-ToolVersion git '--version'
            Write-Info "Git already installed (non-winget): $gitVer"
        }
    } else {
        Write-Info "Installing Git via winget"
        winget install Git.Git --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Abort "Failed to install Git." }
    }
    Refresh-Path
}

function Install-GH {
    if (Has-Command gh) {
        # Check if managed by winget and try to upgrade
        $wingetGH = winget list --id GitHub.cli --accept-source-agreements 2>$null
        if ($wingetGH -and ($wingetGH | Select-String 'GitHub.cli')) {
            Write-Info "Upgrading GitHub CLI via winget"
            winget upgrade --id GitHub.cli --accept-package-agreements --accept-source-agreements
        } else {
            $ghVer = Get-ToolVersion gh '--version'
            Write-Info "GitHub CLI already installed (non-winget): $ghVer"
        }
    } else {
        Write-Info "Installing GitHub CLI via winget"
        winget install GitHub.cli --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Abort "Failed to install GitHub CLI." }
    }
    Refresh-Path
}

function Setup-GHAuth {
    if (-not (Has-Command gh)) { return }

    $authStatus = gh auth status 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Info "GitHub CLI already authenticated"
        return
    }

    if ($env:NONINTERACTIVE -eq '1') {
        Write-Warn "Skipping gh auth login (non-interactive mode)"
        return
    }

    Write-Host ""
    Write-Info "GitHub CLI is installed but not authenticated."
    if (Confirm-Step "Run 'gh auth login' now?") {
        gh auth login --git-protocol https
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "gh auth login failed; you can run it manually later"
        }
    }
}

function Install-Python {
    # Check for real Python (not the Store stub)
    if ((Has-Command python) -and -not (Test-PythonStoreStub)) {
        $pyVer = Get-ToolVersion python '--version'
        Write-Info "Python already installed ($pyVer); skipping"
        return
    }
    if (Has-Command python3) {
        $pyVer = Get-ToolVersion python3 '--version'
        Write-Info "Python already installed ($pyVer); skipping"
        return
    }

    Write-Info "Installing Python via winget"
    winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Abort "Failed to install Python." }
    Refresh-Path
}

function Install-Node {
    if (Has-Command node) {
        # Check if managed by winget and try to upgrade
        $wingetNode = winget list --id OpenJS.NodeJS.LTS --accept-source-agreements 2>$null
        if ($wingetNode -and ($wingetNode | Select-String 'OpenJS.NodeJS.LTS')) {
            Write-Info "Upgrading Node.js via winget"
            winget upgrade --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
            # winget upgrade returns non-zero if already up to date — that's fine
        } else {
            $nodeVer = Get-ToolVersion node '--version'
            Write-Info "Node.js already installed (non-winget): $nodeVer"
        }
    } else {
        Write-Info "Installing Node.js LTS via winget"
        winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Abort "Failed to install Node.js." }
    }
    Refresh-Path
}

function Install-1PasswordCLI {
    $wingetCheck = winget list --id AgileBits.1Password.CLI --accept-source-agreements 2>$null
    if ($wingetCheck -and ($wingetCheck | Select-String 'AgileBits.1Password.CLI')) {
        Write-Info "Upgrading 1Password CLI via winget"
        winget upgrade --id AgileBits.1Password.CLI --accept-package-agreements --accept-source-agreements
    } else {
        Write-Info "Installing 1Password CLI via winget"
        winget install --id AgileBits.1Password.CLI --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install 1Password CLI" }
    }
    Refresh-Path
}

function Install-ClaudeDesktop {
    $wingetCheck = winget list --id Anthropic.Claude --accept-source-agreements 2>$null
    if ($wingetCheck -and ($wingetCheck | Select-String 'Anthropic.Claude')) {
        Write-Info "Claude Desktop already installed; skipping"
        return
    }

    Write-Info "Installing Claude Desktop via winget"
    winget install --id Anthropic.Claude --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install Claude Desktop" }
    Refresh-Path
}

function Install-ChatGPT {
    $wingetCheck = winget list --id OpenAI.ChatGPT --accept-source-agreements 2>$null
    if ($wingetCheck -and ($wingetCheck | Select-String 'OpenAI.ChatGPT')) {
        Write-Info "ChatGPT Desktop already installed; skipping"
        return
    }

    Write-Info "Installing ChatGPT Desktop via winget"
    winget install --id OpenAI.ChatGPT --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install ChatGPT Desktop" }
    Refresh-Path
}

function Install-Claude {
    if ($script:claudeMigration.Count -gt 0) {
        Migrate-Claude
    } elseif (Has-Command claude) {
        $claudeVer = Get-ToolVersion claude '--version'
        Write-Info "Claude Code already installed ($claudeVer); skipping"
        return
    }

    Write-Info "Installing Claude Code (native installer)"
    try {
        irm https://claude.ai/install.ps1 | iex
    } catch {
        Abort "Claude Code installation failed: $_"
    }
    Refresh-Path

    # Workaround: native installer often fails to add .local\bin to PATH
    # https://github.com/anthropics/claude-code/issues/21365
    $localBin = "$env:USERPROFILE\.local\bin"
    $userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($userPath -notlike "*$localBin*") {
        Write-Info "Adding $localBin to user PATH"
        [Environment]::SetEnvironmentVariable("PATH", "$userPath;$localBin", "User")
    }
    $env:PATH = "$env:PATH;$localBin"
}

function Install-Codex {
    if ($script:codexMigration) {
        Migrate-Codex
    }

    if (-not (Has-Command npm)) {
        Write-Warn "npm not found; skipping Codex CLI"
        return
    }

    if (-not $script:codexMigration -and (Has-Command codex)) {
        Write-Info "Updating Codex CLI"
        npm update -g @openai/codex
        if ($LASTEXITCODE -ne 0) {
            npm install -g @openai/codex
            if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to update Codex CLI" }
        }
    } else {
        Write-Info "Installing Codex CLI"
        npm install -g @openai/codex
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install Codex CLI" }
    }
}

function Install-Gemini {
    if (-not (Has-Command npm)) {
        Write-Warn "npm not found; skipping Gemini CLI"
        return
    }

    if (Has-Command gemini) {
        Write-Info "Updating Gemini CLI"
        npm update -g @google/gemini-cli
        if ($LASTEXITCODE -ne 0) {
            npm install -g @google/gemini-cli
            if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to update Gemini CLI" }
        }
    } else {
        Write-Info "Installing Gemini CLI"
        npm install -g @google/gemini-cli
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install Gemini CLI" }
    }
}

# ── Summary ─────────────────────────────────────────────────────────

function Show-Summary {
    Write-Host ""
    Write-Success "Setup complete! Installed versions:"
    Write-Host ""

    if (Has-Command git) {
        $gitVer = Get-ToolVersion git '--version'
        Write-Host "  Git ............... $gitVer"
    }
    if (Has-Command gh) {
        $ghVer = Get-ToolVersion gh '--version'
        Write-Host "  GitHub CLI ........ $ghVer"
    }
    if (Has-Command python) {
        $pyVer = Get-ToolVersion python '--version'
        Write-Host "  Python ............ $pyVer"
    }
    if (Has-Command node) {
        $nodeVer = Get-ToolVersion node '--version'
        $npmVer  = Get-ToolVersion npm '--version'
        Write-Host "  Node.js ........... $nodeVer"
        Write-Host "  npm ............... $npmVer"
    }
    if (Has-Command op) {
        $opVer = Get-ToolVersion op '--version'
        Write-Host "  1Password CLI ..... $opVer"
    }
    $claudeDesktop = winget list --id Anthropic.Claude --accept-source-agreements 2>$null
    if ($claudeDesktop -and ($claudeDesktop | Select-String 'Anthropic.Claude')) {
        Write-Host "  Claude Desktop .... installed"
    }
    $chatgptDesktop = winget list --id OpenAI.ChatGPT --accept-source-agreements 2>$null
    if ($chatgptDesktop -and ($chatgptDesktop | Select-String 'OpenAI.ChatGPT')) {
        Write-Host "  ChatGPT Desktop ... installed"
    }
    if (Has-Command claude) {
        $claudeVer = Get-ToolVersion claude '--version'
        Write-Host "  Claude Code ....... $claudeVer"
    }
    if (Has-Command codex) {
        $codexVer = Get-ToolVersion codex '--version'
        Write-Host "  Codex CLI ......... $codexVer"
    }
    if (Has-Command gemini) {
        $geminiVer = Get-ToolVersion gemini '--version'
        Write-Host "  Gemini CLI ........ $geminiVer"
    }

    Write-Host ""
    Write-Info "Next steps:"
    if (Has-Command gh) {
        $authCheck = gh auth status 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  - Run 'gh auth login --git-protocol https' to authenticate with GitHub"
        }
    }
    Write-Host "  - Run 'claude' to start Claude Code"
    Write-Host "  - Run 'codex' to start Codex CLI"
    Write-Host "  - Run 'gemini' to start Gemini CLI"
    Write-Host ""
    Write-Host "  To update npm-installed tools later:"
    Write-Host "    npm update -g @openai/codex @google/gemini-cli"
    Write-Host ""
    Write-Host "  Claude Code updates itself automatically."
    Write-Host ""
}

# ── Main ────────────────────────────────────────────────────────────

function Main {
    Write-Info "Cloud Security Alliance - Windows AI Tools Setup"

    Detect-NonInteractive
    Test-Preconditions
    Check-RunningTools
    Show-Preflight

    if (-not (Confirm-Step "Proceed with installation?")) {
        Abort "Aborted."
    }

    Write-Host ""
    Install-Git
    Install-GH
    Install-Python
    Install-Node
    Install-1PasswordCLI
    Install-ClaudeDesktop
    Install-ChatGPT
    Install-Claude
    Install-Codex
    Install-Gemini
    Setup-GHAuth
    Show-Summary
}

Main
