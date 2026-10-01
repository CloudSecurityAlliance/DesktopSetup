#!/usr/bin/env python3
r"""No CR may reach the index of a file this repo serves to a shell.

What this repo ships is `curl -fsSL … | bash` and `irm … | iex`, and
raw.githubusercontent.com serves the **index**, not anyone's working tree. A CR in the index
of a `.sh` therefore means a colleague running the documented one-liner on a brand-new machine
gets

    bash: line 2: $'\r': command not found

on a script they were told to pipe straight into a shell, with no checkout to inspect and no
obvious cause. `.gitattributes` now pins this, and `.gitattributes` is a file somebody can
edit — so this is the check that the pinning actually took effect (#66).

Why the index and not the working tree: `text eol=crlf` deliberately gives `.ps1` CRLF on
disk, and that is correct. Checking the working tree would flag it. The only thing that
matters is what gets served, which is the `i/` column of `git ls-files --eol`.

**The format is not what it looks like.** Observed with `cat -A`, 2026-10-01:

    i/lf    w/crlf  attr/text eol=lf      ^Iscripts/macos-ai-tools.sh$

The first three fields are *space-padded*, the path is preceded by a single **tab**, and the
`attr/` value itself contains a space. The first draft of this checker split the line on
"\t", which put all three fields into `fields[0]` — so `i/lf    w/crlf  attr/text eol=lf` was
read as the index value, matched nothing, and the checker reported all 44 served files as
broken. Its self-test missed that because the fixture was written with tabs: it tested the
assumption rather than the output. The fixture below is now real output.

Self-tests before it reports, on output it must reject and output it must accept: a checker
that cannot see a bad entry would print "all clear" for ever and be believed.

    python3 tools/check-line-endings.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

# Served to an interpreter that treats a CR as part of a token. `.ps1` is absent on purpose:
# PowerShell accepts either, and these are pinned to CRLF in the working tree.
MUST_BE_LF = (".sh", ".py", ".txt", ".yml", ".yaml", ".json", ".md")

# `none` is what an empty file reports — no line endings at all is not a CR.
OK_INDEX = {"lf", "none"}

INDEX_EOL = re.compile(r"^i/(\S*)")

# Real `git ls-files --eol` output, including the tab before each path and the space inside
# the attr value. Two rows are deliberately unbroken .ps1 files, one is an empty file, and one
# path contains a space.
SELF_TEST = (
    "i/lf    w/lf    attr/text eol=lf      \tscripts/good.sh\n"
    "i/crlf  w/crlf  attr/text=auto        \tscripts/bad.sh\n"
    "i/mixed w/crlf  attr/text=auto        \ttools/ugly.py\n"
    "i/none  w/none  attr/                 \tscripts/empty.sh\n"
    "i/lf    w/crlf  attr/text eol=crlf    \tscripts/fine.ps1\n"
    "i/crlf  w/crlf  attr/text eol=crlf    \tscripts/also-fine.ps1\n"
    "i/crlf  w/crlf  attr/text=auto        \tdocs/a path with spaces.md\n"
)


def _path_of(line: str) -> str | None:
    """The path is whatever follows the last tab. Nothing else in the line is reliable."""
    if "\t" not in line:
        return None
    return line.rsplit("\t", 1)[1].strip()


def offenders(ls_files_eol: str) -> list[tuple[str, str]]:
    """Return (path, index_eol) for every served file whose index holds a CR."""
    out = []
    for line in ls_files_eol.splitlines():
        path = _path_of(line)
        if not path or not path.endswith(MUST_BE_LF):
            continue
        m = INDEX_EOL.match(line)
        if not m:
            continue
        value = m.group(1)
        if value not in OK_INDEX:
            out.append((path, value))
    return out


def self_test() -> None:
    """The check has to be seen to fail, or its passing means nothing."""
    found = offenders(SELF_TEST)
    paths = sorted(p for p, _ in found)
    assert paths == ["docs/a path with spaces.md", "scripts/bad.sh", "tools/ugly.py"], \
        f"self-test: flagged {paths}"
    assert dict(found)["scripts/bad.sh"] == "crlf", f"self-test: wrong value {found}"
    # CRLF on disk is allowed for .ps1 and must not be flagged. Checking `i/` rather than
    # `w/` is the whole reason that holds.
    assert not any(p.endswith(".ps1") for p, _ in found), "self-test: flagged a .ps1"
    # i/none is an empty file: the absence of line endings is not a CR.
    assert "scripts/empty.sh" not in paths, "self-test: flagged an empty file"
    # The defect that shipped: a line whose attr value contains a space must still parse.
    assert offenders("i/crlf  w/crlf  attr/text eol=lf  \tx.sh") == [("x.sh", "crlf")], \
        "self-test: attr value containing a space broke the parse"
    # And a clean line must produce nothing, or the checker is flagging everything.
    assert offenders("i/lf    w/lf    attr/text eol=lf  \tx.sh") == [], \
        "self-test: flagged a clean entry"


def main(argv: list[str]) -> int:
    self_test()
    root = pathlib.Path(__file__).resolve().parent.parent
    try:
        # encoding="utf-8", not text=True: text=True decodes with the locale encoding,
        # which is cp1252 on a Windows dev box, so a non-ASCII path would crash the check
        # locally while passing in CI.
        proc = subprocess.run(["git", "ls-files", "--eol"], cwd=root, capture_output=True,
                              encoding="utf-8", errors="replace", check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        # 77, not 1: "could not run here" is not "passed". check-all.sh counts these
        # separately for exactly this reason.
        print(f"could not read the index ({exc}) — skipping")
        return 77

    bad = offenders(proc.stdout)
    if bad:
        for path, value in bad:
            print(f"{path}: index holds {value}, must be lf — the index is what "
                  f"raw.githubusercontent.com serves")
        print(f"\n{len(bad)} file(s) would be served with a CR. Fix with:\n"
              f"    git add --renormalize .\n"
              f"and check .gitattributes still pins the extension.")
        return 1

    served = sum(1 for line in proc.stdout.splitlines()
                 if (p := _path_of(line)) and p.endswith(MUST_BE_LF))
    print(f"no CR in the index of {served} served file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
