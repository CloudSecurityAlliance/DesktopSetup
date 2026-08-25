#!/usr/bin/env bash
# Everything CI runs, locally, in one command. Run it before pushing.
#
#   ./tools/check-all.sh
#
# What this proves and what it does not: `pwsh` on macOS is PowerShell 7, and the Windows
# scripts run under Windows PowerShell 5.1. The two differ on the very behaviour the
# Invoke-Native* wrappers exist for — see tests/NativeWrappers.Tests.ps1 for the measured
# table. So a green run here means "parses, analyses clean, and the wrapper contracts hold";
# it does not mean "works on Windows". Only a Windows machine proves that.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
step() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
check() { if "$@"; then :; else fail=1; printf '\033[31m    FAILED: %s\033[0m\n' "$1"; fi; }

step "bash -n"
for f in scripts/*.sh; do
  bash -n "$f" || { fail=1; echo "    FAILED: $f"; }
done
[[ $fail -eq 0 ]] && echo "    all shell scripts parse"

step "shellcheck"
if command -v shellcheck >/dev/null; then
  check shellcheck --severity=warning --exclude=SC1091,SC2016 scripts/*.sh \
    && echo "    clean"
else
  echo "    skipped (brew install shellcheck)"
fi

step "duplication"
check python3 tools/check-duplication.py

step "native-call guards"
check python3 tools/check-powershell-native.py

step "paste safety"
check python3 tools/check-paste-safety.py

if command -v pwsh >/dev/null; then
  step "powershell parse"
  check pwsh -NoProfile -c '
    $bad = $false
    Get-ChildItem scripts/*.ps1 | ForEach-Object {
      $e = $null
      [System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$null,[ref]$e) | Out-Null
      if ($e) { $bad = $true; Write-Host "    FAIL $($_.Name)"; $e | ForEach-Object { Write-Host "      $($_.Extent.StartLineNumber): $($_.Message)" } }
      else { Write-Host "    ok $($_.Name)" }
    }
    if ($bad) { exit 1 }'

  step "PSScriptAnalyzer"
  check pwsh -NoProfile -c '
    if (-not (Get-Module -ListAvailable PSScriptAnalyzer)) { Write-Host "    skipped (Install-Module PSScriptAnalyzer -Scope CurrentUser)"; exit 0 }
    $r = Invoke-ScriptAnalyzer -Path scripts -Recurse -Severity Error
    if ($r) { $r | Format-Table -AutoSize; exit 1 }
    Write-Host "    no errors"'

  step "Pester"
  check pwsh -NoProfile -c '
    # 5.7.1 specifically — see the note in .github/workflows/lint.yml. Matching CI matters
    # more than being current: Pester 6 aborts the whole run under Windows PowerShell 5.1.
    if (-not (Get-Module -ListAvailable Pester | Where-Object Version -eq 5.7.1)) {
      Write-Host "    skipped (Install-Module Pester -RequiredVersion 5.7.1 -Scope CurrentUser)"; exit 0 }
    Remove-Module Pester -Force -ErrorAction SilentlyContinue
    Import-Module Pester -RequiredVersion 5.7.1
    $c = New-PesterConfiguration
    $c.Run.Path = "tests"; $c.Run.Exit = $true; $c.Output.Verbosity = "Normal"
    Invoke-Pester -Configuration $c'
else
  printf '\n\033[33m==> powershell checks skipped — brew install powershell\033[0m\n'
fi

printf '\n'
if [[ $fail -eq 0 ]]; then
  printf '\033[32mall checks passed\033[0m — note this does NOT prove the .ps1 scripts work on Windows\n'
else
  printf '\033[31msome checks failed\033[0m\n'
fi
exit $fail
