#!/usr/bin/env python3
"""Fail if README.md tells a Windows reader to paste more than one line at a time.

Copying a two-line PowerShell block out of the README and pasting it into the console has been
observed to close the window immediately, before either line ran — reported from a real machine,
on the debug-mode instructions. Whatever the mechanism (PSReadLine's handling of a bracketed
paste is the usual suspect), the fix does not depend on knowing it: a `powershell` block in the
README is something a person will select, copy and paste in one go, so each one must be a single
command.

`;` joins two statements on one line and pastes safely. The README already used that form for
`CSA_REPO` long before this check existed, so the house style was already right — in one place.

Only README.md is checked. CLAUDE.md's PowerShell block is a *reference list* of the different
entry points, one per scenario, read by agents rather than pasted wholesale by a person at a
prompt; requiring it to be one line per block would split a table for no benefit.

    python3 tools/check-paste-safety.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "README.md"


def offenders(text: str) -> list[tuple[int, list[str]]]:
    found = []
    for match in re.finditer(r"```powershell\n(.*?)```", text, re.S):
        # Comment-only lines are not commands and cannot be what crashes: a block that is one
        # command plus an explanatory `#` line above it is still a single paste.
        lines = [line for line in match.group(1).rstrip("\n").split("\n")
                 if line.strip() and not line.strip().startswith("#")]
        if len(lines) > 1:
            found.append((text.count("\n", 0, match.start()) + 1, lines))
    return found


def main() -> int:
    if not TARGET.is_file():
        print(f"no such file: {TARGET}")
        return 1
    found = offenders(TARGET.read_text())
    for line, lines in found:
        print(f"    README.md:{line}: a powershell block with {len(lines)} commands")
        for text in lines:
            print(f"        {text[:100]}")
    if found:
        print(f"{len(found)} block(s) ask the reader to paste several lines at once.")
        print("Split them into one block per command, or join them with `;` on a single line.")
        return 1
    print("every powershell block in README.md is a single command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
