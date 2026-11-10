#!/usr/bin/env python3
"""The CSA Python pin is declared in six scripts, and until now only two of them declared it.

`CSA_PYTHON_PREFERRED` (`$CsaPythonPreferred` on Windows) says which interpreter a fresh
machine gets, and is handed to the private gate repo's setup scripts so their
`uv tool install --python` lands the server on it. Only the two `*-ai-tools` scripts defined
it. `macos-update.sh` and `macos-plugins.sh` passed `"${CSA_PYTHON_PREFERRED:-}"` (empty) and
`windows-update.ps1` / `windows-plugins.ps1` assigned `$CsaPythonPreferred`, a variable they
never defined, so a person who ran `-update` or `-plugins` got whatever the gate script's own
fallback was. Nothing failed; the interpreter was simply guessed.

This pins:
  * all six scripts declare the preferred Python exactly once, and all six agree;
  * the floor (`CSA_PYTHON_MIN` / `$CsaPythonMin`) agrees across platforms;
  * every `CSA_DOC_PY_DEPS=(...)` copy in `scripts/*.sh` is identical (it is an array, not a
    function, so `tools/check-duplication.py` does not cover it).

What it cannot check: that 3.14 is the right number. That is a decision (the constants are
pinned below), not something a script can derive.

    python3 tests/test_python_pins.py
    python3 tests/test_python_pins.py --self-test
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

WANT = "3.14"

SH = ["scripts/macos-ai-tools.sh", "scripts/macos-plugins.sh", "scripts/macos-update.sh"]
PS1 = ["scripts/windows-ai-tools.ps1", "scripts/windows-plugins.ps1", "scripts/windows-update.ps1"]
SIX = SH + PS1

# An assignment, not a mention: anchored at line start so `$env:CSA_PYTHON_PREFERRED = ...`,
# `CSA_NESTED=1 CSA_PYTHON_PREFERRED="${...}"` and comments do not count.
PREFERRED_RE = {
    "sh": re.compile(r'^CSA_PYTHON_PREFERRED="([^"]*)"', re.M),
    "ps1": re.compile(r"^\$CsaPythonPreferred\s*=\s*'([^']*)'", re.M),
}
MIN_RE = {
    "sh": re.compile(r'^CSA_PYTHON_MIN="([^"]*)"', re.M),
    "ps1": re.compile(r"^\$CsaPythonMin\s*=\s*'([^']*)'", re.M),
}
# Tolerates indentation and a `local` / `readonly` / `declare -a` prefix, so a copy moved
# inside a function is still found rather than silently ignored.
DEPS_RE = re.compile(
    r"^[ \t]*(?:(?:local|readonly|declare(?:\s+-[a-zA-Z]+)*)\s+)?CSA_DOC_PY_DEPS=\(([^)]*)\)", re.M)


def kind(name: str) -> str:
    return "ps1" if name.endswith(".ps1") else "sh"


def load() -> dict[str, str]:
    return {n: (ROOT / n).read_text(encoding="utf-8") for n in SIX}


def preferred_problems(texts: dict[str, str]) -> list[str]:
    """One message per script that does not declare exactly one preferred Python equal to WANT."""
    out = []
    for name, text in texts.items():
        found = PREFERRED_RE[kind(name)].findall(text)
        if len(found) != 1:
            out.append(f"{name}: {len(found)} declarations of the preferred Python, expected 1")
        elif found[0] != WANT:
            out.append(f"{name}: preferred Python is {found[0]!r}, expected {WANT!r}")
    return out


def min_problems(texts: dict[str, str]) -> list[str]:
    """The floor must be declared and agree across the platforms that declare it."""
    seen = {}
    for name, text in texts.items():
        found = MIN_RE[kind(name)].findall(text)
        if found:
            seen[name] = found[0]
    out = []
    for label, group in (("macOS", SH), ("Windows", PS1)):
        if not any(n in seen for n in group):
            out.append(f"{group[0]}: no {label} script declares the minimum Python")
    if len(set(seen.values())) > 1:
        out.append(f"the minimum Python differs between scripts: {seen}")
    for name, value in seen.items():
        if value != WANT:
            out.append(f"{name}: minimum Python is {value!r}, expected {WANT!r}")
    return out


def deps_problems(texts: dict[str, str]) -> list[str]:
    """Every CSA_DOC_PY_DEPS copy must be identical. Vacuous with one copy, by design."""
    copies = {}
    for name, text in texts.items():
        for m in DEPS_RE.finditer(text):
            copies.setdefault(name, []).append(m.group(1).split())
    out = []
    flat = [(n, c) for n, cs in copies.items() for c in cs]
    if flat:
        ref_name, ref = flat[0]
        for name, c in flat[1:]:
            if c != ref:
                out.append(f"{name}: CSA_DOC_PY_DEPS is {c}, but {ref_name} has {ref}")
    return out


def run_checks(texts: dict[str, str]) -> list[str]:
    return preferred_problems(texts) + min_problems(texts) + deps_problems(texts)


def self_test() -> int:
    """Break the rules on purpose and prove each break is reported, by file."""
    texts = load()
    if run_checks(texts):
        print("self-test cannot start: the real scripts already fail")
        return 1
    ok = True

    def expect(label: str, problems: list[str], names: list[str]) -> None:
        nonlocal ok
        missing = [n for n in names if not any(p.startswith(n) for p in problems)]
        good = bool(problems) and not missing
        print(f"  {'ok  ' if good else 'FAIL'}  {label}" + ("" if good else f" - unreported: {missing or 'anything'}"))
        ok = ok and good

    mutated = dict(texts)
    mutated[SH[0]] = PREFERRED_RE["sh"].sub('CSA_PYTHON_PREFERRED="3.15"', mutated[SH[0]])
    mutated[PS1[1]] = PREFERRED_RE["ps1"].sub("# removed", mutated[PS1[1]])
    expect("a 3.15 copy and a deleted copy are both reported, by file",
           preferred_problems(mutated), [SH[0], PS1[1]])

    mutated = dict(texts)
    mutated[PS1[0]] = MIN_RE["ps1"].sub("$CsaPythonMin = '3.13'", mutated[PS1[0]])
    expect("a floor that differs across platforms is reported",
           min_problems(mutated), [PS1[0]])

    mutated = dict(texts)
    mutated[SH[0]] = MIN_RE["sh"].sub("# removed", mutated[SH[0]])
    expect("a platform with no floor declared is reported",
           min_problems(mutated), [SH[0]])

    mutated = dict(texts)
    real = DEPS_RE.search(mutated[SH[0]]).group(0)
    mutated[SH[1]] = mutated[SH[1]] + "\n" + real.replace("pymupdf", "pymupdf2") + "\n"
    expect("two CSA_DOC_PY_DEPS copies that differ are reported",
           deps_problems(mutated), [SH[1]])

    mutated = dict(texts)
    mutated[SH[2]] = mutated[SH[2]] + "\nf() {\n    local CSA_DOC_PY_DEPS=(pyyaml other)\n}\n"
    ref = DEPS_RE.search(mutated[SH[0]]).group(0)
    mutated[SH[1]] = mutated[SH[1]] + "\nf() {\n    " + ref + "\n}\n"
    expect("an indented or local copy with different contents is found and reported",
           deps_problems(mutated), [SH[2]])

    print("self-test " + ("passed" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    print("CSA Python pins\n")
    texts = load()
    failures = []
    for label, fn in [
        (f"all six scripts declare the preferred Python exactly once, as {WANT}", preferred_problems),
        ("the minimum Python agrees across platforms", min_problems),
        ("every CSA_DOC_PY_DEPS copy is identical", deps_problems),
    ]:
        problems = fn(texts)
        print(f"  {'ok  ' if not problems else 'FAIL'}  {label}")
        for p in problems:
            print(f"        {p}")
        failures += problems
    print()
    if failures:
        print(f"FAILED: {len(failures)} problem(s)")
        return 1
    n = sum(len(DEPS_RE.findall(t)) for t in texts.values())
    print(f"all checks passed - six scripts, {n} CSA_DOC_PY_DEPS copy(ies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
