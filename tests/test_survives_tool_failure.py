#!/usr/bin/env python3
"""A tool that fails must not take the installer down with it. Regression test for #51.

The report: a clean Mac, installer runs, and then

    ==> Claude Code environment already configured

    Warning: stopped early (exit 1). The last line above is where it got to.

No error text. Nothing else. The reason it was invisible is worth stating, because it is the
whole shape of the bug:

    already_added="$(claude plugin marketplace list 2>/dev/null \\
      | sed -n 's/.*GitHub (\\([^)]*\\)).*/\\1/p')"

`claude` had just been installed and had never been run, so `plugin marketplace list` exited
non-zero. Under `set -o pipefail` that makes the *pipeline* non-zero; the assignment inherits
it; an assignment is a simple command rather than a condition, so `set -e` terminated the
script. `2>/dev/null` had already discarded the reason. A silent, total failure caused by a
step that was supposed to be **silent-by-default and optional** — `setup_plugin_marketplaces`
begins with three `|| return 0` guards precisely because a user outside CSA-Internal should
sail past it without noticing.

`tools/check-pipeline-assignments.py` prevents the *class*. This proves the *behaviour*: with a
`claude` that fails exactly the way a freshly-installed one does, the function must return, the
caller must survive, and the run must continue.

The functions under test are extracted from the shipping scripts, so this cannot drift. All
three scripts that carry this step are checked, because the bug was in all three.

    python3 tests/test_survives_tool_failure.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def _posix_bash() -> str:
    r"""Absolute path to a POSIX bash. Resolved once, absolutely, for two reasons.

    These tests replace PATH with a stub-only directory, so a bare "bash" could not be
    found there. And on Windows a bare "bash" is resolved by CreateProcess against the
    PARENT process's PATH, which finds C:\Windows\System32\bash.exe -- the WSL launcher,
    not a shell. It exits 1 with a UTF-16LE "no installed distributions" message, so the
    failure reads as this test failing rather than as bash being absent.

    Git Bash counts as POSIX for our purposes: measured on MINGW64_NT-10.0-26200, it
    resolves and runs a shebang'd stub off PATH even though Windows cannot set the exec
    bit (chmod(0o755) leaves mode 0o666) and `test -x` on that stub reports false.
    """
    override = os.environ.get("CSA_TEST_BASH")
    if override:
        return override
    if os.name != "nt":
        return "/bin/bash"
    for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(candidate):
            return candidate
    found = shutil.which("bash")
    if found and "System32" not in found:      # never the WSL launcher
        return found
    raise SystemExit("no POSIX bash found - install Git for Windows, or set CSA_TEST_BASH")


BASH = _posix_bash()


# Windows needs these to locate its own per-user directories. Handing subprocess a minimal
# env is reasonable on POSIX and actively dangerous here: without LOCALAPPDATA the Python
# Install Manager roots itself at "Python" RELATIVE TO THE WORKING DIRECTORY, decides no
# interpreter is installed, and installs a 167 MB one into the repo -- while the test passes.
# Keep these; control only PATH and HOME, which is what these tests are actually about.
_KEEP_NT = ("SystemRoot", "SystemDrive", "ComSpec", "PATHEXT",
            "LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP")


def base_env() -> dict[str, str]:
    """Platform floor an env= dict must start from. Empty on POSIX, by design."""
    if os.name != "nt":
        return {}
    return {k: os.environ[k] for k in _KEEP_NT if k in os.environ}



ROOT = pathlib.Path(__file__).resolve().parent.parent
# (script, function) — macos-update.sh and macos-plugins.sh name theirs differently on purpose;
# check-duplication.py's PER_SCRIPT map records why.
TARGETS = [
    ("macos-ai-tools.sh", "setup_plugin_marketplaces"),
    ("macos-plugins.sh", "sync_plugin_marketplaces"),
    ("macos-update.sh", "sync_plugin_marketplaces"),
]


def extract(source: pathlib.Path, name: str) -> str:
    text = source.read_text(encoding="utf-8")
    m = (re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
         or re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", text, re.M))
    if not m:
        raise SystemExit(f"could not find {name} in {source.name}")
    return m.group(0)


# How a freshly-installed, never-authenticated Claude Code behaves: the binary exists, and the
# subcommand fails. This is the state a clean machine is in at exactly this point in the run,
# because the installer has just put `claude` on disk and nobody has logged in yet.
CLAUDE_STUB = """#!/bin/sh
if [ "$1" = "plugin" ]; then
  echo "Error: not authenticated" >&2
  exit 1
fi
exit 0
"""
# ...and one that works, so the happy path is covered too.
CLAUDE_OK = """#!/bin/sh
if [ "$1" = "plugin" ] && [ "$2" = "marketplace" ] && [ "$3" = "list" ]; then exit 0; fi
exit 0
"""


def run(script: str, func: str, claude: str) -> tuple[str, int]:
    source = ROOT / "scripts" / script
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        binm = tmp / "bin"
        binm.mkdir()
        (binm / "claude").write_text(claude, encoding="utf-8")
        (binm / "gh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        for f in binm.iterdir():
            f.chmod(0o755)

        harness = f"""#!/usr/bin/env bash
set -euo pipefail
{extract(source, "has_command")}
info() {{ echo "INFO: $*"; }}
warn() {{ echo "WARN: $*"; }}
success() {{ echo "OK: $*"; }}
CSA_MARKETPLACES=(CloudSecurityAlliance/csa-plugins)
plugin_marketplace_repo() {{ echo "CloudSecurityAlliance/csa-plugins"; }}
{extract(source, func)}
{func}
echo "SURVIVED"
"""
        h = tmp / "harness.sh"
        h.write_text(harness, encoding="utf-8")
        env = {**base_env(), "PATH": f"{binm}:/usr/bin:/bin", "HOME": str(tmp)}
        p = subprocess.run([BASH, str(h)], capture_output=True, text=True, env=env)
        return (p.stdout + p.stderr), p.returncode


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    for script, func in TARGETS:
        print(f"\n{script} :: {func}")

        out, rc = run(script, func, CLAUDE_STUB)
        check("SURVIVED" in out, "THE #51 CASE: a claude that cannot list marketplaces "
                                 "does not kill the caller")
        check(rc == 0, f"the run exits 0, not 1 (got {rc})")

        out, rc = run(script, func, CLAUDE_OK)
        check("SURVIVED" in out and rc == 0, "a working claude still completes the step")

    print("\ncontrol: the unguarded assignment, which this test must still catch")
    source = ROOT / "scripts" / "macos-ai-tools.sh"
    broken = extract(source, "setup_plugin_marketplaces").replace(
        '| sed -n \'s/.*GitHub (\\([^)]*\\)).*/\\1/p\')" || already_added=""',
        '| sed -n \'s/.*GitHub (\\([^)]*\\)).*/\\1/p\')"')
    assert broken != extract(source, "setup_plugin_marketplaces"), \
        "control did not actually remove the guard — this test would be vacuous"
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        binm = tmp / "bin"
        binm.mkdir()
        (binm / "claude").write_text(CLAUDE_STUB, encoding="utf-8")
        (binm / "gh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        for f in binm.iterdir():
            f.chmod(0o755)
        harness = ("#!/usr/bin/env bash\nset -euo pipefail\n"
                   + extract(source, "has_command") + "\n"
                   + 'info() { echo "INFO: $*"; }\nwarn() { echo "WARN: $*"; }\n'
                     'success() { echo "OK: $*"; }\n'
                     'CSA_MARKETPLACES=(CloudSecurityAlliance/csa-plugins)\n'
                   + broken + "\nsetup_plugin_marketplaces\necho SURVIVED\n")
        h = tmp / "h.sh"
        h.write_text(harness, encoding="utf-8")
        p = subprocess.run([BASH, str(h)], capture_output=True, text=True,
                           env={**base_env(), "PATH": f"{binm}:/usr/bin:/bin", "HOME": str(tmp)})
        check("SURVIVED" not in (p.stdout + p.stderr) and p.returncode == 1,
              f"unguarded version dies silently with exit 1 (got rc={p.returncode})")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
