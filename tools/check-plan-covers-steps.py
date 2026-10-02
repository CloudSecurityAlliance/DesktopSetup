#!/usr/bin/env python3
"""Every install step `main()` runs must appear in the plan the user agreed to.

These scripts are "show the plan -> confirm -> act". A plan that omits a step means the user
consented to something other than what happens, which is a correctness property and not
formatting. #76 fixed four such cases by hand:

| Plan said | main() did | Shape |
|---|---|---|
| Python: `install via Homebrew` / `install via winget` | uv installs it since #60 | wrong provider named |
| macOS Node: `installed (v26.8.1)` | since #74 that formula is *removed* and replaced | destructive step undisclosed |
| *(nothing)* | `Install-Uv` runs | **step absent from the plan** |
| *(nothing)* | `Install-DocPythonDeps` runs | **step absent from the plan** |

This catches the last two shapes - absence - and deliberately not the first two.

WHAT THIS DOES NOT CHECK, stated plainly so nobody trusts it further than it deserves: whether
a plan row's *wording* matches what the step does. Neither #76 case would have been caught here,
because both rows existed and read plausibly. `install via Homebrew` was simply stale. That
needs a human, and the CLAUDE.md rule added in #76 is the mitigation. A check believed beyond
its reach is worse than no check - `check-powershell-native.py`'s self-test exists for that
reason, and so does this paragraph.

HOW A ROW IS RECOGNISED. Not by parsing labels out of the plan: rows come in two styles, dotted
(`"  Git ............ installed"`) and column-padded (`"  Internal MCP servers install/upgrade"`),
and the padded ones can have a single space before their text when the label already fills the
column - which is how a first draft of this tool silently missed three real rows. Instead each
step is mapped to its label explicitly, in the spirit of `check-parity.py`'s `EQUIV`, and the
plan must contain that label at the start of a row. Explicit beats inferred here, because the
inference failed on the real file.

ONE ENTRY PER CONCEPT, NOT PER PLATFORM. The labels are identical on both sides, so the map is
keyed by a canonical name and `EQUIV` is imported from `check-parity.py` to translate. Two
consequences worth having: there is no second list of counterparts to drift from the first, and
cross-platform label parity falls out for free - both platforms look up the same label, so a
plan missing it on one side is reported for that side.

    python3 tools/check-plan-covers-steps.py [--rev <git-rev>]

WHAT COUNTS AS A STEP, and the limit that follows. On Windows a bare `Verb-Noun` on its own line
inside `Main` is a step; anything with arguments, a pipe or an assignment is not. On macOS a
bare line is a step only if the file also DEFINES a function by that name - which is what keeps
`echo`, `info` and `warn` out of the list, and means a step delegated to an external command or
a sourced file would not be seen. Both extractors are therefore bounded by the file, and that is
the scope being claimed: *every step this script defines and calls from main()*.


`--rev` reads the scripts from a git revision instead of disk, which is how the validation in
#80 is reproducible rather than asserted: at `0846924` (the commit before #76) this must report
exactly `Install-Uv` and `Install-DocPythonDeps` on the Windows side, and nothing else.
"""

import importlib.util
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_equiv() -> dict[str, str]:
    """macOS name -> Windows name, from check-parity.py rather than restated here."""
    spec = importlib.util.spec_from_file_location("_cp", ROOT / "tools" / "check-parity.py")
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load tools/check-parity.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(mod.EQUIV)


EQUIV = _load_equiv()

# A PREIMAGE SET, not a reversed dict. EQUIV is many-to-one - `setup_plugin_marketplaces` and
# `sync_plugin_marketplaces` both map to `Setup-PluginMarketplaces` - so `{w: m for m, w in ...}`
# keeps whichever came last, arbitrarily and without complaint. That is how the first run of this
# tool reported `Setup-PluginMarketplaces` as unmapped: canon() had resolved it to
# `sync_plugin_marketplaces`, a name the label map has no reason to know.
WIN_TO_MAC: dict[str, list[str]] = {}
for _m, _w in EQUIV.items():
    WIN_TO_MAC.setdefault(_w, []).append(_m)

# Canonical step -> the label its plan row must start with. Canonical is the macOS name where a
# counterpart exists (so EQUIV can translate), and the platform's own name where it does not.
PLAN_LABEL: dict[str, str] = {
    # both platforms
    "install_git": "Git",
    "install_gh": "GitHub CLI",
    "install_uv": "uv",
    "install_python": "Python",
    "install_node": "Node.js",
    "install_doc_python_deps": "Preflight deps",
    "install_1password": "1Password",
    "install_1password_cli": "1Password CLI",
    "install_claude_desktop": "Claude Desktop",
    "install_chatgpt": "ChatGPT Desktop",
    "install_claude": "Claude Code",
    "install_codex": "Codex CLI",
    "install_gemini": "Gemini CLI",
    "setup_claude_env": "CLAUDE_CODE_NO_FLICKER",
    "setup_plugin_marketplaces": "Plugin marketplaces",
    "setup_csa_mcp_server": "CSA MCP server",
    "setup_csa_internal_tools": "Internal MCP servers",
    # macOS only
    "install_xcode_cli_tools": "Xcode CLI Tools",
    "install_homebrew": "Homebrew",
    # Windows only
    "Set-LongPathSupport": "Long paths",
}

# A step whose label is one of two rows. `pandoc` and `typst` are installed by one step and
# previewed as two, which is right for the reader and needs saying here.
PLAN_LABEL_EXTRA: dict[str, list[str]] = {
    "install_doc_toolchain": ["pandoc", "typst"],
}

# Steps with no plan row, each with the reason - the shape check-parity.py uses for
# PLATFORM_ONLY. An entry that matches no step is reported, so this list cannot quietly rot.
PLAN_EXEMPT: dict[str, str] = {
    # Control flow and display. These are not installs; previewing them would be previewing
    # the preview.
    "check_running_tools": "runs before the plan and prints its own finding",
    "preflight": "is the plan",
    "summary": "reports what happened, after the fact",
    "csa_show_todo_list": "renders what the run collected; nothing to preview",
    "Detect-NonInteractive": "decides how to prompt; takes no action to preview",
    "Test-Preconditions": "aborts before the plan is shown if the machine is unsuitable",
    # Interactive flows that report their own state as they go. A plan row would have to
    # describe a browser handshake, and the step already prints whether it is needed.
    "setup_gh_auth": "interactive sign-in; prints whether a token is already present",
    "setup_git_identity": "interactive; prints the identity it finds before offering to set one",
    # Installed, but previewed by a nested function rather than a row of its own, because the
    # list is derived from what the account can see. Asserted below rather than exempted
    # blindly: the plan must still CALL that preview.
    "install_plugins": "previewed by install_plugins_preview / Show-PluginsPreview, asserted separately",
}

# For the one exemption that is really "previewed differently", say what must be present.
PREVIEW_CALL = {
    "scripts/macos-ai-tools.sh": "install_plugins_preview",
    "scripts/windows-ai-tools.ps1": "Show-PluginsPreview",
}

SCRIPTS = {
    "scripts/macos-ai-tools.sh": ("main() {", "preflight() {"),
    "scripts/windows-ai-tools.ps1": ("function Main {", "function Show-Preflight"),
}


def _read(path: str, rev: str | None) -> str:
    if rev is None:
        return (ROOT / path).read_text(encoding="utf-8")
    # encoding explicitly, not text=True: these scripts hold UTF-8 punctuation and the locale
    # on a Windows box is cp1252. check-script-versions.py was bitten by exactly this.
    r = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, capture_output=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"cannot read {path} at {rev}: {r.stderr.strip()}")
    return r.stdout


def _span(lines: list[str], opener: str) -> tuple[int, int]:
    """A top-level function body: its opening line to the first `}` in column zero."""
    start = next((i for i, l in enumerate(lines) if l.startswith(opener)), -1)
    if start < 0:
        raise SystemExit(f"cannot find {opener!r}")
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == "}"), -1)
    if end < 0:
        raise SystemExit(f"{opener!r} has no closing brace in column zero")
    return start, end


def steps_in_main(text: str, path: str) -> list[str]:
    lines = text.splitlines()
    start, end = _span(lines, SCRIPTS[path][0])
    body = lines[start + 1 : end]
    if path.endswith(".ps1"):
        # A bare `Verb-Noun` on its own line is a call. Anything with arguments, a pipe or an
        # assignment is not a step in this sense.
        return [l.strip() for l in body if re.fullmatch(r"\s*[A-Z][A-Za-z]+-[A-Za-z0-9]+\s*", l)]
    defined = set(re.findall(r"^([a-z_][a-z0-9_]*)\(\)", text, re.M))
    return [l.strip() for l in body if l.strip() in defined]


def plan_body(text: str, path: str) -> str:
    lines = text.splitlines()
    start, end = _span(lines, SCRIPTS[path][1])
    return "\n".join(lines[start : end + 1])


def plan_has(body: str, label: str) -> bool:
    """A row starting with this label: a quote, two spaces, the label, then a space or a dot.

    The trailing-character requirement is what stops `Git` from being satisfied by
    `GitHub CLI ........`, which is a real pair in these files.
    """
    return re.search(r'"\s{2}' + re.escape(label) + r"(?=[ .\"])", body) is not None


def canon(step: str) -> str:
    """The canonical (macOS-side) name, or the step itself when it has no counterpart.

    Where several macOS names share one Windows name, the one the maps actually use wins; the
    first is the fallback so the result is deterministic either way.
    """
    for cand in candidates(step):
        if cand in PLAN_LABEL or cand in PLAN_LABEL_EXTRA or cand in PLAN_EXEMPT:
            return cand
    return candidates(step)[0]


def candidates(step: str) -> list[str]:
    """Every name this step could be known by: itself, then its EQUIV preimages."""
    return [step, *WIN_TO_MAC.get(step, [])] if step not in EQUIV else [step]


def audit(path: str, rev: str | None) -> tuple[list[str], set[str]]:
    text = _read(path, rev)
    steps = steps_in_main(text, path)
    body = plan_body(text, path)
    problems: list[str] = []
    seen: set[str] = set()

    for step in steps:
        key = canon(step)
        seen.add(key)
        seen.add(step)
        if step in PLAN_EXEMPT or key in PLAN_EXEMPT:
            continue
        labels = PLAN_LABEL_EXTRA.get(key) or PLAN_LABEL_EXTRA.get(step)
        if labels is None:
            label = PLAN_LABEL.get(key) or PLAN_LABEL.get(step)
            if label is None:
                problems.append(
                    f"{path}: {step} runs in main() but is in neither PLAN_LABEL nor "
                    f"PLAN_EXEMPT - decide which, and if it is exempt say why"
                )
                continue
            labels = [label]
        for label in labels:
            if not plan_has(body, label):
                problems.append(
                    f"{path}: {step} runs in main() but the plan has no \"{label}\" row - "
                    f"the user agreed to a list that does not mention it"
                )

    # The one exemption that is really "previewed elsewhere" must still be previewed.
    call = PREVIEW_CALL.get(path)
    if call and any(canon(s) == "install_plugins" for s in steps) and call not in body:
        problems.append(
            f"{path}: install_plugins is exempt because {call} previews it, and the plan does "
            f"not call {call} - so nothing previews it at all"
        )

    return problems, seen


def self_test() -> None:
    """Each rule broken on purpose. A check that has not been seen to fail proves nothing."""
    # plan_has must anchor on a row start, and must not let a longer label satisfy a shorter one
    assert plan_has('Write-Host "  Git ............ installed"', "Git")
    assert plan_has('echo "  uv ................ install via Homebrew"', "uv")
    assert plan_has('Write-Host "  Internal MCP servers install/upgrade 4 servers"',
                    "Internal MCP servers"), "column-padded row with ONE space missed"
    assert not plan_has('Write-Host "  GitHub CLI ........ installed"', "Git"), \
        "'Git' was satisfied by the 'GitHub CLI' row - both exist in these files"
    assert not plan_has('Write-Host "installed Git here"', "Git"), "matched mid-sentence"
    assert plan_has('Write-Host "  CLAUDE_CODE_NO_FLICKER  already set"',
                    "CLAUDE_CODE_NO_FLICKER")

    # step extraction: a bare Verb-Noun is a step; a call with arguments or a pipe is not
    ps = (
        "function Main {\n"
        "    Install-Git\n"
        "    Write-Host \"x\"\n"
        "    $v = Get-Thing\n"
        "    Install-Uv\n"
        "}\n"
    )
    got = steps_in_main(ps, "scripts/windows-ai-tools.ps1")
    assert got == ["Install-Git", "Install-Uv"], got

    sh = (
        "install_git() {\n  :\n}\n"
        "install_uv() {\n  :\n}\n"
        "main() {\n"
        "  install_git\n"
        "  echo hi\n"
        "  install_uv\n"
        "}\n"
    )
    got = steps_in_main(sh, "scripts/macos-ai-tools.sh")
    assert got == ["install_git", "install_uv"], got

    # canon() must translate a Windows name through EQUIV, or this map would need two entries
    assert canon("Install-Uv") == "install_uv"
    assert canon("Set-LongPathSupport") == "Set-LongPathSupport", "platform-only name mangled"
    # The many-to-one case that the first draft got wrong, asserted so it cannot come back.
    assert len(WIN_TO_MAC["Setup-PluginMarketplaces"]) == 2,         "EQUIV no longer has two macOS names for Setup-PluginMarketplaces; the preimage "         "handling may be untested now, but leave it - inverting a many-to-one map is the bug"
    assert canon("Setup-PluginMarketplaces") == "setup_plugin_marketplaces",         "the preimage that the maps actually use must win"


def main(argv: list[str]) -> int:
    self_test()
    rev = None
    if "--rev" in argv:
        rev = argv[argv.index("--rev") + 1]

    all_problems: list[str] = []
    all_seen: set[str] = set()
    for path in SCRIPTS:
        problems, seen = audit(path, rev)
        all_problems.extend(problems)
        all_seen |= seen
        where = f"{path} at {rev}" if rev else path
        print(f"{where}: {len(problems)} step(s) missing from the plan")

    # Stale entries. An allowlist that outlives what it allowed is how a guard stops meaning
    # anything - check-parity.py reports its own for the same reason.
    stale_exempt = sorted(k for k in PLAN_EXEMPT if k not in all_seen)
    stale_label = sorted(
        k for k in list(PLAN_LABEL) + list(PLAN_LABEL_EXTRA) if k not in all_seen
    )
    # Under --rev the allowlists belong to the CURRENT tree and the code is historical, so a
    # "stale" entry usually means the step had not been written yet. Reporting it as a problem
    # would make every historical validation fail for a reason that is not a defect, so it is
    # a note there and a problem here.
    stale = [f"PLAN_EXEMPT has {k!r}, which no main() calls any more - remove it"
             for k in stale_exempt]
    stale += [f"PLAN_LABEL has {k!r}, which no main() calls any more - remove it"
              for k in stale_label]
    if rev and stale:
        print()
        for line in stale:
            print(f"  note (--rev, so this is about today's list, not that commit): {line}")
    else:
        all_problems.extend(stale)

    if all_problems:
        print()
        for p in all_problems:
            print(f"  {p}")
        print(
            f"\n{len(all_problems)} problem(s). The plan is what the user agreed to; a step "
            f"it does not mention is a step nobody consented to.\n"
            f"Note this checks PRESENCE only - it cannot tell you a row's wording is still true."
        )
        return 1
    print("\nevery step in both main() functions is named in its plan, or exempt with a reason.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
