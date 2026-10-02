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

$ScriptVersion = "2026.10020500"

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
#   scripts/windows-update.ps1     (full updater, Windows)
# All six files hard-code the same list. When adding or removing a
# marketplace, update every file and bump each file's SCRIPT_VERSION /
# $ScriptVersion — otherwise the scripts will drift.
# One entry per internal MCP server. Top-level, beside $CSA_MARKETPLACES, because the
# installation plan has to enumerate it and a list local to the function that runs it cannot be
# reached from the plan. The macOS side named two of these four by hand and installed all four;
# this side named NONE of them and installed all four, which is the same defect one degree
# worse. Appending here is the whole change needed to add a server.
$CSA_INTERNAL_SETUPS = @(
    'csa-google-workspace-setup.ps1',
    'csa-google-gmail-calendar-setup.ps1',
    'csa-skilljar-setup.ps1',
    'csa-zendesk-setup.ps1'
)

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
#   scripts/windows-update.ps1
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
# and the Register-CSAMcpServer function in sync across all six scripts.
$CSA_MCP_NAME      = 'csa-mcp'
$CSA_MCP_URL       = 'https://cloudsecurityalliance.org/mcp'
$CSA_MCP_GATE_REPO = 'CloudSecurityAlliance-Internal/CSA-Plugins'

# ── Output helpers ──────────────────────────────────────────────────

# Every one of these records what it printed, so "shown to the user" and "in the debug log"
# stop being two decisions. They were two, and a real run cost two wrong diagnoses: a log
# ending mid-run read as a crash when the script had carried on for several more steps, and
# Claude Desktop was judged absent because its registration line never reached the file (#96).
#
# macOS has never had this problem - its logger is a process-wide `tee`, so everything printed
# is captured by construction. Windows has no equivalent, and Start-Transcript is not one:
# it would bypass Write-CsaLog's redaction, and this file is deliberately redacted.
#
# One kind, 'screen', for all four: the prefix already distinguishes them, and a single kind
# means `grep '[screen]'` reconstructs what the terminal showed.
#
# ORDERING: these call Write-CsaLog, which is defined further down. PowerShell resolves at
# call time, so this is safe only while no Write-* call executes before that definition.
# Measured 2026-10-01: the earliest real call in each of the five scripts is after it. That is
# a property of today's code, not a guarantee - so check-log-coverage.py enforces it, because
# the same CommandNotFoundException-to-$null-to-wrong-branch failure has already cost this
# fleet a release (CSA-Plugins, Test-CsaInteractive).
function Write-Info    { param([string]$Message) $l = "==> $Message";      Write-Host $l -ForegroundColor Cyan;   Write-CsaLog $l 'screen' }
function Write-Success { param([string]$Message) $l = "==> $Message";      Write-Host $l -ForegroundColor Green;  Write-CsaLog $l 'screen' }
function Write-Warn    { param([string]$Message) $l = "Warning: $Message"; Write-Host $l -ForegroundColor Yellow; Write-CsaLog $l 'screen' }
function Write-Err     { param([string]$Message) $l = "Error: $Message";   Write-Host $l -ForegroundColor Red;    Write-CsaLog $l 'screen' }
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

$SCRIPT_LABEL = 'windows-plugins.ps1'
$CsaRawBase = 'https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts'
$CsaDebug = Test-CsaDebugRequested
# Normalise it into the environment, so a child process inherits the setting whichever way it
# was given. The CSA-internal setup is a separate process and reads $env:CSA_DEBUG only.
if ($CsaDebug) { $env:CSA_DEBUG = '1' }
$CsaLog = $null
# Set by the last line of the run. Read by Write-CsaLogTail from a finally, which cannot
# otherwise tell a completed run from an aborted one.
$script:CsaCompleted = $false
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
            # The console codepage, because it has caused two failures in this work that looked
            # like nothing of the kind. A checker crashed with UnicodeDecodeError reading UTF-8
            # script text on a cp1252 box - and passed in CI, where the runner is UTF-8. A probe
            # died printing U+FEFF for the same reason. Neither was guessable from a log that
            # did not say what the codepage was.
            #
            # And whether a prompt was even possible: "the script hung" and "the script asked a
            # question nobody could answer" are the same lines in a log otherwise.
            ("codepage {0} / console {1}; stdin-redirected={2}; NONINTERACTIVE={3}; CI={4}" -f `
                (Get-Culture).Name,
                [Console]::OutputEncoding.WebName,
                [Console]::IsInputRedirected,
                $(if ($env:NONINTERACTIVE) { $env:NONINTERACTIVE } else { '<unset>' }),
                $(if ($env:CI) { $env:CI } else { '<unset>' })) |
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
# When and how the run ended. Its ABSENCE was the defect: #96 diagnosed a crash from a log
# whose last line was an ordinary successful command, because nothing marked the end. A log
# that stops is indistinguishable from a log that was cut off.
#
# Called from a finally, so it also appears after an Abort or an unhandled exception - the two
# cases where a missing terminator is most misleading. Measured on 5.1: `finally` runs on
# `exit` and the exit code survives.
function Write-CsaLogTail {
    if (-not $CsaLog) { return }
    $how = if ($script:CsaCompleted) { 'completed' } else { 'ENDED EARLY (aborted, or threw)' }
    Write-CsaLog ("=== end of {0} v{1}: {2} ===" -f $SCRIPT_LABEL, $ScriptVersion, $how) 'info'
}

function Show-CsaDebugHint {
    if ($CsaLog) {
        Write-Info "debug log: $CsaLog  (redacted, but review before sharing)"
    } else {
        # The exact command, on ONE line joined with ';'. Not "the same command": somebody
        # reading this has just watched something go wrong, and asking them to reconstruct
        # what they typed is asking them to give up. One line because pasting two at once
        # has been observed to close the console - see the README.
        Write-Host "  if anything above went wrong, re-run with logging on and send the log:" -ForegroundColor DarkGray
        Write-Host "    `$env:CSA_DEBUG = '1'; irm $CsaRawBase/$SCRIPT_LABEL -Headers @{'Cache-Control'='no-cache'} | iex" -ForegroundColor DarkGray
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

# Is this output a base64 blob? Measured on a real 6,567-line debug log: 5,390 of its lines -
# 82% of the entire file - were the base64 of the four fetched setup scripts, because
# `gh api --jq '.content'` returns base64 and this function logged every line of it.
#
# That is not merely noise. The setup scripts already explain why it is the wrong thing to log,
# in the comment covering the credential fetch they deliberately exclude: "a redaction rule
# cannot recognise a base64 blob". No secret is leaking here - the credential fetch is a
# separate call and is correctly unlogged - but a person asked to review a log before sharing
# it cannot review 5,390 lines of base64, and the redactor cannot inspect them either.
#
# A length and a hash are BETTER evidence than the blob: they prove what was fetched and can be
# compared against the gate repo, in one line somebody can actually read.
function Test-CsaLooksBase64 {
    param([string[]]$Lines)
    $real = @($Lines | Where-Object { $_.Trim() })
    if ($real.Count -lt 8) { return $false }
    $long = @($real | Where-Object { $_.Length -ge 60 -and $_ -match '^[A-Za-z0-9+/=]+$' })
    return ($long.Count / $real.Count) -ge 0.9
}

function Write-CsaNativeLog {
    param([scriptblock]$Call, [int]$Code, [string]$Output)
    if (-not $CsaLog) { return }
    Write-CsaLog ("{0} -> exit {1}" -f (Expand-CsaCommandText $Call), $Code) 'run'
    if (-not $Output) { return }
    $lines = $Output -split "`r?`n"

    if (Test-CsaLooksBase64 $lines) {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try {
            $h = [BitConverter]::ToString($sha.ComputeHash(
                [System.Text.Encoding]::UTF8.GetBytes($Output))).Replace('-', '').Substring(0, 16)
        } finally { $sha.Dispose() }
        Write-CsaLog ("<base64 omitted: {0} lines, {1} bytes, sha256 {2}>" -f `
            $lines.Count, $Output.Length, $h.ToLower()) 'out'
        return
    }

    # A long SUCCESSFUL command gets its middle elided; a FAILING one never does. The log
    # exists for failures, so evidence is only ever dropped where there is nothing to diagnose.
    # The marker states the count, because output that is quietly incomplete is worse than
    # output that is long.
    if ($Code -eq 0 -and $lines.Count -gt 60) {
        foreach ($line in $lines[0..29]) { Write-CsaLog $line 'out' }
        # The format string is parenthesised BEFORE -f. Without the inner parens, -f binds
        # tighter than + and formats only the SECOND fragment - which has no {0} - so the log
        # read "<{0} lines elided". Identical precedence trap to `-What 'pkg ' + $why` binding
        # only the literal and silently dropping the reason (CSA-Plugins, measured with an
        # argument probe). PowerShell accepts a malformed argument list without complaint.
        Write-CsaLog (("<{0} lines elided; the command succeeded, so they are not diagnostic. " +
                       "A non-zero exit is never elided.>") -f ($lines.Count - 40)) 'out'
        foreach ($line in $lines[($lines.Count - 10)..($lines.Count - 1)]) { Write-CsaLog $line 'out' }
        return
    }

    foreach ($line in $lines) { Write-CsaLog $line 'out' }
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
    Write-CsaLog ("{0} v{1} starting; CSA_DEBUG=1, no argument vector (irm|iex)" -f $SCRIPT_LABEL, $ScriptVersion) 'info'
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
    # Logged BEFORE Read-Host blocks, which is the point: "waiting on a human" and "hung" are
    # indistinguishable in a log that only records what happened afterwards, and a prompt that
    # had lost its value was the actual bug the last investigation was looking for (#96).
    $question = "$Message [Y/n]"
    if ($env:NONINTERACTIVE -eq '1') {
        Write-CsaLog "$question -> auto-yes (NONINTERACTIVE)" 'prompt'
        return $true
    }
    Write-CsaLog $question 'prompt'
    $reply = Read-Host $question
    Write-CsaLog "answered: '$reply'" 'prompt'
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
        Write-Info "  sign in with a free CSA account - https://cloudsecurityalliance.org/ (click 'Sign in or Sign Up')"
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
    Write-Host "                       sign in with a free CSA account - https://cloudsecurityalliance.org/ (click 'Sign in or Sign Up')"
    # DERIVED, for the reason the marketplace line is. This plan named none of the four internal
    # servers while installing all four, so a person agreed to a list that omitted every one of
    # them. Enumerated from $CSA_INTERNAL_SETUPS so the plan and the run cannot disagree.
    Write-Host "  Internal MCP servers install/upgrade $($CSA_INTERNAL_SETUPS.Count) servers if your GitHub account has CSA-Internal access"
    foreach ($setupName in $CSA_INTERNAL_SETUPS) {
        Write-Host "                       $($setupName -replace '-setup\.ps1$', '')"
    }
    Write-Host "                       each prints what it may do before it is used"

    Write-Host ""
}

# ── Main ────────────────────────────────────────────────────────────

# Run CSA-internal setup that cannot live in this public repo (it carries CSA's OAuth
# client). Gated exactly like Register-CSAMcpServer: probe CloudSecurityAlliance-Internal
# with gh and silently do nothing without access, so external users of this public repo
# see no chatter. The fetched script is idempotent and reports for itself.
function Invoke-CSAInternalSetup {
    if (-not (Has-Command 'gh')) { return }
    if ((Invoke-NativeQuiet { gh auth status }) -ne 0) { return }
    if ((Invoke-NativeQuiet { gh api "repos/$CSA_MCP_GATE_REPO" }) -ne 0) { return }

    # One entry per internal MCP server, mirroring setup_csa_internal_tools() in the bash
    # scripts. A list rather than a copied block, so a third server is one line.
    #
    # Both scripts exist in the gate repo. The list is still the right shape for a script
    # that is absent - `continue` below skips one the repo does not carry - which is how
    # csa-skilljar was carried between the day it was listed here and the day its .ps1
    # landed, with no change needed in this file.
    foreach ($name in $CSA_INTERNAL_SETUPS) {
        $encoded = Invoke-NativeOutput { gh api "repos/$CSA_MCP_GATE_REPO/contents/internal-setup/$name" --jq '.content' }
        # `continue`, not `return`: a setup script that is absent - not merged yet, or
        # renamed - must not stop the ones after it. The earlier single-script form
        # returned, so a rename would have silently disabled every server that followed.
        if ($LASTEXITCODE -ne 0 -or -not $encoded) { continue }

        try {
            $script = [System.Text.Encoding]::UTF8.GetString(
                [System.Convert]::FromBase64String(($encoded -replace '\s', '')))
        } catch { continue }

        # CSA_NESTED tells the fetched script that it is running inside another CSA installer, so
        # it should leave the closing summary to this one. Without it both printed "if anything
        # above went wrong, re-run with logging on", one after the other.
        # CSA_PYTHON_PREFERRED tells the fetched setup script which interpreter to install
        # the server on, so `uv tool install --python` lands it there. Measured 2026-09-29:
        # with no --python, uv picks its OWN managed default (3.12 on that box) and ignores
        # both PATH (3.14.3 there) and anything this installer provisioned - which is how
        # four CSA servers ended up on 3.10.20. Only the *-ai-tools orchestrator defines
        # $CsaPythonPreferred; elsewhere this is $null, the variable goes out empty, and the
        # setup script falls back to its own default. Set here regardless so all three
        # copies of this function stay byte-identical, which tools/check-duplication.py
        # enforces. See CSA-Plugins#133.
        $prevNested = $env:CSA_NESTED
        $prevPyPref = $env:CSA_PYTHON_PREFERRED
        $env:CSA_NESTED = '1'
        $env:CSA_PYTHON_PREFERRED = $CsaPythonPreferred
        try { & ([ScriptBlock]::Create($script)) }
        catch { Write-Warn "CSA internal setup ($name) reported a problem: $_" }
        finally {
            $env:CSA_NESTED = $prevNested
            $env:CSA_PYTHON_PREFERRED = $prevPyPref
        }
    }
}

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

    # Runs LAST, after the summary, so the internal setup's own output - including the
    # "you still need to log in" banner - is the final thing on screen instead of being
    # buried under a wall of install output the user has stopped reading.
    Invoke-CSAInternalSetup
}

try {
    Main
    $script:CsaCompleted = $true
} finally {
    Write-CsaLogTail
    Show-CsaDebugHint
}
