# Cloud Security Alliance — Windows Work Tools Setup
#
# Core profile (everyone):
#   1. Git (via winget, includes Git Bash)
#   2. GitHub CLI (gh) + authentication
#   3. Node.js LTS (via winget)
#   4. 1Password
#   5. Slack
#   6. Zoom
#   7. Google Chrome
#
# Dev profile (core + these):
#   8. Visual Studio Code
#   9. AWS CLI
#  10. Wrangler (Cloudflare CLI, via npm)
#
# Usage:
#   irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 | iex

$ErrorActionPreference = 'Stop'

$ScriptVersion = "2026.04201930"

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

function Test-WingetInstalled {
    param([string]$Id)
    $result = winget list --id $Id --accept-source-agreements 2>$null
    return ($result -and ($result | Select-String $Id))
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

# ── Profile selection ───────────────────────────────────────────────

$script:InstallDev = $false

function Select-Profile {
    if ($env:NONINTERACTIVE -eq '1') { return }

    Write-Host ""
    Write-Info "Select a profile:"
    Write-Host ""
    Write-Host "  1) Core - Git, GitHub CLI, 1Password, Slack, Zoom, Chrome"
    Write-Host "  2) Core + Developer - adds VS Code, AWS CLI, Wrangler"
    Write-Host ""

    $reply = Read-Host "Profile [1/2]"
    if ($reply -eq '2') {
        $script:InstallDev = $true
    }
}

# ── Preflight ───────────────────────────────────────────────────────

function Show-Preflight {
    Write-Host ""
    Write-Info "Installation plan:"
    Write-Host ""

    # Base layer
    if (Has-Command git) {
        $gitVer = Get-ToolVersion git '--version'
        Write-Host "  Git ............... installed ($gitVer)"
    } else {
        Write-Host "  Git ............... install via winget"
    }

    # Long path support status
    $lpReg = Get-ItemPropertyValue -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
                                   -Name 'LongPathsEnabled' -ErrorAction SilentlyContinue
    $lpGit = $null
    if (Has-Command git) { $lpGit = git config --global --get core.longpaths 2>$null }
    if ($lpReg -eq 1 -and $lpGit -eq 'true') {
        Write-Host "  Long paths ........ enabled (git + registry)"
    } else {
        Write-Host "  Long paths ........ enable (git config + UAC prompt for registry)"
    }

    if (Has-Command gh) {
        $ghVer = Get-ToolVersion gh '--version'
        Write-Host "  GitHub CLI ........ installed ($ghVer)"
    } else {
        Write-Host "  GitHub CLI ........ install via winget"
    }

    if (Has-Command node) {
        $nodeVer = Get-ToolVersion node '--version'
        Write-Host "  Node.js ........... installed ($nodeVer)"
    } else {
        Write-Host "  Node.js ........... install via winget"
    }

    # Core apps
    Write-Host ""
    Write-Host "  -- Core --"

    $coreApps = @(
        @{ Label = "1Password";     Id = "AgileBits.1Password" },
        @{ Label = "Slack";         Id = "SlackTechnologies.Slack" },
        @{ Label = "Zoom";          Id = "Zoom.Zoom" },
        @{ Label = "Google Chrome"; Id = "Google.Chrome" }
    )

    foreach ($app in $coreApps) {
        if (Test-WingetInstalled $app.Id) {
            Write-Host "  $($app.Label) .... installed"
        } else {
            Write-Host "  $($app.Label) .... install via winget"
        }
    }

    # Dev tools
    if ($script:InstallDev) {
        Write-Host ""
        Write-Host "  -- Developer --"

        $devApps = @(
            @{ Label = "VS Code"; Id = "Microsoft.VisualStudioCode" },
            @{ Label = "AWS CLI"; Id = "Amazon.AWSCLI" }
        )

        foreach ($app in $devApps) {
            if (Test-WingetInstalled $app.Id) {
                Write-Host "  $($app.Label) .... installed"
            } else {
                Write-Host "  $($app.Label) .... install via winget"
            }
        }

        if (Has-Command wrangler) {
            $wranglerVer = Get-ToolVersion wrangler '--version'
            Write-Host "  Wrangler .......... installed ($wranglerVer)"
        } else {
            Write-Host "  Wrangler .......... install via npm"
        }
    }

    Write-Host ""
}

# ── Install helpers ────────────────────────────────────────────────

function Install-WingetPackage {
    param([string]$Label, [string]$Id)

    if (Test-WingetInstalled $Id) {
        Write-Info "Upgrading $Label"
        winget upgrade --id $Id --accept-package-agreements --accept-source-agreements
        # winget upgrade returns non-zero if already up to date — that's fine
    } else {
        Write-Info "Installing $Label"
        winget install --id $Id --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install $Label" }
    }
    Refresh-Path
}

function Install-NpmPackage {
    param([string]$Label, [string]$Package, [string]$Bin)

    if (-not (Has-Command npm)) {
        Write-Warn "npm not found; skipping $Label"
        return
    }

    if (Has-Command $Bin) {
        Write-Info "Updating $Label"
        npm update -g $Package
        if ($LASTEXITCODE -ne 0) {
            npm install -g $Package
            if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to update $Label" }
        }
    } else {
        Write-Info "Installing $Label"
        npm install -g $Package
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install $Label" }
    }
}

# ── Install steps ──────────────────────────────────────────────────

function Install-Git {
    if (Has-Command git) {
        $wingetGit = winget list --id Git.Git --accept-source-agreements 2>$null
        if ($wingetGit -and ($wingetGit | Select-String 'Git.Git')) {
            Write-Info "Upgrading Git via winget"
            winget upgrade --id Git.Git --accept-package-agreements --accept-source-agreements
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

function Set-LongPathSupport {
    # Two-part: user-scope Git config (no admin), then the HKLM registry flag
    # (requires admin — elevated via a single Start-Process -Verb RunAs so the
    # rest of the script stays in the user context where winget/npm/gh expect
    # to run). If elevation is denied or blocked by policy, we warn and print
    # the manual command rather than aborting.

    # 1. Git core.longpaths (user scope)
    if (Has-Command git) {
        $currentGit = git config --global --get core.longpaths 2>$null
        if ($currentGit -eq 'true') {
            Write-Info "Git core.longpaths already enabled"
        } else {
            Write-Info "Enabling Git long-path support (core.longpaths=true)"
            git config --global core.longpaths true
        }
    }

    # 2. Windows LongPathsEnabled (machine scope)
    $regPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem'
    $regName = 'LongPathsEnabled'
    $manualCmd = 'Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -Type DWord'

    $current = Get-ItemPropertyValue -Path $regPath -Name $regName -ErrorAction SilentlyContinue
    if ($current -eq 1) {
        Write-Info "Windows LongPathsEnabled already set"
        return
    }

    if ($env:NONINTERACTIVE -eq '1') {
        Write-Warn "Windows LongPathsEnabled is not set (skipping UAC prompt in non-interactive mode)"
        Write-Host "   To enable later, run in an elevated PowerShell:"
        Write-Host "     $manualCmd"
        return
    }

    Write-Info "Enabling Windows LongPathsEnabled (UAC prompt will appear)"
    $elevatedCmd = $manualCmd
    try {
        Start-Process powershell -Verb RunAs `
            -ArgumentList '-NoProfile', '-Command', $elevatedCmd `
            -Wait -ErrorAction Stop | Out-Null
    } catch {
        Write-Warn "Could not elevate to set LongPathsEnabled ($($_.Exception.Message))"
        Write-Host "   To enable later, run in an elevated PowerShell:"
        Write-Host "     $manualCmd"
        return
    }

    # Verify the change landed (elevated child runs in its own process, so we
    # re-read the registry from the non-admin parent to confirm).
    $after = Get-ItemPropertyValue -Path $regPath -Name $regName -ErrorAction SilentlyContinue
    if ($after -eq 1) {
        Write-Success "Windows LongPathsEnabled set to 1"
    } else {
        Write-Warn "LongPathsEnabled was not applied"
        Write-Host "   To enable later, run in an elevated PowerShell:"
        Write-Host "     $manualCmd"
    }
}

function Install-GH {
    if (Has-Command gh) {
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

function Install-Node {
    if (Has-Command node) {
        $wingetNode = winget list --id OpenJS.NodeJS.LTS --accept-source-agreements 2>$null
        if ($wingetNode -and ($wingetNode | Select-String 'OpenJS.NodeJS.LTS')) {
            Write-Info "Upgrading Node.js via winget"
            winget upgrade --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
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

function Install-Core {
    Write-Info "Installing core apps"
    Write-Host ""

    Install-WingetPackage "1Password"     "AgileBits.1Password"
    Install-WingetPackage "Slack"         "SlackTechnologies.Slack"
    Install-WingetPackage "Zoom"          "Zoom.Zoom"
    Install-WingetPackage "Google Chrome" "Google.Chrome"
}

function Install-Dev {
    Write-Host ""
    Write-Info "Installing developer tools"
    Write-Host ""

    Install-WingetPackage "Visual Studio Code" "Microsoft.VisualStudioCode"
    Install-WingetPackage "AWS CLI"            "Amazon.AWSCLI"
    Install-NpmPackage    "Wrangler"           "wrangler" "wrangler"
}

# ── Post-install setup ─────────────────────────────────────────────

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
    if (Has-Command node) {
        $nodeVer = Get-ToolVersion node '--version'
        $npmVer  = Get-ToolVersion npm '--version'
        Write-Host "  Node.js ........... $nodeVer"
        Write-Host "  npm ............... $npmVer"
    }

    # Core apps
    $coreApps = @(
        @{ Label = "1Password";     Id = "AgileBits.1Password" },
        @{ Label = "Slack";         Id = "SlackTechnologies.Slack" },
        @{ Label = "Zoom";          Id = "Zoom.Zoom" },
        @{ Label = "Google Chrome"; Id = "Google.Chrome" }
    )
    foreach ($app in $coreApps) {
        if (Test-WingetInstalled $app.Id) {
            Write-Host "  $($app.Label) .... installed"
        }
    }

    # Dev tools
    if ($script:InstallDev) {
        if (Test-WingetInstalled "Microsoft.VisualStudioCode") {
            Write-Host "  VS Code ........... installed"
        }
        if (Has-Command aws) {
            $awsVer = Get-ToolVersion aws '--version'
            Write-Host "  AWS CLI ........... $awsVer"
        }
        if (Has-Command wrangler) {
            $wranglerVer = Get-ToolVersion wrangler '--version'
            Write-Host "  Wrangler .......... $wranglerVer"
        }
    }

    Write-Host ""
    Write-Info "Next steps:"
    Write-Host "  - Sign in to 1Password, Slack, Zoom, and Chrome"
    Write-Host "  - Install Microsoft Office from your Microsoft 365 portal"
    if (Has-Command gh) {
        $authCheck = gh auth status 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  - Run 'gh auth login --git-protocol https' to authenticate with GitHub"
        }
    }
    if ($script:InstallDev) {
        if (Has-Command aws) {
            Write-Host "  - Run 'aws configure' to set up AWS credentials"
        }
    }
    Write-Host ""
    Write-Host "  To install AI tools (Claude Code, Codex, Gemini):"
    Write-Host "    irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex"
    Write-Host ""
}

# ── Main ────────────────────────────────────────────────────────────

function Main {
    Write-Info "Cloud Security Alliance - Windows Work Tools Setup v$ScriptVersion"

    Detect-NonInteractive
    Test-Preconditions
    Select-Profile
    Show-Preflight

    if (-not (Confirm-Step "Proceed with installation?")) {
        Abort "Aborted."
    }

    Write-Host ""
    Install-Git
    Set-LongPathSupport
    Install-GH
    Install-Node
    Install-Core

    if ($script:InstallDev) {
        Install-Dev
    }

    Setup-GHAuth
    Show-Summary
}

Main
