#!/usr/bin/env python3
"""On Windows, "shown to the user" and "recorded in the debug log" must be one decision.

macOS has never had this problem: its logger is a process-wide `tee`, so everything the
script prints is captured by construction. Windows has no equivalent — each call site had to
remember to call `Write-CsaLog` — and `Start-Transcript` is not a substitute, because it would
bypass that function's credential redaction.

The cost of the gap, from a real investigation (#96): a log that stopped mid-run was read as a
crash, when the script had carried on for several more steps; and Claude Desktop was judged
absent from a machine because its registration line never reached the file. It was installed.
The prompts were the worst part — `Read-Host` writes straight to the console, so "waiting on a
human" and "hung" looked identical, and a prompt that had lost its value was the actual bug
being hunted.

Three invariants, each the shape of a defect that has already happened:

  1. Every `Write-Info` / `Write-Success` / `Write-Warn` / `Write-Err` body calls
     `Write-CsaLog`. This is the coverage rule.
  2. No `Write-*` helper is CALLED before `Write-CsaLog` is DEFINED. PowerShell resolves at
     call time, so (1) makes the helpers depend on definition order. The same
     CommandNotFoundException -> $null -> wrong branch failure has already cost this fleet a
     release (CSA-Plugins, `Test-CsaInteractive` missing in three of four scripts).
  3. Every `Read-Host` call has a `Write-CsaLog` within the two preceding lines, so the
     question is in the file before the script blocks on it.

Self-tests before it reports, on fixtures it must fail.

    python3 tools/check-log-coverage.py
"""
from __future__ import annotations

import pathlib
import re
import sys

HELPERS = ("Write-Info", "Write-Success", "Write-Warn", "Write-Err")
DEF_LOG = re.compile(r"^function\s+Write-CsaLog\b")
# A call, not the definition and not a mention inside a comment.
CALL = re.compile(r"(?<![-\w])(" + "|".join(HELPERS) + r")\s")
READ_HOST = re.compile(r"(?<![-\w])Read-Host\b")
# A CALL to the logger, not its definition. The first draft of invariant 3 looked for the bare
# string "Write-CsaLog" in the preceding lines, which matched `function Write-CsaLog {` — so a
# Read-Host placed just after that definition would have passed. The self-test caught it, which
# is the entire reason every checker here has one.
LOG_CALL = re.compile(r"(?<![-\w])Write-CsaLog\s")


def _code(line: str) -> str:
    """The line with any trailing comment removed. Crude but sufficient: these scripts do not
    put a '#' inside a string on the lines this checker inspects, and a false negative here is
    safer than a false positive on a comment that merely names a function."""
    return line.split("#", 1)[0]


def offenders(text: str) -> list[str]:
    lines = text.split("\n")
    out: list[str] = []

    log_def_line = next((n for n, l in enumerate(lines, 1) if DEF_LOG.match(l)), None)
    if log_def_line is None:
        return ["no Write-CsaLog definition — nothing in this script can record anything"]

    # 1. coverage: each helper definition logs what it printed
    for helper in HELPERS:
        for n, line in enumerate(lines, 1):
            if re.match(rf"^function\s+{re.escape(helper)}\b", line):
                if "Write-CsaLog" not in line:
                    out.append(f"{n}: {helper} prints without recording — a run of this would "
                               f"show the user something the debug log never mentions")
                break
        else:
            out.append(f"0: {helper} is not defined")

    # 2. ordering: the helpers resolve at call time, so no call may precede the definition
    for n, line in enumerate(lines, 1):
        code = _code(line)
        if n >= log_def_line or re.match(r"^function\s", code):
            continue
        m = CALL.search(code)
        if m:
            out.append(f"{n}: {m.group(1)} is called at line {n}, before Write-CsaLog is "
                       f"defined at {log_def_line} — CommandNotFoundException at run time")

    # 3. prompts: the question must be in the log before Read-Host blocks
    for n, line in enumerate(lines, 1):
        code = _code(line)
        if not READ_HOST.search(code):
            continue
        before = [_code(l) for l in lines[max(0, n - 3):n - 1]]
        if not any(LOG_CALL.search(l) and not l.lstrip().startswith("function")
                   for l in before):
            out.append(f"{n}: Read-Host with no Write-CsaLog in the two lines above — "
                       f"'waiting on a human' will be indistinguishable from 'hung'")
    return out


def self_test() -> None:
    """Each invariant has to be seen to fail."""
    good = (
        "function Write-Info    { param([string]$M) $l = \"==> $M\"; Write-Host $l; Write-CsaLog $l 'screen' }\n"
        "function Write-Success { param([string]$M) Write-Host $M; Write-CsaLog $M 'screen' }\n"
        "function Write-Warn    { param([string]$M) Write-Host $M; Write-CsaLog $M 'screen' }\n"
        "function Write-Err     { param([string]$M) Write-Host $M; Write-CsaLog $M 'screen' }\n"
        "function Write-CsaLog { param($L,$K) }\n"
        "Write-CsaLog 'q' 'prompt'\n"
        "$r = Read-Host 'q'\n"
    )
    assert offenders(good) == [], f"self-test: clean fixture flagged {offenders(good)}"

    # 1. a helper that prints without recording
    bad1 = good.replace(
        "function Write-Warn    { param([string]$M) Write-Host $M; Write-CsaLog $M 'screen' }",
        "function Write-Warn    { param([string]$M) Write-Host $M }")
    assert any("Write-Warn prints without recording" in o for o in offenders(bad1)), "miss 1"

    # 2. a call before the definition
    bad2 = "Write-Info 'early'\n" + good
    assert any("before Write-CsaLog is defined" in o for o in offenders(bad2)), "miss 2"

    # ...but a mention in a COMMENT before the definition is not a call
    ok2 = "# Write-Info is defined below\n" + good
    assert offenders(ok2) == [], f"self-test: a comment was read as a call: {offenders(ok2)}"

    # 3. an unlogged prompt
    bad3 = good.replace("Write-CsaLog 'q' 'prompt'\n", "")
    assert any("Read-Host with no Write-CsaLog" in o for o in offenders(bad3)), "miss 3"

    # a script with no logger at all
    assert offenders("Write-Host 'hi'\n")[0].startswith("no Write-CsaLog"), "miss 4"


def main(argv: list[str]) -> int:
    self_test()
    root = pathlib.Path(__file__).resolve().parent.parent
    files = [pathlib.Path(a) for a in argv[1:]] or sorted((root / "scripts").glob("*.ps1"))
    problems = 0
    for f in files:
        for line in offenders(f.read_text(encoding="utf-8")):
            print(f"{f.name}:{line}")
            problems += 1
    if problems:
        print(f"\n{problems} gap(s) between what a run shows and what its log records. "
              f"The debug log is the tool people reach for when something has already gone "
              f"wrong; it is least useful exactly then if it omits the part they were looking at.")
        return 1
    print(f"screen output and prompts are recorded in all {len(files)} script(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
