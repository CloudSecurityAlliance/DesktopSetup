# Pester tests for #153 on Windows: the installers run `npm install -g <pkg>@latest` and never
# `npm update -g <pkg>`. That command was already their fallback whenever the update failed. The
# macOS half, and the measured cause, are in tests/test_homebrew_owns_npm.py.
#
# windows-update.ps1's Update-Npm still runs a bare `npm update -g`: its rewrite waits for a
# real Windows run (#184), because on Windows npm.cmd prefers a global copy of npm when one
# exists, so excluding npm there needs measuring first. That change and its tests are in their
# own draft PR.
#
# What this proves, and what it does not: which command each installer runs, installed or not,
# and that a failure warns. It does NOT prove that Windows PowerShell 5.1 passes the bare
# `@openai/codex@latest` through as one argument (pwsh 7's parser does), or what npm does on a
# real machine.
#
# npm is a PowerShell function defined for the duration, which takes precedence over npm.cmd, so
# a runner's real npm is never called. Functions are loaded out of the shipping scripts through
# PowerShell's own parser, never copied, as in DesktopApps.Tests.ps1.

BeforeAll {
    # The text of every function reachable from $Roots - the closure DesktopApps.Tests.ps1 uses.
    function script:Get-FunctionClosure {
        param([string]$Path, [string[]]$Roots)
        $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$null, [ref]$errors)
        if ($errors) { throw "cannot parse ${Path}: $($errors.Count) error(s)" }
        $definitions = $ast.FindAll(
            { $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
        $byName = @{}
        foreach ($definition in $definitions) { $byName[$definition.Name] = $definition }
        $needed = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
        $queue = New-Object System.Collections.Queue
        foreach ($r in $Roots) {
            if (-not $byName.ContainsKey($r)) { throw "$Path does not define $r" }
            $queue.Enqueue($r)
        }
        while ($queue.Count -gt 0) {
            $name = [string]$queue.Dequeue()
            if (-not $needed.Add($name)) { continue }
            $calls = $byName[$name].Body.FindAll(
                { $args[0] -is [System.Management.Automation.Language.CommandAst] }, $true)
            foreach ($call in $calls) {
                $called = $call.GetCommandName()
                if ($called -and $byName.ContainsKey($called) -and -not $needed.Contains($called)) {
                    $queue.Enqueue($called)
                }
            }
        }
        $texts = @()
        foreach ($definition in $definitions) {
            if ($needed.Contains($definition.Name)) { $texts += $definition.Extent.Text }
        }
        return $texts
    }

    # The stand-in for npm. Records each call as one line of flattened arguments (an array
    # variable reaches a native command as separate arguments, but a function sees it as one),
    # answers `outdated` from $global:NpmOutdatedText, and sets $LASTEXITCODE as npm would.
    function global:npm {
        $flat = @()
        foreach ($a in $args) { foreach ($x in @($a)) { $flat += "$x" } }
        $global:NpmCalls += ($flat -join ' ')
        if ($flat[0] -eq 'outdated') {
            if ($global:NpmOutdatedText) { Write-Output $global:NpmOutdatedText }
            $global:LASTEXITCODE = $global:NpmOutdatedExit
            return
        }
        # What a real install or update prints. It matters: a caller that treats
        # Invoke-NativeNpm's return value as the exit code sees these lines too.
        if ($flat[0] -eq 'install' -or $flat[0] -eq 'update') { Write-Output 'changed 2 packages in 3s' }
        if ($flat[0] -eq 'install') { $global:LASTEXITCODE = $global:NpmInstallExit; return }
        $global:LASTEXITCODE = 0
    }

    function script:Reset-FakeNpm {
        param([string]$Outdated = '{}', [int]$OutdatedExit = 0, [int]$InstallExit = 0)
        $global:NpmCalls = @()
        $global:NpmOutdatedText = $Outdated
        $global:NpmOutdatedExit = $OutdatedExit
        $global:NpmInstallExit = $InstallExit
    }
}

AfterAll {
    Remove-Item function:global:npm -ErrorAction SilentlyContinue
    Remove-Variable NpmCalls, NpmOutdatedText, NpmOutdatedExit, NpmInstallExit -Scope Global -ErrorAction SilentlyContinue
}

Describe 'windows-ai-tools.ps1: the Codex and Gemini installers' {
    BeforeAll {
        $source = "$PSScriptRoot/../scripts/windows-ai-tools.ps1"
        foreach ($text in (Get-FunctionClosure -Path $source -Roots @('Install-Codex', 'Install-Gemini'))) {
            . ([scriptblock]::Create($text))
        }
    }

    BeforeEach {
        Mock Write-Info {}
        Mock Write-Warn {}
    }

    It 'runs only npm install -g PACKAGE@latest when the CLI is installed' {
        Mock Has-Command { $true } -ParameterFilter { $Name -eq 'codex' -or $Name -eq 'gemini' }
        Reset-FakeNpm
        Install-Codex
        Install-Gemini
        @($global:NpmCalls) | Should -Be @('install -g @openai/codex@latest', 'install -g @google/gemini-cli@latest')
        Should -Invoke Write-Warn -Times 0 -Exactly
    }

    It 'runs the same command when it is not' {
        Mock Has-Command { $false } -ParameterFilter { $Name -eq 'codex' -or $Name -eq 'gemini' }
        Reset-FakeNpm
        Install-Codex
        Install-Gemini
        @($global:NpmCalls) | Should -Be @('install -g @openai/codex@latest', 'install -g @google/gemini-cli@latest')
    }

    It 'warns when the install fails' {
        Mock Has-Command { $true } -ParameterFilter { $Name -eq 'codex' }
        Reset-FakeNpm -InstallExit 1
        Install-Codex
        Should -Invoke Write-Warn -Times 1 -Exactly -ParameterFilter { $Message -match 'Failed to update Codex CLI' }
    }
}

Describe 'windows-work-tools.ps1: Install-NpmPackage' {
    BeforeAll {
        $source = "$PSScriptRoot/../scripts/windows-work-tools.ps1"
        foreach ($text in (Get-FunctionClosure -Path $source -Roots @('Install-NpmPackage'))) {
            . ([scriptblock]::Create($text))
        }
    }

    BeforeEach {
        Mock Write-Info {}
        Mock Write-Warn {}
    }

    It 'runs only npm install -g wrangler@latest when Wrangler is installed' {
        Mock Has-Command { $true } -ParameterFilter { $Name -eq 'wrangler' }
        Reset-FakeNpm
        Install-NpmPackage 'Wrangler' 'wrangler' 'wrangler'
        @($global:NpmCalls) | Should -Be @('install -g wrangler@latest')
    }

    It 'runs the same command when it is not' {
        Mock Has-Command { $false } -ParameterFilter { $Name -eq 'wrangler' }
        Reset-FakeNpm
        Install-NpmPackage 'Wrangler' 'wrangler' 'wrangler'
        @($global:NpmCalls) | Should -Be @('install -g wrangler@latest')
    }

    It 'control (ADR-005): the pre-#153 Install-NpmPackage is caught by the checks above' {
        # The function as it behaved at 7b6d743. If the fake npm could not see its `update -g`, the
        # "runs only install" assertions would pass about nothing.
        . ([scriptblock]::Create(@'
function Install-NpmPackage {
    param([string]$Label, [string]$Package, [string]$Bin)
    if (-not (Has-Command npm)) { Write-Warn "npm not found; skipping $Label"; return }
    if (Has-Command $Bin) {
        Write-Info "Updating $Label"
        $null = Invoke-NativeNpm { npm update -g $Package }
        if ($LASTEXITCODE -ne 0) {
            $null = Invoke-NativeNpm { npm install -g $Package }
            if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to update $Label" }
        }
    } else {
        Write-Info "Installing $Label"
        $null = Invoke-NativeNpm { npm install -g $Package }
        if ($LASTEXITCODE -ne 0) { Write-Warn "Failed to install $Label" }
    }
}
'@))
        Mock Has-Command { $true } -ParameterFilter { $Name -eq 'wrangler' }
        Reset-FakeNpm
        Install-NpmPackage 'Wrangler' 'wrangler' 'wrangler'
        @($global:NpmCalls) | Should -Not -Be @('install -g wrangler@latest')
        $global:NpmCalls | Should -Contain 'update -g wrangler'
    }
}
