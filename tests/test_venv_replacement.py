#!/usr/bin/env python3
"""Replacing the shared venv must never leave the machine worse than it found it.

`install_doc_python_deps` has to replace `~/.default_venv` when it was built by a Python below
`CSA_PYTHON_MIN` — `python3 -m venv` does not upgrade a directory in place, so a 3.9 venv stays
3.9 forever and every later run reinstalls into an interpreter `csa-google-workspace` refuses.

The first version of that repair was written in the obvious order — move the old venv aside,
then create the new one — and that order is wrong in a way nothing would have noticed:

  * A sub-floor venv is **not worthless.** It is below what `csa-google-workspace` needs, but it
    still serves `csa-preflight`, which imports only `yaml` and `fitz`. So if creating the
    replacement failed, the repair itself turned a partly-working tool into a broken one, and
    the only trace was a warn line.
  * The venv may be **active in the calling shell.** Moving it leaves `$VIRTUAL_ENV` and that
    shell's `python3` dangling, and the person is left debugging their own prompt rather than
    reading the warning.

So: build first, swap last, and refuse outright while the venv is active. These tests exist
because those are failure paths — the happy path was never the risk, and a test suite that only
covers the happy path would have passed against the broken ordering.

The function under test is extracted from the shipping script rather than copied, so this
cannot drift from what actually runs. `$py`, `info`, `warn`, `get_version` and
`find_usable_python` are stubbed; `python_meets_floor` and `install_doc_python_deps` are real.

    python3 tests/test_venv_replacement.py
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
AI = ROOT / "scripts" / "macos-ai-tools.sh"


def extract(name: str) -> str:
    text = AI.read_text()
    if name == "CSA_PYTHON_MIN":
        m = re.search(r'^CSA_PYTHON_MIN="[^"]*"$', text, re.M)
    else:
        m = (re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
             or re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", text, re.M))
    if not m:
        raise SystemExit(f"could not find {name} in {AI.name}")
    return m.group(0)


def make_venv(path: pathlib.Path, *, clears_floor: bool, marker: str) -> None:
    """A directory shaped like a venv. Its python3 answers the floor probe by exit status, and
    carries a marker file so a test can tell the original from a replacement."""
    (path / "bin").mkdir(parents=True, exist_ok=True)
    py = path / "bin" / "python3"
    py.write_text("#!/bin/sh\nexit %d\n" % (0 if clears_floor else 1))
    py.chmod(0o755)
    (path / "MARKER").write_text(marker)


def run(tmp: pathlib.Path, *, venv_clears_floor: bool | None, builder_works: bool,
        active: bool, override: str | None = None) -> tuple[str, int, pathlib.Path]:
    """venv_clears_floor=None means no venv exists at all."""
    venv = tmp / "default_venv"
    if venv_clears_floor is not None:
        make_venv(venv, clears_floor=venv_clears_floor, marker="ORIGINAL")

    # Stand-in for the interpreter. It must distinguish the calls the function makes:
    #   -c '<imports>'   the "deps already satisfied?" probe. MUST fail, or the function
    #                    early-returns and never reaches the replacement logic at all — which
    #                    is exactly what the first version of this harness got wrong.
    #   -m venv <dir>    build a venv.
    py = tmp / "python3-stub"
    build = ('if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then\n'
             '  mkdir -p "$3/bin" && printf "#!/bin/sh\\nexit 0\\n" > "$3/bin/python3"\n'
             '  chmod 755 "$3/bin/python3" && echo REPLACEMENT > "$3/MARKER" && exit 0\n'
             'fi\n') if builder_works else (
             'if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then exit 1; fi\n')
    py.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-c" ]; then exit 1; fi\n'   # deps are never already satisfied
        + build
        + "exit 0\n")
    py.chmod(0o755)

    harness = f"""#!/usr/bin/env bash
set -euo pipefail
{extract("CSA_PYTHON_MIN")}
{extract("has_command")}
{extract("python_meets_floor")}
info() {{ echo "INFO: $*"; }}
warn() {{ echo "WARN: $*"; }}
get_version() {{ echo "Python 3.9.6"; }}
find_usable_python() {{ printf '%s\\n' "{py}"; }}
CSA_VENV="{venv}"
CSA_DOC_PY_DEPS=(pyyaml)
{override or extract("install_doc_python_deps")}
install_doc_python_deps
echo "RC=$?"
"""
    script = tmp / "harness.sh"
    script.write_text(harness)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp)}
    if active:
        env["VIRTUAL_ENV"] = str(venv)
    p = subprocess.run(["/bin/bash", str(script)], capture_output=True, text=True, env=env)
    return (p.stdout + p.stderr), p.returncode, venv


# The ordering that shipped first: move the old venv aside, THEN create the new one. Kept so
# this test demonstrates it can still detect the regression rather than merely passing.
MOVE_FIRST = """install_doc_python_deps() {
  local py
  py="$(find_usable_python)"
  if [[ -x "$CSA_VENV/bin/python3" ]] && ! python_meets_floor "$CSA_VENV/bin/python3"; then
    local stale
    stale="${CSA_VENV}.pre-${CSA_PYTHON_MIN}-$(date +%Y%m%d%H%M%S)"
    warn "moving it to $stale and rebuilding"
    mv "$CSA_VENV" "$stale" || return 0
  fi
  if [[ ! -x "$CSA_VENV/bin/python3" ]]; then
    "$py" -m venv "$CSA_VENV" || {
      warn "Could not create $CSA_VENV - skipping document preflight deps"
      return 0
    }
  fi
}"""


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    def marker(v: pathlib.Path) -> str:
        f = v / "MARKER"
        return f.read_text().strip() if f.exists() else "<absent>"

    def stale_copies(v: pathlib.Path) -> list[pathlib.Path]:
        return sorted(v.parent.glob(v.name + ".pre-*"))

    print("\na stale venv, replacement builds fine")
    with tempfile.TemporaryDirectory() as td:
        out, _, venv = run(pathlib.Path(td), venv_clears_floor=False, builder_works=True, active=False)
        check(marker(venv) == "REPLACEMENT", f"venv was replaced (marker={marker(venv)!r})")
        check(len(stale_copies(venv)) == 1, "the old venv is kept, moved aside exactly once")
        check("previous one is at" in out, "the user is told where the old venv went")
        check(not list(venv.parent.glob(venv.name + ".new.*")), "no build directory left behind")

    print("\na stale venv, but the replacement CANNOT be built — the regression case")
    with tempfile.TemporaryDirectory() as td:
        out, _, venv = run(pathlib.Path(td), venv_clears_floor=False, builder_works=False, active=False)
        check(marker(venv) == "ORIGINAL",
              f"THE ORIGINAL VENV SURVIVES UNTOUCHED (marker={marker(venv)!r})")
        check(stale_copies(venv) == [], "nothing was moved aside")
        check(not list(venv.parent.glob(venv.name + ".new.*")), "no build directory left behind")
        check("exactly as it was" in out, "the user is told nothing was changed")

    print("\na stale venv that is ACTIVE in the calling shell")
    with tempfile.TemporaryDirectory() as td:
        out, _, venv = run(pathlib.Path(td), venv_clears_floor=False, builder_works=True, active=True)
        check(marker(venv) == "ORIGINAL", f"active venv is not touched (marker={marker(venv)!r})")
        check(stale_copies(venv) == [], "nothing was moved aside")
        check("ACTIVE in this shell" in out, "the user is told why, and what to do")
        check("deactivate" in out, "the remedy is named")

    print("\na healthy venv is left alone")
    with tempfile.TemporaryDirectory() as td:
        out, _, venv = run(pathlib.Path(td), venv_clears_floor=True, builder_works=True, active=False)
        check(stale_copies(venv) == [], "a floor-clearing venv is never moved aside")

    print("\nno venv at all — created directly, nothing to lose")
    with tempfile.TemporaryDirectory() as td:
        out, _, venv = run(pathlib.Path(td), venv_clears_floor=None, builder_works=True, active=False)
        check(marker(venv) == "REPLACEMENT", "a venv is created when none existed")
        check(stale_copies(venv) == [], "nothing is moved aside when there was nothing there")

    print("\ncontrol: the move-first ordering, which this test must still catch")
    with tempfile.TemporaryDirectory() as td:
        out, _, venv = run(pathlib.Path(td), venv_clears_floor=False, builder_works=False,
                           active=False, override=MOVE_FIRST)
        check(marker(venv) == "<absent>",
              f"move-first LOSES the venv when the build fails (marker={marker(venv)!r})")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
