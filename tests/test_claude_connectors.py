#!/usr/bin/env python3
"""scripts/csa-claude-connectors.py does exactly what it says, and nothing else (issue #129).

What matters most about a tool that rewrites ~/.claude.json is what it leaves alone, so most
of this checks that: report mode changes no file at all; a connector with a similar name is
not caught (claude.ai Gmail2, claude.ai Google Drivex); other projects' keys, other allow and
deny rules, and unrelated settings survive; a second run changes nothing and writes no backup.

Runs the real script against a fake HOME and a fake ~/GitHub, so it exercises the same code
path a person runs.

    python3 tests/test_claude_connectors.py
"""
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "csa-claude-connectors.py"
G = ["claude.ai Gmail", "claude.ai Google Calendar", "claude.ai Google Drive"]
failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)
        print(f"FAIL: {msg}")


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def snapshot(root):
    return {p: p.read_bytes() for p in sorted(Path(root).rglob("*")) if p.is_file()}


spec = importlib.util.spec_from_file_location("conn", SCRIPT)
conn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(conn)

# Names Claude Code actually produced on a real machine.
check(conn.tool_prefix("claude.ai Gmail") == "mcp__claude_ai_Gmail", "Gmail prefix")
check(conn.tool_prefix("claude.ai Google Calendar") == "mcp__claude_ai_Google_Calendar", "Calendar prefix")
check(conn.tool_prefix("claude.ai CSA-Pod") == "mcp__claude_ai_CSA-Pod", "hyphen kept")
p = ["mcp__claude_ai_Gmail"]
check(conn.matches("mcp__claude_ai_Gmail", p), "bare server matches")
check(conn.matches("mcp__claude_ai_Gmail__search_threads", p), "tool matches")
check(not conn.matches("mcp__claude_ai_Gmail2__x", p), "similar server not matched")

with tempfile.TemporaryDirectory() as t:
    home = Path(t) / "home"
    repos = Path(t) / "GitHub"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({
        "numStartups": 7,
        "projects": {
            "/a": {"disabledMcpServers": ["claude.ai Gmail", "claude.ai Spotify"], "lastCost": 1},
            "/b": {},
        },
    }))
    (home / ".claude" / "settings.json").write_text(json.dumps({
        "model": "opus", "permissions": {"deny": ["Bash(rm -rf:*)"], "allow": ["Read"]}}))
    s = repos / "org" / "repo" / ".claude"
    (s / "commands").mkdir(parents=True)
    (s / "settings.local.json").write_text(json.dumps({"permissions": {"allow": [
        "mcp__claude_ai_Gmail__search_threads", "mcp__claude_ai_Gmail2__x",
        "mcp__claude_ai_Google_Drivex__y", "mcp__claude_ai_Airtable__list", "Bash(ls:*)"]}}))
    (s / "commands" / "go.md").write_text("use mcp__claude_ai_Google_Drive__search_files\n")
    (s / "commands" / "other.md").write_text("use mcp__claude_ai_Gmail2__x\n")

    before = snapshot(t)
    r = run("--home", str(home), "--repos", str(repos))
    check(r.returncode == 0, f"report exits 0: {r.stderr}")
    check(snapshot(t) == before, "report mode changed nothing")
    check("go.md" in r.stdout and "other.md" not in r.stdout, "callers: real one reported, look-alike not")

    r = run("--home", str(home), "--repos", str(repos), "--apply")
    check(r.returncode == 0, f"apply exits 0: {r.stderr}")
    cj = json.loads((home / ".claude.json").read_text())
    check(cj["numStartups"] == 7 and cj["projects"]["/a"]["lastCost"] == 1, "other keys kept")
    for proj in ("/a", "/b"):
        d = cj["projects"][proj]["disabledMcpServers"]
        check(all(g in d for g in G), f"{proj}: all three disabled")
        check(len(d) == len(set(d)), f"{proj}: no duplicates")
    check("claude.ai Spotify" in cj["projects"]["/a"]["disabledMcpServers"], "existing disable kept")
    st = json.loads((home / ".claude" / "settings.json").read_text())
    check(st["model"] == "opus" and "Read" in st["permissions"]["allow"], "settings: other keys kept")
    check("Bash(rm -rf:*)" in st["permissions"]["deny"], "settings: existing deny kept")
    for pre in ("mcp__claude_ai_Gmail", "mcp__claude_ai_Google_Calendar", "mcp__claude_ai_Google_Drive"):
        check(pre in st["permissions"]["deny"] and pre + "__*" in st["permissions"]["deny"], f"deny {pre}")
    allow = json.loads((s / "settings.local.json").read_text())["permissions"]["allow"]
    check(allow == ["mcp__claude_ai_Gmail2__x", "mcp__claude_ai_Google_Drivex__y",
                    "mcp__claude_ai_Airtable__list", "Bash(ls:*)"], f"repo allow cleaned exactly: {allow}")
    check((s / "commands" / "go.md").read_text().startswith("use mcp__claude_ai_Google_Drive"),
          "callers reported, never edited")
    backups = list(Path(t).rglob("*.bak-*"))
    check(len(backups) == 3, f"one backup per changed file: {len(backups)}")

    after = snapshot(t)
    r = run("--home", str(home), "--repos", str(repos), "--apply")
    check(snapshot(t) == after, "second apply changes nothing and writes no backup")

# ── #143: bounded backups, and a prune that cannot reach past its own naming scheme ───────
with tempfile.TemporaryDirectory() as t:
    home = Path(t) / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude.json").write_text(json.dumps({"projects": {"/a": {}}}))

    # Five backups from earlier runs, in the exact shape the script makes itself.
    OLD = ["2026010100000" + n for n in "12345"]
    for st in OLD:
        (home / f".claude.json.bak-{st}").write_text("older run " + st)

    # Three files the prune must NOT touch. The middle one is the real name found on the
    # authoring machine holding an OAuth client secret: a `*.bak*` glob would have eaten it,
    # which is why the pattern demands `.bak-` and exactly fourteen digits.
    bystanders = {
        home / ".claude.json.bak": "hand-made, no stamp at all",
        home / "client_secret.json.20260929-pre-bom-fix.bak": "ANOTHER TOOL'S, holds a secret",
        home / ".claude.json.bak-2026": "a truncated stamp - four digits, not fourteen",
        home / ".claude.json.bak-2026010100000x": "fourteen characters but not fourteen digits",
    }
    for path, text in bystanders.items():
        path.write_text(text)

    r = run("--home", str(home), "--apply")
    check(r.returncode == 0, f"retention run exits 0: {r.stderr}")

    mine = sorted(q.name for q in home.glob(".claude.json.bak-*")
                  if re.fullmatch(r"\.claude\.json\.bak-\d{14}", q.name))
    check(len(mine) == conn.BACKUPS_KEPT,
          f"bounded to {conn.BACKUPS_KEPT} generations, found {len(mine)}: {mine}")

    # Newest kept, oldest dropped - not the other way round, which a bound alone would not catch.
    check(OLD[4] in " ".join(mine) and OLD[3] in " ".join(mine),
          f"the two newest seeded backups survived: {mine}")
    check(not any(o in " ".join(mine) for o in OLD[:3]),
          f"the three oldest were pruned: {mine}")
    check(any(not q.startswith(".claude.json.bak-20260101") for q in mine),
          f"this run's own backup is one of the survivors: {mine}")

    # Byte for byte: a file that survived truncated would pass a mere existence check.
    for path, text in bystanders.items():
        check(path.exists() and path.read_text() == text,
              f"the prune left {path.name} untouched")

    # The RULE, not just its effect above. Those checks observe what the prune did to one
    # arrangement of files, and that is weaker than it looks: mutating the matched set to the
    # naive `".bak" in n` leaves the client_secret bystander alive anyway, because "c" sorts
    # above "." and it lands inside the kept three by accident. The survival check would have
    # passed while the implementation was the exact dangerous one. So state what the pattern
    # is allowed to CONSIDER, which no sort order can flatter.
    for name in (".claude.json.bak",
                 "client_secret.json.20260929-pre-bom-fix.bak",
                 ".claude.json.bak-2026",
                 ".claude.json.bak-2026010100000x",
                 ".claude.json.bak-202601010000012"):
        check(not conn.BACKUP_RE.search(name), f"BACKUP_RE must not match {name!r}")
    check(bool(conn.BACKUP_RE.search(".claude.json.bak-20260101000001")),
          "BACKUP_RE matches the one shape this script makes")

    # The closing line has to say what the copies hold, not just where they end.
    low = r.stdout.lower()
    check("credential" in low, f"the Done line says the copies hold credentials: {r.stdout!r}")
    check("restart claude code" in low, "the restart instruction survived on its own line")
    check(str(conn.BACKUPS_KEPT) in r.stdout, "the Done line says how many are kept")


if failures:
    print(f"\n{len(failures)} failure(s)")
    sys.exit(1)
print("csa-claude-connectors: all checks pass")
