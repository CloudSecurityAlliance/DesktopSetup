# Pester tests for #153 on Windows: npm updates only what npm installed. The Node.js installer
# owns npm and corepack, so windows-update.ps1's Update-Npm lists the outdated globals, drops
# those two, and installs the rest @latest; the installers run `npm install -g <pkg>@latest` and
# never `npm update -g`. The macOS half, and the measured cause, are in
# tests/test_homebrew_owns_npm.py.
#
# What this proves, and what it does not. It locks down the DECISIONS: what is installed, what
# is never touched, that `npm outdated -g --json` is read as measured on npm 11.20 (packages,
# `{}`, and the `{"error": ...}` object a failure prints on stdout with the same exit 1 as
# "something is outdated"), and that a failure is never reported as "already current". It does
# NOT prove what npm on a real Windows machine prints, whether npm is in its global tree at all
# (the Node MSI puts it under Program Files\nodejs; globals normally go to %APPDATA%\npm), or that
# Invoke-NativeCapture's merged stderr leaves the JSON readable there. Those are the checks #153
# lists for a Windows session.
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

    # `npm outdated -g --json`, in the shape npm 11.20 printed it (measured 2026-11-11 against a
    # throwaway prefix on macOS; the versions and paths here are illustrative): npm and corepack
    # outdated beside two real globals, one scoped.
    $script:Mixed = @'
{
  "npm": { "current": "11.6.2", "wanted": "11.6.4", "latest": "11.6.4", "dependent": "global", "location": "C:\\Users\\someone\\AppData\\Roaming\\npm\\node_modules\\npm" },
  "corepack": { "current": "0.34.0", "wanted": "0.35.0", "latest": "0.35.0", "dependent": "global", "location": "C:\\Users\\someone\\AppData\\Roaming\\npm\\node_modules\\corepack" },
  "wrangler": { "current": "4.62.0", "wanted": "4.149.0", "latest": "4.149.0", "dependent": "global", "location": "C:\\Users\\someone\\AppData\\Roaming\\npm\\node_modules\\wrangler" },
  "@openai/codex": { "current": "0.50.0", "wanted": "0.60.0", "latest": "0.60.0", "dependent": "global", "location": "C:\\Users\\someone\\AppData\\Roaming\\npm\\node_modules\\@openai\\codex" }
}
'@
    $script:OnlyNode = @'
{
  "npm": { "current": "11.6.2", "wanted": "11.6.4", "latest": "11.6.4", "dependent": "global", "location": "C:\\x" },
  "corepack": { "current": "0.34.0", "wanted": "0.35.0", "latest": "0.35.0", "dependent": "global", "location": "C:\\y" }
}
'@
    # Measured: an unreachable registry prints this on stdout and exits 1 - the same exit code
    # as "something is outdated".
    $script:Failed = @'
{
  "error": {
    "code": "ECONNREFUSED",
    "summary": "FetchError: request to http://127.0.0.1:9/is-number failed, reason: connect ECONNREFUSED 127.0.0.1:9",
    "detail": "If you are behind a proxy, please make sure that the 'proxy' config is set properly."
  }
}
'@
}

AfterAll {
    Remove-Item function:global:npm -ErrorAction SilentlyContinue
    Remove-Variable NpmCalls, NpmOutdatedText, NpmOutdatedExit, NpmInstallExit -Scope Global -ErrorAction SilentlyContinue
}

Describe 'windows-update.ps1: reading npm outdated -g --json' {
    BeforeAll {
        $source = "$PSScriptRoot/../scripts/windows-update.ps1"
        foreach ($text in (Get-FunctionClosure -Path $source -Roots @('ConvertFrom-NpmOutdatedJson'))) {
            . ([scriptblock]::Create($text))
        }
    }

    It 'reads every outdated package, a scoped name whole' {
        $r = ConvertFrom-NpmOutdatedJson $script:Mixed
        $r.Ok | Should -BeTrue
        @($r.Packages | ForEach-Object { $_.Name }) | Should -Be @('npm', 'corepack', 'wrangler', '@openai/codex')
        ($r.Packages | Where-Object Name -eq 'wrangler').Latest | Should -Be '4.149.0'
        ($r.Packages | Where-Object Name -eq '@openai/codex').Current | Should -Be '0.50.0'
        ($r.Packages | Where-Object Name -eq 'wrangler').Location |
            Should -Be 'C:\Users\someone\AppData\Roaming\npm\node_modules\wrangler'
    }

    It 'reads {} as nothing outdated' {
        $r = ConvertFrom-NpmOutdatedJson '{}'
        $r.Ok | Should -BeTrue
        @($r.Packages).Count | Should -Be 0
    }

    It "never reads npm's error object as 'nothing outdated'" {
        (ConvertFrom-NpmOutdatedJson $script:Failed).Ok | Should -BeFalse
    }

    It 'never reads empty or non-JSON output as nothing outdated' {
        (ConvertFrom-NpmOutdatedJson '').Ok | Should -BeFalse
        (ConvertFrom-NpmOutdatedJson 'npm error code ENOENT').Ok | Should -BeFalse
        (ConvertFrom-NpmOutdatedJson '{ "truncated": ').Ok | Should -BeFalse
    }

    It 'still reads the JSON when stderr lines are merged around it (Invoke-NativeCapture)' {
        $merged = "npm warn config production Use ``--omit=dev`` instead.`n" + $script:Mixed + "`nnpm notice done"
        $r = ConvertFrom-NpmOutdatedJson $merged
        $r.Ok | Should -BeTrue
        @($r.Packages).Count | Should -Be 4
    }

    It 'treats a package that is really named "error" as a package' {
        $r = ConvertFrom-NpmOutdatedJson '{ "error": { "current": "1.0.0", "wanted": "2.0.0", "latest": "2.0.0" } }'
        $r.Ok | Should -BeTrue
        $r.Packages[0].Name | Should -Be 'error'
    }
}

Describe 'windows-update.ps1: Update-Npm' {
    BeforeAll {
        $source = "$PSScriptRoot/../scripts/windows-update.ps1"
        foreach ($text in (Get-FunctionClosure -Path $source -Roots @('Update-Npm', 'Test-NpmNodeOwned'))) {
            . ([scriptblock]::Create($text))
        }
    }

    BeforeEach {
        Mock Write-Info {}
        Mock Write-Warn {}
    }

    It 'installs every outdated global @latest in one call, and never npm or corepack' {
        Reset-FakeNpm -Outdated $script:Mixed -OutdatedExit 1
        Update-Npm
        $installs = @($global:NpmCalls | Where-Object { $_ -like 'install *' })
        $installs | Should -Be @('install -g wrangler@latest @openai/codex@latest')
        $global:NpmCalls | Where-Object { $_ -like 'update*' } | Should -BeNullOrEmpty
        $global:NpmCalls | Where-Object { $_ -match '(^| )(npm|corepack)@' } | Should -BeNullOrEmpty
        Should -Invoke Write-Warn -Times 0 -Exactly
    }

    It 'asks npm in the JSON form it reads' {
        Reset-FakeNpm
        Update-Npm
        $global:NpmCalls[0] | Should -Be 'outdated -g --json'
    }

    It 'changes nothing, and says so, when only npm and corepack are outdated' {
        Reset-FakeNpm -Outdated $script:OnlyNode -OutdatedExit 1
        Update-Npm
        @($global:NpmCalls) | Should -Be @('outdated -g --json')
        Should -Invoke Write-Info -Times 1 -Exactly -ParameterFilter { $Message -match 'already current' }
    }

    It 'changes nothing when nothing is outdated' {
        Reset-FakeNpm -Outdated '{}' -OutdatedExit 0
        Update-Npm
        @($global:NpmCalls) | Should -Be @('outdated -g --json')
        Should -Invoke Write-Info -Times 1 -Exactly -ParameterFilter { $Message -match 'already current' }
    }

    It "warns, and never claims 'already current', when npm outdated failed" {
        Reset-FakeNpm -Outdated $script:Failed -OutdatedExit 1
        Update-Npm
        @($global:NpmCalls) | Should -Be @('outdated -g --json')
        Should -Invoke Write-Warn -Times 1 -Exactly -ParameterFilter { $Message -match 'Could not list' }
        Should -Invoke Write-Info -Times 0 -Exactly -ParameterFilter { $Message -match 'already current' }
    }

    It 'warns when the install fails, and does not throw' {
        Reset-FakeNpm -Outdated $script:Mixed -OutdatedExit 1 -InstallExit 1
        { Update-Npm } | Should -Not -Throw
        Should -Invoke Write-Warn -Times 1 -Exactly -ParameterFilter { $Message -match 'npm install -g failed' }
    }

    It 'does not warn after an install that worked, whatever npm printed' {
        # The old `$code = Invoke-NativeNpm {...}; if ($code -ne 0)` compared npm's output lines
        # with 0 as well as its exit code, so every successful run that printed anything warned.
        Reset-FakeNpm -Outdated $script:Mixed -OutdatedExit 1 -InstallExit 0
        Update-Npm
        Should -Invoke Write-Warn -Times 0 -Exactly
    }

    It 'does nothing at all without npm' {
        Reset-FakeNpm
        Mock Has-Command { $false } -ParameterFilter { $Name -eq 'npm' }
        Update-Npm
        @($global:NpmCalls).Count | Should -Be 0
    }

    It 'leaves a package linked from a local folder alone, and says so' {
        Mock Test-NpmLinked { $true } -ParameterFilter { $Path -like '*\wrangler' }
        Reset-FakeNpm -Outdated $script:Mixed -OutdatedExit 1
        Update-Npm
        @($global:NpmCalls | Where-Object { $_ -like 'install *' }) | Should -Be @('install -g @openai/codex@latest')
        Should -Invoke Write-Info -Times 1 -Exactly -ParameterFilter { $Message -match 'Not updating wrangler' }
    }

    It 'control (ADR-005): the pre-#153 Update-Npm is caught by the checks above' {
        # The function as it was at 7b6d743. If the fake npm could not see an `update -g`, or a
        # successful run could not produce the false warning, the assertions above would pass
        # about nothing.
        . ([scriptblock]::Create(@'
function Update-Npm {
    if (-not (Has-Command npm)) { return }
    Write-Info "Updating global npm packages"
    $code = Invoke-NativeNpm { npm update -g }
    if ($code -ne 0) { Write-Warn "npm update -g failed; continuing" }
}
'@))
        Reset-FakeNpm -Outdated $script:Mixed -OutdatedExit 1
        Update-Npm
        $global:NpmCalls | Should -Contain 'update -g'
        Should -Invoke Write-Warn -Times 1 -Exactly -ParameterFilter { $Message -match 'failed' }
    }
}

Describe 'windows-update.ps1: Test-NpmLinked' {
    BeforeAll {
        $source = "$PSScriptRoot/../scripts/windows-update.ps1"
        foreach ($text in (Get-FunctionClosure -Path $source -Roots @('Test-NpmLinked'))) {
            . ([scriptblock]::Create($text))
        }
    }

    It 'is true for a link to a folder, as npm link makes one' {
        $target = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'working-copy')
        $link = Join-Path $TestDrive 'linked'
        # npm makes a junction on Windows; elsewhere a junction does not exist, so a symlink.
        $onWindows = ($null -eq $IsWindows) -or $IsWindows
        if ($onWindows) { $null = New-Item -ItemType Junction -Path $link -Target $target.FullName }
        else            { $null = New-Item -ItemType SymbolicLink -Path $link -Target $target.FullName }
        Test-NpmLinked $link | Should -BeTrue
    }

    It 'is false for an installed package, a missing path and no path' {
        $dir = New-Item -ItemType Directory -Path (Join-Path $TestDrive 'installed')
        Test-NpmLinked $dir.FullName | Should -BeFalse
        Test-NpmLinked (Join-Path $TestDrive 'not-there') | Should -BeFalse
        Test-NpmLinked '' | Should -BeFalse
    }
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
}
