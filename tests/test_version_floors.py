#!/usr/bin/env python3
"""Presence is not usability: the runtime floor must reject what the OS ships.

Issue #53. `install_python()` gated on `has_command python3`, and **macOS always has one** —
`/usr/bin/python3`, which is 3.9.6. So on every stock Mac the installer printed a green
"Python ............ installed (Python 3.9.6)" and never installed Homebrew Python. The
failure surfaced much later and somewhere else, in a pip resolver, long after the point where
the real problem was reported as fine.

The bug is not "we forgot to install Python". It is "the presence check was satisfied by
something unusable that the OS pre-loads". That shape is why it survived: it works on every
machine that already had Homebrew Python, and fails only on the clean ones this repo exists
to serve.

**The Python half moved to `tests/test_csa_python.py`** (#179), along with the #53 case: Python
is no longer chosen by a floor at all, but named by one resolver that accepts only the 3.14
standard build, and that file tests it.

This file keeps Node. `install_node` had the same shape in its `elif has_command node` branch,
with a narrower blast radius — a stock Mac has no node at all, so the install branch runs and
is fine. It only bites a machine carrying an old node, e.g. an abandoned nvm install.

The functions are extracted from the shipping scripts rather than copied, so this cannot
drift from what actually runs.

    python3 tests/test_version_floors.py
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
AI = ROOT / "scripts" / "macos-ai-tools.sh"
WORK = ROOT / "scripts" / "macos-work-tools.sh"


def extract(source: pathlib.Path, name: str) -> str:
    text = source.read_text(encoding="utf-8")
    # Multi-line form first; then the one-liner form (`has_command() { ...; }`), which the
    # multi-line pattern cannot match because there is no `}` in column 0.
    m = (re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
         or re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", text, re.M))
    if not m:
        raise SystemExit(f"could not find {name} in {source.name}")
    return m.group(0)


def extract_assignment(source: pathlib.Path, name: str) -> str:
    """The literal `NAME=value` line from a script, so no test hardcodes a floor."""
    text = source.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}=\S+", text, re.M)
    if not match:
        raise SystemExit(f"could not find {name} in {source.name}")
    return match.group(0)


def bash(body: str, *, path: str | None = None) -> tuple[str, int]:
    script = "#!/usr/bin/env bash\nset -euo pipefail\n" + body
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(script)
        name = fh.name
    env = {**base_env(), "PATH": path or os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp")}
    # bash by absolute path, so a stub-only PATH controls what the SCRIPT resolves without
    # also hiding the interpreter running it.
    p = subprocess.run([BASH, name], capture_output=True, text=True, env=env)
    return (p.stdout + p.stderr).strip(), p.returncode


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    # ---- node_meets_floor ----
    print("\nnode_meets_floor")
    nf = extract(AI, "node_meets_floor")
    check(nf == extract(WORK, "node_meets_floor"),
          "node_meets_floor is identical in both scripts")
    # The floor moved out of the function body into CSA_NODE_MIN, so it has to be extracted
    # too -- without it `min` is empty and the comparison rejects every version, which is how
    # this test caught the change. Extracted rather than hardcoded, for the usual reason: a
    # copy of the number here could disagree with the script and still pass.
    node_min = extract_assignment(AI, "CSA_NODE_MIN")
    check(extract_assignment(WORK, "CSA_NODE_MIN") == node_min,
          f"CSA_NODE_MIN is the same in both scripts ({node_min})")
    check(int(node_min.split("=")[1]) >= 22,
          "node floor is at least 22 (what wrangler's engines.node asks for)")
    with tempfile.TemporaryDirectory() as td:
        # v20 and v21 now FAIL: wrangler needs >= 22, and Node is the Workers/TypeScript
        # runtime here, not only an AI-CLI dependency. v26 is Current, v24 is LTS; both pass.
        for version, expected in [("v18.20.4", False), ("v20.0.0", False), ("v21.7.3", False),
                                  ("v22.0.0", True), ("v24.1.0", True), ("v26.8.1", True),
                                  ("v16.20.0", False), ("", False), ("garbage", False)]:
            d = pathlib.Path(td) / f"n{version or 'empty'}".replace(".", "_")
            d.mkdir(parents=True, exist_ok=True)
            f = d / "node"
            f.write_text(f"#!/bin/sh\necho '{version}'\n", encoding="utf-8")
            f.chmod(0o755)
            _, rc = bash(f"{node_min}\n{nf}\nif node_meets_floor; then exit 0; else exit 1; fi",
                         path=f"{d}:/usr/bin:/bin")
            check((rc == 0) == expected,
                  f"node {version or '(no output)'!r} -> {'accepted' if expected else 'rejected'}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
