#!/usr/bin/env python3
"""Fail if a function duplicated across installer scripts has drifted.

Why this exists rather than a shared library: every script here is an entry point run as
`curl … | bash` or `irm … | iex`, so each must be self-contained — there is no sibling file to
source, and inlining a remote library would make the scripts unauditable (you could no longer
read one and know everything it does). Duplication is therefore deliberate. Silent *divergence*
is not.

`CLAUDE.md` has long said "when changing shared logic, update all files that use it". That is a
manual discipline, and by the time this was written twelve functions had quietly drifted anyway.
This turns the discipline into a check.

Comparison ignores comments, blank lines and whitespace, so reformatting or documenting one copy
is free; only a behavioural difference fails.

    python3 tools/check-duplication.py           # report and exit non-zero on drift
    python3 tools/check-duplication.py --diff     # also print the differences
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import pathlib
import re
import sys
from collections import defaultdict

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

# Functions that are *meant* to differ per script, with the reason. Anything not listed here
# must be identical everywhere it appears — adding a name to this list is a deliberate act,
# which is the point.
PER_SCRIPT = {
    "main": "each script's top-level flow is its whole purpose",
    "Main": "each script's top-level flow is its whole purpose",
    "preflight": "each script previews the steps it actually runs",
    "Show-Preflight": "each script previews the steps it actually runs",
    "summary": "each script summarises what it did",
    "Show-Summary": "each script summarises what it did",
    "Test-Preconditions": "the plugin-only script needs fewer preconditions than the full one",
    "sync_plugin_marketplaces": "macos-update.sh additionally runs `claude plugin marketplace "
                                "update`, which is that script's whole purpose; the installers "
                                "only register what is missing",
}

FUNC_SH = re.compile(r"^([a-z_][a-z0-9_]*)\(\)\s*\{", re.M)
FUNC_PS = re.compile(r"^function\s+([A-Za-z][A-Za-z-]*)\s*\{", re.M)


def functions(path: pathlib.Path) -> dict[str, str]:
    """Function name -> source, delimited by brace matching.

    Brace matching rather than "up to the next definition": the naive version sweeps up the
    comments and constants that sit between functions, which reports drift that is not there.
    That mistake was made first, and it inflated the count from 12 to 38.
    """
    text = path.read_text(errors="replace")
    pattern = FUNC_PS if path.suffix == ".ps1" else FUNC_SH
    found: dict[str, str] = {}
    for match in pattern.finditer(text):
        depth, i = 0, match.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        found[match.group(1)] = text[match.start():i + 1]
    return found


def behaviour(source: str) -> list[str]:
    """The lines that matter: no comments, no blanks, whitespace collapsed."""
    out = []
    for line in source.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            out.append(re.sub(r"\s+", " ", stripped))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--diff", action="store_true", help="print the differences too")
    args = parser.parse_args()

    catalogue: dict[tuple[str, str], dict[str, list[str]]] = defaultdict(dict)
    for path in sorted(SCRIPTS.iterdir()):
        if path.suffix not in (".sh", ".ps1"):
            continue
        for name, source in functions(path).items():
            catalogue[(path.suffix, name)][path.name] = behaviour(source)

    shared = {key: found for key, found in catalogue.items() if len(found) > 1}
    problems = []
    checked = 0

    for (suffix, name), where in sorted(shared.items()):
        if name in PER_SCRIPT:
            continue
        checked += 1
        variants: dict[str, list[str]] = defaultdict(list)
        for script, lines in where.items():
            variants[hashlib.sha256("\n".join(lines).encode()).hexdigest()[:8]].append(script)
        if len(variants) == 1:
            continue
        problems.append((suffix, name, variants, where))

    print(f"{len(shared)} function(s) appear in more than one script")
    allowed = PER_SCRIPT.keys() & {name for _, name in shared}
    print(f"  {len(allowed)} allowed to differ (see PER_SCRIPT)")
    print(f"  {checked} must match; {len(problems)} have drifted\n")

    for suffix, name, variants, where in problems:
        print(f"DRIFT  {name}{suffix} — {len(variants)} variants")
        for digest, scripts in variants.items():
            print(f"         {digest}  {', '.join(sorted(scripts))}")
        if args.diff:
            groups = sorted(variants.items(), key=lambda kv: sorted(kv[1]))
            first = sorted(groups[0][1])[0]
            for _, scripts in groups[1:]:
                other = sorted(scripts)[0]
                for line in difflib.unified_diff(where[first], where[other],
                                                 first, other, lineterm="", n=1):
                    print(f"         {line}")
        print()

    if problems:
        print("Reconcile them, or add the name to PER_SCRIPT with a reason if the difference "
              "is deliberate.")
        return 1
    print("no drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
