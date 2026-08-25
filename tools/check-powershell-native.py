#!/usr/bin/env python3
"""Flag PowerShell constructs that fail on Windows PowerShell 5.1 — the runtime these target.

Two checks, both encoding something that reached a real machine before it reached a test.

**1. Native commands without a stderr guard.**

With `$ErrorActionPreference = 'Stop'`, PowerShell promotes *anything a native command writes to
stderr* into a terminating `NativeCommandError` — even when the command succeeded and exited 0.
`winget`, `npm`, `gh` and `claude` all write progress and notices to stderr routinely.

**No form of redirection prevents this.** Measured on Windows PowerShell 5.1.26100, in the shape
these scripts are actually deployed — `& ([ScriptBlock]::Create(...))` invoked from a `'Stop'`
session, which is how one script runs another here:

    form                                      result
    ----                                      ------
    bare call                                 kills the script AND its caller
    | Out-Null                                kills the script AND its caller
    $x = cmd            (assignment)          kills the script AND its caller
    cmd 2>$null                               kills the script AND its caller
    cmd *> $null                              kills the script AND its caller
    $x = cmd 2>&1 | Out-String                kills the script AND its caller
    any of the above, after EAP = 'Continue'   all six survive

Redirection hides the text, not the termination.

**The trap that makes this hard to believe:** standalone, the same error is only
*statement*-terminating. The script carries on to the next statement, so every form above looks
survivable when you test it in isolation. Inside `& ([ScriptBlock]::Create(...))` the whole
invocation is ONE statement in the caller, so an error that merely ends a statement in the
callee ends the entire call in the caller. Measure it the way it is deployed or not at all.
(This paragraph exists because the note it replaces had the conclusion backwards, twice.)

So the only reliable guards are a `try/catch` around the call, or a wrapper that sets
`$ErrorActionPreference` to `Continue` for the duration — `Invoke-NativeShow` /
`Invoke-NativeOutput` / `Invoke-NativeQuiet` / `Invoke-NativeCapture` here, `Invoke-CsaNative`
in CSA-Plugins. Wrappers are detected by what they DO (a function that sets `Continue`), not by
name, so a new one in a new repo counts without editing this file.

That fix was applied to windows-ai-tools.ps1 and, for a while, to nothing else. This check is
here so the next script does not have to rediscover it on a colleague's machine.

    python3 tools/check-powershell-native.py                       # this repo's scripts/
    python3 tools/check-powershell-native.py path/to/other/*.ps1   # anywhere else
"""
from __future__ import annotations

import pathlib
import re
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
# Windows built-ins belong here too. `icacls` was added after a bare call to it went into
# these scripts unnoticed - it happened to be inside a try/catch, so it was safe, but nothing
# had checked. A native command is a native command whether or not it ships with the OS.
NATIVE = ("winget", "npm", "npx", "node", "gh", "git", "claude", "python", "py", "pipx",
          "choco", "curl", "icacls", "attrib", "reg", "where", "cmd", "powershell", "pwsh",
          "setx", "takeown", "sc", "tasklist", "taskkill")
# Known wrapper names, used when a script CALLS a wrapper it does not define. Files that
# define their own are handled by wrappers_in() below, so a new repo with a differently named
# wrapper needs no edit here.
WRAPPERS = ("Invoke-NativeShow", "Invoke-NativeOutput", "Invoke-NativeQuiet",
            "Invoke-NativeCapture", "Invoke-CsaNative")


def wrappers_in(text: str) -> set[str]:
    """Every function in `text` that sets $ErrorActionPreference to 'Continue'.

    Detecting the guard by behaviour rather than by name is what lets this run against another
    repo unmodified: CSA-Plugins calls its wrapper Invoke-CsaNative, and the next one will call
    it something else again. A function that sets 'Continue' for the duration IS the guard.
    """
    found = set()
    for match in re.finditer(r"^function\s+([\w-]+)\s*\{", text, re.M):
        name, start = match.group(1), match.end()
        depth, i = 1, start
        while i < len(text) and depth:                 # brace-match to the function's end
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        if re.search(r"ErrorActionPreference\s*=\s*'Continue'", text[start:i]):
            found.add(name)
    return found
def _match_brace(text: str, open_at: int) -> int:
    """Index just past the `}` closing the `{` at `open_at`."""
    depth, i = 0, open_at
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def guarded_lines(text: str) -> set[int]:
    """Line numbers inside a `try { ... }`, or inside a Continue-setting wrapper.

    This used to be "is there a `try {` within 6 lines above?", which is wrong in the one way
    that matters: every script here defines its wrapper near the top, and that wrapper contains
    a `try {`. So the six lines following it were exempted wholesale - and a probe file with
    three plainly unguarded calls sitting there was reported as "all native calls are guarded".
    A heuristic that silently exempts the region where the problems cluster is worse than no
    check, because it prints a clean bill of health.

    Brace-matching instead. Calls inside a wrapper's own body are guarded too, by the same
    'Continue' the wrapper exists to set.
    """
    safe: set[int] = set()
    for match in re.finditer(r"\btry\s*\{", text):
        open_at = text.index("{", match.start())
        end = _match_brace(text, open_at)
        safe.update(range(_line_of(text, open_at), _line_of(text, end) + 1))
    for match in re.finditer(r"^function\s+([\w-]+)\s*\{", text, re.M):
        open_at = text.index("{", match.start())
        end = _match_brace(text, open_at)
        if re.search(r"ErrorActionPreference\s*=\s*'Continue'", text[open_at:end]):
            safe.update(range(_line_of(text, open_at), _line_of(text, end) + 1))
    return safe


def posture(text: str) -> str:
    """How this file stands relative to the promotion: 'continue', 'stop', or 'unset'.

    Reported rather than folded into a count, because "0 unguarded calls" means two very
    different things. A file that sets 'Continue' for itself is safe wholesale - the assignment
    is script-scoped and measured to make all six redirection forms survive, which is how the
    CSA-Plugins installer is written. A file with no preference at all is safe only until
    something invokes it from a 'Stop' session. Collapsing both to "0" hides the second.
    """
    # Column 0, deliberately: an indented 'Continue' is a WRAPPER setting it for the duration
    # of one call, which says nothing about the script as a whole. Allowing leading whitespace
    # here made every file in this repo report "script-wide 'Continue'", because each defines
    # such a wrapper - i.e. it turned the check off everywhere while still printing a clean
    # bill of health. A top-level assignment in these scripts is unindented.
    if re.search(r"^\$ErrorActionPreference\s*=\s*'Continue'", text, re.M):
        return "continue"
    if re.search(r"ErrorActionPreference\s*=\s*'Stop'", text):
        return "stop"
    return "unset"


def unguarded(path: pathlib.Path) -> list[tuple[int, str]]:
    text = path.read_text(errors="replace")
    lines = text.split("\n")
    if posture(text) != "stop":
        return []          # no promotion to guard against, for the reasons in posture()

    guards = set(WRAPPERS) | wrappers_in(text)
    safe = guarded_lines(text)

    problems = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Does this line start a native command? The optional prefix is an *assignment*
        # specifically — an earlier version used `\$?\w*\s*=?\s*` here, whose `\w*` swallowed
        # the command name itself and captured the first argument instead. That made the
        # check blind to bare unassigned calls like `winget install …`, which are precisely
        # the ones most likely to write to stderr.
        first = re.match(r"^(?:\$\w+\s*=\s*)?([A-Za-z][\w.-]*)", stripped)
        if not first or first.group(1) not in NATIVE:
            continue
        if any(w in line for w in guards):
            continue
        if (i + 1) in safe:
            continue
        problems.append((i + 1, stripped[:96]))
    return problems


# Cmdlet forms that do not exist in Windows PowerShell 5.1. PSScriptAnalyzer does not catch
# these: PSUseCompatibleCmdlets checks whether a cmdlet *exists*, not whether a parameter set
# does, and PSUseCompatibleSyntax checks language syntax rather than cmdlet binding. Both were
# tried on the known-bad line and reported nothing.
INCOMPATIBLE = [
    (re.compile(r"\bJoin-Path\s+(?:[^\s|;()]+\s+){2,}[^\s|;()]+"),
     "Join-Path with three or more paths needs -AdditionalChildPath (PowerShell 6+). "
     "On 5.1: \"a positional parameter cannot be found\". Nest the calls instead."),
]


def incompatible(path: pathlib.Path) -> list[tuple[int, str, str]]:
    found = []
    for i, line in enumerate(path.read_text(errors="replace").split("\n"), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for pattern, why in INCOMPATIBLE:
            if pattern.search(stripped):
                found.append((i, stripped[:88], why))
    return found


def targets(argv: list[str]) -> list[pathlib.Path]:
    """Files to scan: whatever is named, else this repo's scripts/.

    Taking paths is what lets one copy of this check cover other repos - the CSA-Plugins
    installer, in particular, which is a PowerShell script fetched and run by these scripts
    and was for a while the only place nothing checked. A copy of the file there would have
    been a second thing to keep in sync, which is the problem this repo already has a checker
    for.
    """
    if not argv:
        return sorted(SCRIPTS.glob("*.ps1"))
    paths: list[pathlib.Path] = []
    for arg in argv:
        p = pathlib.Path(arg)
        paths.extend(sorted(p.glob("*.ps1")) if p.is_dir() else [p])
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print(f"no such file: {', '.join(missing)}")
        return []
    return paths


# A file that this check MUST fail on. Its whole purpose is to answer "can this check still
# fail?", which is not rhetorical: two separate mistakes here - a `\w*` that swallowed the
# command name, and a six-line try/catch window that exempted the region where the wrappers
# (and therefore the problems) live - each turned the check into one that printed "all native
# calls are guarded" no matter what was in front of it. A clean bill of health from a check
# that cannot fail is worse than no check, because it is believed.
#
# Inline rather than a fixture file, so there is nothing to drift and nothing to forget to ship.
SELF_TEST = """$ErrorActionPreference = 'Stop'
function Invoke-NativeQuiet {
    param([scriptblock]$Call)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Call | Out-Null; return $LASTEXITCODE } finally { $ErrorActionPreference = $prev }
}
winget install --id Foo.Bar
npm install -g something 2>$null
$v = gh api user --jq '.login'
Invoke-NativeQuiet { claude mcp list }
try { git pull --ff-only } catch { }
$p = Join-Path $HOME "a" "b"
"""
SELF_TEST_EXPECT_UNGUARDED = {8, 9, 10}     # bare, redirected, assigned
SELF_TEST_EXPECT_INCOMPAT = {13}            # three-argument Join-Path


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d) / "self-test.ps1"
        path.write_text(SELF_TEST)
        found = {line for line, _ in unguarded(path)}
        incompat = {line for line, _, _ in incompatible(path)}

    problems = []
    if found != SELF_TEST_EXPECT_UNGUARDED:
        problems.append(f"unguarded: expected lines {sorted(SELF_TEST_EXPECT_UNGUARDED)}, "
                        f"got {sorted(found)}")
    if incompat != SELF_TEST_EXPECT_INCOMPAT:
        problems.append(f"incompatible: expected lines {sorted(SELF_TEST_EXPECT_INCOMPAT)}, "
                        f"got {sorted(incompat)}")
    if problems:
        print("SELF-TEST FAILED - this check can no longer be trusted:")
        for problem in problems:
            print(f"  {problem}")
        print("  A miss here means real problems are being reported as 'all guarded'.")
        return 1
    print("self-test: catches the bare call, the redirected call, the assignment, and the "
          "three-arg Join-Path; exempts the wrapper body and the try/catch.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-test" in argv:
        return self_test()
    paths = targets(argv)
    if not paths:
        return 1
    if self_test():                 # never report on real files with a broken checker
        return 1
    total = 0
    for path in paths:
        found = unguarded(path)
        text = path.read_text(errors="replace")
        available = sorted(wrappers_in(text))
        stance = {"continue": "script-wide 'Continue' - no per-call guard needed",
                  "stop": f"wrappers defined: {', '.join(available) or 'NONE'}",
                  "unset": "no ErrorActionPreference set - safe only while nothing "
                           "invokes it from a 'Stop' session"}[posture(text)]
        print(f"{path.name}: {len(found)} unguarded native call(s); {stance}")
        for number, text in found:
            print(f"    {path.name}:{number}: {text}")
        total += len(found)
    print()
    incompat = 0
    for path in paths:
        for number, text, why in incompatible(path):
            print(f"    {path.name}:{number}: {text}\n        {why}")
            incompat += 1

    if total:
        print(f"{total} native call(s) can raise NativeCommandError on a successful command.")
        print("Wrap them in a Continue-setting wrapper, or try/catch. NO redirection helps:")
        print("`2>$null`, `*> $null`, `2>&1`, `| Out-Null` and a bare call all terminate.")
    else:
        print("all native calls are guarded.")
    if incompat:
        print(f"{incompat} construct(s) fail on Windows PowerShell 5.1.")
    elif not total:
        print("no 5.1 incompatibilities found.")
    return 1 if (total or incompat) else 0


if __name__ == "__main__":
    sys.exit(main())
