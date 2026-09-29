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
Emit "=================================================================="
Write-Host ""
Write-Host "LOG WRITTEN TO: $log" -ForegroundColor Green
Write-Host "Send that path back."
