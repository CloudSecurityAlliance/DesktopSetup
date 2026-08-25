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
    $script:source = Join-Path $PSScriptRoot '..' 'scripts' 'windows-ai-tools.ps1'
    $text = Get-Content $script:source -Raw
    foreach ($name in 'Invoke-NativeQuiet','Invoke-NativeOutput','Invoke-NativeShow','Invoke-NativeCapture') {
        $m = [regex]::Match($text, "(?m)^function $name \{")
        $depth = 0; $i = $m.Index + $m.Length - 1
        while ($i -lt $text.Length) {
            if ($text[$i] -eq '{') { $depth++ }
            elseif ($text[$i] -eq '}') { $depth--; if ($depth -eq 0) { break } }
            $i++
        }
        . ([scriptblock]::Create($text.Substring($m.Index, $i - $m.Index + 1)))
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
        $r = Invoke-NativeCapture { sh -c 'echo "Logged in to github.com" >&2; exit 0' }
        $r.ExitCode | Should -Be 0
        $r.Output | Should -Match 'Logged in'
    }
}

Describe 'Invoke-NativeQuiet' {
    It 'returns the exit code and prints nothing' {
        $out = Invoke-NativeQuiet { sh -c 'echo noisy; echo noisier >&2; exit 0' } 6>&1
        $out | Should -Be 0
    }
}
