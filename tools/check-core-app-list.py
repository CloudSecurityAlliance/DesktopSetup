#!/usr/bin/env python3
"""The core app set is written ONCE per work-tools script, and every consumer reads it (#78).

The defect this exists for shipped in #69. windows-work-tools.ps1 wrote its five core apps out
in six places - the profile menu, the preflight, the install, the summary, the next steps and
the header comment. Adding Microsoft Office updated three of them and missed the rest: the
profile menu left Office out, and the next steps told people to "install Microsoft Office from
your Microsoft 365 portal" right after the script had installed it. That was done by someone who
knew the copies existed and was being careful. Nothing failed - a missed copy makes the plan
promise something the install does not do, or the reverse, and the run looks clean.

#73 made Windows read one `$CoreApps`. macos-work-tools.sh had the same six copies in three
shapes (one with its fields reversed, `zoom.us:Zoom`) until #78 made it read one
`CSA_CORE_APPS`. No existing check could see either: check-duplication.py compares functions
across scripts, check-parity.py compares main() steps across platforms, and this is repeated
DATA within one script.

Rules, for each script:
  * the list is declared exactly once, at top level, and is not empty (on bash 3.2 under
    `set -u`, iterating an empty array is an unbound-variable exit);
  * every macOS entry is `label:cask:app-bundle` with three non-empty fields; every Windows
    entry is `@{ Label = "..."; Id = "..." }`;
  * every consumer function reads the list (macOS: `CSA_CORE_APPS` or `csa_core_app_labels`;
    Windows: `$CoreApps`) - a consumer that stops reading it has gone back to a copy or dropped
    the apps;
  * no value of any entry - label, cask, app bundle, winget Id - appears on a code line outside
    the declaration. A full-line comment may name them (each header keeps a summary). Matched
    as a whole token, case-sensitively, so `Slackware` or `zoom.usx` would not count.

Validated against the commits where the defect lived, with --rev (which reads that commit's
scripts but matches against TODAY's lists):
  * 36e76b4 (main before #78): macos-work-tools.sh fails - no CSA_CORE_APPS, no consumer reads
    one, and the copies in the menu, preflight, install_core, summary and next steps are named
    by line.
  * 1115b64 (#69, the Windows bug as shipped): windows-work-tools.ps1 fails the same way, naming
    the copies in Show-Preflight, Install-Core, Show-Summary and the menu and next-steps lines -
    including the "Install Microsoft Office from your Microsoft 365 portal" line itself.
  The header comments are the sixth copy in each, and are exempt by design: they are summaries,
  and say that the list below is the source.

What it cannot check: that the list is RIGHT (that is a decision), or the dev set. macOS installs
VS Code by cask, the AWS CLI by formula and Wrangler by npm - three mechanisms with no shared
shape - so the dev set is not one list on macOS and this does not pretend it is.

Self-tests before it reports, on mutations of the real scripts it must fail and ones it must
pass; `--self-test` prints each case.

    python3 tools/check-core-app-list.py
    python3 tools/check-core-app-list.py --self-test
    python3 tools/check-core-app-list.py --rev <git-rev>
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

MAC = "scripts/macos-work-tools.sh"
WIN = "scripts/windows-work-tools.ps1"

# Top-level declaration (column 0) and where it closes: the first line that is only `)`.
DECL = {
    MAC: re.compile(r"^CSA_CORE_APPS=\(\s*$"),
    WIN: re.compile(r"^\$CoreApps\s*=\s*@\(\s*$"),
}
# Any assignment to the list, anywhere and at any indent - a second one is a second definition.
ASSIGN = {
    MAC: re.compile(r"\bCSA_CORE_APPS\+?=\("),
    WIN: re.compile(r"\$CoreApps\s*\+?=(?!=)"),
}
MAC_ENTRY = re.compile(r'^\s*"([^"]*)"\s*$')
WIN_ENTRY = re.compile(r'^\s*@\{\s*Label\s*=\s*"([^"]+)"\s*;\s*Id\s*=\s*"([^"]+)"\s*\},?\s*$')

# Every function that renders or acts on the core apps, and what it must mention to be reading
# the list rather than restating it.
CONSUMERS = {
    MAC: (["select_profile", "preflight", "install_core", "summary"],
          re.compile(r"\bCSA_CORE_APPS\b|\bcsa_core_app_labels\b")),
    WIN: (["Select-Profile", "Show-Preflight", "Install-Core", "Show-Summary"],
          re.compile(r"\$CoreApps\b")),
}
LIST_NAME = {MAC: "CSA_CORE_APPS", WIN: "$CoreApps"}


def _read(path: str, rev: str | None) -> str:
    if rev is None:
        return (ROOT / path).read_text(encoding="utf-8")
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"cannot read {path} at {rev}: {r.stderr.strip()}")
    return r.stdout


def is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def declaration(path: str, text: str) -> tuple[list[int], range | None, list[str]]:
    """(line numbers of every assignment, the top-level block's line range, its raw entries).
    Line numbers are 1-based; the range covers the opening line through the closing `)`."""
    lines = text.splitlines()
    assigns = [i for i, l in enumerate(lines, 1) if not is_comment(l) and ASSIGN[path].search(l)]
    for i, line in enumerate(lines):
        if DECL[path].match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == ")":
                    body = [l for l in lines[i + 1:j] if l.strip() and not is_comment(l)]
                    return assigns, range(i + 1, j + 2), body
            return assigns, range(i + 1, len(lines) + 1), []
    return assigns, None, []


def values(path: str, body: list[str]) -> tuple[list[str], list[str]]:
    """(every field value of every entry, malformed-entry problems)."""
    out, bad = [], []
    for line in body:
        if path == MAC:
            m = MAC_ENTRY.match(line)
            fields = m.group(1).split(":") if m else []
            if len(fields) != 3 or not all(fields):
                bad.append(f"entry is not label:cask:app-bundle with three non-empty fields: "
                           f"{line.strip()}")
                continue
            out += fields
        else:
            m = WIN_ENTRY.match(line)
            if not m:
                bad.append(f'entry is not @{{ Label = "..."; Id = "..." }}: {line.strip()}')
                continue
            out += [m.group(1), m.group(2)]
    return list(dict.fromkeys(out)), bad


def function_body(path: str, text: str, name: str) -> str | None:
    head = (re.compile(rf"^{re.escape(name)}\(\)\s*\{{") if path == MAC
            else re.compile(rf"^function\s+{re.escape(name)}\s*\{{", re.I))
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if head.match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("}"):
                    return "\n".join(lines[i + 1:j])
            return "\n".join(lines[i + 1:])
    return None


def token(v: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_.\-])" + re.escape(v) + r"(?![A-Za-z0-9_.\-])")


def problems(path: str, text: str, needles: list[str] | None = None) -> list[str]:
    """Everything wrong with one script. `needles` overrides the values searched for (--rev
    passes today's, since the commit being audited may have no list to take them from)."""
    out = []
    name = LIST_NAME[path]
    assigns, block, body = declaration(path, text)
    if block is None:
        out.append(f"{path}: no top-level `{name}` list")
    if len(assigns) > 1:
        out.append(f"{path}: `{name}` is assigned {len(assigns)} times (lines "
                   f"{', '.join(map(str, assigns))}); it must be declared exactly once")
    found, bad = values(path, body)
    out += [f"{path}: {b}" for b in bad]
    if block is not None and not body:
        out.append(f"{path}: `{name}` is empty - under bash 3.2 `set -u` iterating it exits")
    names, reads = CONSUMERS[path]
    for fn in names:
        b = function_body(path, text, fn)
        if b is None:
            out.append(f"{path}: consumer {fn} not found")
        elif not reads.search(b):
            out.append(f"{path}: {fn} does not read `{name}`")
    exempt = set(block) if block is not None else set()
    pats = [(v, token(v)) for v in (needles if needles is not None else found)]
    for i, line in enumerate(text.splitlines(), 1):
        if i in exempt or is_comment(line):
            continue
        hits = [v for v, p in pats if p.search(line)]
        if hits:
            out.append(f"{path}:{i}: names {', '.join(repr(h) for h in hits)} outside "
                       f"`{name}`: {line.strip()[:110]}")
    return out


def current_needles() -> dict[str, list[str]]:
    out = {}
    for path in (MAC, WIN):
        _, _, body = declaration(path, _read(path, None))
        out[path] = values(path, body)[0]
    return out


# ── Self-test ───────────────────────────────────────────────────────────────────────────────

def self_test(verbose: bool) -> bool:
    real = {p: _read(p, None) for p in (MAC, WIN)}
    ok = True

    def case(label: str, path: str, text: str, expect: list[str] | None) -> None:
        """expect=None: must report nothing. Otherwise every fragment must appear in a problem."""
        nonlocal ok
        got = problems(path, text)
        if expect is None:
            good, why = not got, f"reported: {got}"
        else:
            missing = [e for e in expect if not any(e in g for g in got)]
            good, why = bool(got) and not missing, f"unreported: {missing or 'anything'}"
        if verbose or not good:
            print(f"  {'ok  ' if good else 'FAIL'}  {label}" + ("" if good else f" - {why}"))
        ok = ok and good

    def swap(text: str, old: str, new: str) -> str:
        if old not in text:
            raise SystemExit(f"self-test fixture is stale: {old!r} is no longer in the script")
        return text.replace(old, new, 1)

    mac, win = real[MAC], real[WIN]
    case("the real macOS script passes", MAC, mac, None)
    case("the real Windows script passes", WIN, win, None)

    # The six shapes the issue lists, put back one at a time.
    case("an install_cask line restated in install_core is reported", MAC,
         swap(mac, 'install_formula "GitHub CLI" "gh"\n',
              'install_formula "GitHub CLI" "gh"\n  install_cask "Zoom" "zoom" "zoom.us"\n'),
         ["'Zoom', 'zoom', 'zoom.us'"])
    case("the menu written as prose again (the #69 shape) is reported, and select_profile "
         "no longer reads the list", MAC,
         swap(mac, 'echo "  1) Core — $(csa_core_app_labels), Git, GitHub CLI"',
              'echo "  1) Core — 1Password, Slack, Zoom, Chrome, Git, GitHub CLI"'),
         ["'1Password', 'Slack', 'Zoom'", "select_profile does not read"])
    case("summary's reversed app[:label] array is reported", MAC,
         swap(mac, "  # Check apps\n",
              '  # Check apps\n  local -a check_apps=("1Password" "zoom.us:Zoom")\n'),
         ["'1Password', 'Zoom', 'zoom.us'"])
    case("a second copy of the list inside preflight is reported", MAC,
         swap(mac, "  # Cask apps — check both brew cask and /Applications\n",
              "  # Cask apps — check both brew cask and /Applications\n  local -a cask_apps=(\n"
              '    "Slack:slack:Slack"\n  )\n'),
         ["'Slack', 'slack'"])
    case("the next steps written as prose again are reported", WIN,
         swap(win, "Sign in to $(($CoreApps | ForEach-Object { $_.Label }) -join ', ')",
              "Sign in to 1Password, Slack, Zoom, and Chrome"),
         ["'1Password', 'Slack', 'Zoom'"])
    case("an Install-WingetPackage line restated in Install-Core is reported, and Install-Core "
         "no longer reads the list", WIN,
         swap(win, "foreach ($app in $CoreApps) { Install-WingetPackage $app.Label $app.Id }",
              'Install-WingetPackage "Slack" "SlackTechnologies.Slack"'),
         ["'Slack', 'SlackTechnologies.Slack'", "Install-Core does not read"])

    # The list itself.
    decl = re.search(r"^CSA_CORE_APPS=\(\n(?:.*\n)*?\)\n", mac, re.M).group(0)
    case("no list at all is reported", MAC, swap(mac, decl, ""), ["no top-level"])
    case("a second declaration is reported", MAC, mac + "\n" + decl, ["assigned 2 times"])
    case("an append elsewhere is reported as a second assignment", MAC,
         mac + '\nCSA_CORE_APPS+=("Notion:notion:Notion")\n', ["assigned 2 times"])
    case("an empty list is reported", MAC, swap(mac, decl, "CSA_CORE_APPS=(\n)\n"), ["is empty"])
    case("a two-field entry is reported", MAC,
         swap(mac, '"Zoom:zoom:zoom.us"', '"Zoom:zoom"'), ["three non-empty fields"])
    case("an entry with an empty field is reported", MAC,
         swap(mac, '"Slack:slack:Slack"', '"Slack::Slack"'), ["three non-empty fields"])
    case("a Windows entry with no Id is reported", WIN,
         swap(win, '@{ Label = "Zoom";             Id = "Zoom.Zoom" },', '@{ Label = "Zoom" },'),
         ["is not @{"])

    # What must NOT be reported.
    case("a full-line comment naming the apps is not reported", MAC,
         mac + "\n# Slack, zoom.us and google-chrome are in CSA_CORE_APPS\n", None)
    case("a word that merely contains a value is not reported", MAC,
         mac + '\nf() {\n  echo "Slackware zoom.usx 1Passwords"\n}\n', None)
    case("a PowerShell comment naming the apps is not reported", WIN,
         win + "\n    # Install-WingetPackage \"Slack\" \"SlackTechnologies.Slack\"\n", None)

    if verbose:
        print("self-test " + ("passed" if ok else "FAILED"))
    return ok


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return 0 if self_test(verbose=True) else 2
    if not self_test(verbose=False):
        print("SELF-TEST FAILED - this check cannot be trusted")
        return 2
    rev = argv[argv.index("--rev") + 1] if "--rev" in argv else None
    needles = current_needles() if rev else {}
    found = []
    for path in (MAC, WIN):
        found += problems(path, _read(path, rev), needles.get(path))
    where = f" at {rev}" if rev else ""
    if found:
        for f in found:
            print(f"  {f}")
        print(f"\n{len(found)} core-app-list problem(s){where}.")
        return 1
    print(f"core app list{where}: declared once per work-tools script, read by every consumer, "
          f"and named nowhere else.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
