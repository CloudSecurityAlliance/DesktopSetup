#!/usr/bin/env python3
"""A script that changed must say so: its version has to move, and only forwards.

`main` is the release. Every documented one-liner fetches `HEAD`, and the internal-setup
fetch pins no ref either, so the version a script reports is the only way to know what a
person actually ran. When that version is stale, a debug log sent in to diagnose a problem
cannot answer the first question worth asking — did the fix reach you.

Measured 2026-10-01 on main, before this check existed: **six of ten scripts** reported a
version older than their own code, `windows-ai-tools.ps1` by five commits. Those five
included #104 (provision Python 3.14) and #105 (ChatGPT from the Store), i.e. exactly the
changes somebody would want to know had landed. The rule was already written down inside the
scripts —

    "update every file and bump each file's SCRIPT_VERSION / $ScriptVersion --
     otherwise the scripts will drift."

— and had been accurate and ignored since the day it was written, because nothing checked it
and a missed bump looks like nothing at all (#113).

Diff-scoped on purpose. It judges the change in front of it rather than re-litigating
history, so it lands green and fails only on a new omission.

Self-tests before it reports, on cases it must fail and cases it must pass.

    python3 tools/check-script-versions.py [--base <ref>]
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

VERSION = re.compile(r'(?:\$ScriptVersion\s*=\s*|SCRIPT_VERSION=)"(\d{4}\.\d+)"')


def version_of(text: str) -> str | None:
    m = VERSION.search(text)
    return m.group(1) if m else None


def _key(v: str) -> tuple[int, int]:
    year, rest = v.split(".", 1)
    return int(year), int(rest)


def problem(path: str, old_text: str | None, new_text: str) -> str | None:
    """None when the change is acceptable; otherwise the sentence to print."""
    new_v = version_of(new_text)
    if new_v is None:
        return f"{path}: no version variable — a run of this cannot say which code it is"
    if old_text is None:
        return None                      # new file; it has a version, nothing to move
    if old_text == new_text:
        return None                      # unchanged
    old_v = version_of(old_text)
    if old_v is None:
        return None                      # it only just acquired one; that is the fix
    if old_v == new_v:
        return (f"{path}: changed without bumping {new_v} — a log from this run would name "
                f"a version that is not this code")
    if _key(new_v) <= _key(old_v):
        return f"{path}: version went backwards, {old_v} -> {new_v}"
    return None


def self_test() -> None:
    """The check has to be seen to fail, or its passing means nothing."""
    ps_old = '$ScriptVersion = "2026.09160003"\nWrite-Host "a"\n'
    ps_new = '$ScriptVersion = "2026.09160003"\nWrite-Host "b"\n'
    ps_fix = '$ScriptVersion = "2026.10011200"\nWrite-Host "b"\n'
    sh_old = 'SCRIPT_VERSION="2026.09272200"\necho a\n'
    sh_new = 'SCRIPT_VERSION="2026.10011200"\necho b\n'

    assert problem("a.ps1", ps_old, ps_new), "missed a change with no bump"
    assert problem("a.ps1", ps_old, ps_fix) is None, "flagged a correct bump"
    assert problem("a.sh", sh_old, sh_new) is None, "flagged a correct bash bump"
    assert problem("a.ps1", ps_old, ps_old) is None, "flagged an unchanged file"
    assert problem("a.ps1", None, ps_old) is None, "flagged a new file"
    # Backwards, including the cross-month case the YYYY.MMDDHHMM form makes easy to get
    # wrong: 10011200 must compare GREATER than 09272200, not less.
    assert problem("a.sh", sh_new, sh_old), "missed a backwards version"
    assert _key("2026.10011200") > _key("2026.09272200"), "month rollover compares wrong"
    # A version-only change is a legitimate commit of its own.
    assert problem("a.ps1", ps_old, '$ScriptVersion = "2026.10011200"\nWrite-Host "a"\n') is None
    # A script with no version at all is a defect regardless of the diff.
    assert problem("a.ps1", ps_old, 'Write-Host "b"\n'), "missed a missing version"

    # SCOPE, asserted against this file's own source. `problem()` is a pure function and every
    # case above exercises it correctly - which is precisely why none of them noticed that
    # main() was asking git the wrong question. The diff was merge_base..HEAD, so uncommitted
    # edits were invisible, and locally that is the normal state: this printed "no scripts
    # changed", exited 0, and was a true statement about the empty set while two unbumped
    # scripts went on to fail this same check in CI.
    #
    # Re-adding HEAD would restore that silently, because every assertion above would still
    # pass. A git fixture would be the thorough version of this; this is the cheap one, and it
    # cannot rot because it reads the code it is about.
    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    # The needle includes `_git([` so this line does not match ITSELF. The first version
    # searched for the bare argument pair, found two lines - the call and this assertion - and
    # failed with "expected one changed-file diff, found 2". A check whose own text satisfies
    # its own search is a small, pure instance of the same trap as the rest.
    # The needle is ASSEMBLED rather than written out, so no single line of this file
    # contains it whole - including this one. Two earlier versions matched themselves and
    # failed with "expected one changed-file diff, found 2": the search string sat inside
    # the line doing the searching. A pure, miniature instance of the same trap.
    needle = '_git([' + '"diff", "--name-only"'
    diff_calls = [l for l in src.splitlines() if needle in l]
    assert len(diff_calls) == 1, f"expected one changed-file diff, found {len(diff_calls)}"
    assert '"HEAD"' not in diff_calls[0], (
        "the changed-file diff must NOT name HEAD: with it the comparison is commit-only and "
        "uncommitted edits - the local case - are invisible. Omitted, it compares against the "
        "working tree, and in CI the working tree equals HEAD anyway."
    )


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    root = pathlib.Path(__file__).resolve().parent.parent
    # encoding="utf-8" explicitly, NOT text=True. text=True decodes with the locale
    # encoding, which is cp1252 on a Windows dev box, and these scripts contain UTF-8
    # ("·", "—"). The first draft crashed with UnicodeDecodeError on `git show` — and it
    # would have passed in CI, where the runner is UTF-8, so the failure was reachable only
    # on the platform that ships least tested. Same local-vs-CI asymmetry as zendesk#66.
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          encoding="utf-8", errors="replace")


def main(argv: list[str]) -> int:
    self_test()
    base = None
    if "--base" in argv:
        base = argv[argv.index("--base") + 1]
    else:
        for candidate in ("origin/main", "main"):
            if _git(["rev-parse", "--verify", "--quiet", candidate]).returncode == 0:
                base = candidate
                break
    if base is None:
        # 77, not 0: a check that could not run has not passed. CI uses fetch-depth: 0 so
        # this does not silently become a no-op there.
        print("no base ref (origin/main or main) — skipping. In CI this means the checkout "
              "was shallow; set fetch-depth: 0.")
        return 77

    merge_base = _git(["merge-base", base, "HEAD"]).stdout.strip() or base
    # NO "HEAD" in this diff, deliberately. With it the comparison is merge_base..HEAD, which is
    # commit-only, and locally the edits are usually not committed yet - on a fresh branch HEAD
    # IS the merge base. So this printed "no scripts changed against origin/main", exited 0, and
    # was a true statement about the empty set; two unbumped scripts then failed this same check
    # in CI. Omitting HEAD compares merge_base to the WORKING TREE, staged and unstaged included,
    # so a local run sees the change while somebody can still act on it. In CI the working tree
    # equals HEAD, so nothing there changes - this only adds the case that was missing.
    changed = _git(["diff", "--name-only", merge_base, "--", "scripts/"]).stdout.split()
    scripts = [p for p in changed if p.endswith((".ps1", ".sh"))]
    if not scripts:
        print(f"no scripts changed against {base} (working tree included).")
        return 0

    root = pathlib.Path(__file__).resolve().parent.parent
    problems = []
    for path in sorted(scripts):
        # From disk, not `git show HEAD:path` - on disk is where an uncommitted version lives,
        # and it is the one a log from this run would actually print.
        disk = root / path
        if not disk.exists():
            continue                       # deleted in this change
        new_text = disk.read_text(encoding="utf-8", errors="replace")
        old = _git(["show", f"{merge_base}:{path}"])
        msg = problem(path, old.stdout if old.returncode == 0 else None, new_text)
        if msg:
            problems.append(msg)

    for msg in problems:
        print(msg)
    if problems:
        print(f"\n{len(problems)} script(s) changed without a truthful version. `main` is the "
              f"release, so the version is the only way to tell what somebody ran.\n"
              f"Set it to the current UTC YYYY.MMDDHHMM.")
        return 1
    print(f"all {len(scripts)} changed script(s) bumped their version: "
          f"{', '.join(sorted(scripts))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
