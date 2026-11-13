#!/usr/bin/env python3
"""A Homebrew Codex CLI is migrated to npm whether Homebrew holds it as a cask or a formula.

TODO.md H4. Homebrew has shipped the Codex CLI both ways: a homebrew-core FORMULA until
2025-10-17, then a CASK (homebrew-core's tap_migrations.json maps "codex" to homebrew/cask). An
installed formula's keg is not moved by that, so a Mac that installed Codex from Homebrew early
still has the formula. `detect_migrations` in scripts/macos-ai-tools.sh asked only
`brew list --cask codex`. Measured on 2026-11-12 with Homebrew 7.0.13: a codex keg in the Cellar
is found by `brew list --formula codex` (exit 0) and missed by `brew list --cask codex` (exit 1).
Missed, the formula stays: gone from homebrew-core, it is never upgraded again, and its link at
<prefix>/bin/codex is the same path where npm, under Homebrew's node, links the npm Codex.

(TODO.md said no `codex` cask exists, so the cask check was dead code. That was not so by the
time it was checked: the cask is homebrew-cask's Casks/c/codex.rb, with 1.27 million installs in
the year to 2026-11-12. The cask half was live; the formula half was missing.)

`detect_migrations` and `migrate_codex` are extracted from the shipping script, not copied, and
run against a `brew` stub that records what it is asked.

A CONTROL, as ADR-005 asks: the same cases against the Codex lines of `detect_migrations` and
`migrate_codex` as they stood at 36e76b4. They must FAIL the formula case.

    python3 tests/test_codex_migration.py
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
SOURCE = ROOT / "scripts" / "macos-ai-tools.sh"
TEXT = SOURCE.read_text(encoding="utf-8")

# The Codex lines of detect_migrations, and migrate_codex, as they stood at 36e76b4: the control.
OLD_FUNCTIONS = """detect_migrations() {
  # Codex: should be npm, not brew
  if has_command brew && brew list --cask codex >/dev/null 2>&1; then
    codex_needs_migration="brew"
  fi
}

migrate_codex() {
  if [[ "$codex_needs_migration" == "brew" ]]; then
    info "Removing Codex CLI from Homebrew (migrating to npm)"
    brew uninstall --cask codex || warn "brew uninstall codex failed; continuing"
  fi
}"""

DRIVER = r"""#!/usr/bin/env bash
set -euo pipefail
LOG='@@LOG@@'
info() { echo "INFO $*"; }
warn() { echo "WARN $*"; }
has_command() { command -v "$1" >/dev/null 2>&1; }
ensure_brew_in_path() { :; }
npm() { return 1; }
if [[ '@@BREW@@' == yes ]]; then
  brew() {
    echo "brew $*" >> "$LOG"
    case "$1 $2" in
      "list --cask")    for c in @@CASKS@@; do [[ "$c" == "$3" ]] && return 0; done; return 1 ;;
      "list --formula") for f in @@FORMULAS@@; do [[ "$f" == "$3" ]] && return 0; done; return 1 ;;
      "uninstall --cask"|"uninstall --formula") return 0 ;;
    esac
    return 1
  }
fi
claude_needs_migration=""
codex_needs_migration=""
codex_brew_kind=""
gemini_needs_migration=""
copilot_needs_migration=""
@@FUNCTIONS@@
detect_migrations
echo "CSA_TEST_CODEX=[$codex_needs_migration]"
migrate_codex
"""


def extract(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not match:
        raise SystemExit(f"could not find {name}() in {SOURCE.name}")
    return match.group(0)


NEW_FUNCTIONS = extract(TEXT, "detect_migrations") + "\n" + extract(TEXT, "migrate_codex")


def run(*, brew: bool = True, casks: tuple[str, ...] = (), formulas: tuple[str, ...] = (),
        old: bool = False) -> tuple[str, list[str]]:
    """(codex_needs_migration, the `brew uninstall` calls made)."""
    work = tempfile.mkdtemp(prefix="csa-codex-")
    try:
        log = pathlib.Path(work, "brew.log")
        log.write_text("", encoding="utf-8")
        script = (DRIVER.replace("@@LOG@@", str(log))
                  .replace("@@BREW@@", "yes" if brew else "no")
                  .replace("@@CASKS@@", " ".join(casks) or "''")
                  .replace("@@FORMULAS@@", " ".join(formulas) or "''")
                  .replace("@@FUNCTIONS@@", OLD_FUNCTIONS if old else NEW_FUNCTIONS))
        path = pathlib.Path(work, "driver.sh")
        path.write_text(script, encoding="utf-8")
        proc = subprocess.run([BASH, str(path)], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin", "HOME": work}, timeout=60)
        out = proc.stdout + proc.stderr
        state = re.search(r"CSA_TEST_CODEX=\[(.*?)\]", out)
        if proc.returncode != 0 or not state:
            return f"<exit {proc.returncode}: {out!r}>", []
        calls = [c for c in log.read_text(encoding="utf-8").splitlines()
                 if c.startswith("brew uninstall") and c.endswith(" codex")]
        return state.group(1), calls
    finally:
        shutil.rmtree(work, ignore_errors=True)


CASES = [
    ("the cask (Homebrew since 2025-10-17) is migrated with `uninstall --cask`",
     dict(casks=("codex",)), ("brew", ["brew uninstall --cask codex"])),
    ("the formula (Homebrew until 2025-10-17) is migrated with `uninstall --formula`",
     dict(formulas=("codex",)), ("brew", ["brew uninstall --formula codex"])),
    ("no Homebrew Codex: nothing to migrate, nothing uninstalled",
     dict(casks=("chatgpt",), formulas=("gemini-cli",)), ("", [])),
    ("no Homebrew at all: nothing to migrate, nothing uninstalled",
     dict(brew=False), ("", [])),
]


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    print("\ndetect_migrations / migrate_codex")
    for label, kw, want in CASES:
        got = run(**kw)
        check(got == want, f"{label} ({got})")

    print("\n  control: the Codex lines at 36e76b4 must fail the formula case")
    got = run(formulas=("codex",), old=True)
    check(got != CASES[1][2], f"the old check misses a formula install ({got})")
    got = run(casks=("codex",), old=True)
    check(got == CASES[0][2], f"and agrees on the cask, so the harness is not what differs ({got})")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("all Codex migration checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
