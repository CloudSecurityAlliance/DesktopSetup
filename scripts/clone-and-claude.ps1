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
$SCRIPT_LABEL = 'clone-and-claude.ps1'
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


function Has-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
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
# Nested rather than `Join-Path $HOME "GitHub" $Org`: the three-argument form needs
# -AdditionalChildPath, added in PowerShell 6, and fails on Windows PowerShell 5.1 —
# which is the runtime this script targets.
$DefaultBase = Join-Path (Join-Path $HOME "GitHub") $Org

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
    if (-not (Has-Command git) -or -not (Has-Command gh)) {
        Write-Host "  First, install work tools (Git, GitHub CLI, and more):"
        Write-Host ""
        Write-Host "    irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-work-tools.ps1 | iex"
        Write-Host ""
    }
    if (-not (Has-Command claude)) {
        Write-Host "  Install AI tools (Claude Code, Codex, Gemini):"
        Write-Host ""
        Write-Host "    irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex"
        Write-Host ""
    }
    Write-Host "  Then re-run this script."
    exit 1
}

# Check gh authentication
$authCheck = (Invoke-NativeCapture { gh auth status }).Output
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
    $null = Invoke-NativeShow { gh repo clone $RepoSlug $TargetDir }
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

Show-CsaDebugHint
