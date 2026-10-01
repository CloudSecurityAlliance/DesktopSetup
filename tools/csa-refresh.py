#!/usr/bin/env python3
"""Pull the repos a session is working in, and say WHICH FILES MOVED UNDER IT.

The pulling is the easy half and three tools already do it (`~/GitHub/git-pull-all.py`,
`CloudSecurityAlliance/pull-all.sh`, `sync-csa-repos.sh`). The half nothing does is the one
that matters to an agent: **a session that read a file twenty turns ago and reasoned about it
has no way to learn the file changed.** A pull log reading "updated 7 repos" does not tell it;
only a list of changed paths does.

So the contract here is NOT "pull". It is "tell me what moved beneath me", and pulling is
merely how fresh data arrives. Two consequences fall out of stating it that way:

  * `--check` must exist. If somebody pulled in another terminal, the session is stale and no
    pull of its own will reveal that - the repo is already current. Drift is measured against
    what this tool last SAW, not against the remote.

  * The state lives on disk (`~/.csa-refresh.json`), not in the session's head. A context
    window compacts; the file does not. After compaction the session no longer knows which
    repos it touched, and the only durable record of "you have looked here before" is this.

WHAT IT WILL NOT DO, and why each one is deliberate:

  * Never checks out, never switches branch, never stashes. It pulls the branch you are on,
    `--ff-only`, or it reports and moves on. A tool that reorganises a working tree mid-task
    is a tool that loses work.
  * Never touches a dirty repo. Reported by name and skipped, because `--ff-only` would fail
    anyway and a skipped repo the session is told about is strictly better than a clever one
    it is not.
  * Never pulls what it was not asked to. The default is the repo containing the current
    directory; everything else is explicit, or remembered from a previous explicit run.

Usage:
    csa-refresh.py                     the repo containing $PWD
    csa-refresh.py DIR [DIR ...]       those repos, and remember them
    csa-refresh.py --known             every repo remembered from earlier runs
    csa-refresh.py --check [...]       report drift, pull nothing
    csa-refresh.py --forget DIR        drop a repo from the remembered set
    csa-refresh.py --self-test         prove the diff reporting can still fail
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

STATE = pathlib.Path(os.environ.get("CSA_REFRESH_STATE",
                                    pathlib.Path.home() / ".csa-refresh.json"))

# Paths whose change should stop a session rather than inform it: they are the files an agent
# reads once, treats as settled, and then acts on for the rest of a session. A changed CLAUDE.md
# is a changed instruction set, and an agent working from the old one is not merely out of date.
LOUD = ("CLAUDE.md", "AGENTS.md", "TODO.md", "DECISIONS.md", "README.md", ".claude/")


def git(repo: pathlib.Path, *args: str) -> tuple[int, str]:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True)
    return p.returncode, (p.stdout or p.stderr).strip()


def repo_root(start: pathlib.Path) -> pathlib.Path | None:
    rc, out = git(start, "rev-parse", "--show-toplevel")
    return pathlib.Path(out) if rc == 0 and out else None


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # A missing or corrupt state file means "nothing remembered", never a crash: this tool
        # exists to be run reflexively, and one that can fail at startup will not be.
        return {}


def save_state(state: dict) -> None:
    try:
        STATE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as e:
        print(f"  ! could not write {STATE}: {e}", file=sys.stderr)


def changed_files(repo: pathlib.Path, old: str, new: str) -> list[tuple[str, str]]:
    rc, out = git(repo, "diff", "--name-status", f"{old}..{new}")
    if rc != 0 or not out:
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            rows.append((parts[0], parts[-1]))
    return rows


def refresh(repo: pathlib.Path, state: dict, *, check_only: bool) -> dict:
    """Pull (or just measure), and return what a session needs to know."""
    key = str(repo)
    seen = state.get(key, {}).get("sha")
    rc, branch = git(repo, "branch", "--show-current")
    _, dirty = git(repo, "status", "--porcelain")
    dirty_n = len([l for l in dirty.splitlines() if l.strip()])
    before = git(repo, "rev-parse", "HEAD")[1]

    result = {"repo": repo, "branch": branch or "(detached)", "dirty": dirty_n,
              "before": before, "after": before, "status": "", "files": []}

    if check_only:
        git(repo, "fetch", "-q", "origin")
        behind = git(repo, "rev-list", "--count", "HEAD..@{u}")[1] if branch else "?"
        result["status"] = f"behind {behind}" if behind.isdigit() and int(behind) else "current"
    elif dirty_n:
        result["status"] = "SKIPPED (uncommitted changes)"
    else:
        git(repo, "fetch", "-q", "origin")
        rc, out = git(repo, "pull", "-q", "--ff-only")
        result["after"] = git(repo, "rev-parse", "HEAD")[1]
        result["status"] = "pulled" if rc == 0 else f"PULL FAILED: {out.splitlines()[0] if out else '?'}"

    # The number that matters is drift since this tool last LOOKED, not since the pull started.
    # Those differ exactly when somebody pulled in another terminal - which is the case the
    # session is least able to notice on its own and most likely to be wrong about.
    baseline = seen or before
    if baseline != result["after"]:
        result["files"] = changed_files(repo, baseline, result["after"])
        result["drifted_from"] = baseline

    state[key] = {"sha": result["after"], "branch": result["branch"]}
    return result


def report(results: list[dict]) -> int:
    loud_hits: list[str] = []
    any_change = False

    for r in results:
        name = r["repo"].name
        line = f"{name:<28} {r['branch']:<10} {r['status']}"
        if r["before"] != r["after"]:
            line += f"  {r['before'][:7]}..{r['after'][:7]}"
        print(line)
        if r["dirty"] and "SKIPPED" not in r["status"]:
            print(f"    {r['dirty']} uncommitted change(s) — left alone")

    print()
    for r in results:
        if not r["files"]:
            continue
        any_change = True
        base = r.get("drifted_from", "")[:7]
        print(f"CHANGED in {r['repo'].name}  (since this tool last saw {base})")
        for status, path in r["files"]:
            mark = "  *" if any(path.startswith(p) or path.endswith(p) for p in LOUD) else "   "
            print(f"{mark} {status:<3} {path}")
            if mark.strip():
                loud_hits.append(f"{r['repo'].name}/{path}")
        print()

    if not any_change:
        print("Nothing moved since this tool last looked. Earlier reads are still good.")
        return 0

    print("Anything you read from the files above was read from a DIFFERENT version.")
    print("Re-read before relying on a conclusion drawn from one.")
    if loud_hits:
        print()
        print("  ** INSTRUCTION FILES CHANGED — re-read these first:")
        for h in loud_hits:
            print(f"       {h}")
    return 0


SELF_TEST_NOTE = """self-test: creates a repo, commits twice, and checks the diff is reported.
A tool whose whole value is naming changed files must be able to prove it still names them."""


def self_test() -> int:
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        repo = pathlib.Path(d) / "r"
        repo.mkdir()
        for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
            git(repo, *args)
        (repo / "CLAUDE.md").write_text("one\n", encoding="utf-8")
        git(repo, "add", "-A"); git(repo, "commit", "-qm", "one")
        first = git(repo, "rev-parse", "HEAD")[1]
        (repo / "CLAUDE.md").write_text("two\n", encoding="utf-8")
        (repo / "other.txt").write_text("x\n", encoding="utf-8")
        git(repo, "add", "-A"); git(repo, "commit", "-qm", "two")
        second = git(repo, "rev-parse", "HEAD")[1]

        files = changed_files(repo, first, second)
        paths = sorted(p for _, p in files)
        problems = []
        if paths != ["CLAUDE.md", "other.txt"]:
            problems.append(f"changed_files: expected both files, got {paths}")
        if not any(p == "CLAUDE.md" and any(p.endswith(x) for x in LOUD) for _, p in files):
            problems.append("CLAUDE.md did not match the LOUD list — the loud path is dead")
        if changed_files(repo, second, second):
            problems.append("a no-op range reported changes")

    if problems:
        print("SELF-TEST FAILED — this tool can no longer report what moved:")
        for p in problems:
            print(f"  {p}")
        return 1
    print(SELF_TEST_NOTE)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pull the repos this session works in, and say what moved.")
    ap.add_argument("dirs", nargs="*", help="repos to refresh (default: the repo containing $PWD)")
    ap.add_argument("--known", action="store_true", help="every repo remembered from earlier runs")
    ap.add_argument("--check", action="store_true", help="report drift, pull nothing")
    ap.add_argument("--forget", metavar="DIR", help="drop a repo from the remembered set")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    state = load_state()

    if args.forget:
        root = repo_root(pathlib.Path(args.forget).resolve())
        if root and state.pop(str(root), None) is not None:
            save_state(state)
            print(f"forgotten: {root}")
        else:
            print(f"not remembered: {args.forget}")
        return 0

    targets: list[pathlib.Path] = []
    if args.known:
        targets = [pathlib.Path(k) for k in sorted(state)]
    for d in args.dirs:
        root = repo_root(pathlib.Path(d).resolve())
        if root is None:
            print(f"not a git repo: {d}", file=sys.stderr)
            return 1
        targets.append(root)
    if not targets:
        root = repo_root(pathlib.Path.cwd())
        if root is None:
            print("not inside a git repo, and no directories given", file=sys.stderr)
            return 1
        targets = [root]

    seen: set[pathlib.Path] = set()
    ordered = [t for t in targets if not (t in seen or seen.add(t))]
    missing = [t for t in ordered if not (t / ".git").exists()]
    ordered = [t for t in ordered if t not in missing]
    for m in missing:
        print(f"{m.name:<28} GONE — remembered but no longer a repo here")
        state.pop(str(m), None)

    results = [refresh(t, state, check_only=args.check) for t in ordered]
    save_state(state)
    return report(results)


if __name__ == "__main__":
    sys.exit(main())
