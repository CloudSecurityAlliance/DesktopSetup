# Cloud Security Alliance — Windows AI Tools Setup
#
# Installs:
#   1. Git (via winget, includes Git Bash)
#   2. GitHub CLI (gh, via winget) + authentication
#   3. Python (via winget)
#   4. Node.js LTS (via winget)
#   5. Document toolchain: pandoc + typst (via winget), plus pyyaml +
#      pymupdf (via pip) — required by the document-pipeline plugin
#   6. 1Password (via winget, GUI app — needed for biometric CLI unlock)
#   7. 1Password CLI (via winget)
#   8. Claude Desktop (via winget, auto-updates)
#   9. ChatGPT Desktop (via winget, auto-updates)
#  10. Claude Code (native installer, auto-updates)
#  11. OpenAI Codex CLI (via npm)
#  12. Google Gemini CLI (via npm)
#
# Usage:
#   irm https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/windows-ai-tools.ps1 | iex

$ErrorActionPreference = 'Stop'

$ScriptVersion = "2026.08241200"

# ── CSA plugin marketplaces ─────────────────────────────────────────
# Plugin marketplaces to register with Claude Code. Each entry is an
# ORG/REPO on GitHub. At install time, each is probed via `gh` for
# accessibility; inaccessible ones (private org repos the user isn't a
# member of) are silently skipped.
#
# KEEP IN SYNC: This array is duplicated in
#   scripts/macos-ai-tools.sh      (installer, macOS)
#   scripts/macos-update.sh        (full updater, macOS)
#   scripts/macos-plugins.sh       (standalone plugins, macOS)
#   scripts/windows-plugins.ps1    (standalone plugins, Windows)
# All five files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion -- otherwise the scripts will drift.
$CSA_MARKETPLACES = @(
    "CloudSecurityAlliance-Internal/Accounting-Plugins"
    "CloudSecurityAlliance-Internal/CINO-Plugins"
    "CloudSecurityAlliance-Internal/CSA-Plugins"
    "CloudSecurityAlliance-Internal/Research-Plugins"
    "CloudSecurityAlliance-Internal/Training-Plugins"
    "CloudSecurityAlliance/csa-plugins-official"
)

# Marketplace name -> GitHub repo. See the matching block in
# scripts/macos-ai-tools.sh for the full rationale.
#
# KEEP IN SYNC: duplicated as plugin_marketplace_repo in
#   scripts/macos-ai-tools.sh
#   scripts/macos-update.sh
#   scripts/macos-plugins.sh
# and as $PluginMarketplaceRepos in
#   scripts/windows-plugins.ps1
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
# Registers the CSA MCP server with Claude Code (HTTP transport,
# OAuth 2.1 + PKCE). Gated on `gh` access to a canonical CSA-Internal
# repo so this public bootstrap only auto-wires CSA tooling for CSA-
# eligible accounts — not because the server is restricted (it answers
# unauthenticated callers). See scripts/macos-ai-tools.sh for full rationale.
#
# KEEP IN SYNC: same constants and logic in
#   scripts/macos-ai-tools.sh
#   scripts/macos-update.sh
#   scripts/macos-plugins.sh
#   scripts/windows-plugins.ps1
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

$SCRIPT_LABEL = 'windows-ai-tools.ps1'
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
            "=== DesktopSetup $(Get-Date -Format o) ===" | Set-Content $CsaLog -Encoding UTF8
            "This log is REDACTED for known credential shapes, but review it before sharing." |
                Add-Content $CsaLog -Encoding UTF8
            "PowerShell $($PSVersionTable.PSVersion) $($PSVersionTable.PSEdition) on $env:COMPUTERNAME" |
                Add-Content $CsaLog -Encoding UTF8
            # A bare native call piped to Out-Null. Not through a wrapper: the wrappers call
            # THIS, and the recursion would be unbounded.
            icacls $CsaLog /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
        }
        "{0:HH:mm:ss} [{1}] {2}" -f (Get-Date), $Kind, $redacted | Add-Content $CsaLog -Encoding UTF8
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

# A scriptblock's source text, plus the values of any variables in it.
#
# $Call.ToString() is the SOURCE, so a real log said `winget list --exact --id $pkg.Id` and
# `gh api "repos/$CSA_MCP_GATE_REPO"` - true, and useless for answering "which package?" or
# "which repo?". The values are reachable, because PowerShell resolves variables dynamically:
# a wrapper called from a loop can see that loop's $pkg.
#
# It ANNOTATES rather than substitutes, and that is the whole design. Rewriting the command
# with values filled in was tried first, via ExpandString, and every version of it produced
# log lines that misrepresented what ran:
#
#   $pkg.Id                 ->  --id @{Id=Git.Git}.Id   (object stringified, `.Id` left as text)
#   $pkg.Id.ToUpper()       ->  echo r()                (the regex ate a prefix of the chain)
#   $doesNotExist.Thing     ->  echo                    (reads as "ran with no argument")
#
# A log that says the wrong thing is worse than one that says a vague thing, and each guard
# added revealed another hole. Appending cannot have that failure mode: the command is
# reproduced verbatim, and a value that cannot be resolved is simply not mentioned. Nothing is
# ever executed to produce it either - properties are walked through psobject, so a method
# call in the source is data, not something to run.
function Expand-CsaCommandText {
    param([scriptblock]$Call)
    $text = $Call.ToString().Trim() -replace '\s+', ' '
    $seen = @{}
    $parts = @()
    foreach ($match in [regex]::Matches($text, '\$(\w+(?:\.\w+)*)')) {
        $path = $match.Groups[1].Value
        if ($seen.ContainsKey($path)) { continue }
        $seen[$path] = $true
        $names = $path -split '\.'
        $value = Get-Variable -Name $names[0] -ValueOnly -ErrorAction SilentlyContinue
        # `1..($names.Count - 1)` is NOT empty for a single-element path: 1..0 counts DOWN in
        # PowerShell, giving {1, 0}. So a plain `$py` walked to $names[1] (null) and then back
        # to $names[0], resolved to nothing, and was silently dropped - which is why the plain
        # variables, the most useful ones, were the only ones not annotated.
        $rest = @()
        if ($names.Count -gt 1) { $rest = $names[1..($names.Count - 1)] }
        foreach ($name in $rest) {
            if ($null -eq $value) { break }
            $property = $value.psobject.Properties[$name]
            if (-not $property) { $value = $null; break }
            $value = $property.Value
        }
        # Scalars only, and short ones. A hashtable or an object renders as @{...} or a type
        # name, which is noise, and a long value belongs in the output lines rather than in
        # the command line.
        if ($null -eq $value -or $value -is [System.Collections.IEnumerable] -and $value -isnot [string]) { continue }
        $rendered = "$value"
        if (-not $rendered -or $rendered.Length -gt 120) { continue }
        $parts += "$path=$rendered"
    }
    if ($parts.Count) { return "$text  [" + ($parts -join '; ') + "]" }
    return $text
}

function Write-CsaNativeLog {
    param([scriptblock]$Call, [int]$Code, [string]$Output)
    if (-not $CsaLog) { return }
    Write-CsaLog ("{0} -> exit {1}" -f (Expand-CsaCommandText $Call), $Code) 'run'
    if ($Output) { foreach ($line in ($Output -split "`r?`n")) { Write-CsaLog $line 'out' } }
}

# AFTER the definitions above, not up where $CsaLog is decided. PowerShell does not hoist
# functions: a call placed earlier in the file than its `function` statement fails at runtime
# with "the term 'Write-CsaLog' is not recognized" - which is exactly what the first version
# of this did, and nothing local caught it. The parse check only parses, and the Pester tests
# load each function on its own. It took a run on a real Windows machine.
if ($CsaDebug -and $CsaLog) {
    Write-Info "debug logging to $CsaLog"
    # Decode native output as UTF-8 while logging. [Console]::OutputEncoding was measured at
    # cp437 (IBM437) on a real machine, and PowerShell decodes a native command's stdout with
    # it - so gh's UTF-8 checkmark arrived as three cp437 characters and reached the log as the
    # bytes 47 A3 F4. The corruption happens at DECODE, so writing the file as UTF-8 alone
    # would faithfully record the wrong characters.
    #
    # Only under CSA_DEBUG, and deliberately not restored: a normal run is untouched, so this
    # cannot affect anybody who did not ask for a log, and the process is about to end anyway.
    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
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

# Query winget for an exact-id package, return its Version field or $null
# if not installed / parse failed. Winget's columnar output varies in
# width, so we look for a line that contains the ID followed by at least
# one non-whitespace token (the version). Graceful degradation: callers
# should treat $null as "installed but version unknown" only if a
# separate presence check has already passed.
function Get-WingetVersion {
    param([string]$Id)
    try {
        $output = winget list --exact --id $Id --accept-source-agreements 2>$null
    } catch { return $null }
    if (-not $output) { return $null }
    $pattern = [regex]::Escape($Id) + '\s+(\S+)'
    foreach ($line in $output) {
        if ($line -match $pattern) {
            return $matches[1]
        }
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
$script:envUpdated      = $false  # set to $true if CLAUDE_CODE_NO_FLICKER was written

function Detect-Migrations {
    # Claude: should be native installer, not npm or winget
    # Check both the original scoped package name and the bare "claude" package.
    if (Has-Command npm) {
        $npmList = Invoke-NativeOutput { npm list -g @anthropic-ai/claude-code }
        if ($npmList -and ($npmList | Select-String '@anthropic-ai/claude-code')) {
            $script:claudeMigration += "npm"
        } else {
            $npmListBare = Invoke-NativeOutput { npm list -g claude }
            if ($npmListBare -and ($npmListBare | Select-String 'claude@')) {
                $script:claudeMigration += "npm"
            }
        }
    }
    $wingetCheck = Invoke-NativeOutput { winget list --id Anthropic.ClaudeCode --accept-source-agreements }
    if ($wingetCheck -and ($wingetCheck | Select-String 'Anthropic.ClaudeCode')) {
        $script:claudeMigration += "winget"
    }

    # Codex: should be npm, not winget
    $codexWinget = Invoke-NativeOutput { winget list --id OpenAI.Codex --accept-source-agreements }
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

    # Long path support status
    $lpReg = Get-ItemPropertyValue -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
                                   -Name 'LongPathsEnabled' -ErrorAction SilentlyContinue
    $lpGit = $null
    if (Has-Command git) { $lpGit = Invoke-NativeOutput { git config --global --get core.longpaths } }
    if ($lpReg -eq 1 -and $lpGit -eq 'true') {
        Write-Host "  Long paths ........ enabled (git + registry)"
    } else {
        Write-Host "  Long paths ........ enable (git config + UAC prompt for registry)"
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

    # Document toolchain (document-pipeline plugin: Markdown -> tagged PDF)
    if (Has-Command pandoc) {
        Write-Host "  pandoc ............ installed ($(Get-ToolVersion pandoc '--version'))"
    } else {
        Write-Host "  pandoc ............ install via winget"
    }
    if (Has-Command typst) {
        Write-Host "  typst ............. installed ($(Get-ToolVersion typst '--version'))"
    } else {
        Write-Host "  typst ............. install via winget"
    }

    # 1Password (GUI app — needed for biometric CLI unlock)
    # --exact: avoid matching AgileBits.1Password.CLI
    $onePwGui = Invoke-NativeOutput { winget list --exact --id AgileBits.1Password --accept-source-agreements }
    if ($onePwGui -and ($onePwGui | Select-String 'AgileBits.1Password')) {
        $v = Get-WingetVersion 'AgileBits.1Password'
        $suffix = if ($v) { ", v$v" } else { '' }
        Write-Host "  1Password ......... installed (winget$suffix)"
    } else {
        Write-Host "  1Password ......... install via winget"
    }

    # 1Password CLI
    if (Has-Command op) {
        $opVer = Get-ToolVersion op '--version'
        Write-Host "  1Password CLI ..... installed ($opVer)"
    } else {
        Write-Host "  1Password CLI ..... install via winget"
    }

    # Claude Desktop
    $claudeDesktop = Invoke-NativeOutput { winget list --id Anthropic.Claude --accept-source-agreements }
    if ($claudeDesktop -and ($claudeDesktop | Select-String 'Anthropic.Claude')) {
        $v = Get-WingetVersion 'Anthropic.Claude'
        $suffix = if ($v) { ", v$v" } else { '' }
        Write-Host "  Claude Desktop .... installed (winget$suffix)"
    } else {
        Write-Host "  Claude Desktop .... install via winget"
    }

    # ChatGPT Desktop
    $chatgptDesktop = Invoke-NativeOutput { winget list --id OpenAI.ChatGPT --accept-source-agreements }
    if ($chatgptDesktop -and ($chatgptDesktop | Select-String 'OpenAI.ChatGPT')) {
        $v = Get-WingetVersion 'OpenAI.ChatGPT'
        $suffix = if ($v) { ", v$v" } else { '' }
        Write-Host "  ChatGPT Desktop ... installed (winget$suffix)"
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

    # Claude Code flicker fix
    $flickerVar = [Environment]::GetEnvironmentVariable("CLAUDE_CODE_NO_FLICKER", "User")
    if ($flickerVar -eq "1") {
        Write-Host "  CLAUDE_CODE_NO_FLICKER  already set"
    } else {
        Write-Host "  CLAUDE_CODE_NO_FLICKER  set (enables flicker-free terminal renderer)"
    }

    # Plugin marketplaces
    Write-Host "  Plugin marketplaces  probe $($CSA_MARKETPLACES.Count) CSA repos, add any your GitHub account can access"
    Show-PluginsPreview
    Write-Host "  CSA MCP server       register $CSA_MCP_NAME if your GitHub account has CSA-Internal access"

    Write-Host ""
}

# ── Migration steps ─────────────────────────────────────────────────
# Remove tools installed via the wrong method before reinstalling.
# Config files in $HOME are never touched.

function Migrate-Claude {
    foreach ($method in $script:claudeMigration) {
        if ($method -eq "npm") {
            Write-Info "Removing Claude Code from npm (migrating to native installer)"
            try { npm uninstall -g @anthropic-ai/claude-code 2>$null } catch {}
            try { npm uninstall -g claude 2>$null } catch {}
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
        $wingetGit = Invoke-NativeOutput { winget list --id Git.Git --accept-source-agreements }
        if ($wingetGit -and ($wingetGit | Select-String 'Git.Git')) {
            Write-Info "Upgrading Git via winget"
            $null = Invoke-NativeShow { winget upgrade --id Git.Git --accept-package-agreements --accept-source-agreements }
            # winget upgrade returns non-zero if already up to date — that's fine
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
        # Check if managed by winget and try to upgrade
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

function Setup-GitIdentity {
    $currentName  = Invoke-NativeOutput { git config --global user.name }
    $currentEmail = Invoke-NativeOutput { git config --global user.email }

    if ($currentName -and $currentEmail) {
        Write-Info "Git identity already configured: $currentName <$currentEmail>"
        return
    }

    # Need gh authenticated to pull profile info
    $ghAuthed = $false
    if (Has-Command gh) {
        if ((Invoke-NativeQuiet { gh auth status }) -eq 0) { $ghAuthed = $true }
    }

    if (-not $ghAuthed) {
        Write-Warn "Git identity not configured. Run these after authenticating with GitHub:"
        if (-not $currentName)  { Write-Host "  git config --global user.name `"Your Name`"" }
        if (-not $currentEmail) { Write-Host "  git config --global user.email `"you@example.com`"" }
        return
    }

    # Fetch name and email from GitHub profile
    $ghName  = Invoke-NativeOutput { gh api user --jq '.name // empty' }
    $ghEmail = Invoke-NativeOutput { gh api user --jq '.email // empty' }

    # If email is private/null, try the emails endpoint. Requires user:email
    # scope on the gh token -- returns 404 otherwise, which is fine; we just
    # fall through without an email and the user can set it manually.
    if (-not $ghEmail) {
        $ghEmail = Invoke-NativeOutput { gh api user/emails --jq '[.[] | select(.primary==true)][0].email // empty' }
    }

    # Use GitHub values only for fields not already set
    $setName  = if ($currentName)  { $currentName }  else { $ghName }
    $setEmail = if ($currentEmail) { $currentEmail } else { $ghEmail }

    if (-not $setName -and -not $setEmail) {
        Write-Warn "Could not determine Git identity from GitHub profile."
        Write-Warn "Run: git config --global user.name `"Your Name`""
        Write-Warn "Run: git config --global user.email `"you@example.com`""
        return
    }

    if ($env:NONINTERACTIVE -eq '1') {
        if (-not $currentName  -and $setName)  { git config --global user.name  $setName }
        if (-not $currentEmail -and $setEmail) { git config --global user.email $setEmail }
        if ($setName -and $setEmail) {
            Write-Info "Git identity configured from GitHub profile"
        } else {
            Write-Warn "Git identity partially configured from GitHub profile. Still missing:"
            if (-not $setName)  { Write-Host "  user.name  (run: git config --global user.name `"Your Name`")" }
            if (-not $setEmail) { Write-Host "  user.email (run: git config --global user.email `"you@example.com`")" }
        }
        return
    }

    Write-Host ""
    Write-Info "Git identity (user.name / user.email) is used in every commit."
    if (-not $currentName  -and $setName)  { Write-Host "  Name:  $setName (from GitHub)" }
    if (-not $currentEmail -and $setEmail) { Write-Host "  Email: $setEmail (from GitHub)" }

    if (Confirm-Step "Set Git identity from your GitHub profile?") {
        if (-not $currentName -and $setName) {
            $null = Invoke-NativeShow { git config --global user.name $setName }
            Write-Success "Set user.name to: $setName"
        }
        if (-not $currentEmail -and $setEmail) {
            $null = Invoke-NativeShow { git config --global user.email $setEmail }
            Write-Success "Set user.email to: $setEmail"
        }

        # Catch partial success: GitHub didn't expose everything we needed
        # (common cause: existing gh token lacks the user:email scope, so
        # the email fallback returns 404 and we have no email to set).
        if (-not $setName -or -not $setEmail) {
            Write-Warn "GitHub didn't expose everything. Set manually:"
            if (-not $setName)  { Write-Host "  git config --global user.name `"Your Name`"" }
            if (-not $setEmail) {
                Write-Host "  git config --global user.email `"you@example.com`""
                Write-Host "  (or run 'gh auth refresh --scopes user:email' and re-run this script to pull it from GitHub)"
            }
        }
    } else {
        Write-Warn "Skipped. Set manually with:"
        if (-not $currentName)  { Write-Host "  git config --global user.name `"Your Name`"" }
        if (-not $currentEmail) { Write-Host "  git config --global user.email `"you@example.com`"" }
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
    $null = Invoke-NativeShow { winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements }
    if ($LASTEXITCODE -ne 0) { Abort "Failed to install Python." }
    Refresh-Path
}

# ── Document toolchain ──────────────────────────────────────────────
# pandoc and typst render Markdown into CSA-branded, PDF/UA-1 tagged
# PDFs; the document-pipeline plugin's build script hard-requires both
# on PATH. pyyaml + pymupdf back its preflight checks.
#
# Unlike macOS, the deps go straight into the winget Python rather than a
# venv: winget Python is not PEP 668 externally-managed, so pip works,
# and document-pipeline's bash launcher probes a PATH `python` — it looks
# for a venv only at the Unix path ~/.default_venv/bin/python3, which
# does not exist on Windows.
function Install-DocToolchain {
    foreach ($pkg in @(
        @{ Id = 'JohnMacFarlane.Pandoc'; Name = 'pandoc' },
        @{ Id = 'Typst.Typst';          Name = 'typst'  }
    )) {
        $installed = Invoke-NativeOutput { winget list --exact --id $pkg.Id --accept-source-agreements }
        if ($installed -and ($installed | Select-String $pkg.Id)) {
            Write-Info "$($pkg.Name) already installed; skipping"
            continue
        }
        Write-Info "Installing $($pkg.Name) via winget"
        $null = Invoke-NativeShow { winget install --exact --id $pkg.Id --accept-package-agreements --accept-source-agreements }
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Failed to install $($pkg.Name) - document rendering stays broken until it is installed"
        }
    }
    Refresh-Path
}

function Install-DocPythonDeps {
    $py = if (Has-Command python) { 'python' } elseif (Has-Command python3) { 'python3' } else { $null }
    if (-not $py) {
        Write-Warn "No Python on PATH - skipping document preflight deps"
        return
    }

    # This probe is SUPPOSED to fail when the deps are absent - that is how it detects
    # them. But a bare native call cannot use `2>$null` here: under
    # $ErrorActionPreference='Stop', Python's traceback on stderr is promoted to a
    # NativeCommandError and terminates the whole script (see the note above
    # Invoke-NativeOutput). Invoke-NativeQuiet is the shield this file already provides.
    # `pymupdf`, not `fitz`. Same package - `fitz` is the legacy import alias, and PyMuPDF now
    # prints "The `fitz` API is deprecated and will be removed in future" on every use. It showed
    # up in a real debug log. When it is finally removed this probe starts failing, and a failing
    # probe here means the script reinstalls the dependency on every single run, forever, while
    # reporting success. Probing the name we actually install avoids both.
    if ((Invoke-NativeQuiet { & $py -c 'import yaml, pymupdf' }) -eq 0) {
        Write-Info "Document preflight deps already installed; skipping"
        return
    }

    Write-Info "Installing document preflight deps (pyyaml, pymupdf)"
    # Same shield: pip writes warnings to stderr, and a failed install must degrade to a
    # warning rather than abort setup.
    if ((Invoke-NativeQuiet { & $py -m pip install --quiet --upgrade pyyaml pymupdf }) -ne 0) {
        Write-Warn "Failed to install pyyaml/pymupdf - csa-preflight will print its own install hint"
    }
}

function Install-Node {
    if (Has-Command node) {
        # Check if managed by winget and try to upgrade
        $wingetNode = Invoke-NativeOutput { winget list --id OpenJS.NodeJS.LTS --accept-source-agreements }
        if ($wingetNode -and ($wingetNode | Select-String 'OpenJS.NodeJS.LTS')) {
            Write-Info "Upgrading Node.js via winget"
            $null = Invoke-NativeShow { winget upgrade --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements }
            # winget upgrade returns non-zero if already up to date — that's fine
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

function Install-1Password {
    # --exact: avoid matching AgileBits.1Password.CLI
    $wingetCheck = Invoke-NativeOutput { winget list --exact --id AgileBits.1Password --accept-source-agreements }
    if ($wingetCheck -and ($wingetCheck | Select-String 'AgileBits.1Password')) {
        Write-Info "1Password already installed; skipping"
        return
    }

    Write-Info "Installing 1Password via winget"
    $null = Invoke-NativeShow { winget install --exact --id AgileBits.1Password --accept-package-agreements --accept-source-agreements }
    if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install 1Password" }
    Refresh-Path
}

function Install-1PasswordCLI {
    $wingetCheck = Invoke-NativeOutput { winget list --id AgileBits.1Password.CLI --accept-source-agreements }
    if ($wingetCheck -and ($wingetCheck | Select-String 'AgileBits.1Password.CLI')) {
        Write-Info "Upgrading 1Password CLI via winget"
        $null = Invoke-NativeShow { winget upgrade --id AgileBits.1Password.CLI --accept-package-agreements --accept-source-agreements }
    } else {
        Write-Info "Installing 1Password CLI via winget"
        $null = Invoke-NativeShow { winget install --id AgileBits.1Password.CLI --accept-package-agreements --accept-source-agreements }
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install 1Password CLI" }
    }
    Refresh-Path
}

function Install-ClaudeDesktop {
    $wingetCheck = Invoke-NativeOutput { winget list --id Anthropic.Claude --accept-source-agreements }
    if ($wingetCheck -and ($wingetCheck | Select-String 'Anthropic.Claude')) {
        Write-Info "Claude Desktop already installed; skipping"
        return
    }

    Write-Info "Installing Claude Desktop via winget"
    $null = Invoke-NativeShow { winget install --id Anthropic.Claude --accept-package-agreements --accept-source-agreements }
    if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install Claude Desktop" }
    Refresh-Path
}

function Install-ChatGPT {
    $wingetCheck = Invoke-NativeOutput { winget list --id OpenAI.ChatGPT --accept-source-agreements }
    if ($wingetCheck -and ($wingetCheck | Select-String 'OpenAI.ChatGPT')) {
        Write-Info "ChatGPT Desktop already installed; skipping"
        return
    }

    Write-Info "Installing ChatGPT Desktop via winget"
    $null = Invoke-NativeShow { winget install --id OpenAI.ChatGPT --accept-package-agreements --accept-source-agreements }
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
        $null = Invoke-NativeShow { npm update -g @openai/codex }
        if ($LASTEXITCODE -ne 0) {
            $null = Invoke-NativeShow { npm install -g @openai/codex }
            if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to update Codex CLI" }
        }
    } else {
        Write-Info "Installing Codex CLI"
        $null = Invoke-NativeShow { npm install -g @openai/codex }
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
        $null = Invoke-NativeShow { npm update -g @google/gemini-cli }
        if ($LASTEXITCODE -ne 0) {
            $null = Invoke-NativeShow { npm install -g @google/gemini-cli }
            if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to update Gemini CLI" }
        }
    } else {
        Write-Info "Installing Gemini CLI"
        $null = Invoke-NativeShow { npm install -g @google/gemini-cli }
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install Gemini CLI" }
    }
}

# ── Environment setup ──────────────────────────────────────────────

function Setup-ClaudeEnv {
    # Enable the flicker-free renderer — eliminates the terminal redraw flicker
    # that makes Claude Code unpleasant to use for long sessions.
    $env:CLAUDE_CODE_NO_FLICKER = "1"

    $current = [Environment]::GetEnvironmentVariable("CLAUDE_CODE_NO_FLICKER", "User")
    if ($current -eq "1") {
        Write-Info "Claude Code environment already configured"
        return
    }

    [Environment]::SetEnvironmentVariable("CLAUDE_CODE_NO_FLICKER", "1", "User")
    Write-Success "Set CLAUDE_CODE_NO_FLICKER=1 (flicker-free terminal renderer)"
    $script:envUpdated = $true
}

# ── Plugin marketplaces ─────────────────────────────────────────────
# Register CSA plugin marketplaces with Claude Code, but only the ones
# the authenticated GitHub account can actually see. Missing preconditions
# (no claude, no gh, not authenticated) and inaccessible repos are silent --
# a user who isn't in CSA-Internal just gets the public marketplace and
# doesn't see any chatter about the internal ones.

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
# Silent unless we actually register. Does not clobber an existing
# entry -- removing and re-adding would invalidate the OAuth session.
# The user must run /mcp inside Claude Code to complete browser sign-in;
# we print that reminder only on a fresh registration.
function Register-CSAMcpServer {
    if (-not (Has-Command claude)) { return }
    if (-not (Has-Command gh))     { return }
    if ((Invoke-NativeQuiet { gh auth status }) -ne 0) { return }

    # Already registered? Silent skip.
    $listing = Invoke-NativeOutput { claude mcp list }
    foreach ($line in $listing) {
        if ($line -match "^${CSA_MCP_NAME}[: ]") { return }
    }

    # CSA-membership gate via gh probe of a canonical CSA-Internal repo.
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

# Run CSA-internal setup that cannot live in this public repo (it carries CSA's OAuth
# client). Gated exactly like Register-CSAMcpServer: probe CloudSecurityAlliance-Internal
# with gh and silently do nothing without access, so external users of this public repo
# see no chatter. The fetched script is idempotent and reports for itself.
function Invoke-CSAInternalSetup {
    if (-not (Has-Command 'gh')) { return }
    if ((Invoke-NativeQuiet { gh auth status }) -ne 0) { return }
    if ((Invoke-NativeQuiet { gh api "repos/$CSA_MCP_GATE_REPO" }) -ne 0) { return }

    $encoded = Invoke-NativeOutput { gh api "repos/$CSA_MCP_GATE_REPO/contents/internal-setup/csa-google-workspace-setup.ps1" --jq '.content' }
    if ($LASTEXITCODE -ne 0 -or -not $encoded) { return }

    try {
        $script = [System.Text.Encoding]::UTF8.GetString(
            [System.Convert]::FromBase64String(($encoded -replace '\s', '')))
    } catch { return }

    try { & ([ScriptBlock]::Create($script)) }
    catch { Write-Warn "CSA internal setup reported a problem: $_" }
}

# ── Plugin install ──────────────────────────────────────────────────
# Fetch the public and internal plugin list files from HEAD, register
# any missing marketplaces (CSA ones are gh-probed first), then
# install plugins that aren't yet installed. Silent on skip, loud on
# actual install or error. Mirrors install_plugins() in the bash
# scripts.

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

# Preflight helper: print one line summarizing what Install-Plugins would
# do. Fetches the list files and diffs against `claude plugin list`.
# Intentionally cheap -- no gh-probes here, so the count is "up to N";
# CSA plugins the user can't access get filtered out at actual install
# time.
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
    if (Has-Command pandoc) {
        Write-Host "  pandoc ............ $(Get-ToolVersion pandoc '--version')"
    }
    if (Has-Command typst) {
        Write-Host "  typst ............. $(Get-ToolVersion typst '--version')"
    }
    $onePwGuiInstalled = Invoke-NativeOutput { winget list --exact --id AgileBits.1Password --accept-source-agreements }
    if ($onePwGuiInstalled -and ($onePwGuiInstalled | Select-String 'AgileBits.1Password')) {
        Write-Host "  1Password ......... installed"
    }
    if (Has-Command op) {
        $opVer = Get-ToolVersion op '--version'
        Write-Host "  1Password CLI ..... $opVer"
    }
    $claudeDesktop = Invoke-NativeOutput { winget list --id Anthropic.Claude --accept-source-agreements }
    if ($claudeDesktop -and ($claudeDesktop | Select-String 'Anthropic.Claude')) {
        Write-Host "  Claude Desktop .... installed"
    }
    $chatgptDesktop = Invoke-NativeOutput { winget list --id OpenAI.ChatGPT --accept-source-agreements }
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
        if ((Invoke-NativeQuiet { gh auth status }) -ne 0) {
            Write-Host "  - Run 'gh auth login --git-protocol https' to authenticate with GitHub"
        }
    }
    $summaryGitName  = Invoke-NativeOutput { git config --global user.name }
    $summaryGitEmail = Invoke-NativeOutput { git config --global user.email }
    if (-not $summaryGitName -or -not $summaryGitEmail) {
        Write-Host "  - Configure Git identity: git config --global user.name `"Your Name`""
        Write-Host "    and: git config --global user.email `"you@example.com`""
    }
    Write-Host "  - Enable 1Password CLI integration: 1Password app > Settings > Developer > 'Integrate with 1Password CLI', then restart 1Password"
    Write-Host "  - Run 'claude' to start Claude Code"
    Write-Host "  - Run 'codex' to start Codex CLI"
    Write-Host "  - Run 'gemini' to start Gemini CLI"
    Write-Host ""
    Write-Host "  To update npm-installed tools later:"
    Write-Host "    npm update -g @openai/codex @google/gemini-cli"
    Write-Host ""
    Write-Host "  To refresh plugin marketplaces:"
    Write-Host "    claude plugin marketplace update"
    Write-Host "  (auto-update per marketplace is opt-in -- toggle from /plugin in Claude Code)"
    Write-Host ""
    Write-Host "  Claude Code updates itself automatically."
    Write-Host ""
    Write-Info "Learn Claude Code in your terminal:"
    Write-Host "  /powerup  -- interactive lessons with animated demos, one feature at a time"
    Write-Host "  /init     -- in a project directory, first ask Claude to read all the files,"
    Write-Host "               then type /init -- creates a CLAUDE.md tailored to your codebase"
    Write-Host ""

    if ($script:envUpdated) {
        Write-Warn "Open a new terminal window for CLAUDE_CODE_NO_FLICKER to take effect in future sessions."
        Write-Host ""
    }
}

# ── Main ────────────────────────────────────────────────────────────

function Main {
    Write-Info "Cloud Security Alliance - Windows AI Tools Setup v$ScriptVersion"

    Detect-NonInteractive
    Test-Preconditions
    Check-RunningTools
    Show-Preflight

    if (-not (Confirm-Step "Proceed with installation?")) {
        Abort "Aborted."
    }

    Write-Host ""
    Install-Git
    Set-LongPathSupport
    Install-GH
    Setup-GHAuth
    Setup-GitIdentity
    Install-Python
    Install-Node
    Install-DocToolchain
    Install-DocPythonDeps
    Install-1Password
    Install-1PasswordCLI
    Install-ClaudeDesktop
    Install-ChatGPT
    Install-Claude
    Install-Codex
    Install-Gemini
    Setup-ClaudeEnv
    Setup-PluginMarketplaces
    Install-Plugins
    Register-CSAMcpServer
    Show-Summary
    # Runs LAST, after the summary, so the internal setup's own output - including
    # the "you still need to log in" banner - is the final thing on screen rather
    # than buried under install output the user has stopped reading.
    Invoke-CSAInternalSetup
}

Main
Show-CsaDebugHint
