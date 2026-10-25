# Pester tests for windows-update.ps1's wait before `winget upgrade --all` replaces a running
# desktop AI app (Claude, ChatGPT, Gemini, Copilot).
#
# What this proves, and what it does not. It locks down the DECISIONS, which are pure logic and
# testable on any runtime: which processes count as the app (by image path, in this user's
# session only - the session-0 services Claude and Copilot run would make a wait endless), that
# winget is asked about running apps only, that nobody-at-the-keyboard means no wait, and that
# an interactive wait can always be left. It does NOT prove the path patterns match what these
# apps really run from on Windows, or that `winget list --upgrade-available` answers the way it
# is parsed here. Nothing has measured those yet: #161.
#
# The same discipline as NativeWrappers.Tests.ps1: functions are loaded out of the shipping
# script through PowerShell's own parser, never copied, so the tests cannot drift from it.

BeforeAll {
    $script:source = "$PSScriptRoot/../scripts/windows-update.ps1"
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $script:source, [ref]$null, [ref]$errors)
    if ($errors) { throw "cannot parse $($script:source): $($errors.Count) error(s)" }

    # The table of apps is data, not a function: evaluate its right-hand side as written.
    $assignment = $ast.Find({
        param($node)
        $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -eq '$DesktopApps'
    }, $false)
    if (-not $assignment) { throw 'cannot find $DesktopApps in windows-update.ps1' }
    $script:DesktopApps = @(& ([scriptblock]::Create($assignment.Right.Extent.Text)))

    # Roots, and the transitive closure of script-defined functions they call - the loader
    # NativeWrappers.Tests.ps1 uses, for the reason it gives (#132).
    $roots = 'Get-RunningDesktopApps', 'Test-DesktopAppRunning', 'Test-WingetUpgradePending',
             'Get-DesktopAppsAwaitingClose', 'Wait-ForAppExit'
    $definitions = $ast.FindAll(
        { $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
    $byName = @{}
    foreach ($definition in $definitions) { $byName[$definition.Name] = $definition }
    $needed = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    $queue = New-Object System.Collections.Queue
    foreach ($r in $roots) {
        if (-not $byName.ContainsKey($r)) { throw "windows-update.ps1 does not define $r" }
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
    foreach ($definition in $definitions) {
        if ($needed.Contains($definition.Name)) {
            . ([scriptblock]::Create($definition.Extent.Text))
        }
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

Describe 'which processes count as a desktop app' {
    BeforeEach {
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
}

Describe 'which running apps winget is about to replace' {
    It 'asks winget only about apps that are running, and keeps those with an update waiting' {
        $claude = $script:DesktopApps | Where-Object { $_.Name -eq 'Claude Desktop' }
        $gemini = $script:DesktopApps | Where-Object { $_.Name -eq 'Gemini Desktop' }
        Mock Get-RunningDesktopApps { @($claude, $gemini) }
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
}
