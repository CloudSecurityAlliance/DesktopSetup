# Pester tests for Confirm-Step, the consent prompt of the four Windows entry scripts.
#
# End of input is not consent. Read-Host returns $null when its input closes (measured on pwsh
# 7.6: a redirected stdin at end of file; Windows PowerShell 5.1 is not measured here). Each
# Confirm-Step answers that no, and logs it as a closed input, never as an empty answer. Its bash
# twin, confirm(), once took end of input for the empty reply's default, yes, and a run went on to
# re-point a config (the review of f18337c, M2); tests/test_headless.py holds the bash side.
#
# The function is loaded out of each shipping script through PowerShell's own parser, never copied
# (the discipline of NativeWrappers.Tests.ps1). The last case is a control: a Confirm-Step that
# turns $null into '' must be seen to answer yes, so the first case is able to fail.

BeforeDiscovery {
    $script:Files = @(
        @{ File = 'windows-ai-tools.ps1' }
        @{ File = 'windows-update.ps1' }
        @{ File = 'windows-plugins.ps1' }
        @{ File = 'windows-work-tools.ps1' }
    )
}

Describe 'Confirm-Step in <File>' -ForEach $Files {
    BeforeAll {
        $path = Join-Path $PSScriptRoot "../scripts/$File"
        $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$null, [ref]$errors)
        if ($errors) { throw "cannot parse ${path}: $($errors.Count) error(s)" }
        $definition = $ast.Find({
            param($node)
            $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq 'Confirm-Step'
        }, $true)
        if (-not $definition) { throw "$path does not define Confirm-Step" }
        $script:ConfirmText = $definition.Extent.Text
        . ([scriptblock]::Create($script:ConfirmText))
        function Write-CsaLog { param($Line, $Kind) $script:Logged += , [string]$Line }
    }

    BeforeEach {
        $script:Logged = @()
        $script:SavedNonInteractive = $env:NONINTERACTIVE
        $env:NONINTERACTIVE = $null
    }

    AfterEach {
        $env:NONINTERACTIVE = $script:SavedNonInteractive
    }

    It 'answers no at end of input, and logs it as a closed input' {
        Mock Read-Host { return $null }
        Confirm-Step 'Proceed?' | Should -BeFalse
        $script:Logged | Should -Contain 'no answer: input closed -> no'
    }

    It 'answers yes to Enter alone, the default' {
        Mock Read-Host { return '' }
        Confirm-Step 'Proceed?' | Should -BeTrue
    }

    It 'answers no to n, and yes to y' {
        Mock Read-Host { return 'n' }
        Confirm-Step 'Proceed?' | Should -BeFalse
        Mock Read-Host { return 'y' }
        Confirm-Step 'Proceed?' | Should -BeTrue
    }

    It 'control: one that turns end of input into an empty reply answers yes, so the first case can fail' {
        $from = '$reply = Read-Host $question'
        $script:ConfirmText.Contains($from) | Should -BeTrue
        $mutant = $script:ConfirmText.Replace($from, '$reply = [string](Read-Host $question)').Replace(
            'function Confirm-Step', 'function Confirm-StepMutant')
        . ([scriptblock]::Create($mutant))
        Mock Read-Host { return $null }
        Confirm-StepMutant 'Proceed?' | Should -BeTrue
    }
}
