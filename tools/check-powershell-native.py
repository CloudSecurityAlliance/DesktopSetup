#!/usr/bin/env python3
"""Flag native commands invoked without a stderr guard in scripts that set ErrorActionPreference.

The lesson this encodes, learned the hard way on a colleague's machine:

With `$ErrorActionPreference = 'Stop'`, PowerShell promotes *anything a native command writes to
stderr* into a terminating `NativeCommandError` — even when the command succeeded. `winget`,
`npm`, `gh` and `claude` all write progress and notices to stderr routinely.

And the obvious defence does not work. `2>$null` and `*> $null` suppress the *text*; they do not
prevent the promotion. Nor does assigning the output. The only reliable guards are a `try/catch`
around the call, or a wrapper that sets `$ErrorActionPreference` to `Continue` for the duration —
which is what `Invoke-NativeShow` / `Invoke-NativeOutput` / `Invoke-NativeQuiet` /
`Invoke-NativeCapture` exist for.

That fix was applied to windows-ai-tools.ps1 and, for a while, to nothing else. This check is
here so the next script does not have to rediscover it on a colleague's machine.
"""
from __future__ import annotations

import pathlib
import re
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"
NATIVE = ("winget", "npm", "npx", "node", "gh", "git", "claude", "python", "py", "pipx",
          "choco", "curl")
WRAPPERS = ("Invoke-NativeShow", "Invoke-NativeOutput", "Invoke-NativeQuiet",
            "Invoke-NativeCapture")
# A call is considered guarded if the line invokes it through a wrapper, or the enclosing
# construct is a try/catch. Detecting try/catch precisely needs a parser; instead we look for a
# `try {` within a few lines above, which is how these scripts are actually written.
TRY_WINDOW = 6


def unguarded(path: pathlib.Path) -> list[tuple[int, str]]:
    lines = path.read_text(errors="replace").split("\n")
    if not any(re.search(r"ErrorActionPreference\s*=\s*'Stop'", line) for line in lines):
        return []          # no promotion, no problem

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
        if any(w in line for w in WRAPPERS):
            continue
        if any("try {" in lines[j] or "try{" in lines[j]
               for j in range(max(0, i - TRY_WINDOW), i)):
            continue
        problems.append((i + 1, stripped[:96]))
    return problems


def main() -> int:
    total = 0
    for path in sorted(SCRIPTS.glob("*.ps1")):
        found = unguarded(path)
        available = [w for w in WRAPPERS if f"function {w}" in path.read_text(errors="replace")]
        print(f"{path.name}: {len(found)} unguarded native call(s); "
              f"wrappers defined: {', '.join(available) or 'NONE'}")
        for number, text in found:
            print(f"    {path.name}:{number}: {text}")
        total += len(found)
    print()
    if total:
        print(f"{total} native call(s) can raise NativeCommandError on a successful command.")
        print("Wrap them in Invoke-Native* (or try/catch). `2>$null` does NOT prevent this.")
        return 1
    print("all native calls are guarded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
