#!/usr/bin/env python3
"""TODO.md must cite code by function name, and every cited function must still exist.

The audit findings in TODO.md were originally cited as `file:line`. Within seven months every
one of them had rotted: C2 pointed 243 lines away from the pip loop it describes, at a comment
about `sed` versus `grep -v` — also about shell quoting, so it looked right, which is worse than
a citation that is obviously wrong. H5 pointed 877 lines off. A line number is a duplicated fact
with no check behind it, and it goes stale on the first unrelated edit above it.

A function name survives those edits, and unlike a line number it can be verified. So two rules:

  1. No `file.sh:123` citations anywhere in TODO.md. This is the mechanism that rotted, so it is
     refused outright rather than checked for accuracy.
  2. In each finding's citation — the parenthetical right after its bold title — every name that
     looks like a function must be defined: in each script the citation lists, or, when it lists
     none ("all three scripts, `ensure_brew_in_path`"), in at least one script. A rename or a
     removal then fails here instead of leaving a finding pointing at nothing.

Rule 2 is also how re-anchoring found H5 already fixed while still marked open: locating the code
to cite it showed the code had changed. This check cannot tell whether a finding is still true —
only that what it cites still exists — but it keeps the citations navigable, which is what makes
checking by hand cheap.

Self-tests before it reports, on a fixture it must fail: a checker that cannot detect a bad
citation would print "all citations resolve" forever and be believed.

    python3 tools/check-todo-citations.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODO = ROOT / "TODO.md"
SCRIPTS = ROOT / "scripts"

LINE_CITE = re.compile(r"`([A-Za-z0-9._-]+\.(?:sh|ps1)):\d")
# A finding: optional checkbox, bold title, then its citation in the first parenthetical.
FINDING = re.compile(r"^- (?:\[[ x]\] )?\*\*([^*]+)\*\*\s*\(([^)]*)\)", re.M)
TICKED = re.compile(r"`([^`]+)`")
SCRIPT_NAME = re.compile(r"^[A-Za-z0-9._-]+\.(?:sh|ps1)$")
BASH_FUNC = re.compile(r"^[a-z_][a-z0-9_]*$")
PS_FUNC = re.compile(r"^[A-Z][A-Za-z0-9]*-[A-Za-z0-9]+$")


def defined(name: str, script: pathlib.Path) -> bool:
    text = script.read_text(encoding="utf-8")
    if script.suffix == ".ps1":
        return re.search(rf"^\s*function\s+{re.escape(name)}\b", text, re.M | re.I) is not None
    return re.search(rf"^\s*{re.escape(name)}\(\)\s*\{{", text, re.M) is not None


def problems(todo: str, scripts: dict[str, pathlib.Path]) -> list[str]:
    found = []
    for m in LINE_CITE.finditer(todo):
        line = todo.count("\n", 0, m.start()) + 1
        found.append(f"TODO.md:{line}: line-number citation into {m.group(1)} — cite a function name")

    for m in FINDING.finditer(todo):
        title, citation = m.group(1).strip(), m.group(2)
        names = TICKED.findall(citation)
        files = [n for n in names if SCRIPT_NAME.match(n)]
        funcs = [n for n in names if not SCRIPT_NAME.match(n)
                 and (BASH_FUNC.match(n) or PS_FUNC.match(n))]
        for f in files:
            if f not in scripts:
                found.append(f"{title}: cites `{f}`, which does not exist in scripts/")
        present = [scripts[f] for f in files if f in scripts]
        for fn in funcs:
            if present:
                missing = [p.name for p in present if not defined(fn, p)]
                if missing:
                    found.append(f"{title}: `{fn}` is not defined in {', '.join(missing)}")
            elif not any(defined(fn, p) for p in scripts.values()):
                found.append(f"{title}: `{fn}` is not defined in any script")
    return found


SELF_TEST_TODO = """\
- [ ] **X1 — a line number** (`macos-update.sh:274`)
- [ ] **X2 — a function that is gone** (`macos-update.sh`, `no_such_function_here`)
- [ ] **X3 — a script that is gone** (`macos-nonexistent.sh`, `update_pip`)
- [ ] **X4 — correct, must NOT be reported** (`macos-update.sh`, `update_pip`)
"""


def self_test(scripts: dict[str, pathlib.Path]) -> None:
    got = problems(SELF_TEST_TODO, scripts)
    expect = {"line-number citation", "no_such_function_here", "macos-nonexistent.sh"}
    caught = {e for e in expect if any(e in g for g in got)}
    false_positive = [g for g in got if "X4" in g]
    if caught != expect or false_positive:
        print("SELF-TEST FAILED — this check cannot be trusted:")
        print(f"  expected to catch: {sorted(expect)}")
        print(f"  actually caught:   {sorted(caught)}")
        if false_positive:
            print(f"  wrongly reported a correct citation: {false_positive}")
        sys.exit(2)


def main() -> int:
    scripts = {p.name: p for p in sorted(SCRIPTS.iterdir()) if p.suffix in (".sh", ".ps1")}
    self_test(scripts)

    if not TODO.is_file():
        print(f"no such file: {TODO}")
        return 1
    todo = TODO.read_text(encoding="utf-8")
    found = problems(todo, scripts)
    cited = len(FINDING.findall(todo))
    if found:
        for p in found:
            print(p)
        print(f"\n{len(found)} citation problem(s) across {cited} finding(s).")
        return 1
    print(f"all {cited} finding citations resolve to functions that exist; no line numbers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
