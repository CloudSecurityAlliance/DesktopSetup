# Cloud Security Alliance — Clone Repo & Launch Claude (Windows)
#
# Clones a CSA GitHub repo into ~/GitHub/OrgName/RepoName and prints
# instructions to launch Claude Code.  Safe to re-run — skips clone
# if the directory already exists.
#
# Prerequisites: git, gh (authenticated), claude
# Missing tools?  Run the AI tools installer first:
#   irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex
#
# Usage (set $env:CSA_REPO before piping):
#   $env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 | iex
#
# Example:
#   $env:CSA_REPO='CloudSecurityAlliance-Internal/Training-Documentation'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 | iex

$ErrorActionPreference = 'Stop'

# ── Output helpers ──────────────────────────────────────────────────

function Write-Info    { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Success { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Green }
function Write-Warn    { param([string]$Message) Write-Host "Warning: $Message" -ForegroundColor Yellow }
function Write-Err     { param([string]$Message) Write-Host "Error: $Message" -ForegroundColor Red }
function Abort         { param([string]$Message) Write-Err $Message; exit 1 }

function Has-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# ── Parse argument ──────────────────────────────────────────────────

$RepoSlug = $env:CSA_REPO

if (-not $RepoSlug) {
    Write-Host ""
    Write-Err "No repository specified."
    Write-Host ""
    Write-Host "  Usage:"
    Write-Host "    `$env:CSA_REPO='ORG/REPO'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 | iex"
    Write-Host ""
    Write-Host "  Example:"
    Write-Host "    `$env:CSA_REPO='CloudSecurityAlliance-Internal/Training-Documentation'; irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/clone-and-claude.ps1 | iex"
    Write-Host ""
    exit 1
}

# Clean up the env var so it doesn't leak into future runs
Remove-Item Env:\CSA_REPO -ErrorAction SilentlyContinue

if ($RepoSlug -notmatch '/') {
    Abort "Repository must be in ORG/REPO format (e.g., CloudSecurityAlliance-Internal/Training-Documentation)"
}

$Org = $RepoSlug.Split('/')[0]
$Repo = $RepoSlug.Split('/')[1]
$DefaultBase = Join-Path $HOME "GitHub" $Org

Write-Info "Cloud Security Alliance - Clone & Claude"
Write-Host ""
Write-Host "  Repository: $RepoSlug"
Write-Host ""

# ── Check prerequisites ─────────────────────────────────────────────

$Missing = @()

if (-not (Has-Command git))    { $Missing += "git" }
if (-not (Has-Command gh))     { $Missing += "gh (GitHub CLI)" }
if (-not (Has-Command claude)) { $Missing += "claude (Claude Code)" }

if ($Missing.Count -gt 0) {
    Write-Err "Missing required tools: $($Missing -join ', ')"
    Write-Host ""
    Write-Host "  Install them with the CSA AI tools setup script:"
    Write-Host ""
    Write-Host "    irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex"
    Write-Host ""
    Write-Host "  Then re-run this script."
    exit 1
}

# Check gh authentication
$authCheck = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Err "GitHub CLI is not authenticated."
    Write-Host ""
    Write-Host "  Run this to log in:"
    Write-Host ""
    Write-Host "    gh auth login --git-protocol https"
    Write-Host ""
    Write-Host "  Then re-run this script."
    exit 1
}

Write-Info "All prerequisites OK"
Write-Host ""

# ── Choose location ─────────────────────────────────────────────────

Write-Host "  The repo will be cloned into a folder named '$Repo' inside a base directory."
Write-Host ""
Write-Host "  Default: $DefaultBase\$Repo"
Write-Host ""

if ([Environment]::UserInteractive) {
    while ($true) {
        $reply = Read-Host "  Clone to default location, or choose your own? [yes/No]"
        $replyLower = $reply.ToLower()
        if ($replyLower -eq 'y' -or $replyLower -eq 'yes') {
            $BaseDir = $DefaultBase
            break
        } elseif ($replyLower -eq 'n' -or $replyLower -eq 'no' -or $reply -eq '') {
            Write-Host ""
            Write-Host "  Enter the path where you want the repo."
            Write-Host "  Example: ~\Projects or C:\Users\yourname\work"
            Write-Host ""
            $customPath = Read-Host "  Path"
            if (-not $customPath) {
                Abort "No path entered."
            }
            # Expand ~ if user typed it
            if ($customPath.StartsWith('~')) {
                $customPath = $customPath.Replace('~', $HOME)
            }
            # Strip trailing slashes
            $customPath = $customPath.TrimEnd('\', '/')
            # If the path already ends with the repo name, use it as-is
            if ((Split-Path $customPath -Leaf) -eq $Repo) {
                $BaseDir = Split-Path $customPath -Parent
            } else {
                $BaseDir = $customPath
            }
            break
        } else {
            Write-Host "  Please enter yes or no."
        }
    }
} else {
    $BaseDir = $DefaultBase
}

$TargetDir = Join-Path $BaseDir $Repo

# ── Safety check ────────────────────────────────────────────────────
# The final target must be a new directory. Refuse to clone into an
# existing non-git directory (e.g., C:\Windows, C:\Program Files).

$GitDir = Join-Path $TargetDir ".git"
if ((Test-Path $TargetDir) -and -not (Test-Path $GitDir)) {
    Abort "Directory already exists and is not a git repo: $TargetDir`n  Refusing to clone into an existing directory. Choose a different location."
}

if ([Environment]::UserInteractive) {
    Write-Host ""
    Write-Host "  Will clone to: $TargetDir"
    Write-Host ""
    while ($true) {
        $confirmReply = Read-Host "  Proceed? [y/N]"
        $confirmLower = $confirmReply.ToLower()
        if ($confirmLower -eq 'y' -or $confirmLower -eq 'yes') {
            break
        } elseif ($confirmLower -eq 'n' -or $confirmLower -eq 'no' -or $confirmReply -eq '') {
            Abort "Aborted."
        } else {
            Write-Host "  Please enter yes or no."
        }
    }
}

Write-Host ""

# ── Clone ───────────────────────────────────────────────────────────

if (Test-Path (Join-Path $TargetDir ".git")) {
    Write-Success "Already cloned: $TargetDir"
    Write-Host "  Pulling latest changes..."
    try {
        git -C $TargetDir pull --ff-only 2>$null
    } catch {
        Write-Warn "Pull failed (you may have local changes); continuing"
    }
} else {
    Write-Info "Cloning $RepoSlug"
    $ParentDir = Split-Path $TargetDir -Parent
    if (-not (Test-Path $ParentDir)) {
        New-Item -ItemType Directory -Path $ParentDir -Force | Out-Null
    }
    gh repo clone $RepoSlug $TargetDir
    if ($LASTEXITCODE -ne 0) {
        Abort "Clone failed. Check that you have access to $RepoSlug."
    }
    Write-Success "Cloned to $TargetDir"
}

# ── Done ────────────────────────────────────────────────────────────

Write-Host ""
Write-Success "Ready! Run these commands to start working:"
Write-Host ""
Write-Host "    cd '$TargetDir'; claude"
Write-Host ""
