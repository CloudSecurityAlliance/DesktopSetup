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
# Accepts either spelling, because both are things people actually type:
#
#   $env:CSA_DEBUG = '1'      # the documented one
#   $CSA_DEBUG = '1'          # the one you type when you forget `$env:`
#
# The second works because `iex` and `& ([ScriptBlock]::Create(...))` both run this text in a
# scope that can see the caller's variables (measured, both shapes). Accepting only the first
# would mean a forgotten `$env:` silently produces no log at all - and the person then reports
# "I ran it with debug on and there was nothing", which is the worst possible outcome for a
# switch whose entire job is producing evidence.
#
# NOT a -Debug parameter: there is no parameter to pass. `irm ... | iex` fetches text and
# executes it, so the script never sees an argument vector. Worth knowing what the plausible
# guesses actually do, since neither is inert in the way you would hope:
#   irm ... --Debug   fails outright - "a positional parameter cannot be found"
#   irm ... -Debug    is a real parameter ON IRM: it sets the debug stream for the DOWNLOAD
#                     and has nothing to do with the script iex then runs. Silent no-op.
function Test-CsaDebugRequested {
    $plain = Get-Variable -Name CSA_DEBUG -ValueOnly -ErrorAction SilentlyContinue
    foreach ($value in @($env:CSA_DEBUG, $plain)) {
        if ($null -eq $value) { continue }
        if ($value -is [bool]) { if ($value) { return $true } else { continue } }
        if ("$value".Trim() -match '^(1|true|yes|on)$') { return $true }
    }
    return $false
}

$SCRIPT_LABEL = 'windows-work-tools.ps1'
$CsaDebug = Test-CsaDebugRequested
# Normalise it into the environment, so a child process inherits the setting whichever way it
# was given. The CSA-internal setup is a separate process and reads $env:CSA_DEBUG only.
if ($CsaDebug) { $env:CSA_DEBUG = '1' }
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

# Run a native command, swallow stdout+stderr, return its exit code.
# Why: under $ErrorActionPreference='Stop', a native command that exits
# non-zero AND writes to stderr (e.g. `gh auth status` when logged out)
# is promoted to a terminating NativeCommandError before $LASTEXITCODE
# can be checked. This wrapper absorbs the promotion so callers can
# branch on the exit code as intended.
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

# Run a native command, shield against NativeCommandError, and return both
# the merged stdout+stderr output (as a trimmed string) and the exit code.
# Used when a caller needs to surface the command's error text on failure
# (e.g. `claude plugin marketplace add` schema-validation errors).
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
    $result = Invoke-NativeOutput { winget list --id $Id --accept-source-agreements }
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
        $null = Invoke-NativeShow { winget upgrade --id $Id --accept-package-agreements --accept-source-agreements }
        # winget upgrade returns non-zero if already up to date — that's fine
    } else {
        Write-Info "Installing $Label"
        $null = Invoke-NativeShow { winget install --id $Id --accept-package-agreements --accept-source-agreements }
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
        $null = Invoke-NativeShow { npm update -g $Package }
        if ($LASTEXITCODE -ne 0) {
            $null = Invoke-NativeShow { npm install -g $Package }
            if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to update $Label" }
        }
    } else {
        Write-Info "Installing $Label"
        $null = Invoke-NativeShow { npm install -g $Package }
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install $Label" }
    }
}

# ── Install steps ──────────────────────────────────────────────────

function Install-Git {
    if (Has-Command git) {
        $wingetGit = Invoke-NativeOutput { winget list --id Git.Git --accept-source-agreements }
        if ($wingetGit -and ($wingetGit | Select-String 'Git.Git')) {
            Write-Info "Upgrading Git via winget"
            $null = Invoke-NativeShow { winget upgrade --id Git.Git --accept-package-agreements --accept-source-agreements }
        } else {
            $gitVer = Get-ToolVersion git '--version'
            Write-Info "Git already installed (non-winget): $gitVer"
        }
    } else {
        Write-Info "Installing Git via winget"
        $null = Invoke-NativeShow { winget install Git.Git --accept-package-agreements --accept-source-agreements }
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
        $currentGit = Invoke-NativeOutput { git config --global --get core.longpaths }
        if ($currentGit -eq 'true') {
            Write-Info "Git core.longpaths already enabled"
        } else {
            Write-Info "Enabling Git long-path support (core.longpaths=true)"
            $null = Invoke-NativeShow { git config --global core.longpaths true }
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
        $wingetGH = Invoke-NativeOutput { winget list --id GitHub.cli --accept-source-agreements }
        if ($wingetGH -and ($wingetGH | Select-String 'GitHub.cli')) {
            Write-Info "Upgrading GitHub CLI via winget"
            $null = Invoke-NativeShow { winget upgrade --id GitHub.cli --accept-package-agreements --accept-source-agreements }
        } else {
            $ghVer = Get-ToolVersion gh '--version'
            Write-Info "GitHub CLI already installed (non-winget): $ghVer"
        }
    } else {
        Write-Info "Installing GitHub CLI via winget"
        $null = Invoke-NativeShow { winget install GitHub.cli --accept-package-agreements --accept-source-agreements }
        if ($LASTEXITCODE -ne 0) { Abort "Failed to install GitHub CLI." }
    }
    Refresh-Path
}

function Install-Node {
    if (Has-Command node) {
        $wingetNode = Invoke-NativeOutput { winget list --id OpenJS.NodeJS.LTS --accept-source-agreements }
        if ($wingetNode -and ($wingetNode | Select-String 'OpenJS.NodeJS.LTS')) {
            Write-Info "Upgrading Node.js via winget"
            $null = Invoke-NativeShow { winget upgrade --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements }
        } else {
            $nodeVer = Get-ToolVersion node '--version'
            Write-Info "Node.js already installed (non-winget): $nodeVer"
        }
    } else {
        Write-Info "Installing Node.js LTS via winget"
        $null = Invoke-NativeShow { winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements }
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

    if ((Invoke-NativeQuiet { gh auth status }) -eq 0) {
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
        # --scopes user:email: lets Setup-GitIdentity read the user's
        # primary email via `gh api user/emails` when it's not public on
        # the user profile. Without it that endpoint returns HTTP 404.
        $null = Invoke-NativeShow { gh auth login --git-protocol https --scopes user:email }
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
        $authCheck = (Invoke-NativeCapture { gh auth status }).Output
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
Show-CsaDebugHint
