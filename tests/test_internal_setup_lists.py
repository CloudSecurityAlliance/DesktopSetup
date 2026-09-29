#!/usr/bin/env python3
"""The internal-setup list is copied into six scripts, and it has drifted twice.

`setup_csa_internal_tools` names one setup script per internal MCP server. It exists in all
three macOS scripts and all three Windows scripts, as six separate copies, with a comment
saying to keep them in sync — which is a request, not a mechanism. The request has been
declined twice:

    #85  fix: the Gmail/Calendar setup belongs in all five lists, not four
    #92  feat: csa-zendesk joins the internal setup lists

Both were found by somebody noticing a server was missing, which is the expensive way. The
failure is silent by construction: the loop does `continue` on a script it cannot fetch —
deliberately, so one absent server does not stop the ones after it — so a name that is
missing from a list produces no output at all. A person whose Mac got four servers and whose
Windows box got three has nothing to read that says so.

**What this cannot check.** The lists name files in CloudSecurityAlliance-Internal/CSA-Plugins,
which is private and not available here. So this asserts the six copies agree with each other;
it cannot tell you they agree with the gate repo. That is the same split as everywhere else -
internal consistency is cheap and mechanical, external truth needs the other system - and it
is worth saying out loud rather than letting the green tick imply more than it checked.

    python3 tests/test_internal_setup_lists.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: The six copies, by the extension the names inside them must carry. A script added to this
#: repo that holds a seventh copy is caught by `test_every_copy_is_listed_here` below.
COPIES = {
    "scripts/macos-ai-tools.sh": "sh",
    "scripts/macos-plugins.sh": "sh",
    "scripts/macos-update.sh": "sh",
    "scripts/windows-ai-tools.ps1": "ps1",
    "scripts/windows-plugins.ps1": "ps1",
    "scripts/windows-update.ps1": "ps1",
}

failures: list[str] = []


def check(ok: bool, label: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok:
        failures.append(label)


def servers_in(path: pathlib.Path) -> list[str]:
    """The server names one copy lists, in order, stripped of extension.

    Order is kept because these run in sequence and the order is a UX decision - the Google
    servers first because most people have those - not an implementation detail.
    """
    text = path.read_text(encoding="utf-8")
    block = re.search(r"setups\s*=\s*[\(@]\(?(.*?)\)", text, re.S)
    if not block:
        return []
    names = re.findall(r"csa-([a-z0-9-]+)-setup\.(?:sh|ps1)", block.group(1))
    return names


def extensions_in(path: pathlib.Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    block = re.search(r"setups\s*=\s*[\(@]\(?(.*?)\)", text, re.S)
    if not block:
        return set()
    return set(re.findall(r"csa-[a-z0-9-]+-setup\.(sh|ps1)", block.group(1)))


def main() -> int:
    print("Internal-setup lists\n")

    lists = {name: servers_in(ROOT / name) for name in COPIES}

    # The potency guard, first. A regex that silently stopped matching would make every
    # comparison below pass by comparing six empty lists - which is the exact way a census
    # becomes decorative, and it costs one assertion to rule out.
    for name, servers in lists.items():
        check(len(servers) >= 2, f"{name}: found {len(servers)} servers (extraction works)")

    print()
    reference = lists["scripts/macos-ai-tools.sh"]
    for name, servers in lists.items():
        check(servers == reference,
              f"{name}: same servers, same order as macos-ai-tools.sh"
              + ("" if servers == reference
                 else f" — has {servers}, expected {reference}"))

    print()
    for name, want in COPIES.items():
        got = extensions_in(ROOT / name)
        check(got == {want},
              f"{name}: names carry .{want}" + ("" if got == {want} else f" — found {got or 'none'}"))

    print()
    # Fail-closed on a SEVENTH copy. The list was duplicated once and then again; a script
    # added later that carries its own copy must land here rather than quietly going stale,
    # because nothing about a missing server is visible at run time.
    holders = sorted(
        str(p.relative_to(ROOT))
        for p in (ROOT / "scripts").glob("*")
        if p.suffix in {".sh", ".ps1"} and "setup_csa_internal_tools" in p.read_text(encoding="utf-8")
    )
    check(holders == sorted(COPIES),
          "every script holding the list is checked here"
          + ("" if holders == sorted(COPIES)
             else f" — untracked: {sorted(set(holders) - set(COPIES))}"))

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print(f"all checks passed — {len(reference)} servers, six copies in agreement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
