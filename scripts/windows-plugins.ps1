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

# ── Debug logging ───────────────────────────────────────────────────
#
# CSA_DEBUG=1 records every native command, its output and its exit code to a timestamped
# file, and prints the path. Off by default.
#
#   $env:CSA_DEBUG = '1'
#
# An environment variable rather than a -Debug switch because the documented invocation is
# `irm ... | iex`, which gives the script no argument vector at all (NONINTERACTIVE already
# works this way). CSA_LOG is exported so anything this script invokes - notably the
# CSA-internal setup, fetched and run as a scriptblock - appends to the SAME file. One file
# per run: the person debugging is being asked to send a log, and "send both of them, and
# mind the timestamps" is how half a report goes missing.
#
# Nothing needs to be added at the call sites. Every native command in these scripts already
# goes through Invoke-Native* (check-powershell-native.py enforces it), so the wrappers are
# the one place that has to know about this.
$SCRIPT_LABEL = 'windows-plugins.ps1'
$CsaDebug = ($env:CSA_DEBUG -eq '1')
$CsaLog = $null
if ($CsaDebug) {
    if ($env:CSA_LOG) {
        $CsaLog = $env:CSA_LOG
    } else {
        $CsaLog = Join-Path $env:USERPROFILE ("desktopsetup-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
        $env:CSA_LOG = $CsaLog
    }
}

# Redacted by shape, keeping the key so the line stays diagnostic: `client_secret: <redacted>`
# still tells you which line failed, `<redacted>` does not. EVERY pattern must define the
# 'keep' group even when it captures nothing - .NET leaves an unknown group reference in the
# replacement as LITERAL TEXT, so a pattern without one writes '${keep}' into the log.
#
# The key/value pattern tolerates the JSON shape ("client_secret": "..."), because the quote
# between key and colon otherwise breaks the match - and that is exactly how a credentials
# file is written.
$CsaSecretPatterns = @(
    '(?<keep>(oauth_token|client_secret|refresh_token|access_token|private_key)"?\s*[:=]\s*"?)[^\s,}"]+',
    '(?<keep>)(gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{20,})',
    '(?<keep>"?temp_clone_token"?\s*[:=]\s*"?)[A-Za-z0-9]{16,}',
    '(?<keep>Bearer\s+)\S{16,}',
    '(?<keep>)ya29\.[A-Za-z0-9._-]{20,}'
)

function Write-CsaLog {
    param([string]$Line, [string]$Kind = 'log')
    if (-not $CsaLog) { return }
    $redacted = $Line
    foreach ($pattern in $CsaSecretPatterns) {
        $redacted = [regex]::Replace($redacted, $pattern, '${keep}<redacted>',
                                     [Text.RegularExpressions.RegexOptions]::IgnoreCase)
    }
    try {
        if (-not (Test-Path $CsaLog)) {
            "=== DesktopSetup $(Get-Date -Format o) ===" | Set-Content $CsaLog
            "This log is REDACTED for known credential shapes, but review it before sharing." |
                Add-Content $CsaLog
            "PowerShell $($PSVersionTable.PSVersion) $($PSVersionTable.PSEdition) on $env:COMPUTERNAME" |
                Add-Content $CsaLog
            # A bare native call piped to Out-Null. Not through a wrapper: the wrappers call
            # THIS, and the recursion would be unbounded.
            icacls $CsaLog /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
        }
        "{0:HH:mm:ss} [{1}] {2}" -f (Get-Date), $Kind, $redacted | Add-Content $CsaLog
    } catch { }   # a log that cannot be written must never stop the install
}

# What a wrapper records. Kept in one place so all four agree: the command as written, its
# exit code, and its output - the last being the part that matters, since a discarded stderr
# is a discarded diagnosis.
# Printed at the end of every run, either way. The moment somebody needs the logging
# incantation is the moment the run went wrong - not later, in a README they are not reading.
function Show-CsaDebugHint {
    if ($CsaLog) {
        Write-Info "debug log: $CsaLog  (redacted, but review before sharing)"
    } else {
        Write-Host "  if anything above went wrong, re-run with logging on:" -ForegroundColor DarkGray
        Write-Host "    `$env:CSA_DEBUG = '1'" -ForegroundColor DarkGray
    }
}

function Write-CsaNativeLog {
    param([scriptblock]$Call, [int]$Code, [string]$Output)
    if (-not $CsaLog) { return }
    Write-CsaLog ("{0} -> exit {1}" -f $Call.ToString().Trim(), $Code) 'run'
    if ($Output) { foreach ($line in ($Output -split "`r?`n")) { Write-CsaLog $line 'out' } }
}

# AFTER the definitions above, not up where $CsaLog is decided. PowerShell does not hoist
# functions: a call placed earlier in the file than its `function` statement fails at runtime
# with "the term 'Write-CsaLog' is not recognized" - which is exactly what the first version
# of this did, and nothing local caught it. The parse check only parses, and the Pester tests
# load each function on its own. It took a run on a real Windows machine.
if ($CsaDebug -and $CsaLog) {
    Write-Info "debug logging to $CsaLog"
    # Create the file NOW rather than on the first command that gets logged. A script can
    # abort before running anything - the Administrator guard and the preconditions both do -
    # and then the path announced above names a file that does not exist. "Send me the log"
    # then sends nothing, and the one fact worth having (which check refused to proceed) is
    # lost with it.
    Write-CsaLog ("{0} starting; CSA_DEBUG=1, no argument vector (irm|iex)" -f $SCRIPT_LABEL) 'info'
}


# ── Utility functions ───────────────────────────────────────────────

function Has-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# Run a native command, swallow stderr, return stdout on success or $null
# on failure. Same NativeCommandError shield as Invoke-NativeQuiet, but
# preserves stdout so callers can capture values (e.g. `gh api user --jq`).
# Note: `2>$null` alone does NOT prevent NativeCommandError promotion in
# Windows PowerShell 5.1 — the try/catch is required.
function Invoke-NativeOutput {
    param([scriptblock]$Call)
    # $ErrorActionPreference='Continue' for the duration, not just a try/catch. Under
    # Windows PowerShell 5.1 the catch alone still turns a SUCCESSFUL command that wrote
    # to stderr into a failure — measured: this returned $null on 5.1 and the real value
    # on pwsh 7 for the same input. Callers use these as probes (`if ($x -and ...)`), so
    # that silently reported 'not installed' for anything winget or npm was chatty about.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $result = & $Call 2>$null
        $code = $LASTEXITCODE
        Write-CsaNativeLog $Call $code ($result | Out-String)
        if ($code -ne 0) { return $null }
        return $result
    } catch {
        Write-CsaNativeLog $Call 1 $_.Exception.Message
        return $null
    } finally {
        $ErrorActionPreference = $prev
    }
}

# Run a native command with its output VISIBLE, shielded against NativeCommandError,
# returning the exit code. The fourth member of this family, for the case the other
# three cannot serve: an installer or download whose progress the user should see.
#
# Why it is needed at all: a bare native call is unsafe under
# $ErrorActionPreference='Stop'. npm prints deprecation warnings to stderr as a matter
# of routine and winget occasionally does too, and either terminates the script BEFORE
# the caller's `if ($LASTEXITCODE -ne 0)` can run — so the script's own error handling
# becomes unreachable exactly when it is needed. Setting 'Continue' for the duration
# suppresses the promotion without hiding anything.
#
# Callers keep using `if ($LASTEXITCODE -ne 0)` after this: $LASTEXITCODE is global and
# is still the native command's, because nothing between it and the caller runs another
# native command. Assign the result to $null rather than letting it fall out, or the
# exit code prints into the transcript.
function Invoke-NativeShow {
    param([scriptblock]$Call)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Output goes to the console, so with logging off there is nothing to intercept and
        # this stays a plain pass-through. With logging on it is teed, not captured, because
        # this wrapper's whole purpose is that the user sees the command work.
        if ($CsaLog) {
            $captured = & $Call 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { $_ }
            } | Tee-Object -Variable teed | Out-String
            $code = $LASTEXITCODE
            Write-CsaNativeLog $Call $code $captured
            return $code
        }
        & $Call
        return $LASTEXITCODE
    }
    catch { Write-CsaNativeLog $Call 1 $_.Exception.Message; return 1 }
    finally { $ErrorActionPreference = $prev }
}

# Run a native command, swallow stdout+stderr, return its exit code.
# Shields against NativeCommandError promotion under
# $ErrorActionPreference='Stop'.
function Invoke-NativeQuiet {
    param([scriptblock]$Call)
    # $ErrorActionPreference='Continue' for the duration, not just a try/catch. Under
    # Windows PowerShell 5.1 the catch alone still turns a SUCCESSFUL command that wrote
    # to stderr into a failure — measured: this returned $null on 5.1 and the real value
    # on pwsh 7 for the same input. Callers use these as probes (`if ($x -and ...)`), so
    # that silently reported 'not installed' for anything winget or npm was chatty about.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # `*> $null` throws the output away, which is right for a probe and wrong for a
        # debug log - the discarded text is the diagnosis. With logging on it is captured
        # and written down instead; the caller still gets only the exit code either way.
        if ($CsaLog) {
            $captured = (& $Call 2>&1 | ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { $_ }
            } | Out-String).Trim()
            $code = $LASTEXITCODE
            Write-CsaNativeLog $Call $code $captured
            return $code
        }
        & $Call *> $null
        return $LASTEXITCODE
    }
    catch { Write-CsaNativeLog $Call 1 $_.Exception.Message; return 1 }
    finally { $ErrorActionPreference = $prev }
}

# Run a native command, shield against NativeCommandError, and return
# both the merged stdout+stderr output (as a trimmed string) and the
# exit code.
function Invoke-NativeCapture {
    param([scriptblock]$Call)
    # $ErrorActionPreference='Continue' for the duration, not just a try/catch. Under
    # Windows PowerShell 5.1 the catch alone still turns a SUCCESSFUL command that wrote
    # to stderr into a failure — measured: this returned $null on 5.1 and the real value
    # on pwsh 7 for the same input. Callers use these as probes (`if ($x -and ...)`), so
    # that silently reported 'not installed' for anything winget or npm was chatty about.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Unwrap the ErrorRecords `2>&1` makes of stderr. Without this the capture carries
        # PowerShell's decoration - "At line:N char:M", the source line, CategoryInfo -
        # ahead of the message. NOT .TargetObject, which is null for these records and
        # produced an entirely EMPTY capture when tried (measured on 5.1.26100).
        $output = (& $Call 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) { $_.Exception.Message } else { $_ }
        } | Out-String).Trim()
        $code = $LASTEXITCODE
        Write-CsaNativeLog $Call $code $output
        return [pscustomobject]@{ ExitCode = $code; Output = $output }
    } catch {
        Write-CsaNativeLog $Call 1 $_.Exception.Message
        return [pscustomobject]@{ ExitCode = 1; Output = $_.Exception.Message }
    } finally {
        $ErrorActionPreference = $prev
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
        $pluginListing = (Invoke-NativeCapture { claude plugin list }).Output
        foreach ($m in [regex]::Matches([string]$pluginListing, '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')) {
            $installedPlugins += $m.Value
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

    # Already-registered marketplaces and already-installed plugins.
    $registeredRepos = @()
    $listing = Invoke-NativeOutput { claude plugin marketplace list }
    foreach ($line in $listing) {
        if ($line -match 'GitHub \(([^)]+)\)') { $registeredRepos += $matches[1] }
    }
    $installedPlugins = @()
            # Parse name@marketplace tokens rather than anchoring on the leading '❯'
            # glyph. Windows consoles routinely misdecode non-ASCII from `claude` (the
            # same mangling that shows '×' as '├ù' in transcripts), so a glyph-anchored
            # match silently finds nothing — every plugin then looks uninstalled and all
            # 43 are reinstalled on every run. Token matching is ASCII and survives
            # bullets, colour codes and format changes.
    # Capture regardless of exit code: a chatty-but-working `claude plugin list` must
    # not be read as "nothing is installed".
    $pluginListing = (Invoke-NativeCapture { claude plugin list }).Output
    foreach ($m in [regex]::Matches([string]$pluginListing, '[A-Za-z0-9._-]+@[A-Za-z0-9._-]+')) {
        $installedPlugins += $m.Value
    }

    $ghAuthed = (Has-Command gh) -and ((Invoke-NativeQuiet { gh auth status }) -eq 0)

    $added = @()
    $failed = @()

    $allEntries = @()
    $allEntries += Get-PluginListEntries $publicList
    $allEntries += Get-PluginListEntries $internalList

    $seenMarkets   = @{}
    $marketUsable  = @{}
    $seenPlugins   = @{}   # dedup guard across list files

    # Pass 1: ensure each referenced marketplace is registered.
    foreach ($entry in $allEntries) {
        $parts = $entry -split '@', 2
        if ($parts.Count -ne 2) { continue }
        $market = $parts[1]

        if ($seenMarkets.ContainsKey($market)) { continue }
        $seenMarkets[$market] = $true

        $repo = $PluginMarketplaceRepos[$market]
        if (-not $repo) {
            # Unknown marketplace in list file -- developer mistake.
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

    # Pass 2: collect plugins to install (in usable marketplace, not already
    # installed, deduped across list files).
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

    # Pass 3: announce, then install each pending plugin with per-item
    # progress so the user sees forward motion instead of a silent wait.
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

    # Snapshot already-registered marketplaces (single call).
    # list format: "    Source: GitHub (ORG/REPO)"
    $listing = Invoke-NativeOutput { claude plugin marketplace list }
    $alreadyAdded = @()
    foreach ($line in $listing) {
        if ($line -match 'GitHub \(([^)]+)\)') {
            $alreadyAdded += $matches[1]
        }
    }

    $added = @()
    $failed = @()

    foreach ($repo in $CSA_MARKETPLACES) {
        # Already registered, or not accessible to this account -- silently skip.
        if ($alreadyAdded -contains $repo) { continue }
        if ((Invoke-NativeQuiet { gh api "repos/$repo" }) -ne 0) { continue }

        # Capture stderr so a real failure (e.g. schema-invalid manifest)
        # surfaces its reason instead of a generic "Failed to register".
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
        Write-Success "Registered Claude Code plugin marketplaces:"
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

    $listing = Invoke-NativeOutput { claude mcp list }
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
Show-CsaDebugHint
