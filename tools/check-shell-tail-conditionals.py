#!/usr/bin/env python3
"""Refuse `[[ cond ]] && cmd` in TAIL POSITION under `set -e`.

The trap, which cost a real user a broken install:

    install_1password_cli() {
      ...
      [[ "$before" != "$after" ]] && success "1Password CLI upgraded: $after"
    }

When nothing needed upgrading — the ordinary case — the test is false, so the `&&` chain
returns **1**. That is the last statement, so it becomes the function's exit status, and with
`set -euo pipefail` the entire script dies. Silently: nothing is printed, the exit code is 1,
and the run simply stops looking like it finished.

On macOS that killed everything after 1Password CLI: Claude Desktop, ChatGPT, Claude Code,
Codex, Gemini, the plugin marketplaces, all 40 plugins, and both MCP servers. It shipped as
part of a change whose only purpose was to make the output *quieter* — remediation is a change
like any other.

**Tail position, not every occurrence.** There are 60-odd `[[ ]] &&` lines across these scripts
and almost all are mid-block and harmless; flagging them would be a check that alarms on correct
behaviour, whose fix is deletion rather than muting. What matters is a conditional immediately
before a block terminator, where its status can become a function's return value.

The remedy is one token: `|| true`.
"""
from __future__ import annotations

import pathlib
import re
import sys

TERMINATORS = ("}", "fi", "else", "done", "esac", ";;")
CONDITIONAL = re.compile(r'^\[\[.*\]\]\s*&&')
# `continue`, `return` and `break` transfer control rather than falling through to the
# terminator, so the conditional's status never becomes the block's.
TRANSFERS = re.compile(r'&&\s*(continue|return|break)\b')

SELF_TEST = """\
bad() {
  [[ -n "$x" ]] && echo hi
}
good() {
  [[ -n "$x" ]] && echo hi || true
}
alsofine() {
  for i in 1 2; do
    [[ -n "$x" ]] && continue
  done
  return 0
}
"""


def offenders(text: str, name: str = "<text>") -> list[tuple[int, str]]:
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if line.strip() not in TERMINATORS:
            continue
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j < 0:
            continue
        stmt = lines[j].strip()
        if CONDITIONAL.match(stmt) and "||" not in stmt and not TRANSFERS.search(stmt):
            out.append((j + 1, stmt))
    return out


def self_test() -> None:
    """The check has to be seen to fail, or its passing means nothing."""
    found = offenders(SELF_TEST)
    assert len(found) == 1, f"self-test: expected exactly 1 offender, got {found}"
    assert "echo hi" in found[0][1], f"self-test: wrong line flagged: {found}"


def main(argv: list[str]) -> int:
    self_test()
    roots = [pathlib.Path(a) for a in argv[1:]] or [pathlib.Path(__file__).parent.parent / "scripts"]
    files: list[pathlib.Path] = []
    for root in roots:
        files.extend(sorted(root.glob("*.sh")) if root.is_dir() else [root])

    problems = 0
    for f in files:
        for line_no, stmt in offenders(f.read_text(), str(f)):
            print(f"{f}:{line_no}: `[[ ]] &&` in tail position — under `set -e` this returns 1 "
                  f"when the condition is false, which becomes the function's exit status and "
                  f"kills the script.\n    {stmt}\n    fix: append `|| true`")
            problems += 1
    if problems:
        print(f"\n{problems} tail-position conditional(s). Each one can silently end the run.")
        return 1
    print(f"no tail-position conditionals in {len(files)} script(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
