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
    "Test-Preconditions": "the plugin-only script needs fewer preconditions than the full "
                          "one, and the updater fewer still - every Update-* returns early "
                          "when its tool is missing, so a missing winget is no reason to "
                          "refuse to update npm",
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
    text = path.read_text(encoding="utf-8")
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


def self_test() -> None:
    """Every rule broken on purpose. A check that has not been seen to fail proves nothing.

    #144: this checker went without one for its whole life, while holding 65 functions to a
    byte-identical contract across two platforms. #71 and #72 were both guards that ran,
    passed, and could not have failed; `check-powershell-native.py` self-tests because two
    separate bugs each turned it into a check that printed a clean bill of health no matter
    what.
    """
    # 1. Comments and whitespace are noise. That is the feature.
    a = 'f() {\n  echo hi\n}'
    b = 'f() {\n  # a comment nobody runs\n  echo    hi\n}'
    assert behaviour(a) == behaviour(b), "comments or whitespace are being treated as behaviour"

    # 2. A non-ASCII difference is NOT noise, and this is the hazard worth guarding. If the
    # read ever slips to `errors="replace"`, both of these decode to the same U+FFFD and
    # compare EQUAL - two functions that differ, reported identical, by the tool whose whole
    # job is catching silent drift.
    dot = 'f() {\n  echo "a \u00b7 b"\n}'
    dash = 'f() {\n  echo "a \u2014 b"\n}'
    assert behaviour(dot) != behaviour(dash), (
        "a non-ASCII difference is being collapsed; if this passes, two functions differing "
        "only in punctuation would compare equal"
    )

    # 3. The read is where that hazard lives, and no string-level test can reach it - so it is
    # asserted against this file's own source instead.
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    read_lines = [l for l in src.splitlines() if ".read_text(" in l and "__file__" not in l]
    assert read_lines, "no read_text call found to check"
    for line in read_lines:
        assert 'encoding="utf-8"' in line, f"read without an explicit utf-8 encoding: {line.strip()}"
        assert "errors=" not in line, (
            f"errors= on the read would decode cp1252 silently and substitute U+FFFD, making "
            f"property 2 above unprovable: {line.strip()}"
        )

    # 4. Brace matching, not "up to the next definition". The naive version swept up whatever
    # sat between functions and inflated the count from 12 to 38.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "x.sh"
        f.write_text('a() {\n  :\n}\n\n# a comment between\nCONST=1\n\nb() {\n  :\n}\n',
                     encoding="utf-8")
        got = functions(f)
        assert set(got) == {"a", "b"}, got
        assert "CONST" not in got["a"], "the body of `a` swept up what follows it"
        assert "comment between" not in got["a"], "the body of `a` swept up the comment after it"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--diff", action="store_true", help="print the differences too")
    args = parser.parse_args()

    # BEFORE reporting, not after. A clean bill of health from a check that cannot fail is
    # worse than no check, because it is believed.
    self_test()

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
    shared_names = {name for _, name in shared}
    allowed = PER_SCRIPT.keys() & shared_names
    print(f"  {len(allowed)} allowed to differ (see PER_SCRIPT)")

    # A stale exception is reported, not silently counted. `check-parity.py` already does this
    # for its own allowlist, for the reason that applies here unchanged: an exception for a
    # function that no longer appears in more than one script has stopped checking anything,
    # and it stopped without failing. Until #144 this was the only allowlist in tools/ that
    # could rot in silence.
    stale = sorted(PER_SCRIPT.keys() - shared_names)
    for name in stale:
        print(f"  STALE: PER_SCRIPT has {name!r}, which is not shared by more than one script "
              f"any more - remove it")
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
