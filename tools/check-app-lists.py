#!/usr/bin/env python3
"""Each work-tools script names its app sets ONCE, and every consumer reads them (#78).

The defect this exists for shipped in #69. windows-work-tools.ps1 wrote its five core apps out
in six places - the profile menu, the preflight, the install, the summary, the next steps and
the header comment. Adding Microsoft Office updated three of them and missed the rest: the
profile menu left Office out, and the next steps told people to "install Microsoft Office from
your Microsoft 365 portal" right after the script had installed it. That was done by someone who
knew the copies existed and was being careful. Nothing failed - a missed copy makes the plan
promise something the install does not do, or the reverse, and the run looks clean.

#73 made Windows read one `$CoreApps` and one `$DevWingetApps`. macos-work-tools.sh had the core
set six times in three shapes (one with its fields reversed, `zoom.us:Zoom`) and the dev set
four times, until #78 made it read `CSA_CORE_APPS` and `CSA_DEV_TOOLS`. No other check could see
either: check-duplication.py compares functions across scripts, check-parity.py compares main()
steps across platforms, and this is repeated DATA within one script.

The lists:
  macos-work-tools.sh     CSA_CORE_APPS   label:cask:app-bundle
                          CSA_DEV_TOOLS   label:kind:package:probe, kind in cask|formula|npm
  windows-work-tools.ps1  $CoreApps       @{ Label = "..."; Id = "..." }
                          $DevWingetApps  the same; Wrangler (npm) is outside it by #73's design

Rules, for each list:
  * DECLARED ONCE: exactly one top-level declaration, not empty (on bash 3.2 under `set -u`,
    iterating an empty array is an unbound-variable exit), every entry well-formed;
  * NEVER CHANGED: no other line assigns it, indexes into it with `=`, appends to it, unsets it
    or re-declares it (`CSA_CORE_APPS[5]=…`, `+=`, `unset`, `local`; `$CoreApps += …`,
    `$CoreApps[0].Label = …`, `.Add(…)`, `Remove-Variable`);
  * READ BY EVERY CONSUMER: each named rendering - the menu line, the plan loop, the install
    loop, the summary's presence loop, the next steps - is built from the list, checked one by
    one, so deleting one while another in the same function still reads the list is caught;
  * NO LITERAL INSTALLS: install_core / Install-Core and install_dev / Install-Dev may not call
    install_cask, install_formula, install_npm_package or Install-WingetPackage with a literal
    first argument. A new app added that way is not in the list, so the value rule below
    cannot see it. (install_core's Git and GitHub CLI formulas are not part of the app set,
    and Windows' Wrangler is npm, outside $DevWingetApps: those calls are allowed.)
  * NAMED NOWHERE ELSE: no label, cask, package, app bundle, probe or winget Id from a list
    appears on a code line outside the declarations, except the lines in ALLOWED, each with
    its reason. An ALLOWED entry that matches no line is itself reported.

How a value is matched - read this before acting on a report. Whole token, case-sensitive, on
every line that is not a full-line comment. A token boundary is anything except a letter,
digit, `_`, `.` or `-`. So a TRAILING comment that names an app is reported, and so is unrelated
prose that happens to use a short value as a word ("zoom in", "the aws docs"); `slack.com`,
`Slackware`, `zoom.usx` and `1Passwords` are not. The answer to a false report is to reword the
line or, if it really is not a copy of the list, add it to ALLOWED with a reason.

Validated against the commits where the defect lived, with --rev (which reads that commit's
scripts but matches against TODAY's lists, and skips the stale-ALLOWED check):
  * 36e76b4 (main before #78): macos-work-tools.sh fails - no lists, no consumer reads one, and
    every copy of both sets in the menu, preflight, install_core, install_dev, summary and next
    steps is named by line, along with the literal installs.
  * 1115b64 (#69, the Windows bug as shipped): windows-work-tools.ps1 fails the same way, naming
    every copy - including the "Install Microsoft Office from your Microsoft 365 portal" line.
  The header comments are the sixth copy in each, and are exempt by design: they are summaries,
  and say that the lists below are the source.

What it cannot check: that a list is RIGHT (that is a decision), or that a consumer which reads
the list renders every entry of it.

Self-tests before it reports, on mutations of the real scripts it must fail and ones it must
pass; `--self-test` prints each case.

    python3 tools/check-app-lists.py
    python3 tools/check-app-lists.py --self-test
    python3 tools/check-app-lists.py --rev <git-rev>
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

MAC = "scripts/macos-work-tools.sh"
WIN = "scripts/windows-work-tools.ps1"

DEV_KINDS = ("cask", "formula", "npm")


class Spec:
    """One list: where it lives, its shape, and which of its fields are values to look for."""

    def __init__(self, path: str, name: str, fields: int = 0, needles: tuple[int, ...] = (),
                 kind_field: int | None = None):
        self.path, self.name, self.fields, self.needles, self.kind_field = (
            path, name, fields, needles, kind_field)
        n = re.escape(name)
        if path == MAC:
            self.shown = name
            self.decl = re.compile(rf"^{n}=\(\s*$")
            self.change = [
                re.compile(rf"(?<![\w$]){n}(?:\[[^\]]*\])?\+?="),
                re.compile(rf"\bunset\s+(?:-[fv]\s+)?(?:\S+\s+)*?['\"]?{n}\b"),
                re.compile(rf"\b(?:declare|typeset|local|readonly|export)\s+(?:-\w+\s+)*"
                           rf"(?:[A-Za-z_]\w*\s+)*{n}\b"),
            ]
        else:
            self.shown = "$" + name
            self.decl = re.compile(rf"^\${n}\s*=\s*@\(\s*$")
            self.change = [
                re.compile(rf"\$(?:script:|global:)?{n}\b(?:\[[^\]]*\])?(?:\.\w+)*\s*[-+*/]?=(?!=)"),
                re.compile(rf"\$(?:script:|global:)?{n}\.(?:Add|AddRange|Remove|RemoveAt|Clear|Insert)\("),
                re.compile(rf"\b(?:Remove|Set|Clear|New)-Variable\b[^#\n]*\b{n}\b", re.I),
            ]


LISTS = [
    Spec(MAC, "CSA_CORE_APPS", fields=3, needles=(0, 1, 2)),
    Spec(MAC, "CSA_DEV_TOOLS", fields=4, needles=(0, 2, 3), kind_field=1),
    Spec(WIN, "CoreApps"),
    Spec(WIN, "DevWingetApps"),
]
MAC_ENTRY = re.compile(r'^\s*"([^"]*)"\s*$')
WIN_ENTRY = re.compile(r'^\s*@\{\s*Label\s*=\s*"([^"]+)"\s*;\s*Id\s*=\s*"([^"]+)"\s*\},?\s*$')


def _loop(path: str, name: str) -> str:
    if path == MAC:
        return rf'\bfor\s+\w+\s+in\s+"\$\{{{name}\[@\]\}}"'
    return rf"\bforeach\s*\(\s*\$\w+\s+in\s+\${name}\s*\)"


# (script, function, what must be built from the list, list, pattern). Each is checked on its
# own, so a function that still reads the list for one rendering cannot hide a deleted other.
_MAC_JOIN = r"csa_labels\s+'[^']*'\s+\"\$\{{{0}\[@\]\}}\""
REQUIRED = [
    (MAC, "select_profile", "the menu's core line", "CSA_CORE_APPS",
     r"1\) Core — \$\(" + _MAC_JOIN.format("CSA_CORE_APPS")),
    (MAC, "select_profile", "the menu's developer line", "CSA_DEV_TOOLS",
     r"2\) Core \+ Developer — adds \$\(" + _MAC_JOIN.format("CSA_DEV_TOOLS")),
    (MAC, "preflight", "the core plan", "CSA_CORE_APPS", _loop(MAC, "CSA_CORE_APPS")),
    (MAC, "preflight", "the developer plan", "CSA_DEV_TOOLS", _loop(MAC, "CSA_DEV_TOOLS")),
    (MAC, "install_core", "the core install", "CSA_CORE_APPS", _loop(MAC, "CSA_CORE_APPS")),
    (MAC, "install_dev", "the developer install", "CSA_DEV_TOOLS", _loop(MAC, "CSA_DEV_TOOLS")),
    (MAC, "summary", "the installed-apps lines", "CSA_CORE_APPS", _loop(MAC, "CSA_CORE_APPS")),
    (MAC, "summary", "the developer lines", "CSA_DEV_TOOLS", _loop(MAC, "CSA_DEV_TOOLS")),
    (MAC, "summary", "the next steps", "CSA_CORE_APPS",
     r"Sign in to \$\(" + _MAC_JOIN.format("CSA_CORE_APPS")),
    (WIN, "Select-Profile", "the menu's core line", "$CoreApps", r"1\) Core - .*\$\(\(\$CoreApps\s*\|"),
    (WIN, "Select-Profile", "the menu's developer line", "$DevWingetApps",
     r"2\) Core \+ Developer - adds \$\(\(\$DevWingetApps\s*\|"),
    (WIN, "Show-Preflight", "the core plan", "$CoreApps", _loop(WIN, "CoreApps")),
    (WIN, "Show-Preflight", "the developer plan", "$DevWingetApps", _loop(WIN, "DevWingetApps")),
    (WIN, "Install-Core", "the core install", "$CoreApps", _loop(WIN, "CoreApps")),
    (WIN, "Install-Dev", "the developer install", "$DevWingetApps", _loop(WIN, "DevWingetApps")),
    (WIN, "Show-Summary", "the installed-apps lines", "$CoreApps", _loop(WIN, "CoreApps")),
    (WIN, "Show-Summary", "the next steps", "$CoreApps", r"Sign in to \$\(\(\$CoreApps\s*\|"),
]

# (script, function, install calls that may not take a literal first argument there).
LITERAL_INSTALLS = [
    (MAC, "install_core", r"install_cask"),
    (MAC, "install_dev", r"install_cask|install_formula|install_npm_package"),
    (WIN, "Install-Core", r"Install-WingetPackage"),
    (WIN, "Install-Dev", r"Install-WingetPackage"),
]

# Code lines that may name a listed value, matched by substring, each with its reason.
ALLOWED = [
    (MAC, "below the v${CSA_NODE_MIN} Wrangler needs",
     "install_node names Wrangler as the reason for the Node floor, not as a tool to install"),
    (MAC, "Run 'aws configure' to set up AWS credentials",
     "the AWS CLI's own first-run instruction in the next steps, not a rendering of the list"),
    (WIN, 'Test-WingetInstalled "Microsoft.VisualStudioCode"',
     "Show-Summary's dev block is outside $DevWingetApps by #73's design: it reports CLI versions"),
    (WIN, 'Write-Host "  AWS CLI ........... $awsVer"',
     "Show-Summary's dev block is outside $DevWingetApps by #73's design: it reports CLI versions"),
]


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


def declaration(spec: Spec, lines: list[str]) -> tuple[int | None, range | None, list[str]]:
    """(the 1-based declaration line, the range through its closing `)`, its entry lines)."""
    for i, line in enumerate(lines):
        if spec.decl.match(line):
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == ")":
                    body = [l for l in lines[i + 1:j] if l.strip() and not is_comment(l)]
                    return i + 1, range(i + 1, j + 2), body
            return i + 1, range(i + 1, len(lines) + 1), []
    return None, None, []


def parse(spec: Spec, body: list[str]) -> tuple[list[str], list[str]]:
    """(the values to look for elsewhere, malformed-entry problems)."""
    out, bad = [], []
    for line in body:
        if spec.path == MAC:
            m = MAC_ENTRY.match(line)
            fields = m.group(1).split(":") if m else []
            if len(fields) != spec.fields or not all(fields):
                bad.append(f"entry is not {spec.fields} non-empty colon-separated fields: "
                           f"{line.strip()}")
                continue
            if spec.kind_field is not None and fields[spec.kind_field] not in DEV_KINDS:
                bad.append(f"entry's kind {fields[spec.kind_field]!r} is not one of "
                           f"{'|'.join(DEV_KINDS)}: {line.strip()}")
                continue
            out += [fields[k] for k in spec.needles]
        else:
            m = WIN_ENTRY.match(line)
            if not m:
                bad.append(f'entry is not @{{ Label = "..."; Id = "..." }}: {line.strip()}')
                continue
            out += [m.group(1), m.group(2)]
    return list(dict.fromkeys(out)), bad


def function_body(path: str, lines: list[str], name: str) -> list[tuple[int, str]] | None:
    head = (re.compile(rf"^{re.escape(name)}\(\)\s*\{{") if path == MAC
            else re.compile(rf"^function\s+{re.escape(name)}\s*\{{", re.I))
    for i, line in enumerate(lines):
        if head.match(line):
            out = []
            for j in range(i + 1, len(lines)):
                if lines[j].startswith("}"):
                    break
                out.append((j + 1, lines[j]))
            return out
    return None


def token(v: str) -> re.Pattern[str]:
    return re.compile(r"(?<![A-Za-z0-9_.\-])" + re.escape(v) + r"(?![A-Za-z0-9_.\-])")


def problems(path: str, text: str, needles: dict[str, list[str]] | None = None) -> list[str]:
    """Everything wrong with one script. `needles` (list name -> values) overrides the values
    searched for: --rev passes today's, since the audited commit may have no list at all."""
    out = []
    lines = text.splitlines()
    exempt: set[int] = set()
    owner: dict[str, str] = {}
    for spec in (s for s in LISTS if s.path == path):
        decl_line, block, body = declaration(spec, lines)
        if block is None:
            out.append(f"{path}: no top-level `{spec.shown}` list")
        else:
            exempt |= set(block)
            if not body:
                out.append(f"{path}: `{spec.shown}` is empty - under bash 3.2 `set -u` "
                           f"iterating it exits")
        values, bad = parse(spec, body)
        out += [f"{path}: `{spec.shown}` {b}" for b in bad]
        for v in (needles[spec.name] if needles is not None else values):
            owner.setdefault(v, spec.shown)
        for i, line in enumerate(lines, 1):
            if i == decl_line or is_comment(line):
                continue
            if any(p.search(line) for p in spec.change):
                out.append(f"{path}:{i}: `{spec.shown}` is assigned or changed outside its one "
                           f"declaration: {line.strip()[:100]}")

    for p, fn, what, shown, pattern in REQUIRED:
        if p != path:
            continue
        body = function_body(path, lines, fn)
        if body is None:
            out.append(f"{path}: consumer {fn} not found")
        elif not any(re.search(pattern, l) for _, l in body if not is_comment(l)):
            out.append(f"{path}: {fn} does not build {what} from `{shown}`")

    for p, fn, calls in LITERAL_INSTALLS:
        if p != path:
            continue
        lit = re.compile(rf"\b(?:{calls})\s+(?!\"?\$)\S")
        for i, line in function_body(path, lines, fn) or []:
            if not is_comment(line) and lit.search(line):
                out.append(f"{path}:{i}: {fn} installs by a literal call, not from the list: "
                           f"{line.strip()[:100]}")

    allowed = [(s, why) for p, s, why in ALLOWED if p == path]
    pats = [(v, token(v)) for v in owner]
    for i, line in enumerate(lines, 1):
        if i in exempt or is_comment(line) or any(s in line for s, _ in allowed):
            continue
        hits = [v for v, pat in pats if pat.search(line)]
        if hits:
            lists = ", ".join(sorted({f"`{owner[h]}`" for h in hits}))
            out.append(f"{path}:{i}: names {', '.join(repr(h) for h in hits)} outside {lists}: "
                       f"{line.strip()[:100]}")
    return out


def stale_allowed(texts: dict[str, str]) -> list[str]:
    out = []
    for path, s, _ in ALLOWED:
        if not any(s in l for l in texts[path].splitlines() if not is_comment(l)):
            out.append(f"{path}: ALLOWED entry {s!r} matches no line - remove it")
    return out


def current_needles() -> dict[str, list[str]]:
    out = {}
    for spec in LISTS:
        _, _, body = declaration(spec, _read(spec.path, None).splitlines())
        out[spec.name] = parse(spec, body)[0]
    return out


# ── Self-test ───────────────────────────────────────────────────────────────────────────────

def self_test(verbose: bool) -> bool:
    real = {p: _read(p, None) for p in (MAC, WIN)}
    ok = True

    def run(path: str, text: str) -> list[str]:
        return problems(path, text) + stale_allowed({**real, path: text})

    def case(label: str, path: str, text: str, expect: list[str] | None) -> None:
        """expect=None: must report nothing. Otherwise every fragment must be in some problem."""
        nonlocal ok
        got = run(path, text)
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

    def cut(text: str, pattern: str) -> str:
        new, n = re.subn(pattern, "", text, count=1, flags=re.M)
        if n != 1:
            raise SystemExit(f"self-test fixture is stale: {pattern!r} matches nothing")
        return new

    mac, win = real[MAC], real[WIN]
    case("the real macOS script passes", MAC, mac, None)
    case("the real Windows script passes", WIN, win, None)

    # The copies #78 and #69 removed, put back one at a time.
    case("an install_cask line restated in install_core is reported", MAC,
         swap(mac, '  install_formula "GitHub CLI" "gh"\n',
              '  install_formula "GitHub CLI" "gh"\n  install_cask "Zoom" "zoom" "zoom.us"\n'),
         ["'Zoom', 'zoom', 'zoom.us'", "install_core installs by a literal call"])
    case("the core menu written as prose again (the #69 shape) is reported", MAC,
         swap(mac, """$(csa_labels ', ' "${CSA_CORE_APPS[@]}"), Git, GitHub CLI""",
              "1Password, Slack, Zoom, Chrome, Git, GitHub CLI"),
         ["'1Password', 'Slack', 'Zoom'", "select_profile does not build the menu's core line"])
    case("summary's reversed app[:label] array is reported", MAC,
         swap(mac, "  # Check apps\n",
              '  # Check apps\n  local -a check_apps=("1Password" "zoom.us:Zoom")\n'),
         ["'1Password', 'Zoom', 'zoom.us'"])
    case("a second copy of the core list inside preflight is reported", MAC,
         swap(mac, "  # Cask apps — check both brew cask and /Applications\n",
              "  # Cask apps — check both brew cask and /Applications\n  local -a cask_apps=(\n"
              '    "Slack:slack:Slack"\n  )\n'),
         ["'Slack', 'slack'"])
    case("the Windows next steps written as prose again are reported", WIN,
         swap(win, "Sign in to $(($CoreApps | ForEach-Object { $_.Label }) -join ', ')",
              "Sign in to 1Password, Slack, Zoom, and Chrome"),
         ["'1Password', 'Slack', 'Zoom'", "Show-Summary does not build the next steps"])
    case("an Install-WingetPackage line restated in Install-Core is reported", WIN,
         swap(win, "foreach ($app in $CoreApps) { Install-WingetPackage $app.Label $app.Id }",
              'Install-WingetPackage "Slack" "SlackTechnologies.Slack"'),
         ["'Slack', 'SlackTechnologies.Slack'", "Install-Core does not build the core install",
          "Install-Core installs by a literal call"])

    # The dev set.
    case("a dev plan line restated in preflight is reported", MAC,
         swap(mac, "    local kind package probe\n",
              '    plan_line "AWS CLI" "install via Homebrew"\n    local kind package probe\n'),
         ["'AWS CLI'"])
    case("the dev menu written as prose again is reported", MAC,
         swap(mac, """adds $(csa_labels ', ' "${CSA_DEV_TOOLS[@]}")""",
              "adds VS Code, AWS CLI, Wrangler"),
         ["'VS Code', 'AWS CLI', 'Wrangler'",
          "select_profile does not build the menu's developer line"])
    case("a dev install restated in install_dev is reported", MAC,
         swap(mac, '      npm)     install_npm_package "$label" "$package" "$probe" ;;\n',
              '      npm)     install_npm_package "$label" "$package" "$probe" ;;\n'
              '    esac\n    install_formula "AWS CLI" "awscli"\n    case x in\n'),
         ["'AWS CLI', 'awscli'", "install_dev installs by a literal call"])
    case("an Install-WingetPackage line restated in Install-Dev is reported", WIN,
         swap(win, "foreach ($app in $DevWingetApps) { Install-WingetPackage $app.Label $app.Id }",
              'Install-WingetPackage "AWS CLI" "Amazon.AWSCLI"'),
         ["'AWS CLI', 'Amazon.AWSCLI'", "Install-Dev does not build the developer install",
          "Install-Dev installs by a literal call"])

    # A NEW app added by a literal call is not in any list, so only the literal rule sees it.
    case("a new core app installed by a literal install_cask is reported", MAC,
         swap(mac, '  install_formula "GitHub CLI" "gh"\n',
              '  install_formula "GitHub CLI" "gh"\n  install_cask "Notion" "notion" "Notion"\n'),
         ["install_core installs by a literal call", 'install_cask "Notion"'])
    case("a new dev tool installed by a literal install_formula is reported", MAC,
         swap(mac, "  local entry label kind package probe\n  for entry in \"${CSA_DEV_TOOLS[@]}\"",
              '  install_formula "Terraform" "terraform"\n'
              "  local entry label kind package probe\n  for entry in \"${CSA_DEV_TOOLS[@]}\""),
         ["install_dev installs by a literal call", 'install_formula "Terraform"'])
    case("a new app installed by a literal Install-WingetPackage in Install-Core is reported", WIN,
         swap(win, "foreach ($app in $CoreApps) { Install-WingetPackage $app.Label $app.Id }",
              "foreach ($app in $CoreApps) { Install-WingetPackage $app.Label $app.Id }\n"
              '    Install-WingetPackage "Notion" "Notion.Notion"'),
         ["Install-Core installs by a literal call"])
    case("a new app installed by a literal Install-WingetPackage in Install-Dev is reported", WIN,
         swap(win, 'Install-NpmPackage "Wrangler" "wrangler" "wrangler"',
              'Install-NpmPackage "Wrangler" "wrangler" "wrangler"\n'
              '    Install-WingetPackage "Docker" "Docker.DockerDesktop"'),
         ["Install-Dev installs by a literal call"])
    case("Windows' literal Wrangler npm install in Install-Dev is not a literal-install problem",
         WIN, win, None)

    # A consumer that stops reading the list for one rendering, while another still does.
    case("summary's presence loop deleted (the next steps still read the list) is reported", MAC,
         cut(mac, r'^  for entry in "\$\{CSA_CORE_APPS\[@\]\}"; do\n    IFS=: read -r label _ '
                  r'app_name <<< "\$entry"\n(?:.*\n)*?  done\n'),
         ["summary does not build the installed-apps lines from `CSA_CORE_APPS`"])
    case("summary's developer loop deleted is reported", MAC,
         cut(mac, r'^    for entry in "\$\{CSA_DEV_TOOLS\[@\]\}"; do\n      IFS=: read -r label '
                  r'kind _ probe <<< "\$entry"\n(?:.*\n)*?    done\n'),
         ["summary does not build the developer lines from `CSA_DEV_TOOLS`"])
    case("Show-Summary's presence loop deleted (the next steps still read it) is reported", WIN,
         cut(win, r'^    # Core apps\n    foreach \(\$app in \$CoreApps\) \{\n        if '
                  r'\(Test-WingetInstalled \$app\.Id\) \{\n(?:.*\n)*?    \}\n'),
         ["Show-Summary does not build the installed-apps lines from `$CoreApps`"])

    # Changing a list after its declaration.
    tail_fn = "\nf() {\n  {}\n}\n"
    for label, path, line in [
        ("an indexed assignment, CSA_CORE_APPS[5]=…", MAC, 'CSA_CORE_APPS[5]="Notion:notion:Notion"'),
        ("unset CSA_CORE_APPS", MAC, "unset CSA_CORE_APPS"),
        ("unset of one dev entry", MAC, "unset 'CSA_DEV_TOOLS[2]'"),
        ("an append, CSA_CORE_APPS+=(…)", MAC, 'CSA_CORE_APPS+=("Notion:notion:Notion")'),
        ("a local re-declaration", MAC, 'local CSA_CORE_APPS=("Notion:notion:Notion")'),
        ("a readonly re-declaration", MAC, "readonly CSA_DEV_TOOLS"),
    ]:
        case(f"{label} is reported", path, real[path] + tail_fn.replace("{}", line),
             ["assigned or changed outside its one declaration"])
    case("a second top-level declaration is reported", MAC,
         mac + "\nCSA_CORE_APPS=(\n  \"Notion:notion:Notion\"\n)\n",
         ["assigned or changed outside its one declaration"])
    for label, line in [
        ("$CoreApps += @{…}", '$CoreApps += @{ Label = "Notion"; Id = "Notion.Notion" }'),
        ("$CoreApps[0].Label = …", '$CoreApps[0].Label = "Notion"'),
        ("$script:DevWingetApps = …", "$script:DevWingetApps = @()"),
        ("Remove-Variable CoreApps", "Remove-Variable -Name CoreApps"),
    ]:
        case(f"{label} is reported", WIN, win + "\nfunction F {\n    " + line + "\n}\n",
             ["assigned or changed outside its one declaration"])
    case("reading an element is not a change", MAC,
         mac + '\nf() {\n  local first="${CSA_CORE_APPS[0]}" n=${#CSA_DEV_TOOLS[@]}\n}\n', None)

    # The lists themselves.
    core = re.search(r"^CSA_CORE_APPS=\(\n(?:.*\n)*?\)\n", mac, re.M).group(0)
    case("no core list at all is reported", MAC, swap(mac, core, ""),
         ["no top-level `CSA_CORE_APPS`"])
    case("an empty dev list is reported", MAC,
         swap(mac, re.search(r"^CSA_DEV_TOOLS=\(\n(?:.*\n)*?\)\n", mac, re.M).group(0),
              "CSA_DEV_TOOLS=(\n)\n"), ["`CSA_DEV_TOOLS` is empty"])
    case("a two-field core entry is reported", MAC, swap(mac, '"Zoom:zoom:zoom.us"', '"Zoom:zoom"'),
         ["3 non-empty colon-separated fields"])
    case("a core entry with an empty field is reported", MAC,
         swap(mac, '"Slack:slack:Slack"', '"Slack::Slack"'), ["3 non-empty colon-separated fields"])
    case("a dev entry with an unknown kind is reported", MAC,
         swap(mac, '"AWS CLI:formula:awscli:aws"', '"AWS CLI:pip:awscli:aws"'), ["kind 'pip'"])
    case("a three-field dev entry is reported", MAC,
         swap(mac, '"AWS CLI:formula:awscli:aws"', '"AWS CLI:formula:awscli"'),
         ["4 non-empty colon-separated fields"])
    case("a Windows entry with no Id is reported", WIN,
         swap(win, '@{ Label = "Zoom";             Id = "Zoom.Zoom" },', '@{ Label = "Zoom" },'),
         ["is not @{"])

    # ALLOWED cannot rot in silence.
    case("an ALLOWED line that no longer exists is reported", MAC,
         swap(mac, "  - Run 'aws configure' to set up AWS credentials", "  - Configure AWS"),
         ["ALLOWED entry \"Run 'aws configure' to set up AWS credentials\" matches no line"])

    # What must NOT be reported, and the documented edges of whole-token matching.
    case("a full-line comment naming the apps is not reported", MAC,
         mac + "\n# Slack, zoom.us, google-chrome and awscli are in the lists\n", None)
    case("words that merely contain a value are not reported", MAC,
         mac + '\nf() {\n  echo "Slackware slack.com zoom.usx 1Passwords awscli2"\n}\n', None)
    case("a PowerShell comment naming the apps is not reported", WIN,
         win + "\n    # Install-WingetPackage \"Slack\" \"SlackTechnologies.Slack\"\n", None)
    case("unrelated prose using a value as a word ('zoom in') IS reported, as documented", MAC,
         mac + '\nf() {\n  echo "zoom in to read this"\n}\n', ["'zoom'"])
    case("a trailing comment naming an app IS reported, as documented", MAC,
         mac + "\nf() {\n  true  # Slack\n}\n", ["'Slack'"])

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
    needles = current_needles() if rev else None
    texts = {p: _read(p, rev) for p in (MAC, WIN)}
    found = []
    for path in (MAC, WIN):
        found += problems(path, texts[path], needles)
    if rev is None:
        found += stale_allowed(texts)
    where = f" at {rev}" if rev else ""
    if found:
        for f in found:
            print(f"  {f}")
        print(f"\n{len(found)} app-list problem(s){where}.")
        return 1
    print(f"app lists{where}: {len(LISTS)} lists, each declared once and never changed, read by "
          f"every consumer, installed only from the list, and named nowhere else "
          f"({len(ALLOWED)} ALLOWED lines, all still present).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
