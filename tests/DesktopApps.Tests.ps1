# Pester tests for the Windows desktop-AI-app logic: windows-update.ps1's wait before
# `winget upgrade --all` replaces a running app (Claude, ChatGPT, Gemini, Copilot), and
# windows-ai-tools.ps1's detection of Claude Desktop's old .exe build.
#
# What this proves, and what it does not. It locks down the DECISIONS, which are pure logic and
# testable on any runtime: which processes count as the app (by image path, in this user's
# session only - the session-0 services Claude and Copilot run would make a wait endless), that
# winget is asked about running apps only, that nobody-at-the-keyboard means no wait, that an
# interactive wait can always be left, that an app still running is HELD BACK from the upgrade
# rather than replaced anyway, and that the hold is removed afterwards. It does NOT prove the
# path patterns match what these apps really run from on Windows, or that winget's `list` and
# `pin` answer the way they are used here. Nothing has measured those yet: #161.
#
# The same discipline as NativeWrappers.Tests.ps1: functions are loaded out of the shipping
# scripts through PowerShell's own parser, never copied, so the tests cannot drift from them.

BeforeAll {
    # The text of every function reachable from $Roots, in definition order - the transitive
    # closure NativeWrappers.Tests.ps1 uses, for the reason it gives (#132). Returned as text
    # because a function dot-sourced inside this helper would vanish with its scope; each
    # Describe dot-sources the result into its own.
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

    function script:New-FakeProcess {
        param([string]$Path, [int]$SessionId = 1, [switch]$PathThrows)
        $p = New-Object PSObject
        Add-Member -InputObject $p -MemberType NoteProperty -Name SessionId -Value $SessionId
        if ($PathThrows) {
            Add-Member -InputObject $p -MemberType ScriptProperty -Name Path -Value { throw 'Access is denied' }
        } else {
            Add-Member -InputObject $p -MemberType NoteProperty -Name Path -Value $Path
        }
        return $p
    }
}

Describe 'windows-update.ps1' {
    BeforeAll {
        $source = "$PSScriptRoot/../scripts/windows-update.ps1"
        foreach ($text in (Get-FunctionClosure -Path $source -Roots @(
                'Get-RunningDesktopApps', 'Test-DesktopAppRunning', 'Test-WingetUpgradePending',
                'Get-DesktopAppsAwaitingClose', 'Wait-ForAppExit', 'Get-DesktopAppPatterns',
                'Add-WingetHold', 'Remove-WingetHold', 'Update-Winget'))) {
            . ([scriptblock]::Create($text))
        }
        # The table of apps is data, not a function: evaluate its right-hand side as written.
        $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$null, [ref]$errors)
        $assignment = $ast.Find({
            param($node)
            $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left.Extent.Text -eq '$DesktopApps'
        }, $false)
        if (-not $assignment) { throw 'cannot find $DesktopApps in windows-update.ps1' }
        $script:DesktopApps = @(& ([scriptblock]::Create($assignment.Right.Extent.Text)))
        $script:Claude = $script:DesktopApps | Where-Object { $_.Name -eq 'Claude Desktop' }
        $script:Gemini = $script:DesktopApps | Where-Object { $_.Name -eq 'Gemini Desktop' }
        $script:ChatGpt = $script:DesktopApps | Where-Object { $_.Name -eq 'ChatGPT Desktop' }
    }

    Describe 'which processes count as a desktop app' {
        BeforeEach {
            Mock Get-GeminiDesktopEntry {
                [pscustomobject]@{ DisplayName = 'Gemini'; Publisher = 'Google LLC'
                                   InstallLocation = 'C:\Users\someone\AppData\Local\Programs\Gemini' }
            }
            # Our own session is 1. Session 0 is where Windows runs services.
            Mock Get-Process -ParameterFilter { $Id -contains $PID } { New-FakeProcess -Path 'C:\me.exe' -SessionId 1 }
            Mock Get-Process {
                @(
                    (New-FakeProcess -Path 'C:\Program Files\WindowsApps\Claude_3.6556.2.0_x64__pzs8sxrjxfjjc\app\claude.exe'),
                    # Copilot's proxy runs as a service: never exits when Copilot is quit.
                    (New-FakeProcess -Path 'C:\Program Files (x86)\Microsoft\Copilot\Application\mscopilot_proxy.exe' -SessionId 0),
                    (New-FakeProcess -Path 'C:\Users\someone\AppData\Local\Programs\Gemini\Gemini.exe'),
                    # Not ChatGPT Desktop: a folder that merely shares the MSIX identity's name.
                    (New-FakeProcess -Path 'C:\Tools\OpenAI.Codex\codex.exe'),
                    (New-FakeProcess -Path $null),
                    (New-FakeProcess -PathThrows)
                )
            }
        }

        It 'finds apps by image path in this session, and ignores services, look-alikes and unreadable processes' {
            $names = @(Get-RunningDesktopApps | ForEach-Object { $_.Name })
            $names | Should -Be @('Claude Desktop', 'Gemini Desktop')
        }

        It 'reports a single app as running or not' {
            Test-DesktopAppRunning 'Claude Desktop' | Should -BeTrue
            Test-DesktopAppRunning 'Copilot Desktop' | Should -BeFalse
        }

        It 'does not take any Gemini.exe for Gemini Desktop when its install folder is known' {
            Mock Get-Process {
                @((New-FakeProcess -Path 'C:\Users\someone\Downloads\Gemini.exe'))
            }
            @(Get-RunningDesktopApps).Count | Should -Be 0
        }
    }

    Describe 'where Gemini Desktop is looked for' {
        It 'uses the install folder from its uninstall entry, escaped' {
            Mock Get-GeminiDesktopEntry { [pscustomobject]@{ InstallLocation = 'C:\Apps\Gem[ini]\' } }
            Get-DesktopAppPatterns $script:Gemini | Should -Be @('C:\Apps\Gem`[ini`]\*')
        }

        It 'falls back to the folder of its DisplayIcon' {
            Mock Get-GeminiDesktopEntry { [pscustomobject]@{ DisplayIcon = '"C:\Apps\Gemini\Gemini.exe",0' } }
            Get-DesktopAppPatterns $script:Gemini | Should -Be @('C:\Apps\Gemini\*')
        }

        It 'falls back to the file name only when nothing says where it is' {
            Mock Get-GeminiDesktopEntry { $null }
            Get-DesktopAppPatterns $script:Gemini | Should -Be @('*\Gemini.exe')
        }

        It 'leaves every other app on its fixed patterns' {
            Mock Get-GeminiDesktopEntry { throw 'must not be asked' }
            Get-DesktopAppPatterns $script:Claude | Should -Be @($script:Claude.Paths)
        }
    }

    Describe 'which running apps winget is about to replace' {
        It 'asks winget only about apps that are running, and keeps those with an update waiting' {
            Mock Get-RunningDesktopApps { @($script:Claude, $script:Gemini) }
            Mock Test-WingetUpgradePending { $Id -eq 'Anthropic.Claude' }

            $due = @(Get-DesktopAppsAwaitingClose)

            $due.Count | Should -Be 1
            $due[0].Name | Should -Be 'Claude Desktop'
            Should -Invoke Test-WingetUpgradePending -Times 2 -Exactly
        }

        It 'costs no winget call at all when nothing is running' {
            Mock Get-RunningDesktopApps { @() }
            Mock Test-WingetUpgradePending { $true }
            @(Get-DesktopAppsAwaitingClose).Count | Should -Be 0
            Should -Invoke Test-WingetUpgradePending -Times 0 -Exactly
        }

        It 'reads a pending upgrade from winget, and passes the source for the Store id' {
            Mock Invoke-NativeOutput { @('Name     Id           Version Available', 'ChatGPT  9PLM9XGG6VKS 26.1    26.2') }
            Test-WingetUpgradePending '9PLM9XGG6VKS' 'msstore' | Should -BeTrue
            Should -Invoke Invoke-NativeOutput -Times 1 -Exactly -ParameterFilter { $Call.ToString() -match '--source \$Source' }

            Mock Invoke-NativeOutput { @('No installed package found matching input criteria.') }
            Test-WingetUpgradePending 'Anthropic.Claude' '' | Should -BeFalse
        }
    }

    Describe 'waiting for an app to be quit' {
        BeforeEach {
            $script:checks = 0
            $script:runningFor = 0
            $script:answers = @()
            Mock Test-DesktopAppRunning { $script:checks++; return ($script:checks -le $script:runningFor) }
            Mock Start-Sleep { }
            Mock Write-Host { }
            Mock Confirm-Step {
                $next = $script:answers[0]
                $script:answers = @($script:answers | Select-Object -Skip 1)
                return $next
            }
            $script:savedNonInteractive = $env:NONINTERACTIVE
            $env:NONINTERACTIVE = $null
        }
        AfterEach {
            $env:NONINTERACTIVE = $script:savedNonInteractive
        }

        It 'does not wait for an app that is not running' {
            Wait-ForAppExit 'Claude Desktop' | Should -BeTrue
            Should -Invoke Start-Sleep -Times 0 -Exactly
        }

        It 'with nobody at the keyboard, does not wait at all and reports the app as still running' {
            $env:NONINTERACTIVE = '1'
            $script:runningFor = 100000
            Wait-ForAppExit 'Claude Desktop' | Should -BeFalse
            Should -Invoke Start-Sleep -Times 0 -Exactly
            Should -Invoke Confirm-Step -Times 0 -Exactly
        }

        It 'waits until the app exits, without asking inside the first minute' {
            $script:runningFor = 4
            Wait-ForAppExit 'Claude Desktop' | Should -BeTrue
            Should -Invoke Start-Sleep -Times 3 -Exactly
            Should -Invoke Confirm-Step -Times 0 -Exactly
        }

        It 'asks after a minute, and a no ends the wait with the app still running' {
            $script:runningFor = 100000
            $script:answers = @($false)
            Wait-ForAppExit 'Claude Desktop' | Should -BeFalse
            Should -Invoke Start-Sleep -Times 30 -Exactly
            Should -Invoke Confirm-Step -Times 1 -Exactly -ParameterFilter { $Message -like 'Claude Desktop is still running*' }
        }

        It 'a yes waits another minute and asks again' {
            $script:runningFor = 100000
            $script:answers = @($true, $false)
            Wait-ForAppExit 'Claude Desktop' | Should -BeFalse
            Should -Invoke Start-Sleep -Times 60 -Exactly
            Should -Invoke Confirm-Step -Times 2 -Exactly
        }

        It 'an app quit while the question was on screen counts as quit, even after a no' {
            # 32 checks: the first, then one per poll until the minute is up. The 33rd - the
            # re-check after the answer - finds it gone.
            $script:runningFor = 32
            $script:answers = @($false)
            Wait-ForAppExit 'Claude Desktop' | Should -BeTrue
            Should -Invoke Confirm-Step -Times 1 -Exactly
        }
    }

    Describe 'an app still running is held back from the upgrade, not replaced' {
        BeforeEach {
            $script:order = @()
            Mock Has-Command { $true }
            Mock Write-Info { }
            Mock Write-Warn { }
            Mock Invoke-NativeShow {
                if ($Call.ToString() -match 'upgrade --all') {
                    $script:order += 'upgrade'
                    if ($script:upgradeThrows) { throw 'winget died' }
                }
            }
            Mock Get-DesktopAppsAwaitingClose { @($script:Claude) }
            Mock Add-WingetHold { $script:order += 'hold'; return $script:holdResult }
            Mock Remove-WingetHold { $script:order += 'release' }
            $script:upgradeThrows = $false
            $script:holdResult = 'added'
        }

        It 'holds a declined app back for the upgrade, and releases it afterwards' {
            Mock Wait-ForAppExit { $false }
            Update-Winget
            $script:order | Should -Be @('hold', 'upgrade', 'release')
        }

        It 'never removes a pin the person set themselves' {
            Mock Wait-ForAppExit { $false }
            $script:holdResult = 'existing'
            Update-Winget
            $script:order | Should -Be @('hold', 'upgrade')
        }

        It 'holds nothing back when the app was quit' {
            Mock Wait-ForAppExit { $true }
            Update-Winget
            $script:order | Should -Be @('upgrade')
        }

        It 'releases its pin even when the upgrade itself fails' {
            Mock Wait-ForAppExit { $false }
            $script:upgradeThrows = $true
            { Update-Winget } | Should -Throw
            $script:order | Should -Be @('hold', 'upgrade', 'release')
        }
    }

    Describe 'placing the hold' {
        It "treats the person's own pin as theirs, and adds none" {
            Mock Invoke-NativeOutput { @('Name    Id               Version', 'Claude  Anthropic.Claude 3.6556.2') }
            Mock Invoke-NativeQuiet { 0 }
            Add-WingetHold $script:Claude | Should -Be 'existing'
            Should -Invoke Invoke-NativeQuiet -Times 0 -Exactly
        }

        It 'adds a pin, with the source for the Store app, and reports it as ours' {
            Mock Invoke-NativeOutput { @('There are no pins configured.') }
            Mock Invoke-NativeQuiet { 0 }
            Add-WingetHold $script:ChatGpt | Should -Be 'added'
            Should -Invoke Invoke-NativeQuiet -Times 1 -Exactly -ParameterFilter { $Call.ToString() -match 'pin add .*--source \$App.Source' }
        }

        It 'reports a pin winget refused' {
            Mock Invoke-NativeOutput { @() }
            Mock Invoke-NativeQuiet { 1 }
            Add-WingetHold $script:Claude | Should -Be 'failed'
        }
    }
}

Describe 'windows-ai-tools.ps1: Claude Desktop''s old .exe build' {
    BeforeAll {
        foreach ($text in (Get-FunctionClosure -Path "$PSScriptRoot/../scripts/windows-ai-tools.ps1" -Roots @('Test-ClaudeLegacyExe'))) {
            . ([scriptblock]::Create($text))
        }
        # Get-AppxPackage exists only on Windows; Pester can only mock a command that exists.
        if (-not (Get-Command Get-AppxPackage -ErrorAction SilentlyContinue)) {
            function script:Get-AppxPackage { param([string]$Name, $ErrorAction) }
        }
    }

    BeforeEach {
        $script:savedLocalAppData = $env:LOCALAPPDATA
        $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString())
        $script:root = Join-Path $env:LOCALAPPDATA 'AnthropicClaude'
        $null = New-Item -ItemType Directory -Path (Join-Path $script:root 'app-0.14.10') -Force
        $null = New-Item -ItemType File -Path (Join-Path $script:root 'Update.exe') -Force
        $null = New-Item -ItemType File -Path (Join-Path (Join-Path $script:root 'app-0.14.10') 'claude.exe') -Force
        Mock Get-AppxPackage { $null }
    }
    AfterEach {
        $env:LOCALAPPDATA = $script:savedLocalAppData
    }

    It 'is the old build when it is a live install and no Claude MSIX is registered' {
        Test-ClaudeLegacyExe | Should -BeTrue
    }

    It 'is not, once a Claude MSIX is registered' {
        Mock Get-AppxPackage { [pscustomobject]@{ Name = 'Claude' } }
        Test-ClaudeLegacyExe | Should -BeFalse
    }

    It "is not, when Squirrel has marked it .dead (an uninstall's residue)" {
        $null = New-Item -ItemType File -Path (Join-Path $script:root '.dead') -Force
        Test-ClaudeLegacyExe | Should -BeFalse
    }

    It 'is not, when only Update.exe is left and no app folder holds claude.exe' {
        Remove-Item -Recurse -Force (Join-Path $script:root 'app-0.14.10')
        Test-ClaudeLegacyExe | Should -BeFalse
    }

    It 'is not, when there is no Update.exe at all' {
        Remove-Item -Force (Join-Path $script:root 'Update.exe')
        Test-ClaudeLegacyExe | Should -BeFalse
    }
}
