# Pester tests for the Invoke-Native* wrappers.
#
# READ THIS BEFORE CONCLUDING THE WRAPPERS ARE UNNECESSARY.
#
# These tests run on pwsh 7 (macOS/Linux/CI). They CANNOT reproduce the bug the wrappers
# exist for, because pwsh 7 and Windows PowerShell 5.1 treat native stderr fundamentally
# differently — measured, not assumed:
#
#                                    stderr on success   non-zero exit
#   Windows PowerShell 5.1                TERMINATES        terminates
#   pwsh 7, $PSNativeCommandUseErrorActionPreference=$false   survives    survives
#   pwsh 7, $PSNativeCommandUseErrorActionPreference=$true    survives    terminates
#
# In 5.1, *stderr output* is promoted to a terminating NativeCommandError under
# $ErrorActionPreference='Stop', whatever the exit code. In pwsh 7 that is not an error
# condition under any setting; the flag only makes a non-zero *exit code* respect the
# preference. So the trigger does not exist here.
#
# What these tests do lock down is the wrappers' contract — return values, exit-code
# preservation, and that they restore $ErrorActionPreference. Those are the parts a refactor
# is likely to break, and they are testable everywhere.

BeforeAll {
    # Load the wrapper definitions out of the real script, so the tests cannot drift from it.
    #
    # Uses PowerShell's own parser rather than hand-rolled brace matching. The first version
    # walked the text counting braces, and it aborted the entire run under Windows PowerShell
    # 5.1 — every test failing with "a 'break' or 'continue' statement … escaped from your
    # code" (Pester #2669) — while passing on pwsh 7. The AST has no loop to escape from, is
    # available on both runtimes, and cannot mis-parse a brace inside a string or comment,
    # which the text walker could.
    # Not `Join-Path a b c d` — that form needs -AdditionalChildPath, which arrived in
    # PowerShell 6. Under Windows PowerShell 5.1 it fails with "a positional parameter cannot
    # be found that accepts argument 'scripts'". Forward slashes are fine on Windows.
    $script:source = "$PSScriptRoot/../scripts/windows-ai-tools.ps1"
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $script:source, [ref]$null, [ref]$errors)
    if ($errors) { throw "cannot parse $($script:source): $($errors.Count) error(s)" }

    # Write-CsaLog / Write-CsaNativeLog are what the wrappers call to record a command in the
    # CSA_DEBUG log. They have to be loaded too, or every wrapper test fails with
    # CommandNotFoundException - which is how this list was found to be incomplete.
    #
    # $CsaLog is deliberately left unset, so those two return immediately: these tests are
    # about the wrappers' contract, and asserting it holds with logging OFF is asserting it
    # for the path every normal run takes.
    $wanted = 'Invoke-NativeQuiet', 'Invoke-NativeOutput', 'Invoke-NativeShow',
              'Invoke-NativeCapture', 'Write-CsaLog', 'Write-CsaNativeLog',
              'Expand-CsaCommandText'
    $definitions = $ast.FindAll(
        { $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
    foreach ($definition in $definitions) {
        if ($wanted -contains $definition.Name) {
            . ([scriptblock]::Create($definition.Extent.Text))
        }
    }
}

Describe 'the wrappers are defined in the script under test' {
    It 'defines all four' {
        foreach ($n in 'Invoke-NativeQuiet','Invoke-NativeOutput','Invoke-NativeShow','Invoke-NativeCapture') {
            Get-Command $n -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
        }
    }

    It 'loads the logging helpers the wrappers depend on' {
        # Not decoration: the wrappers call Write-CsaNativeLog unconditionally, so if this
        # list ever falls behind again, every other test in this file fails with
        # CommandNotFoundException and the reason is three screens up. This one names it.
        foreach ($n in 'Write-CsaLog','Write-CsaNativeLog') {
            Get-Command $n -ErrorAction SilentlyContinue | Should -Not -BeNullOrEmpty
        }
    }
}

Describe 'logging does not change what a wrapper returns' {
    # The wrappers take a different code path when $CsaLog is set (they capture output in
    # order to write it down). The contract must not depend on which path ran.
    It 'Invoke-NativeCapture reports the same exit code either way' {
        $script:CsaLog = $null
        $off = Invoke-NativeCapture { & sh -c 'echo out; echo err 1>&2; exit 7' }
        $script:CsaLog = (Join-Path ([IO.Path]::GetTempPath()) ("csa-test-{0}.log" -f [guid]::NewGuid()))
        try {
            $on = Invoke-NativeCapture { & sh -c 'echo out; echo err 1>&2; exit 7' }
        } finally {
            Remove-Item $script:CsaLog -ErrorAction SilentlyContinue
            $script:CsaLog = $null
        }
        $on.ExitCode | Should -Be $off.ExitCode
        $on.ExitCode | Should -Be 7
    }

    It 'Invoke-NativeQuiet reports the same exit code either way' {
        $script:CsaLog = $null
        $off = Invoke-NativeQuiet { & sh -c 'echo chatty 1>&2; exit 3' }
        $script:CsaLog = (Join-Path ([IO.Path]::GetTempPath()) ("csa-test-{0}.log" -f [guid]::NewGuid()))
        try {
            $on = Invoke-NativeQuiet { & sh -c 'echo chatty 1>&2; exit 3' }
        } finally {
            Remove-Item $script:CsaLog -ErrorAction SilentlyContinue
            $script:CsaLog = $null
        }
        $on | Should -Be $off
        $on | Should -Be 3
    }
}

Describe 'Invoke-NativeOutput' {
    It 'returns stdout when the command succeeds' {
        Invoke-NativeOutput { sh -c 'echo hello' } | Should -Be 'hello'
    }
    It 'returns stdout even when the command also writes to stderr' {
        Invoke-NativeOutput { sh -c 'echo hello; echo noise >&2' } | Should -Be 'hello'
    }
    It 'returns $null on a non-zero exit rather than partial output' {
        # The point of the null: callers test `if ($x -and ...)`, so a failed probe must not
        # look like a successful one that happened to print something.
        Invoke-NativeOutput { sh -c 'echo partial; exit 1' } | Should -BeNullOrEmpty
    }
}

Describe 'Invoke-NativeShow' {
    It 'returns the exit code' {
        Invoke-NativeShow { sh -c 'exit 0' } | Should -Be 0
        Invoke-NativeShow { sh -c 'exit 7' } | Should -Be 7
    }
    It 'leaves $LASTEXITCODE readable by the caller' {
        # Callers rely on this: they run `$null = Invoke-NativeShow {...}` and then test
        # `if ($LASTEXITCODE -ne 0)`. If the wrapper clobbered it, every one of those
        # checks would silently pass.
        $null = Invoke-NativeShow { sh -c 'exit 9' }
        $LASTEXITCODE | Should -Be 9
    }
    It 'restores $ErrorActionPreference afterwards' {
        $ErrorActionPreference = 'Stop'
        $null = Invoke-NativeShow { sh -c 'exit 0' }
        $ErrorActionPreference | Should -Be 'Stop'
    }
    It 'restores $ErrorActionPreference even when the call throws' {
        $ErrorActionPreference = 'Stop'
        $null = Invoke-NativeShow { throw 'boom' }
        $ErrorActionPreference | Should -Be 'Stop'
    }
    It 'returns 1 rather than propagating an exception' {
        Invoke-NativeShow { throw 'boom' } | Should -Be 1
    }
}

Describe 'Invoke-NativeCapture' {
    It 'merges stdout and stderr into Output' {
        $r = Invoke-NativeCapture { sh -c 'echo out; echo err >&2' }
        $r.Output | Should -Match 'out'
        $r.Output | Should -Match 'err'
    }
    It 'reports the exit code' {
        (Invoke-NativeCapture { sh -c 'exit 4' }).ExitCode | Should -Be 4
    }
    It 'is what `gh auth status` needs, since that writes its normal output to stderr' {
        # Single-word output, no nested quotes. Windows PowerShell 5.1 does not pass quotes
        # *inside* a native argument the way pwsh 7 does, so `sh -c 'echo "a b" >&2'` arrives
        # truncated at the first space — this assertion failed with "expected 'Logged in' to
        # match 'Logged'" until the quoting was removed. The behaviour under test is that
        # stderr-only output is captured at all, which needs no spaces to demonstrate.
        $r = Invoke-NativeCapture { sh -c 'echo LoggedIn >&2; exit 0' }
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match 'LoggedIn'
    }
}

Describe 'Invoke-NativeQuiet' {
    It 'returns the exit code and prints nothing' {
        $out = Invoke-NativeQuiet { sh -c 'echo noisy; echo noisier >&2; exit 0' } 6>&1
        $out | Should -Be 0
    }
}

Describe 'Expand-CsaCommandText' {
    # It annotates rather than substitutes, and these tests are mostly about the cases where it
    # must stay QUIET. Substituting values into the command text was tried first and produced
    # log lines that misrepresented what ran - `--id @{Id=Git.Git}.Id`, `echo r()`, and an empty
    # `echo ` for an undefined variable. A log that says the wrong thing is worse than one that
    # says a vague thing, so every case below that cannot be resolved cleanly is left bare.

    BeforeAll {
        $script:pkg  = [pscustomobject]@{ Id = 'Git.Git' }
        $script:repo = 'CloudSecurityAlliance-Internal/CSA-Plugins'
        $script:py   = '/usr/bin/python3'
        $script:deep = [pscustomobject]@{ a = [pscustomobject]@{ b = 'nested' } }
        $script:tbl  = @{ x = 1 }
        $script:long = 'x' * 200
        $script:sideEffects = 0
        function script:Boom { $script:sideEffects++; 'BOOM' }
    }

    It 'leaves a command with no variables alone' {
        Expand-CsaCommandText { winget list --exact --id AgileBits.1Password } |
            Should -Be 'winget list --exact --id AgileBits.1Password'
    }

    It 'annotates a plain variable' {
        # The case that matters most, and the one that silently did not work: `1..($n - 1)` is
        # {1,0} in PowerShell for a single-element path, not empty, so a bare $py resolved to
        # nothing and was dropped.
        Expand-CsaCommandText { & $py -c 'import x' } | Should -Be "& `$py -c 'import x'  [py=/usr/bin/python3]"
    }

    It 'annotates a variable used inside a string' {
        Expand-CsaCommandText { gh api "repos/$repo" } |
            Should -Be 'gh api "repos/$repo"  [repo=CloudSecurityAlliance-Internal/CSA-Plugins]'
    }

    It 'annotates a property, and a nested property chain' {
        Expand-CsaCommandText { winget list --id $pkg.Id } | Should -Match '\[pkg\.Id=Git\.Git\]$'
        Expand-CsaCommandText { echo $deep.a.b }           | Should -Match '\[deep\.a\.b=nested\]$'
    }

    It 'names each variable once, however often it appears' {
        Expand-CsaCommandText { echo $py $py } | Should -Be 'echo $py $py  [py=/usr/bin/python3]'
    }

    It 'lists several different variables' {
        Expand-CsaCommandText { echo $py $pkg.Id } |
            Should -Be 'echo $py $pkg.Id  [py=/usr/bin/python3; pkg.Id=Git.Git]'
    }

    It 'says nothing about a method call, and does not invoke it' {
        Expand-CsaCommandText { echo $pkg.Id.ToUpper() } | Should -Be 'echo $pkg.Id.ToUpper()'
    }

    It 'does not evaluate a subexpression' {
        # The important one. ExpandString would have RUN Boom to produce a log line.
        Expand-CsaCommandText { echo "$(Boom)" } | Should -Be 'echo "$(Boom)"'
        $script:sideEffects | Should -Be 0
    }

    It 'says nothing about an undefined variable, rather than rendering it empty' {
        Expand-CsaCommandText { echo $doesNotExist.Thing } | Should -Be 'echo $doesNotExist.Thing'
    }

    It 'skips a collection and an over-long value, which are noise on a command line' {
        Expand-CsaCommandText { echo $tbl }  | Should -Be 'echo $tbl'
        Expand-CsaCommandText { echo $long } | Should -Be 'echo $long'
    }
}
