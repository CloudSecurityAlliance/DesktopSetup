#!/usr/bin/env python3
"""The closing summary must report pip THROUGH the Python it names, not beside it.

The report this exists for (issue #100), from a macOS debug run. Two adjacent lines of one
summary:

    Python ............ Python 3.13.1
    pip ............... pip 26.2.1 from /opt/homebrew/lib/python3.14/site-packages/pip (python 3.14)

Read together those say "your Python is 3.13.1 and its pip is 26.2.1". They are two different
installations. `python3` resolved to a venv at ~/.default_venv; `pip3` resolved to Homebrew's
3.14 site-packages. Each row probed PATH on its own, so nothing tied them together, and the one
person this summary exists for - somebody working out why a `pip install` did not show up for
the Python they are running - is told the opposite of the truth.

Windows had the other half of the same defect, and it was invisible: **no pip row at all**, plus
a bare `python` that is the one candidate `Find-UsablePython` refuses outright when a Store
alias is present. So Windows could name an interpreter the installer had declined to use, and
could not answer "is pip there for it" in either direction. `check-parity.py` cannot see this -
it proves a step exists, not that both platforms say the same thing (#111).

Both scripts already own the resolver the installer itself uses - `find_usable_python` /
`Find-UsablePython`. The summary was the one place that forgot.

Why this is a test and not just a one-line fix: the obvious correction is

    summary_pip="$("$summary_py" -m pip --version 2>/dev/null | head -n1)"

and it is wrong in a way that passes every casual check, because the failure is SILENT. These
scripts run under `set -e -o pipefail`, so an interpreter with no pip makes that pipeline exit
non-zero and the script dies **at the summary, after every install succeeded** - printing
nothing after that line and never reaching the "not available" branch written directly below
it. The guard `|| summary_pip=""` is what makes that branch reachable at all.

So the unguarded form is kept below as a CONTROL. It must still die, or this test has stopped
being able to detect the guard's removal - and a control is the only thing that distinguishes
"the hazard is handled" from "the hazard is not reproducible here".

Caveat this test states rather than hides: the behavioural part runs the *shell logic* of the
macOS summary, under whatever bash is available (Git Bash on a Windows host). That is not macOS.
It verifies the `set -e`/pipefail semantics and the two branches, which is where the bug lived;
it does not verify anything about Homebrew, venvs or real interpreter resolution.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MACOS = ROOT / "scripts" / "macos-ai-tools.sh"
WINDOWS = ROOT / "scripts" / "windows-ai-tools.ps1"

failures: list[str] = []
checks = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"    ok    {name}")
    else:
        print(f"    FAIL  {name}")
        if detail:
            for line in detail.splitlines():
                print(f"          {line}")
        failures.append(name)


def _summary_block(text: str, start: str) -> str:
    """The summary function's body, so a match elsewhere in the script cannot satisfy a check."""
    i = text.index(start)
    rest = text[i:]
    # the next line that starts a new top-level construct ends the block
    m = re.search(r"\n(?=\S)", rest[len(start):])
    return rest[: len(start) + (m.start() if m else len(rest))]


def _code_only(block: str) -> str:
    """Comments removed, because a check must not be satisfiable by a comment.

    Mutation testing caught this: "macOS summary resolves the interpreter it reports" asked
    whether `find_usable_python` appears in the summary, and it still did after the call was
    replaced - in the explanatory comment written directly above it. A containment check over
    text that includes prose is a check against the prose.

    Full-line comments only. Both scripts put their reasoning on its own lines, and a naive
    strip of trailing `#` would corrupt `"  pip ..............."` and PowerShell's `$#`.
    """
    return "\n".join(
        l for l in block.splitlines() if not l.lstrip().startswith("#")
    )


def _lift_pip_span(block: str) -> str:
    """The real pip span out of macos-ai-tools.sh, from the assignment to its closing `fi`.

    Lifted rather than restated. The first version of this test ran a copy of the code held in
    the test file, so deleting the guard from the script did not fail anything - the test was
    evidence about its own copy. `internal-setup/test-credential-bytes.ps1` lifts each script's
    real line for the same reason.
    """
    lines = block.splitlines()
    start = next(i for i, l in enumerate(lines) if l.lstrip().startswith("summary_pip="))
    end = next(i for i in range(start, len(lines)) if lines[i] == "    fi")
    span = "\n".join(lines[start : end + 1])
    # the stub interpreter arrives as $1 in the harness below
    return span.replace('"$summary_py"', '"$1"').replace("$summary_py", "$1")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Static: neither summary may report pip independently of the Python it names.
# ─────────────────────────────────────────────────────────────────────────────
sh = MACOS.read_text(encoding="utf-8")
ps = WINDOWS.read_text(encoding="utf-8")

sh_summary_raw = _summary_block(sh, "summary() {")
ps_summary_raw = _summary_block(ps, "function Show-Summary {")
sh_summary = _code_only(sh_summary_raw)
ps_summary = _code_only(ps_summary_raw)

check(
    "macOS summary does not report a bare pip3",
    "get_version pip3" not in sh_summary,
    "This is the exact line from #100. pip3 resolves off PATH independently of the\n"
    "python3 reported one row above, so the two rows can describe different installs.",
)
check(
    "macOS summary resolves the interpreter it reports",
    "find_usable_python" in sh_summary,
    "The summary must name the interpreter install_python itself resolved, not whatever\n"
    "`python3` happens to mean at the end of the run.",
)
check(
    "macOS summary asks that interpreter for its pip",
    "-m pip --version" in sh_summary,
    "pip must be reported THROUGH the resolved interpreter, which is the only way the two\n"
    "rows cannot disagree.",
)
check(
    "Windows summary resolves the interpreter it reports",
    "Find-UsablePython" in ps_summary,
    "A bare `python` here is the one candidate Find-UsablePython refuses when a Store alias\n"
    "is present, so the summary could name an interpreter the installer declined to use.",
)
check(
    "Windows summary has a pip row at all",
    "-m', 'pip'" in ps_summary or "-m','pip'" in ps_summary,
    "Windows printed no pip row for the whole life of this script, so 'is pip available for\n"
    "the Python I am using' had no answer here. That is half of #100.",
)
check(
    "Windows summary does not fall back to a bare pip",
    not re.search(r"Get-ToolVersion\s+pip\b", ps_summary),
    "A pip belonging to another interpreter is not a substitute for the missing one.",
)

check(
    "the macOS pip assignment carries its set -e guard",
    '|| summary_pip=""' in sh_summary,
    "Without it, `set -o pipefail` + `set -e` kill the script at this line when the\n"
    "interpreter has no pip - at the summary, after everything succeeded, printing nothing.\n"
    "The `not available` branch below it becomes unreachable. The behavioural control further\n"
    "down proves this by running the script's own text with the guard stripped.",
)

# Both platforms must say the same thing when pip is absent — the half check-parity cannot see.
check(
    "both platforms report an absent pip rather than omitting the row",
    "not available for" in sh_summary and "not available for" in ps_summary,
    "An absent pip for the Python in use is the single most useful thing this summary can\n"
    "say to somebody debugging a package that 'did not install'.",
)

# ─────────────────────────────────────────────────────────────────────────────
# 2. Behavioural: the two branches, and the control that proves the guard matters.
# ─────────────────────────────────────────────────────────────────────────────
bash = shutil.which("bash")
if not bash:
    print()
    print("    SKIPPED: no bash on this machine, so the shell behaviour was not exercised.")
    print("    The static checks above ran; exiting 77 so this is not counted as a pass.")
    sys.exit(77)

WITH_PIP = """#!/bin/sh
case "$1" in
  --version) echo "Python 3.14.3" ;;
  -m) [ "$2" = "pip" ] && echo "pip 25.3 from /somewhere/python3.14/site-packages/pip (python 3.14)" ;;
esac
"""

NO_PIP = """#!/bin/sh
case "$1" in
  --version) echo "Python 3.14.3" ;;
  -m) echo "No module named pip" >&2; exit 1 ;;
esac
"""

# Lifted out of scripts/macos-ai-tools.sh, not restated. This is the whole point: mutation
# testing showed that a restated copy passes happily while the script's own guard is deleted.
GUARDED = _lift_pip_span(sh_summary_raw) + '\necho "REACHED_END"\n'

# The CONTROL is that same lifted text with only the guard removed, so what it proves is that
# the guard IN THE SCRIPT is load-bearing - not that some hazard exists somewhere in bash.
if '|| summary_pip=""' not in GUARDED:
    print("    FAIL  cannot build the control: the lifted span has no guard to remove")
    sys.exit(1)
UNGUARDED = GUARDED.replace(' || summary_pip=""', "")


def run(body: str, interpreter: Path) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile(
        "w", suffix=".sh", delete=False, encoding="utf-8", newline="\n"
    ) as f:
        f.write("set -eu\nset -o pipefail\n" + body)
        script = f.name
    try:
        return subprocess.run(
            [bash, script, str(interpreter)],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    finally:
        os.unlink(script)


print()
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    with_pip = tmp / "py-with-pip"
    no_pip = tmp / "py-no-pip"
    with_pip.write_text(WITH_PIP, encoding="utf-8", newline="\n")
    no_pip.write_text(NO_PIP, encoding="utf-8", newline="\n")
    with_pip.chmod(0o755)
    no_pip.chmod(0o755)

    r = run(GUARDED, with_pip)
    check(
        "an interpreter with pip has its own pip reported",
        r.returncode == 0 and "pip 25.3" in r.stdout and "(python 3.14)" in r.stdout,
        f"exit={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}",
    )

    r = run(GUARDED, no_pip)
    check(
        "an interpreter without pip is reported as not having one",
        r.returncode == 0
        and "not available for" in r.stdout
        and "REACHED_END" in r.stdout,
        f"exit={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}",
    )

    # The control. Without the guard, set -e + pipefail kills the script AT the assignment:
    # non-zero exit, and nothing after that line printed. If this ever starts passing, the
    # hazard has stopped being reproducible here and the two checks above have lost their point.
    r = run(UNGUARDED, no_pip)
    check(
        "CONTROL: the unguarded assignment still dies under set -e, silently",
        r.returncode != 0 and "REACHED_END" not in r.stdout,
        "The guard `|| summary_pip=\"\"` is supposed to be load-bearing. If the unguarded\n"
        "form now survives, this test can no longer detect the guard being deleted.\n"
        f"exit={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}",
    )
    # And it must die in the way that makes it nasty: no error of its own.
    r2 = run(UNGUARDED, no_pip)
    check(
        "CONTROL: and it dies without printing a reason",
        "No module named pip" not in r2.stdout and "pip ..." not in r2.stdout,
        "The 2>/dev/null that makes the guarded form tidy is what makes the unguarded form\n"
        "silent: the installer would stop at its own summary with no message at all.\n"
        f"stdout:\n{r2.stdout}\nstderr:\n{r2.stderr}",
    )

print()
if failures:
    print(f"FAIL: {len(failures)} of {checks} check(s) failed: {', '.join(failures)}")
    sys.exit(1)
print(f"all {checks} checks passed: the summary names one interpreter and reports its pip.")
