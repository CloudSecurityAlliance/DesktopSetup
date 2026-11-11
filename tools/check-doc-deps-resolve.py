#!/usr/bin/env python3
"""Fail if the document deps `~/.default_venv` gets would bring in onnxruntime, resolved for real.

Why: onnxruntime's official macOS and Linux builds (1.29 on) ship Microsoft 1DS telemetry that is
ON by default - a device id and an event cache under
`~/Library/Application Support/Microsoft/DeveloperTools/.onnxruntime`, uploaded to
`mobile.events.data.microsoft.com` - and only `ORT_DISABLE_TELEMETRY=1`, set before it loads,
turns it off. Two routes in were found by #179's final review (2026-11-10):

  * `pymupdf` unpinned resolves to 2.x, which requires onnxruntime, pymupdf-layout and
    pymupdf4llm unconditionally (and has no macOS x86_64 wheel). `CSA_DOC_PY_DEPS` pins it
    below 2; 1.28.2 has no dependencies.
  * `markitdown` -> `magika` -> onnxruntime. It is no longer installed.

`tests/test_python_pins.py` checks the text of the scripts. Only a resolver can say what a list
of names actually pulls in today, so this runs `uv pip compile` on `CSA_DOC_PY_DEPS`, as each
script declares it, three ways:

  * `--universal`, so a dependency behind any platform marker counts;
  * Apple silicon, macOS 15 (`MACOSX_DEPLOYMENT_TARGET`: uv's default target for
    aarch64-apple-darwin is older than onnxruntime's macOS 14 wheels, so without it uv quietly
    backtracks to pymupdf 1.x and the old, unpinned list looks clean - measured);
  * Intel macOS, which must still resolve at all.

Each must succeed and must not contain onnxruntime.

Needs `uv` and PyPI. Without uv, or when PyPI cannot be reached, it exits 77 (skipped) - unless
CSA_TEST_REQUIRE_REAL_UV is set, as `.github/workflows/doc-deps.yml` sets it, where a skip is a
failure. That workflow runs on pull requests touching the two scripts, this tool or itself, and
weekly, because the answer can change upstream with no change here. It is kept out of lint.yml
so a PyPI outage cannot hide the other jobs' results.

`--self-test` expires the day unpinned pymupdf stops requiring onnxruntime: then the 495ad6b list
resolves clean and the self-test fails. That is the signal to revisit the pymupdf<2 pin and this
guard, not a CI bug.

    python3 tools/check-doc-deps-resolve.py
    python3 tools/check-doc-deps-resolve.py --self-test        # the 495ad6b list must fail
    python3 tools/check-doc-deps-resolve.py --script <file>    # check another copy of a script
"""
from __future__ import annotations

import argparse
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = [ROOT / "scripts" / "macos-ai-tools.sh", ROOT / "scripts" / "macos-update.sh"]
PY = "3.14"
FORBIDDEN = ("onnxruntime",)
# (label, extra uv arguments, extra environment)
TARGETS = [
    ("universal", ["--universal"], {}),
    ("Apple silicon, macOS 15", ["--python-platform", "aarch64-apple-darwin"],
     {"MACOSX_DEPLOYMENT_TARGET": "15.0"}),
    ("Intel macOS", ["--python-platform", "x86_64-apple-darwin"], {}),
]
# The array as it stood at 495ad6b, the commit the final review found the defect in.
DEFECT_495AD6B = ["pyyaml", "pymupdf", "csa-google-workspace"]
DEPS_RE = re.compile(r"^CSA_DOC_PY_DEPS=\(([^)]*)\)$", re.M)
SKIP = 77


def deps_of(text: str) -> list[str] | None:
    """The array's elements as bash reads them (shlex in POSIX mode does the quoting the same way
    for a plain literal like this one)."""
    m = DEPS_RE.search(text)
    return shlex.split(m.group(1)) if m else None


def pins(output: str) -> dict[str, str]:
    """name -> version from `uv pip compile --no-annotate --no-header` output."""
    out = {}
    for line in output.splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"([A-Za-z0-9._-]+)==(\S+)", line)
        if m:
            out[re.sub(r"[-_.]+", "-", m.group(1)).lower()] = m.group(2)
    return out


def compile_deps(uv: str, deps: list[str], args: list[str], env_extra: dict[str, str],
                 work: pathlib.Path) -> subprocess.CompletedProcess:
    req = work / "requirements.in"
    req.write_text("\n".join(deps) + "\n", encoding="utf-8")
    env = dict(os.environ)
    env.update({"UV_CACHE_DIR": str(work / "uv-cache"), "UV_NO_CONFIG": "1",
                "UV_PYTHON_DOWNLOADS": "never"})
    env.update(env_extra)
    return subprocess.run([uv, "pip", "compile", "--quiet", "--no-header", "--no-annotate",
                           "--python-version", PY, *args, str(req)],
                          capture_output=True, text=True, env=env, timeout=300)


def reachable(uv: str, work: pathlib.Path) -> bool:
    """Can uv resolve anything at all? Tells "PyPI is unreachable" (skip) from "this list does
    not resolve" (fail)."""
    return compile_deps(uv, ["pyyaml"], ["--universal"], {}, work).returncode == 0


def problems_for(uv: str, deps: list[str], work: pathlib.Path) -> list[str]:
    out = []
    for label, args, env_extra in TARGETS:
        p = compile_deps(uv, deps, args, env_extra, work)
        if p.returncode != 0:
            out.append(f"{label}: does not resolve: {p.stderr.strip()[-400:]}")
            continue
        got = pins(p.stdout)
        for name in FORBIDDEN:
            if name in got:
                via = ", ".join(f"{n}=={v}" for n, v in sorted(got.items()) if n.startswith("pymupdf"))
                out.append(f"{label}: brings in {name}=={got[name]} (resolved: {via or 'no pymupdf'})")
        print(f"    {label}: " + ", ".join(f"{n}=={v}" for n, v in sorted(got.items())
                                          if n.startswith(("pymupdf", "pyyaml", "csa-"))))
    return out


def unavailable(reason: str) -> int:
    if os.environ.get("CSA_TEST_REQUIRE_REAL_UV"):
        print(f"FAILED: CSA_TEST_REQUIRE_REAL_UV is set, but {reason}")
        return 1
    print(f"SKIP: {reason}")
    return SKIP


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--script", action="append", type=pathlib.Path)
    a = ap.parse_args()

    uv = shutil.which("uv")
    if not uv:
        return unavailable("there is no uv on PATH")
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        if not reachable(uv, work):
            return unavailable("uv cannot resolve even pyyaml (no network, or PyPI is unreachable)")

        if a.self_test:
            print(f"self-test: the list at 495ad6b, {DEFECT_495AD6B}, must be reported")
            found = problems_for(uv, DEFECT_495AD6B, work)
            for f in found:
                print(f"    reported: {f}")
            good = any("onnxruntime" in f for f in found)
            print("self-test " + ("passed" if good else "FAILED: the defect was not reported"))
            return 0 if good else 1

        lists: dict[tuple[str, ...], list[str]] = {}
        for path in a.script or SCRIPTS:
            deps = deps_of(path.read_text(encoding="utf-8"))
            if deps is None:
                print(f"FAILED: {path} declares no CSA_DOC_PY_DEPS=(...)")
                return 1
            lists.setdefault(tuple(deps), []).append(path.name)
        failures = []
        for deps, names in lists.items():
            print(f"  {', '.join(names)}: {list(deps)}")
            for f in problems_for(uv, list(deps), work):
                failures.append(f"{', '.join(names)}: {f}")
    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        print(f"\nFAILED: {len(failures)} problem(s)")
        return 1
    print(f"all checks passed - the document deps resolve on Python {PY} without "
          f"{', '.join(FORBIDDEN)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
