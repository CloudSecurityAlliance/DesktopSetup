#!/usr/bin/env python3
"""Fail if an assignment from a *pipeline* is unguarded under `set -e` + `pipefail`.

This is issue #51, and it was not one bug — it was twelve.

    already_added="$(claude plugin marketplace list 2>/dev/null \\
      | sed -n 's/.*GitHub (\\([^)]*\\)).*/\\1/p')"

Under `set -o pipefail` the pipeline's status is the rightmost non-zero one, so a `claude` that
exits non-zero — which is exactly what a freshly installed, never-authenticated one does — makes
the *assignment* non-zero. An assignment is a simple command, not a condition, so `set -e` then
terminates the script. And `2>/dev/null` has already thrown away the reason, so the user sees a
bare `exit 1` with no error text whatsoever. That is precisely what #51 reported: the last line
printed was the previous step's, and nothing else.

The single-line calls in these scripts were already written `… 2>/dev/null || true`. Every
*multi-line piped* one had been written without a guard — same author, same day, same intent,
and the continuation is enough to make the missing `|| true` invisible when reading. Twelve of
them, across three scripts. That is what makes it worth a check rather than twelve fixes: the
shape recurs because it looks finished.

`2>/dev/null` is what makes this class so bad. It suppresses the diagnosis but not the
termination — the same trap as `2>$null` on the PowerShell side, documented in CLAUDE.md.

What counts as guarded: any `||` follow-on (`|| true`, `|| var=""`, `|| continue`, `|| return 0`),
or the assignment being a condition (`if x="$(…)"`, `while`, `&&`/`||` operands) — in those
positions `set -e` does not fire.

    python3 tools/check-pipeline-assignments.py
"""
from __future__ import annotations

import pathlib
import re
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent / "scripts"

# An assignment at statement position: optional `local `/`export `, a name, then ="$( … )"
ASSIGN = re.compile(r'^[ \t]*(?:local[ \t]+|export[ \t]+)?[A-Za-z_][A-Za-z0-9_]*=(["\']?)\$\(')
# Positions where set -e does not fire, so a bare assignment is fine there.
CONDITION = re.compile(r'^[ \t]*(?:if|elif|while|until|!)[ \t]|^[ \t]*(?:&&|\|\|)[ \t]')


def logical_lines(text: str) -> list[tuple[int, str]]:
    """Join backslash continuations, keeping the line number of the first physical line."""
    out: list[tuple[int, str]] = []
    buf, start = "", 0
    for n, line in enumerate(text.splitlines(), 1):
        if not buf:
            start = n
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        out.append((start, buf + stripped))
        buf = ""
    if buf:
        out.append((start, buf))
    return out


def offenders(path: pathlib.Path) -> list[tuple[int, str]]:
    text = path.read_text()
    # Only scripts that actually run under both settings can hit this.
    if "pipefail" not in text or "set -e" not in text.replace("set -euo", "set -e"):
        return []
    bad = []
    for lineno, line in logical_lines(text):
        if CONDITION.match(line) or not ASSIGN.match(line):
            continue
        body = line[line.index("$(") + 2:]
        # An `||` ANYWHERE in the logical line counts as a guard. Deliberately crude: these
        # are written both as `$(cmd | cmd)" || var=""` and as `$(cmd | cmd || true)"`, and a
        # checker that tries to tell those apart grows exceptions faster than it grows value.
        # One simple rule that is easy to satisfy beats a clever one people switch off.
        if "||" in body:
            continue
        # Pipes inside quotes are NOT shell pipelines - a `--jq '[.[] | select(...)]'` filter
        # is the common case here, and counting it produced two false positives on the first
        # run of this check. Blank quoted spans before looking.
        unquoted = re.sub(r"'[^']*'", "''", body)
        unquoted = re.sub(r'"[^"]*"', '""', unquoted)
        if "|" in unquoted:
            bad.append((lineno, line.strip()))
    return bad


FIXTURE_BAD = '''#!/usr/bin/env bash
set -euo pipefail
x="$(claude plugin marketplace list 2>/dev/null \\
  | sed -n 's/a/b/p')"
'''
FIXTURE_OK = '''#!/usr/bin/env bash
set -euo pipefail
x="$(claude plugin marketplace list 2>/dev/null \\
  | sed -n 's/a/b/p')" || x=""
if y="$(claude plugin list | grep -o a)"; then :; fi
z="$(brew list --versions pkg 2>/dev/null || true)"
# the two shapes that were false positives on this check's first run:
jq_filter="$(gh api user/emails --jq '[.[] | select(.primary==true)][0].email' 2>/dev/null || true)"
inner_guard=$(echo "$x" | python3 -c "import sys; print(sys.stdin.read())" 2>/dev/null || true)
'''


def self_test() -> None:
    """Run before reporting. A check that cannot fail is worse than no check, because it is
    believed — and the multi-line joining here is exactly the part that could silently stop
    matching, since that is what hid the bug from readers in the first place."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        bad = pathlib.Path(td) / "bad.sh"
        bad.write_text(FIXTURE_BAD)
        if not offenders(bad):
            raise SystemExit("SELF-TEST FAILED: the unguarded fixture was not flagged")
        ok = pathlib.Path(td) / "ok.sh"
        ok.write_text(FIXTURE_OK)
        found = offenders(ok)
        if found:
            raise SystemExit(f"SELF-TEST FAILED: guarded fixture flagged anyway: {found}")
    print("self-test: flags the unguarded multi-line pipeline; accepts `|| x=\"\"`, "
          "`if x=$(...)`, and `|| true`.")


def main() -> int:
    self_test()
    total = 0
    for path in sorted(SCRIPTS.glob("*.sh")):
        bad = offenders(path)
        print(f"{path.name}: {len(bad)} unguarded pipeline assignment(s)")
        for lineno, line in bad:
            print(f"    {path.name}:{lineno}: {line[:100]}")
        total += len(bad)
    print()
    if total:
        print(f"FAIL: {total} assignment(s) from a pipeline can kill the script under set -e.")
        print("Add a guard: `... )\" || var=\"\"` — an empty value is almost always the right")
        print("reading, and it keeps the failure from being fatal AND silent.")
        return 1
    print("no unguarded pipeline assignments.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
