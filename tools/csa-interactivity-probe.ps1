# CSA interactivity probe (Windows)
#
# Question it answers: when DesktopSetup runs an internal setup script, is there a
# terminal to prompt at? The setup scripts assume there is not, and skip their
# directory prompts on that basis. This replicates the real invocation chain:
#
#     you run:        irm ...windows-ai-tools.ps1 | iex     <- piped to iex
#     it then runs:   & ([ScriptBlock]::Create($script))    <- the setup script
#
#
# MEASURED SO FAR
#   Windows 11 / PowerShell 5.1.26100.9549 (Desktop edition), real ConsoleHost window,
#   2026-09-29: IsInputRedirected = False at every level - baseline, OUTER and INNER.
#   Test-CsaInteractive returns TRUE, so the directory prompts DO run. `irm | iex` is an
#   object pipeline; it does not redirect the process's stdin, and ScriptBlock::Create
#   runs in the same session. The comment in csa-*-setup.ps1 claiming otherwise is wrong.
#   macOS: not yet measured. That is what the .sh alongside this is for.
# Run this from a REAL interactive PowerShell window (not from an editor task,
# not from CI, not through another tool). Then send back the log path it prints.

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$log   = Join-Path $HOME "csa-interactivity-probe-$stamp.log"

function Emit([string]$line) { Write-Host $line; Add-Content -LiteralPath $log -Value $line -Encoding utf8 }

Emit "CSA interactivity probe (Windows)  $(Get-Date -Format o)"
Emit "=================================================================="
Emit ""
Emit "-- environment --"
Emit ("  PSVersion            : " + $PSVersionTable.PSVersion)
Emit ("  PSEdition            : " + $PSVersionTable.PSEdition)
Emit ("  Host                 : " + $Host.Name)
Emit ("  OS                   : " + [System.Environment]::OSVersion.VersionString)
Emit ("  NONINTERACTIVE       : " + $(if ($env:NONINTERACTIVE) { $env:NONINTERACTIVE } else { '<unset>' }))
Emit ("  CI                   : " + $(if ($env:CI) { $env:CI } else { '<unset>' }))
Emit ""
Emit "-- baseline: this window, before any nesting --"
Emit ("  [Console]::IsInputRedirected  = " + [Console]::IsInputRedirected)
Emit ("  [Environment]::UserInteractive = " + [Environment]::UserInteractive)
Emit ""
Emit "-- replicating the DesktopSetup chain --"

$outerBody = @'
Write-Output ("OUTER (windows-ai-tools.ps1 body, reached via | iex)")
Write-Output ("    IsInputRedirected = " + [Console]::IsInputRedirected)
$inner = @"
Write-Output ("INNER (the internal setup script, via ScriptBlock::Create)")
Write-Output ("    IsInputRedirected = " + [Console]::IsInputRedirected)
"@
& ([ScriptBlock]::Create($inner))
'@

# `| Invoke-Expression` is exactly what `irm ... | iex` does.
$captured = $outerBody | Invoke-Expression
foreach ($l in $captured) { Emit ("  " + $l) }

Emit ""
Emit "-- verdict --"
$inner2 = 'if ([Console]::IsInputRedirected) { "SKIPPED" } else { "RUN" }'
$verdict = & ([ScriptBlock]::Create($inner2))
Emit ("  Test-CsaInteractive would return : " + $(if ([Console]::IsInputRedirected) { 'FALSE' } else { 'TRUE' }))
Emit ("  => directory prompts would be    : " + $verdict)
Emit ""

# ------------------------------------------------------------------------------------------
# A SEPARATE QUESTION, and nothing above answers it.
#
# The CSA setup scripts now WAIT for a locked MCP server executable to be released, and offer
# `q` to skip. Read-Host and [Console]::KeyAvailable are not interchangeable: Read-Host works
# fine with redirected stdin, while KeyAvailable THROWS InvalidOperationException when stdin is
# redirected, and some hosts (ISE, remoting) refuse it outright regardless.
#
# The wait loop guards KeyAvailable in try/catch, which is correct - an exception must not be
# mistaken for "the user quit" - but that guard also means a host where it throws would
# ADVERTISE `q` and silently never honour it. A refusal that cannot be triggered is the same
# class of defect as a check that cannot fail, so it gets measured rather than assumed.
Emit "-- can the wait loop's 'q to skip' actually work here --"

$keyProbe = @'
$r = @{}
try   { $r.Available = [Console]::KeyAvailable; $r.Throws = $false }
catch { $r.Available = $null; $r.Throws = $true; $r.Error = $_.Exception.GetType().Name }
Write-Output ("    KeyAvailable readable = " + $(if ($r.Throws) { "NO - throws " + $r.Error } else { "YES (currently " + $r.Available + ")" }))
'@

Emit "  baseline:"
foreach ($l in (& ([ScriptBlock]::Create($keyProbe)))) { Emit $l }
Emit "  INNER (as the setup script sees it):"
$nested = "`$outer = @'`n$keyProbe`n'@`n& ([ScriptBlock]::Create(`$outer))"
foreach ($l in ($nested | Invoke-Expression)) { Emit $l }

$keyOk = $false
try { $null = [Console]::KeyAvailable; $keyOk = $true } catch { $keyOk = $false }
Emit ("  => 'q to skip' would be          : " + $(if ($keyOk) { 'HONOURED' } else { 'ADVERTISED BUT DEAD - fix the offer' }))
Emit ""

# Only ask for a keypress when it can be read at all, and never block: a probe that hangs is
# worse than one that reports less.
if ($keyOk -and -not [Console]::IsInputRedirected) {
    Write-Host "  Press q within 5 seconds to confirm a keypress is actually delivered (or wait)..."
    $deadline = (Get-Date).AddSeconds(5)
    $saw = '<none>'
    while ((Get-Date) -lt $deadline) {
        if ([Console]::KeyAvailable) { $saw = [Console]::ReadKey($true).Key; break }
        Start-Sleep -Milliseconds 200
    }
    Emit ("  keypress delivered               : " + $saw)
    Emit ("  => q/Escape would cancel the wait: " + $(if ($saw -eq 'Q' -or $saw -eq 'Escape') { 'CONFIRMED' } elseif ($saw -eq '<none>') { 'untested (no key pressed)' } else { "saw '$saw' - would be IGNORED, which is correct" }))
    Emit ""
}
Emit "=================================================================="
Write-Host ""
Write-Host "LOG WRITTEN TO: $log" -ForegroundColor Green
Write-Host "Send that path back."
