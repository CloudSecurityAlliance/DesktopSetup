#!/usr/bin/env python3
"""Every macOS script must have a Windows counterpart, and their main() flows must match.

check-duplication.py proves that a function present in several scripts has the same body in
each. It cannot see a function that is *absent* — and absence is the failure that shipped. Three
gaps closed in #69, none detectable by any check that existed:

  - there was no windows-update.ps1 at all, while macos-update.sh had existed for months;
  - windows-plugins.ps1 never ran the internal MCP-server setup macos-plugins.sh runs (#65);
  - windows-work-tools.ps1 never set the Git identity macos-work-tools.sh sets, while still
    requesting the gh `user:email` scope with a comment saying the scope existed for that step.

All three were found by hand in minutes, by pulling each script's main() call sequence and laying
the two platforms side by side. This is that, run on every PR. Whole-file diffs are useless across
bash and PowerShell, which share no syntax; the *sequence of steps* is the same abstraction on both
sides, and a missing line in a twelve-line list is obvious where a missing function in 900 is not.

Why a check and not care: these scripts are silent by default — a step with nothing to do prints
nothing, so users outside CSA see no chatter about repos they cannot reach. That is the right
contract, and its price is that "absent" and "nothing to do" look identical at the terminal. An
omission produces a clean, quiet, successful run, so nobody ever reports one.

Steps are compared as sets, not sequences: the platforms legitimately order their base layers
differently. A step on one side only must be named in PLATFORM_ONLY (every pair) or PER_PAIR (one
pair) with a reason, so allowing a difference is a deliberate act, as in check-duplication.py's
PER_SCRIPT. An allowlist entry that no longer matches any script is itself reported: an exception
for a step that no longer exists has stopped checking without failing.

Self-tests before it reports, on fixtures it must fail and one it must pass.

    python3 tools/check-parity.py
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# macOS script -> its Windows counterpart. A missing file on either side fails the check.
PAIRS = {
    "macos-ai-tools.sh": "windows-ai-tools.ps1",
    "macos-work-tools.sh": "windows-work-tools.ps1",
    "macos-update.sh": "windows-update.ps1",
    "macos-plugins.sh": "windows-plugins.ps1",
}
# Pairs with no main() to compare, checked for existence only.
PRESENCE_ONLY = {"clone-and-claude.sh": "clone-and-claude.ps1"}

# Output and plumbing helpers are not steps.
HELPERS = {
    "info", "success", "warn", "error", "abort", "confirm", "has_command",
    "Write-Info", "Write-Success", "Write-Warn", "Write-Err", "Abort", "Confirm-Step",
    "Has-Command", "Invoke-NativeOutput", "Invoke-NativeShow", "Invoke-NativeQuiet",
    "Invoke-NativeCapture", "Invoke-NativeNpm",
}

# bash step -> PowerShell step. Many-to-one is fine.
EQUIV = {
    "check_running_tools": "Check-RunningTools",
    "select_profile": "Select-Profile",
    "preflight": "Show-Preflight",
    "summary": "Show-Summary",
    "install_git": "Install-Git",
    "install_gh": "Install-GH",
    "setup_gh_auth": "Setup-GHAuth",
    "setup_git_identity": "Setup-GitIdentity",
    "install_node": "Install-Node",
    "install_uv": "Install-Uv",
    "install_python": "Install-Python",
    "install_doc_toolchain": "Install-DocToolchain",
    "install_doc_python_deps": "Install-DocPythonDeps",
    "install_1password": "Install-1Password",
    "install_1password_cli": "Install-1PasswordCLI",
    "install_claude_desktop": "Install-ClaudeDesktop",
    "install_chatgpt": "Install-ChatGPT",
    "install_claude": "Install-Claude",
    "install_codex": "Install-Codex",
    "install_gemini": "Install-Gemini",
    "setup_claude_env": "Setup-ClaudeEnv",
    "install_core": "Install-Core",
    "install_dev": "Install-Dev",
    "setup_plugin_marketplaces": "Setup-PluginMarketplaces",
    # The updater's bash version also refreshes; the PowerShell updater does that refresh
    # inline in Main right after this step. Same capability, split differently.
    "sync_plugin_marketplaces": "Setup-PluginMarketplaces",
    "install_plugins": "Install-Plugins",
    "setup_csa_mcp_server": "Register-CSAMcpServer",
    "setup_csa_internal_tools": "Invoke-CSAInternalSetup",
    "snapshot": "Save-Snapshot",
    "update_brew": "Update-Winget",
    "update_npm": "Update-Npm",
    "update_pip": "Update-Python",
    "update_claude_code": "Update-ClaudeCode",
}

# Steps that exist on one platform only, in every pair where they appear.
PLATFORM_ONLY = {
    "install_xcode_cli_tools": "Homebrew needs the Xcode Command Line Tools; Windows has no "
                               "equivalent prerequisite",
    "install_homebrew": "Homebrew must be installed on macOS; winget ships with Windows as App "
                        "Installer, so there is nothing to install",
    "ensure_brew_in_path": "Homebrew's shellenv has to be loaded into PATH on macOS; winget is on "
                           "PATH by default",
    "Detect-NonInteractive": "the bash scripts detect non-interactive mode at top level, before "
                             "main(); PowerShell does it as a Main step",
    "Test-Preconditions": "the bash scripts run their precondition checks at top level, before "
                          "main(); PowerShell does it as a Main step",
    "Set-LongPathSupport": "sets git core.longpaths for Windows' 260-character MAX_PATH limit, "
                           "which macOS does not have",
}

# Structural differences confined to one pair.
PER_PAIR = {
    ("macos-work-tools.sh", "windows-work-tools.ps1"): {
        "Install-Git": "macOS installs Git inside install_core; Windows installs it as a base-"
                       "layer step first, because Set-LongPathSupport needs git present",
        "Install-GH": "macOS installs the GitHub CLI inside install_core; Windows installs it as "
                      "its own base-layer step",
    },
}

BASH_TOKEN = re.compile(r"\b[a-z_][a-z0-9_]*\b")
PS_TOKEN = re.compile(r"\b[A-Z][A-Za-z0-9]*-[A-Za-z0-9]+\b")


def steps(text: str, bash: bool) -> list[str] | None:
    """Functions defined in this script and called from its main(), minus helpers, in order."""
    pat = r"^main\(\)\s*\{\n(.*?)^\}" if bash else r"^function Main\s*\{\n(.*?)^\}"
    m = re.search(pat, text, re.S | re.M)
    if not m:
        return None
    if bash:
        defined = set(re.findall(r"^([a-z_][a-z0-9_]*)\(\)\s*\{", text, re.M))
        tokens = BASH_TOKEN.findall(m.group(1))
    else:
        defined = set(re.findall(r"^function\s+([A-Za-z][A-Za-z0-9-]*)", text, re.M))
        tokens = PS_TOKEN.findall(m.group(1))
    out: list[str] = []
    for t in tokens:
        if t in defined and t not in HELPERS and t not in out:
            out.append(t)
    return out


def compare(mac_name: str, win_name: str, mac: list[str], win: list[str],
            seen: set[str]) -> list[str]:
    seen.update(mac, win)
    allowed = PER_PAIR.get((mac_name, win_name), {})
    found = []
    mapped = set()
    for s in mac:
        if s in PLATFORM_ONLY or s in allowed:
            continue
        target = EQUIV.get(s)
        if target is None:
            found.append(f"{mac_name}: step `{s}` has no Windows equivalent in EQUIV — map it, "
                         f"or name it in PLATFORM_ONLY/PER_PAIR with a reason")
        elif target not in win:
            found.append(f"{win_name}: missing `{target}` — {mac_name} runs `{s}` in main()")
        else:
            mapped.add(target)
    for s in win:
        if s in mapped or s in PLATFORM_ONLY or s in allowed:
            continue
        if s in EQUIV.values():
            sources = [b for b, p in EQUIV.items() if p == s]
            found.append(f"{mac_name}: missing `{' / '.join(sources)}` — {win_name} runs `{s}`")
        else:
            found.append(f"{win_name}: step `{s}` has no macOS equivalent in EQUIV — map it, or "
                         f"name it in PLATFORM_ONLY/PER_PAIR with a reason")
    return found


def check(files: dict[str, str]) -> tuple[list[str], set[str]]:
    found: list[str] = []
    seen: set[str] = set()
    for mac_name, win_name in {**PAIRS, **PRESENCE_ONLY}.items():
        for name in (mac_name, win_name):
            if name not in files:
                other = win_name if name == mac_name else mac_name
                found.append(f"{name}: does not exist, but {other} does — every script needs a "
                             f"counterpart on the other platform")
    for mac_name, win_name in PAIRS.items():
        if mac_name not in files or win_name not in files:
            continue
        mac = steps(files[mac_name], bash=True)
        win = steps(files[win_name], bash=False)
        if mac is None or win is None:
            found.append(f"{mac_name if mac is None else win_name}: no main()/Main found to compare")
            continue
        found += compare(mac_name, win_name, mac, win, seen)
    return found, seen


def stale_allowlist(seen: set[str]) -> list[str]:
    stale = [f"PLATFORM_ONLY `{k}` matches no script's main() — remove it"
             for k in PLATFORM_ONLY if k not in seen]
    for pair, entries in PER_PAIR.items():
        stale += [f"PER_PAIR {pair[1]} `{k}` matches no script's main() — remove it"
                  for k in entries if k not in seen]
    stale += [f"EQUIV `{b}` -> `{p}` matches no script's main() — remove it"
              for b, p in EQUIV.items() if b not in seen and p not in seen]
    return stale


def self_test() -> None:
    mac = ("main() {\n  preflight\n  setup_git_identity\n  setup_csa_internal_tools\n}\n"
           "preflight() {\n}\nsetup_git_identity() {\n}\nsetup_csa_internal_tools() {\n}\n")
    win_ok = ("function Show-Preflight {}\nfunction Setup-GitIdentity {}\n"
              "function Invoke-CSAInternalSetup {}\n"
              "function Main {\n    Show-Preflight\n    Setup-GitIdentity\n"
              "    Invoke-CSAInternalSetup\n}\n")
    # The #65 shape: the Windows script simply never runs the internal setup.
    win_missing = ("function Show-Preflight {}\nfunction Setup-GitIdentity {}\n"
                   "function Main {\n    Show-Preflight\n    Setup-GitIdentity\n}\n")
    # An unmapped step must not slip through as "no difference".
    win_unmapped = win_ok.replace("function Main {\n",
                                  "function Do-Surprise {}\nfunction Main {\n    Do-Surprise\n")
    probs = []
    got_ok = compare("macos-ai-tools.sh", "windows-ai-tools.ps1",
                     steps(mac, True), steps(win_ok, False), set())
    got_missing = compare("macos-ai-tools.sh", "windows-ai-tools.ps1",
                          steps(mac, True), steps(win_missing, False), set())
    got_unmapped = compare("macos-ai-tools.sh", "windows-ai-tools.ps1",
                           steps(mac, True), steps(win_unmapped, False), set())
    # The missing-script shape: a macOS script with no Windows file at all.
    got_absent, _ = check({k: "" for k in [*PAIRS, *PAIRS.values(), *PRESENCE_ONLY,
                                           *PRESENCE_ONLY.values()]
                           if k != "windows-update.ps1"})
    if got_ok:
        probs.append(f"reported a matching pair: {got_ok}")
    if not any("Invoke-CSAInternalSetup" in g for g in got_missing):
        probs.append(f"missed an absent step (the #65 shape): {got_missing}")
    if not any("Do-Surprise" in g for g in got_unmapped):
        probs.append(f"missed an unmapped step: {got_unmapped}")
    if not any("windows-update.ps1: does not exist" in g for g in got_absent):
        probs.append("missed an absent counterpart script")
    if probs:
        print("SELF-TEST FAILED — this check cannot be trusted:")
        for p in probs:
            print(f"  {p}")
        sys.exit(2)


def main() -> int:
    self_test()
    files = {p.name: p.read_text(encoding="utf-8")
             for p in sorted(SCRIPTS.iterdir()) if p.suffix in (".sh", ".ps1")}
    found, seen = check(files)
    found += stale_allowlist(seen)
    if found:
        for f in found:
            print(f)
        print(f"\n{len(found)} parity problem(s).")
        return 1
    print(f"{len(PAIRS)} script pairs have matching main() steps; "
          f"{len(PRESENCE_ONLY)} presence-only pair(s) exist; no stale allowlist entries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
