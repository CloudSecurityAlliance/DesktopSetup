#!/usr/bin/env python3
"""Presence is not usability: the interpreter/runtime floors must reject what the OS ships.

Issue #53. `install_python()` gated on `has_command python3`, and **macOS always has one** —
`/usr/bin/python3`, which is 3.9.6. So on every stock Mac the installer printed a green
"Python ............ installed (Python 3.9.6)" and never installed Homebrew Python. The
failure surfaced much later and somewhere else: `csa-google-workspace` requires >= 3.10, so a
machine set up by this repo died in a pip resolver with several hundred lines of
`Requires-Python >=3.10`, long after the point where the real problem was reported as fine.

The bug is not "we forgot to install Python". It is "the presence check was satisfied by
something unusable that the OS pre-loads". That shape is why it survived: it works on every
machine that already had Homebrew Python, and fails only on the clean ones this repo exists
to serve.

`install_node` had the same shape in its `elif has_command node` branch, with a narrower
blast radius — a stock Mac has no node at all, so the install branch runs and is fine. It
only bites a machine carrying an old node, e.g. an abandoned nvm install.

**How the two halves are tested, and why differently.** `python_meets_floor` runs real Python
code, so it is checked against the real interpreters on this machine, cross-referenced with
what each one reports about itself — including `/usr/bin/python3` where that is the 3.9.6 in
the report. `find_usable_python` only ever consults `python_meets_floor`'s exit status, so its
*selection* logic is driven with stub interpreters that exit 0 or 1 on demand. That keeps the
selection test identical on macOS and on CI's Linux, where the real interpreter mix differs.

The functions are extracted from the shipping scripts rather than copied, so this cannot
drift from what actually runs.

    python3 tests/test_version_floors.py
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
WORK = ROOT / "scripts" / "macos-work-tools.sh"


def extract(source: pathlib.Path, name: str) -> str:
    text = source.read_text()
    if name == "CSA_PYTHON_MIN":
        m = re.search(r'^CSA_PYTHON_MIN="[^"]*"$', text, re.M)
    else:
        m = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not m:
        raise SystemExit(f"could not find {name} in {source.name}")
    return m.group(0)


def floor() -> tuple[int, ...]:
    raw = extract(AI, "CSA_PYTHON_MIN").split('"')[1]
    return tuple(int(p) for p in raw.split("."))


def bash(body: str, *, path: str | None = None) -> tuple[str, int]:
    script = "#!/usr/bin/env bash\nset -euo pipefail\n" + body
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(script)
        name = fh.name
    env = {"PATH": path or os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/tmp")}
    # bash by absolute path, so a stub-only PATH controls what the SCRIPT resolves without
    # also hiding the interpreter running it.
    p = subprocess.run(["/bin/bash", name], capture_output=True, text=True, env=env)
    return (p.stdout + p.stderr).strip(), p.returncode


# Every name find_usable_python probes. Each case below stubs ALL of them, so a real
# python3.12 sitting in /usr/bin on the CI runner cannot leak into a case meant to have none.
PROBED = ["python3", "python3.14", "python3.13", "python3.12", "python3.11", "python3.10"]


def stub_dir(tmp: pathlib.Path, good: set[str], present: list[str] | None = None) -> str:
    """Fake interpreters; `good` clears the floor, everything else in `present` does not.
    python_meets_floor only reads the exit status, so a two-line shell script is a faithful
    stand-in and keeps this test identical on macOS and Linux."""
    tmp.mkdir(parents=True, exist_ok=True)
    for cmd in (PROBED if present is None else present):
        f = tmp / cmd
        f.write_text("#!/bin/sh\nexit %d\n" % (0 if cmd in good else 1))
        f.chmod(0o755)
    return str(tmp)


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    min_v = floor()
    print(f"\nfloor declared by the script: {'.'.join(map(str, min_v))}")
    check(min_v >= (3, 10), "floor is at least 3.10 (what csa-google-workspace requires)")

    # ---- python_meets_floor, against real interpreters ----
    print("\npython_meets_floor vs. real interpreters")
    body = extract(AI, "CSA_PYTHON_MIN") + "\n" + extract(AI, "python_meets_floor")
    candidates = ["/usr/bin/python3", sys.executable]
    for name in ("python3", "python3.9", "python3.10", "python3.11", "python3.12", "python3.13"):
        from shutil import which
        found = which(name)
        if found:
            candidates.append(found)

    tested = 0
    for path in dict.fromkeys(candidates):
        if not os.path.exists(path):
            continue
        real = subprocess.run([path, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                              capture_output=True, text=True)
        if real.returncode != 0:
            continue
        actual = tuple(int(p) for p in real.stdout.strip().split("."))
        expected = actual >= min_v
        _, rc = bash(f'{body}\nif python_meets_floor "{path}"; then exit 0; else exit 1; fi')
        check((rc == 0) == expected,
              f"{path} is {'.'.join(map(str, actual))} -> {'accepts' if expected else 'rejects'}")
        tested += 1
        # The exact case from the report.
        if path == "/usr/bin/python3" and actual < (3, 10):
            check(rc != 0, f"THE #53 CASE: stock macOS /usr/bin/python3 {'.'.join(map(str, actual))} is rejected")
    check(tested > 0, "at least one real interpreter was exercised")

    # ---- find_usable_python selection, with stubs ----
    print("\nfind_usable_python selection")
    sel = body + "\n" + extract(AI, "find_usable_python")
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)

        # A stock Mac: python3 is too old, nothing else present.
        p = stub_dir(base / "stock", good=set())
        out, rc = bash(f"{sel}\nfind_usable_python", path=p)
        check(rc != 0, "only-an-old-python3 (stock Mac) -> reports nothing usable")

        # The case the naive fix would get wrong: a good interpreter beside the old one,
        # not first on PATH. Must be found rather than trigger a redundant install.
        p = stub_dir(base / "beside", good={"python3.12"})
        out, rc = bash(f"{sel}\nfind_usable_python", path=p)
        check(rc == 0 and out.endswith("python3.12"),
              f"old python3 + good python3.12 beside it -> picks python3.12 (got {out!r})")

        # Fast path: python3 itself is fine.
        p = stub_dir(base / "fine", good={"python3", "python3.12"})
        out, rc = bash(f"{sel}\nfind_usable_python", path=p)
        check(rc == 0 and out.endswith("python3"), f"good python3 -> picks it first (got {out!r})")

        # Nothing at all.
        p = stub_dir(base / "empty", good=set(), present=[])
        out, rc = bash(f"{sel}\nfind_usable_python", path=p)
        check(rc != 0, "no python at all -> reports nothing usable")

    # ---- node_meets_floor ----
    print("\nnode_meets_floor")
    nf = extract(AI, "node_meets_floor")
    check(nf == extract(WORK, "node_meets_floor"),
          "node_meets_floor is identical in both scripts")
    with tempfile.TemporaryDirectory() as td:
        for version, expected in [("v18.20.4", False), ("v20.0.0", True), ("v24.1.0", True),
                                  ("v16.20.0", False), ("", False), ("garbage", False)]:
            d = pathlib.Path(td) / f"n{version or 'empty'}".replace(".", "_")
            d.mkdir(parents=True, exist_ok=True)
            f = d / "node"
            f.write_text(f"#!/bin/sh\necho '{version}'\n")
            f.chmod(0o755)
            _, rc = bash(f"{nf}\nif node_meets_floor; then exit 0; else exit 1; fi",
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
