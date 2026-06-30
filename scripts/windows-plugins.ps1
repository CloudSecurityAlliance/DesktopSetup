# Cloud Security Alliance — Windows Plugin Install/Update
#
# Standalone script that just handles Claude Code plugins: register
# missing marketplaces (CSA ones via gh probe), install any plugins
# from scripts/csa-plugins.txt and scripts/csa-plugins-internal.txt
# that aren't yet installed, then refresh all registered marketplaces.
#
# Use this when you want to get current on plugins without running
# the full windows-ai-tools.ps1 (which also installs winget apps).
#
# Usage:
#   irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-plugins.ps1 -Headers @{'Cache-Control'='no-cache'} | iex

$ErrorActionPreference = 'Stop'

$ScriptVersion = "2026.04271200"

# ── CSA plugin marketplaces ─────────────────────────────────────────
# Registered in Setup-PluginMarketplaces regardless of whether
# Install-Plugins pulls anything from them. Keeps zero-plugin
# marketplaces browsable after this script runs.
#
# KEEP IN SYNC: This array is duplicated in
#   scripts/macos-ai-tools.sh      (installer, macOS)
#   scripts/macos-update.sh        (full updater, macOS)
#   scripts/macos-plugins.sh       (standalone plugins, macOS)
#   scripts/windows-ai-tools.ps1   (installer, Windows)
# All five files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion — otherwise the scripts will drift.
$CSA_MARKETPLACES = @(
    "CloudSecurityAlliance-Internal/Accounting-Plugins"
    "CloudSecurityAlliance-Internal/CINO-Plugins"
    "CloudSecurityAlliance-Internal/CSA-Plugins"
    "CloudSecurityAlliance-Internal/Research-Plugins"
    "CloudSecurityAlliance-Internal/Training-Plugins"
    "CloudSecurityAlliance/csa-plugins-official"
)

# Marketplace name -> GitHub repo. See macos-ai-tools.sh for full
# rationale.
#
# KEEP IN SYNC: duplicated as plugin_marketplace_repo in
#   scripts/macos-ai-tools.sh
#   scripts/macos-update.sh
#   scripts/macos-plugins.sh
# and as $PluginMarketplaceRepos in
#   scripts/windows-ai-tools.ps1
$PluginMarketplaceRepos = @{
    'claude-plugins-official'  = 'anthropics/claude-plugins-official'
    'anthropic-agent-skills'   = 'anthropics/skills'
    'accounting-plugins'       = 'CloudSecurityAlliance-Internal/Accounting-Plugins'
    'csa-cino-plugins'         = 'CloudSecurityAlliance-Internal/CINO-Plugins'
    'csa-plugins'              = 'CloudSecurityAlliance-Internal/CSA-Plugins'
    'csa-research-plugins'     = 'CloudSecurityAlliance-Internal/Research-Plugins'
    'csa-training-plugins'     = 'CloudSecurityAlliance-Internal/Training-Plugins'
    'csa-plugins-official'     = 'CloudSecurityAlliance/csa-plugins-official'
}

# ── CSA MCP server ──────────────────────────────────────────────────
# See scripts/macos-ai-tools.sh for full rationale. Keep these constants
# and the Register-CSAMcpServer function in sync across all five scripts.
$CSA_MCP_NAME      = 'csa-mcp'
$CSA_MCP_URL       = 'https://cloudsecurityalliance.org/mcp'
$CSA_MCP_GATE_REPO = 'CloudSecurityAlliance-Internal/CSA-Plugins'

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

# Run a native command, swallow stdout+stderr, return its exit code.
# Shields against NativeCommandError promotion under
# $ErrorActionPreference='Stop'.
function Invoke-NativeQuiet {
    param([scriptblock]$Call)
    try {
        & $Call 2>&1 | Out-Null
        return $LASTEXITCODE
    } catch {
        return 1
    }
}

# Run a native command, shield against NativeCommandError, and return
# both the merged stdout+stderr output (as a trimmed string) and the
# exit code.
function Invoke-NativeCapture {
    param([scriptblock]$Call)
    try {
        $output = (& $Call 2>&1 | Out-String).Trim()
        return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = $output }
    } catch {
        return [pscustomobject]@{ ExitCode = 1; Output = $_.Exception.Message }
    }
}

function Confirm-Step {
    param([string]$Message)
    if ($env:NONINTERACTIVE -eq '1') { return $true }
    $reply = Read-Host "$Message [Y/n]"
    return ($reply -eq '' -or $reply -match '^[Yy]')
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

# ── Preconditions ───────────────────────────────────────────────────

function Test-Preconditions {
    $osVersion = [System.Environment]::OSVersion.Version
    if ($osVersion.Major -lt 10) {
        Abort "This script requires Windows 10 or later."
    }

    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if ($principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Abort "Don't run this as Administrator. Run from a normal PowerShell prompt."
    }

    $policy = Get-ExecutionPolicy -Scope CurrentUser
    if ($policy -eq 'Restricted' -or $policy -eq 'AllSigned') {
        Abort "Execution policy is '$policy'. Fix with: Set-ExecutionPolicy RemoteSigned -Scope CurrentUser"
    }

    if (-not (Has-Command claude)) {
        Abort "claude CLI not found -- install it first via scripts/windows-ai-tools.ps1"
    }
}

# ── Plugin install ──────────────────────────────────────────────────

$PluginListUrlPublic   = 'https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins.txt'
$PluginListUrlInternal = 'https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/csa-plugins-internal.txt'

function Get-PluginMarketplaceKind {
    param([string]$Name)
    if ($Name -eq 'claude-plugins-official' -or $Name -eq 'anthropic-agent-skills') {
        return 'public'
    }
    return 'csa'
}

function Get-PluginListEntries {
    param([string]$Text)
    if (-not $Text) { return @() }
    return $Text -split "`r?`n" | Where-Object {
        $_ -and ($_ -notmatch '^\s*(#|$)')
    }
}

function Show-PluginsPreview {
    try {
        $publicList = Invoke-RestMethod -Uri $PluginListUrlPublic -Headers @{ 'Cache-Control' = 'no-cache' } -ErrorAction Stop
    } catch { $publicList = '' }
    try {
        $internalList = Invoke-RestMethod -Uri $PluginListUrlInternal -Headers @{ 'Cache-Control' = 'no-cache' } -ErrorAction Stop
    } catch { $internalList = '' }

    if (-not $publicList -and -not $internalList) {
        Write-Host "  Plugins              (skipped: couldn't fetch plugin lists)"
        return
    }

    $installedPlugins = @()
    if (Has-Command claude) {
        $pluginListing = claude plugin list 2>$null
        foreach ($line in $pluginListing) {
            if ($line -match '^\s*❯\s*(.*)$') { $installedPlugins += $matches[1].Trim() }
        }
    }

    $allEntries = @()
    $allEntries += Get-PluginListEntries $publicList
    $allEntries += Get-PluginListEntries $internalList

    $total = $allEntries.Count
    $already = 0
    foreach ($entry in $allEntries) {
        if ($installedPlugins -contains $entry) { $already += 1 }
    }
    $new = $total - $already

    if ($total -eq 0) {
        Write-Host "  Plugins              (list files empty)"
    } elseif ($new -eq 0) {
        Write-Host "  Plugins              all $already defaults already installed"
    } elseif ($already -eq 0) {
        Write-Host "  Plugins              install up to $total defaults from csa-plugins*.txt"
    } else {
        Write-Host "  Plugins              install up to $new new ($already already present)"
    }
}

function Install-Plugins {
    if (-not (Has-Command claude)) { return }

    try {
        $publicList = Invoke-RestMethod -Uri $PluginListUrlPublic -Headers @{ 'Cache-Control' = 'no-cache' } -ErrorAction Stop
    } catch { $publicList = '' }
    try {
        $internalList = Invoke-RestMethod -Uri $PluginListUrlInternal -Headers @{ 'Cache-Control' = 'no-cache' } -ErrorAction Stop
    } catch { $internalList = '' }

    if (-not $publicList -and -not $internalList) { return }

    $registeredRepos = @()
    $listing = claude plugin marketplace list 2>$null
    foreach ($line in $listing) {
        if ($line -match 'GitHub \(([^)]+)\)') { $registeredRepos += $matches[1] }
    }
    $installedPlugins = @()
    $pluginListing = claude plugin list 2>$null
    foreach ($line in $pluginListing) {
        if ($line -match '^\s*❯\s*(.*)$') { $installedPlugins += $matches[1].Trim() }
    }

    $ghAuthed = (Has-Command gh) -and ((Invoke-NativeQuiet { gh auth status }) -eq 0)

    $added = @()
    $failed = @()

    $allEntries = @()
    $allEntries += Get-PluginListEntries $publicList
    $allEntries += Get-PluginListEntries $internalList

    $seenMarkets   = @{}
    $marketUsable  = @{}
    $seenPlugins   = @{}

    foreach ($entry in $allEntries) {
        $parts = $entry -split '@', 2
        if ($parts.Count -ne 2) { continue }
        $market = $parts[1]

        if ($seenMarkets.ContainsKey($market)) { continue }
        $seenMarkets[$market] = $true

        $repo = $PluginMarketplaceRepos[$market]
        if (-not $repo) {
            Write-Warn "Plugin list references unknown marketplace '$market' -- update `$PluginMarketplaceRepos"
            continue
        }

        if ($registeredRepos -contains $repo) {
            $marketUsable[$market] = $true
            continue
        }

        if ((Get-PluginMarketplaceKind $market) -eq 'csa') {
            if (-not $ghAuthed) { continue }
            if ((Invoke-NativeQuiet { gh api "repos/$repo" }) -ne 0) { continue }
        }

        $result = Invoke-NativeCapture { claude plugin marketplace add $repo }
        if ($result.ExitCode -eq 0) {
            $added += $repo
            $marketUsable[$market] = $true
        } else {
            $failed += [pscustomobject]@{
                What   = "marketplace $repo"
                Output = if ($result.Output) { $result.Output } else { '<no stderr output>' }
            }
        }
    }

    if ($added.Count -gt 0) {
        Write-Success "Registered plugin marketplaces:"
        $added | ForEach-Object { Write-Host "  + $_" }
    }

    $pendingInstalls = @()
    foreach ($entry in $allEntries) {
        $parts = $entry -split '@', 2
        if ($parts.Count -ne 2) { continue }
        $name = $parts[0]
        $market = $parts[1]

        $key = "$name@$market"
        if ($seenPlugins.ContainsKey($key)) { continue }
        $seenPlugins[$key] = $true

        if (-not $marketUsable.ContainsKey($market)) { continue }
        if ($installedPlugins -contains $key) { continue }

        $pendingInstalls += $key
    }

    if ($pendingInstalls.Count -gt 0) {
        Write-Info "Installing $($pendingInstalls.Count) plugin(s):"
        foreach ($plugin in $pendingInstalls) {
            $result = Invoke-NativeCapture { claude plugin install $plugin }
            if ($result.ExitCode -eq 0) {
                Write-Host "  + $plugin"
            } else {
                $out = if ($result.Output) { $result.Output } else { '<no stderr output>' }
                $failed += [pscustomobject]@{
                    What   = "plugin $plugin"
                    Output = $out
                }
                Write-Host "  ! $plugin"
                Write-Host "      $out"
            }
        }
    }

    if ($failed.Count -gt 0) {
        Write-Warn "Plugin install finished with $($failed.Count) failure(s) (details above)."
    }
}

# ── CSA marketplace registration ────────────────────────────────────

function Setup-PluginMarketplaces {
    if (-not (Has-Command claude)) { return }
    if (-not (Has-Command gh))     { return }

    if ((Invoke-NativeQuiet { gh auth status }) -ne 0) { return }

    $listing = claude plugin marketplace list 2>$null
    $alreadyAdded = @()
    foreach ($line in $listing) {
        if ($line -match 'GitHub \(([^)]+)\)') {
            $alreadyAdded += $matches[1]
        }
    }

    $added = @()
    $failed = @()

    foreach ($repo in $CSA_MARKETPLACES) {
        if ($alreadyAdded -contains $repo) { continue }
        if ((Invoke-NativeQuiet { gh api "repos/$repo" }) -ne 0) { continue }

        $result = Invoke-NativeCapture { claude plugin marketplace add $repo }
        if ($result.ExitCode -eq 0) {
            $added += $repo
        } else {
            $failed += [pscustomobject]@{
                Repo   = $repo
                Output = if ($result.Output) { $result.Output } else { '<no stderr output>' }
            }
        }
    }

    if ($added.Count -gt 0) {
        Write-Success "Registered new CSA plugin marketplaces:"
        $added | ForEach-Object { Write-Host "  + $_" }
    }
    if ($failed.Count -gt 0) {
        Write-Warn "Failed to register $($failed.Count) marketplace(s):"
        foreach ($f in $failed) {
            Write-Host "  ! $($f.Repo)"
            Write-Host "      $($f.Output)"
        }
    }
}

# Register the CSA MCP server (csa-mcp) with Claude Code if missing.
# See scripts/windows-ai-tools.ps1 Register-CSAMcpServer for full rationale --
# silent unless we actually register, gh-probed CSA-Internal access gate,
# does not clobber existing OAuth sessions.
function Register-CSAMcpServer {
    if (-not (Has-Command claude)) { return }
    if (-not (Has-Command gh))     { return }
    if ((Invoke-NativeQuiet { gh auth status }) -ne 0) { return }

    $listing = claude mcp list 2>$null
    foreach ($line in $listing) {
        if ($line -match "^${CSA_MCP_NAME}[: ]") { return }
    }

    if ((Invoke-NativeQuiet { gh api "repos/$CSA_MCP_GATE_REPO" }) -ne 0) { return }

    $result = Invoke-NativeCapture { claude mcp add --transport http --scope user $CSA_MCP_NAME $CSA_MCP_URL }
    if ($result.ExitCode -eq 0) {
        Write-Success "Registered Claude Code MCP server: $CSA_MCP_NAME"
        Write-Info "Run /mcp inside Claude Code to authenticate with the CSA MCP server."
    } else {
        Write-Warn "Failed to register Claude Code MCP server '$CSA_MCP_NAME':"
        $msg = if ($result.Output) { $result.Output } else { '<no stderr output>' }
        Write-Host "      $msg"
    }
}

# ── Preflight ───────────────────────────────────────────────────────

function Show-Preflight {
    Write-Host ""
    Write-Info "Plugin sync plan:"
    Write-Host ""

    Write-Host "  Plugin marketplaces: refresh registered, add accessible CSA repos"
    Show-PluginsPreview
    Write-Host "  CSA MCP server     : register $CSA_MCP_NAME if your GitHub account has CSA-Internal access"

    Write-Host ""
}

# ── Main ────────────────────────────────────────────────────────────

function Main {
    Write-Info "Cloud Security Alliance -- Windows Plugin Sync v$ScriptVersion"

    Detect-NonInteractive
    Test-Preconditions

    Show-Preflight

    if (-not (Confirm-Step "Proceed with plugin sync?")) {
        Abort "Aborted."
    }

    Setup-PluginMarketplaces
    Install-Plugins
    Register-CSAMcpServer

    Write-Info "Refreshing plugin marketplaces"
    $result = Invoke-NativeCapture { claude plugin marketplace update }
    if ($result.ExitCode -ne 0) {
        Write-Warn "marketplace update failed; continuing"
        if ($result.Output) { Write-Host "      $($result.Output)" }
    }

    Write-Host ""
    Write-Success "Plugin sync complete."
    Write-Host ""
    Write-Host "  To list installed plugins:"
    Write-Host "    claude plugin list"
    Write-Host ""
    Write-Host "  To enable/disable individual plugins:"
    Write-Host "    claude plugin enable <name>"
    Write-Host "    claude plugin disable <name>"
    Write-Host ""
}

Main
