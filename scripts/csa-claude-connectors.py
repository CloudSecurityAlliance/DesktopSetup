#!/usr/bin/env python3
"""Disable selected claude.ai connectors in Claude Code, everywhere (issue #129).

CSA ships its own Google MCP servers (csa-google-gmail-calendar, csa-google-workspace), and
they do more than the claude.ai account connectors for Gmail, Google Calendar and Google
Drive. When both are present Claude may pick the weaker one.

Claude.ai connectors are ON by default in every Claude Code project. The only per-project
switch is `disabledMcpServers` in ~/.claude.json, which `/mcp` writes one project at a time,
and the only documented global switch (`disableClaudeAiConnectors`) turns off ALL connectors,
including ones people still use. So this tool does it selectively, in three places:

  1. ~/.claude.json          add the connectors to every project's `disabledMcpServers`,
                             so they stop loading in projects Claude Code already knows.
  2. ~/.claude/settings.json add `permissions.deny` rules for their tools, which apply in
                             every directory, including ones never opened before.
  3. --repos DIR (optional)  remove stale `allow` entries for those tools from
                             DIR/<org>/<repo>/.claude/settings*.json, and REPORT (not edit)
                             commands, agents and skills that call them.

Reports only, unless --apply. Every file it changes is backed up with a timestamp first and
written atomically. Idempotent: running it twice changes nothing the second time.

Run it with Claude Code closed: a running session can rewrite ~/.claude.json on exit and
undo step 1. If that happens, run it again.

    python3 scripts/csa-claude-connectors.py                    # report
    python3 scripts/csa-claude-connectors.py --apply            # do it
    python3 scripts/csa-claude-connectors.py --apply --repos ~/GitHub
    python3 scripts/csa-claude-connectors.py --connector "claude.ai Slack"   # other connectors
"""
import argparse
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_VERSION = "2026.10030141"

DEFAULT_CONNECTORS = [
    "claude.ai Gmail",
    "claude.ai Google Calendar",
    "claude.ai Google Drive",
]


def tool_prefix(connector):
    """'claude.ai Google Calendar' -> 'mcp__claude_ai_Google_Calendar'.

    Claude Code builds MCP tool names as mcp__<server>__<tool>, with characters outside
    [A-Za-z0-9_-] in the server name replaced by '_'. Matches the names seen in practice:
    mcp__claude_ai_Gmail, mcp__claude_ai_Google_Drive, mcp__claude_ai_CSA-Pod.
    """
    return "mcp__" + re.sub(r"[^A-Za-z0-9_-]", "_", connector)


def matches(rule, prefixes):
    """A permission rule names one of the connectors: the server itself or one of its tools."""
    return any(rule == p or rule.startswith(p + "__") for p in prefixes)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# How many generations of each backup survive a run. Three, not one: the purpose is crash
# recovery for THIS run, which one copy satisfies, but a bounded little undo depth costs
# nothing and the file being copied is one people break by hand. One per run forever was the
# defect (#143); the exact number is a judgement, the bound is not.
BACKUPS_KEPT = 3

# `<name>.bak-` plus EXACTLY fourteen digits - the %Y%m%d%H%M%S stamp, and nothing else.
# This narrowness is the whole safety property of the prune below; see prune_backups.
BACKUP_RE = re.compile(r"\.bak-\d{14}$")


def prune_backups(path, keep=BACKUPS_KEPT):
    """Bound `path`'s backups to the `keep` most recent. Returns the names removed.

    Matches ONLY the name this script generates. The obvious implementation is a `*.bak*`
    glob and it is the wrong one: on the authoring machine that would also have matched
    `client_secret.json.20260929-pre-bom-fix.bak`, written by a different tool entirely and
    holding a real OAuth client secret. A prune may only ever delete what its own naming
    scheme made, so the pattern demands the literal `.bak-` and exactly fourteen digits.

    Sorted by NAME, descending. The stamp is fixed-width `%Y%m%d%H%M%S`, so a reverse string
    sort is already newest-first - no `stat()` call, and no dependence on an mtime that a
    copy, a restore or a backup tool may have rewritten since.
    """
    d = os.path.dirname(path) or "."
    prefix = os.path.basename(path) + ".bak-"
    try:
        names = os.listdir(d)
    except OSError:
        return []
    mine = sorted((n for n in names if n.startswith(prefix) and BACKUP_RE.search(n)),
                  reverse=True)
    removed = []
    for name in mine[keep:]:
        try:
            os.unlink(os.path.join(d, name))
            removed.append(name)
        except OSError:
            # A copy we cannot delete is not a reason to fail the run that just made one.
            # Reported by the caller either way, so it does not vanish silently.
            pass
    return removed


def check_backup_mode(src, dst):
    """Return a warning if the backup is more permissive than the file it copied, else None.

    `shutil.copy2` preserves the POSIX mode, so this should never fire. That is exactly why
    it is worth asserting: the file is `~/.claude.json`, whose keys include `oauthAccount`,
    and "copy2 handles it" is an inherited guarantee rather than a checked one.

    On Windows this returns None and does not pretend otherwise. `copy2` does not copy ACLs
    at all - the new file inherits the containing directory's, which being the same directory
    is the right one, but that is a different claim from the one made here - and `os.chmod`
    honours only the read-only bit (csa-google-workspace#452). A mode comparison on Windows
    would compare two values that do not govern access.
    """
    if os.name == "nt":
        return None
    src_mode = stat.S_IMODE(os.stat(src).st_mode)
    dst_mode = stat.S_IMODE(os.stat(dst).st_mode)
    extra = dst_mode & ~src_mode
    if extra:
        return (f"{os.path.basename(dst)} is mode {oct(dst_mode)} but the file it copied is "
                f"{oct(src_mode)} - the copy is the more permissive one. It holds the same "
                f"credentials; tighten or delete it.")
    return None


def write_json(path, data, stamp):
    """Back up, then replace atomically, so a crash never leaves half a config file.

    The backup is bounded to BACKUPS_KEPT generations and its mode is checked rather than
    assumed (#143). It used to be one copy per changing run, forever, of a file that holds
    the signed-in account - so the pile grew without limit and nothing but the suffix was
    ever said about it.
    """
    backup = f"{path}.bak-{stamp}"
    shutil.copy2(path, backup)
    problem = check_backup_mode(path, backup)
    if problem:
        print(f"  WARNING: {problem}")
    prune_backups(path)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".csa-connectors-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def patch_projects(data, connectors):
    """Step 1. Returns [(project, [connectors added])]."""
    changes = []
    for project, entry in (data.get("projects") or {}).items():
        disabled = entry.setdefault("disabledMcpServers", [])
        added = [c for c in connectors if c not in disabled]
        if added:
            disabled.extend(added)
            changes.append((project, added))
    return changes


def deny_rules(prefixes):
    """Both forms, as csa-google-workspace's own settings.json does: the bare server name
    (documented to cover all of a server's tools) and an explicit wildcard."""
    return [r for p in prefixes for r in (p, p + "__*")]


def patch_deny(data, prefixes):
    """Step 2. Returns the deny rules added."""
    deny = data.setdefault("permissions", {}).setdefault("deny", [])
    added = [r for r in deny_rules(prefixes) if r not in deny]
    deny.extend(added)
    return added


def repo_settings_files(root):
    """<root>/<org>/<repo>/.claude/settings*.json, the layout clone-and-claude uses."""
    return sorted(Path(root).glob("*/*/.claude/settings*.json"))


def strip_allow(data, prefixes):
    """Step 3. Remove allow entries naming the connectors. Returns the entries removed."""
    allow = (data.get("permissions") or {}).get("allow")
    if not isinstance(allow, list):
        return []
    removed = [a for a in allow if isinstance(a, str) and matches(a, prefixes)]
    if removed:
        data["permissions"]["allow"] = [a for a in allow if a not in removed]
    return removed


def find_callers(root, prefixes):
    """Commands, agents and skills that call the connectors. Reported, never edited:
    they need porting to the CSA servers, which is a judgement, not a substitution."""
    hits = []
    # Not \b: the next character after the server name is "_" (mcp__claude_ai_Gmail__x),
    # which \b treats as part of the word, so \b never matched a real tool name.
    pattern = re.compile("|".join(re.escape(p) + r"(?![A-Za-z0-9-]|_(?!_))" for p in prefixes))
    for path in sorted(Path(root).glob("*/*/.claude/**/*")):
        if not path.is_file() or "worktrees" in path.parts or path.suffix not in (".md", ".json"):
            continue
        if path.name.startswith("settings"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = sorted(set(m.group(0) for m in pattern.finditer(text)))
        if found:
            hits.append((path, found))
    return hits


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="make the changes (default: report only)")
    ap.add_argument("--connector", action="append", metavar="NAME",
                    help="connector to disable, as shown in /mcp; repeatable; replaces the defaults")
    ap.add_argument("--repos", metavar="DIR", help="also clean <DIR>/<org>/<repo>/.claude settings")
    ap.add_argument("--home", metavar="DIR", default=str(Path.home()), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    connectors = args.connector or DEFAULT_CONNECTORS
    prefixes = [tool_prefix(c) for c in connectors]
    stamp = time.strftime("%Y%m%d%H%M%S")
    mode = "APPLY" if args.apply else "REPORT ONLY (nothing changed; use --apply)"
    print(f"csa-claude-connectors {SCRIPT_VERSION} — {mode}")
    print("Connectors: " + ", ".join(connectors))

    home = Path(args.home)
    claude_json = home / ".claude.json"
    settings_json = home / ".claude" / "settings.json"

    # 1. ~/.claude.json
    if claude_json.exists():
        data = load_json(claude_json)
        changes = patch_projects(data, connectors)
        total = len(data.get("projects") or {})
        print(f"\n~/.claude.json: {len(changes)} of {total} projects need the connectors disabled")
        for project, added in changes[:20]:
            print(f"  {project}: + {', '.join(added)}")
        if len(changes) > 20:
            print(f"  ... and {len(changes) - 20} more")
        if changes and args.apply:
            write_json(claude_json, data, stamp)
    else:
        print("\n~/.claude.json: not found (Claude Code has not been run here); skipped")

    # 2. ~/.claude/settings.json
    if settings_json.exists():
        data = load_json(settings_json)
    else:
        data = {}
    added = patch_deny(data, prefixes)
    print(f"\n~/.claude/settings.json: {len(added)} deny rule(s) to add"
          + (": " + ", ".join(added) if added else ""))
    if added and args.apply:
        if settings_json.exists():
            write_json(settings_json, data, stamp)
        else:
            settings_json.parent.mkdir(parents=True, exist_ok=True)
            settings_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # 3. repos
    if args.repos:
        root = Path(args.repos).expanduser()
        print(f"\nRepos under {root}:")
        cleaned = 0
        for path in repo_settings_files(root):
            try:
                data = load_json(path)
            except (OSError, ValueError) as e:
                print(f"  {path}: unreadable ({e}); skipped")
                continue
            removed = strip_allow(data, prefixes)
            if removed:
                cleaned += 1
                print(f"  {path.relative_to(root)}: remove {len(removed)} allow entr"
                      + ("y" if len(removed) == 1 else "ies"))
                if args.apply:
                    write_json(path, data, stamp)
        print(f"  {cleaned} settings file(s) with stale allow entries")
        callers = find_callers(root, prefixes)
        if callers:
            print("\n  These call the connectors and need porting to the CSA servers by hand:")
            for path, found in callers:
                print(f"    {path.relative_to(root)}: {', '.join(found)}")

    if args.apply:
        print(f"\nDone. Backups of each changed file end in .bak-{stamp}. They contain"
              f" your Claude credentials, including the signed-in account, so delete them"
              f" once you are happy. The {BACKUPS_KEPT} most recent of each are kept.")
        print("Restart Claude Code to pick up the changes.")
    print("\nNote: this covers Claude Code only. Disconnecting at claude.ai -> Settings -> "
          "Connectors also removes them from claude.ai web.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
