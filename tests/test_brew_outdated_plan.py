#!/usr/bin/env python3
"""The update plan says when its Homebrew list may be behind what `brew update` will see.

TODO.md H3 said `macos-update.sh`'s plan lists `brew outdated` from a stale index, because
update_brew's `brew update` runs later. Half of that was wrong: `brew outdated` is one of
Homebrew's auto-update commands (since 4.0.7), and re-downloads the API index for homebrew/core
and homebrew/cask when it is older than 450 s. But measured on Homebrew 7.0.13 on 2026-11-12,
the git repositories, every third-party tap among them, are fetched only once a day: a run 25
minutes after the last left every FETCH_HEAD alone. So a tap's formulae can be a day behind, and
with HOMEBREW_NO_AUTO_UPDATE set nothing is refreshed at all.

`brew_outdated_plan` is extracted from the shipping script, not copied, and run against a `brew`
stub. It must:
  - say nothing extra when only homebrew/ taps are present;
  - name the third-party taps when there are any (read with `brew tap`, no network call);
  - say the list is from the cache when HOMEBREW_NO_AUTO_UPDATE is set;
  - keep `brew outdated`'s stderr (where its update report goes) out of the list.

A CONTROL, as ADR-005 asks: the same cases against the plan's Homebrew rows as they stood at
36e76b4, which must fail the two that need a note.

On a Mac with Homebrew, it also checks the assumption the comment rests on, in the installed
Homebrew's own source: `outdated` is in its auto-update command list.

    python3 tests/test_brew_outdated_plan.py
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
    r"""Absolute path to a POSIX bash, never a bare "bash": on Windows that resolves to
    C:\Windows\System32\bash.exe, the WSL launcher. Git Bash is preferred; CSA_TEST_BASH
    overrides. The same helper as the other tests/*.py files."""
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
ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "macos-update.sh"
TEXT = SOURCE.read_text(encoding="utf-8")

# The Homebrew rows of preflight as they stood at 36e76b4, verbatim, wrapped as a function: the
# control.
OLD_FUNCTION = """brew_outdated_plan() {
    info "Checking Homebrew for outdated packages..."
    echo ""

    local outdated_formulas outdated_casks
    outdated_formulas=$(brew outdated --formula --verbose 2>/dev/null || true)
    outdated_casks=$(brew outdated --cask --verbose 2>/dev/null || true)

    if [[ -n "$outdated_formulas" ]]; then
      echo "  Homebrew formulas to upgrade:"
      echo "$outdated_formulas" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  Homebrew formulas: all up to date"
    fi
    echo ""

    if [[ -n "$outdated_casks" ]]; then
      echo "  Homebrew casks to upgrade:"
      echo "$outdated_casks" | while IFS= read -r line; do echo "    $line"; done
    else
      echo "  Homebrew casks: all up to date"
    fi
}"""

DRIVER = r"""#!/usr/bin/env bash
set -euo pipefail
info() { echo "INFO $*"; }
TAPS='@@TAPS@@'
TAP_FAILS='@@TAP_FAILS@@'
brew() {
  case "$*" in
    "outdated --formula --verbose")
      echo "==> Auto-updated Homebrew!" >&2
      echo "git (2.56.0_2) < 2.56.1"
      echo "terraform (1.17.1) < 1.17.2" ;;
    "outdated --cask --verbose") ;;
    "tap")
      if [[ "$TAP_FAILS" == 1 ]]; then return 1; fi
      if [[ -n "$TAPS" ]]; then printf '%s\n' $TAPS; fi ;;
    *) echo "UNEXPECTED brew $*" >&2; return 2 ;;
  esac
}
@@FUNCTION@@
brew_outdated_plan
echo "CSA_TEST_END"
"""


def extract(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not match:
        raise SystemExit(f"could not find {name}() in {SOURCE.name}")
    return match.group(0)


def run(*, taps: tuple[str, ...] = (), tap_fails: bool = False, no_auto_update: bool = False,
        old: bool = False) -> str:
    work = tempfile.mkdtemp(prefix="csa-brew-plan-")
    try:
        script = (DRIVER.replace("@@TAPS@@", " ".join(taps))
                  .replace("@@TAP_FAILS@@", "1" if tap_fails else "0")
                  .replace("@@FUNCTION@@", OLD_FUNCTION if old else extract(TEXT, "brew_outdated_plan")))
        path = pathlib.Path(work, "driver.sh")
        path.write_text(script, encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "HOME": work}
        if no_auto_update:
            env["HOMEBREW_NO_AUTO_UPDATE"] = "1"
        proc = subprocess.run([BASH, str(path)], capture_output=True, text=True, env=env, timeout=60)
        return proc.stdout + ("" if proc.returncode == 0 else f"\n<exit {proc.returncode}>{proc.stderr}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


TAP_NOTE = "(Formulae from hashicorp/tap, heroku/brew are listed as Homebrew last fetched those taps"
CACHE_NOTE = "(HOMEBREW_NO_AUTO_UPDATE is set, so this is from Homebrew's cached index"
THIRD_PARTY = ("hashicorp/tap", "heroku/brew")


def homebrew_lists_outdated_as_auto_update() -> tuple[str, str]:
    """('ok' | 'fail' | 'not run', detail) from the installed Homebrew's own source."""
    brew = shutil.which("brew")
    if not brew:
        return "not run", "no Homebrew here"
    repo = subprocess.run([brew, "--repository"], capture_output=True, text=True).stdout.strip()
    lib = pathlib.Path(repo, "Library", "Homebrew")
    for candidate in (lib / "utils" / "auto-update.sh", lib / "brew.sh"):
        if not candidate.exists():
            continue
        m = re.search(r"AUTO_UPDATE_COMMANDS=\((.*?)\)", candidate.read_text(encoding="utf-8"), re.S)
        if m:
            commands = m.group(1).split()
            return ("ok" if "outdated" in commands else "fail"), f"{candidate.name}: {commands}"
    return "not run", "AUTO_UPDATE_COMMANDS not found where Homebrew 4-7 keep it"


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    print("\nbrew_outdated_plan")
    out = run(taps=("homebrew/core", "homebrew/cask"))
    check("CSA_TEST_END" in out and TAP_NOTE[:20] not in out and CACHE_NOTE not in out
          and "    git (2.56.0_2) < 2.56.1" in out and "Homebrew casks: all up to date" in out,
          "only homebrew/ taps: the list, and no note")
    out = run(taps=("homebrew/core",) + THIRD_PARTY)
    check(TAP_NOTE in out and CACHE_NOTE not in out, "third-party taps: named, with how fresh they are")
    out = run(taps=THIRD_PARTY, no_auto_update=True)
    check(CACHE_NOTE in out and TAP_NOTE not in out,
          "HOMEBREW_NO_AUTO_UPDATE: says the whole list is from the cache")
    out = run(tap_fails=True)
    check("CSA_TEST_END" in out and "Formulae from" not in out, "a failing `brew tap` adds no note and stops nothing")
    check("Auto-updated" not in run(), "brew outdated's update report (stderr) never lands in the list")

    print("\n  control: the plan's Homebrew rows at 36e76b4 must fail the cases needing a note")
    check(TAP_NOTE not in run(taps=THIRD_PARTY, old=True), "the old rows never mention third-party taps")
    check(CACHE_NOTE not in run(taps=THIRD_PARTY, no_auto_update=True, old=True),
          "the old rows never mention HOMEBREW_NO_AUTO_UPDATE")
    check("    git (2.56.0_2) < 2.56.1" in run(old=True), "and agree on the list, so the harness is not what differs")

    print("\nthe installed Homebrew")
    state, detail = homebrew_lists_outdated_as_auto_update()
    if state == "not run":
        print(f"    not run  ({detail})")
    else:
        check(state == "ok", f"`outdated` is one of its auto-update commands ({detail})")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("all brew-outdated plan checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
