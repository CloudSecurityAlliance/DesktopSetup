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

    $wanted = 'Invoke-NativeQuiet', 'Invoke-NativeOutput', 'Invoke-NativeShow',
              'Invoke-NativeCapture'
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
