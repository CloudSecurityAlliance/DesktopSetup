#!/usr/bin/env python3
"""The macOS desktop-app logic: what counts as running, how the wait ends, and which state the
plan and the install act on.

Four things are under test, all extracted from scripts/macos-ai-tools.sh rather than copied,
so a test cannot drift from what ships:

  app_running / wait_for_app_exit
      An app is about to be replaced only after the person has quit it. "Running" is the
      app's MAIN executable only; nothing else in the bundle counts - not the vendor's launchd
      agents (LoginItems, LaunchServices, Helpers), and not even a crash handler under
      Frameworks, which can have launchd as its parent and outlive the app - because a wait
      that counted them might never end. Matched by path prefix, so a look-alike bundle
      ("Copilot Beta.app", "Copilot.app.bak") is not the app. With nobody at the keyboard it
      must not wait at all; interactively it must ask, every minute, whether to keep waiting,
      so it can always be left - and an app quit while that question is on screen counts as quit.

  install_copilot_desktop
      Nothing is removed before its replacement is on disk and verified. The Homebrew Copilot's
      uninstall deletes the app, so a download, signature, Gatekeeper or sudo failure after it
      would leave no Copilot at all (independent review, 2026-10-25). Run against stubs that
      record the order of calls.

  gemini_desktop_state
      `brew install --cask gemini` is MacPaw's duplicate-file cleaner, and Google's app is
      also Gemini.app. Only the bundle identifier tells them apart, and an unrelated
      Gemini.app must never be treated as installed OR installed over. Apple Silicon and
      macOS 15 are required.

  copilot_desktop_state / copilot_app_path
      Found through the package receipt (which records its own volume and location), so the
      former app and the unified one are both recognised whatever the bundle is called; a
      receipt for an app dragged to the Trash is not an install. macOS 14 is required.

The wait cases run against a stubbed `ps` and a `sleep` that only counts, so they take no
real time; a `ps` that is called absurdly often kills the harness, so a broken loop fails the
test instead of hanging it.

A CONTROL, as in test_npm_output_filter.py: the agent and look-alike cases are re-run against
a naive `ps | grep -q "$bundle"` matcher, which must FAIL them. A test that would pass the
naive version is not testing the thing that matters.

    python3 tests/test_desktop_apps.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def _posix_bash() -> str:
    r"""Absolute path to a POSIX bash. Resolved once, absolutely, for two reasons.

    These tests replace PATH with a stub-only directory, so a bare "bash" could not be
    found there. And on Windows a bare "bash" is resolved by CreateProcess against the
    PARENT process's PATH, which finds C:\Windows\System32\bash.exe -- the WSL launcher,
    not a shell. It exits 1 with a UTF-16LE "no installed distributions" message, so the
    failure reads as this test failing rather than as bash being absent.

    Git Bash counts as POSIX for our purposes: measured on MINGW64_NT-10.0-26200, it
    resolves and runs a shebang'd stub off PATH even though Windows cannot set the exec
    bit (chmod(0o755) leaves mode 0o666) and `test -x` on that stub reports false.
    """
    override = os.environ.get("CSA_TEST_BASH")
    if override:
        return override
    if os.name != "nt":
        return "/bin/bash"
    for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(candidate):
            return candidate
    found = shutil.which("bash")
    if found and "System32" not in found:      # never the WSL launcher
        return found
    raise SystemExit("no POSIX bash found - install Git for Windows, or set CSA_TEST_BASH")


BASH = _posix_bash()
ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "macos-ai-tools.sh"

BUNDLE = "/Applications/Copilot.app"
MAIN = f"{BUNDLE}/Contents/MacOS/Copilot"
RENDERER = (f"{BUNDLE}/Contents/Frameworks/Microsoft Edge Framework.framework/Versions/"
            "153.0.4234.38/Helpers/Microsoft Edge Helper (Renderer).app/Contents/MacOS/"
            "Microsoft Edge Helper (Renderer)")
# Seen beside the running apps on 2026-10-24: launchd jobs living inside the bundles.
AGENTS = [
    f"{BUNDLE}/Contents/Library/LoginItems/CopilotAppHost.app/Contents/MacOS/CopilotAppHost",
    f"{BUNDLE}/Contents/Library/LaunchServices/com.microsoft.EdgeUpdater.helper",
    f"{BUNDLE}/Contents/Helpers/crashpad_handler",
]
# Seen 2026-10-25 under Copilot's Frameworks with launchd (ppid 1) as its parent, so it may
# outlive the app: a wait that counted it might never end.
CRASHPAD = (f"{BUNDLE}/Contents/Frameworks/Microsoft Edge Framework.framework/Versions/"
            "153.0.4234.38/Helpers/msedge_crashpad_handler")
LOOKALIKES = [
    "/Applications/Copilot.app.bak/Contents/MacOS/Copilot",
    "/Applications/Copilot Beta.app/Contents/MacOS/Copilot",
    "/Users/someone/Applications/Copilot.app/Contents/MacOS/Copilot",
]
OTHER_APP = "/Applications/Claude.app/Contents/MacOS/Claude"
FOREVER = 100000

NAIVE_APP_RUNNING = """app_running() {
  ps -x -U "$(id -u)" -o comm= 2>/dev/null | grep -q -F "$1"
}"""


def extract(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not match:
        raise SystemExit(f"could not find {name}() in {SOURCE.name}")
    return match.group(0)


def constants(text: str, *names: str) -> str:
    out = []
    for name in names:
        match = re.search(rf"^{name}=.*$", text, re.M)
        if not match:
            raise SystemExit(f"could not find {name}= in {SOURCE.name}")
        out.append(match.group(0))
    return "\n".join(out)


TEXT = SOURCE.read_text(encoding="utf-8")


def run_bash(script: str, stdin: str = "", env_extra: dict[str, str] | None = None) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    env = {"PATH": "/usr/bin:/bin", "HOME": tempfile.gettempdir()}
    env.update(env_extra or {})
    try:
        proc = subprocess.run([BASH, path], input=stdin, capture_output=True, text=True,
                              env=env, timeout=60)
    finally:
        os.unlink(path)
    return proc.stdout + proc.stderr


# ── the wait ─────────────────────────────────────────────────────────

def run_wait(running: list[str], polls: int, always: list[str] | None = None,
             stdin: str = "", noninteractive: bool = False,
             app_running: str | None = None) -> tuple[str, int, int]:
    """(output, exit status, sleeps). `running` is listed by the first `polls` ps calls."""
    state = tempfile.mkdtemp(prefix="csa-wait-")
    try:
        pathlib.Path(state, "ps_calls").write_text("0", encoding="utf-8")
        pathlib.Path(state, "sleeps").write_text("0", encoding="utf-8")
        pathlib.Path(state, "running").write_text("".join(f"{p}\n" for p in running),
                                                  encoding="utf-8")
        pathlib.Path(state, "always").write_text("".join(f"{p}\n" for p in (always or [])),
                                                 encoding="utf-8")
        # The real confirm, renamed and wrapped: `read -p` prints its prompt only when stdin is a
        # terminal, and here it is a pipe, so the question is recorded by the wrapper instead.
        real_confirm = extract(TEXT, "confirm").replace("confirm() {", "real_confirm() {", 1)
        script = f"""#!/usr/bin/env bash
set -euo pipefail
info() {{ echo "INFO $*"; }}
warn() {{ echo "WARN $*"; }}
success() {{ echo "OK $*"; }}
{real_confirm}
confirm() {{ echo "ASKED: $1"; real_confirm "$1"; }}
{app_running if app_running is not None else extract(TEXT, "app_running")}
{extract(TEXT, "wait_for_app_exit")}

STATE='{state}'
id() {{ echo 501; }}
# `ps` runs on the left of a pipe, so in a subshell: the count lives in a file. $$ is still the
# harness, so a runaway loop is killed rather than left to hang.
ps() {{
  local n
  n=$(cat "$STATE/ps_calls"); n=$((n + 1)); echo "$n" > "$STATE/ps_calls"
  if [[ $n -gt 500 ]]; then echo "RUNAWAY" >&2; kill -TERM $$; fi
  if [[ $n -le {polls} ]]; then cat "$STATE/running"; fi
  cat "$STATE/always"
}}
sleep() {{ local n; n=$(cat "$STATE/sleeps"); echo $((n + 1)) > "$STATE/sleeps"; }}

status=0
wait_for_app_exit "Copilot" "{BUNDLE}" || status=$?
echo "CSA_TEST_EXIT=$status"
echo "CSA_TEST_SLEEPS=$(cat "$STATE/sleeps")"
"""
        out = run_bash(script, stdin, {"NONINTERACTIVE": "1"} if noninteractive else None)
    finally:
        shutil.rmtree(state, ignore_errors=True)
    status = re.search(r"CSA_TEST_EXIT=(\d+)", out)
    sleeps = re.search(r"CSA_TEST_SLEEPS=(\d+)", out)
    return out, int(status.group(1)) if status else -1, int(sleeps.group(1)) if sleeps else -1


# ── the states ───────────────────────────────────────────────────────

STATE_FUNCS = ["get_app_bundle_id", "macos_major", "is_apple_silicon", "gemini_desktop_state",
               "copilot_app_path", "copilot_desktop_state"]


def run_state(call: str, *, brew_casks: tuple[str, ...] = (), bundle_id: str = "",
              arm: bool = True, macos: str = "26.1", gemini_app: bool = False,
              receipt: tuple[str, str, str] | None = None, receipt_app_exists: bool = False,
              copilot_app: bool = False, migration: str = "") -> str:
    """Run one state function against stubs. `receipt` is (volume-subdir, location, app)."""
    root = tempfile.mkdtemp(prefix="csa-state-")
    try:
        gem = pathlib.Path(root, "Gemini.app")
        cop = pathlib.Path(root, "Copilot.app")
        if gemini_app:
            gem.mkdir()
        if copilot_app:
            cop.mkdir()
        pkg_info = pkg_files = ""
        if receipt is not None:
            volume_sub, location, app = receipt
            volume = str(pathlib.Path(root, volume_sub)) + "/"
            pkg_info = f"package-id: com.microsoft.m365copilot\\nversion: 153.0\\nvolume: {volume}\\nlocation: {location}\\n"
            pkg_files = f"{app}\\n{app}/Contents\\n{app}/Contents/MacOS\\n"
            if receipt_app_exists:
                pathlib.Path(volume, location, app).mkdir(parents=True)
        casks = " ".join(brew_casks)
        script = f"""#!/usr/bin/env bash
set -euo pipefail
has_command() {{ command -v "$1" >/dev/null 2>&1; }}
{chr(10).join(extract(TEXT, f) for f in STATE_FUNCS)}
{constants(TEXT, "COPILOT_RECEIPT")}
GEMINI_DESKTOP_APP='{gem}'
GEMINI_DESKTOP_ID="$(printf '%s' '{constants(TEXT, "GEMINI_DESKTOP_ID").split("=", 1)[1].strip(chr(34))}')"
COPILOT_APP='{cop}'
copilot_needs_migration='{migration}'

brew() {{
  if [[ "$1 $2" == "list --cask" ]]; then
    for c in {casks}; do if [[ "$c" == "$3" ]]; then return 0; fi; done
  fi
  return 1
}}
defaults() {{ if [[ -n '{bundle_id}' ]]; then echo '{bundle_id}'; else return 1; fi; }}
sysctl() {{ if [[ '{int(arm)}' == 1 ]]; then echo 1; else return 1; fi; }}
sw_vers() {{ if [[ -n '{macos}' ]]; then echo '{macos}'; else return 1; fi; }}
pkgutil() {{
  if [[ -z '{pkg_info}' ]]; then return 1; fi
  case "$1" in
    --pkg-info) printf '{pkg_info}' ;;
    --files)    printf '{pkg_files}' ;;
    *)          return 1 ;;
  esac
}}
echo "CSA_TEST_RESULT=[$({call})]"
"""
        out = run_bash(script)
        out = out.replace(root, "<root>")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    match = re.search(r"CSA_TEST_RESULT=\[(.*)\]", out)
    return match.group(1) if match else f"<no result: {out.strip()[:300]}>"


# ── the Copilot install, in order ────────────────────────────────────

GOOD_SIG = ("Package \"Copilot.pkg\":\n"
            "   Status: signed by a developer certificate issued by Apple for distribution\n"
            "   Notarization: trusted by the Apple notary service\n"
            "   Certificate Chain:\n"
            "    1. Developer ID Installer: Microsoft Corporation (UBF8T346G9)\n")
GOOD_GATEKEEPER = ("Copilot.pkg: accepted\nsource=Notarized Developer ID\n"
                   "origin=Developer ID Installer: Microsoft Corporation (UBF8T346G9)\n")
# The right name on a certificate Apple did not issue for distribution.
FORGED_SIG = GOOD_SIG.replace("signed by a developer certificate issued by Apple for distribution",
                              "signed by untrusted certificate")

INSTALL_FUNCS = ["app_running", "wait_for_app_exit", "macos_major", "is_apple_silicon",
                 "copilot_app_path", "copilot_desktop_state", "copilot_ready_to_replace",
                 "install_copilot_desktop"]


def run_install(*, migrate: bool, running: bool = False, receipt: bool = True,
                noninteractive: bool = False, sudo_n_ok: bool = True, curl_ok: bool = True,
                sig: str = GOOD_SIG, gatekeeper: str = GOOD_GATEKEEPER,
                uninstall_ok: bool = True) -> tuple[list[str], bool, str]:
    """(calls in order, whether the downloaded package was left behind, output)."""
    root = tempfile.mkdtemp(prefix="csa-install-")
    try:
        home = pathlib.Path(root, "home")
        home.mkdir()
        apps = pathlib.Path(root, "vol", "Applications")
        bundle = apps / "Copilot.app"
        pkg_info = pkg_files = ""
        if migrate and receipt:
            bundle.mkdir(parents=True)
            pkg_info = f"package-id: com.microsoft.m365copilot\\nvolume: {root}/vol/\\nlocation: Applications\\n"
            pkg_files = "Copilot.app\\nCopilot.app/Contents\\n"
        calls = pathlib.Path(root, "calls")
        calls.write_text("", encoding="utf-8")
        script = f"""#!/usr/bin/env bash
set -euo pipefail
info() {{ echo "INFO $*"; }}
warn() {{ echo "WARN $*"; }}
success() {{ echo "OK $*"; }}
has_command() {{ command -v "$1" >/dev/null 2>&1; }}
ensure_brew_in_path() {{ :; }}
{extract(TEXT, "confirm")}
{chr(10).join(extract(TEXT, f) for f in INSTALL_FUNCS)}
{constants(TEXT, "COPILOT_RECEIPT", "COPILOT_PKG_ARM64", "COPILOT_PKG_X64", "COPILOT_SIGNER", "COPILOT_PKG_CACHE")}
COPILOT_APP='{root}/no-such/Copilot.app'
copilot_needs_migration='{"brew" if migrate else ""}'

CALLS='{calls}'
log() {{ echo "$*" >> "$CALLS"; }}
csa_todo_add() {{ log "todo"; return 0; }}
id() {{ echo 501; }}
ps() {{ if [[ '{int(running)}' == 1 ]]; then echo '{bundle}/Contents/MacOS/Copilot'; fi; }}
sleep() {{ :; }}
sysctl() {{ echo 1; }}
sw_vers() {{ echo 26.1; }}
brew() {{
  if [[ "$1" == "uninstall" ]]; then log "brew-uninstall"; [[ '{int(uninstall_ok)}' == 1 ]]; return; fi
  return 1
}}
curl() {{
  log "curl"
  local out=""
  while [[ $# -gt 0 ]]; do if [[ "$1" == "-o" ]]; then out="$2"; shift; fi; shift; done
  if [[ '{int(curl_ok)}' == 1 ]]; then echo pkg > "$out"; return 0; fi
  return 22
}}
pkgutil() {{
  case "$1" in
    --check-signature) log "pkgutil-sig"; printf '%s' "$SIG_TEXT"; return 0 ;;
    --pkg-info) if [[ -n '{pkg_info}' ]]; then printf '{pkg_info}'; else return 1; fi ;;
    --files)    if [[ -n '{pkg_files}' ]]; then printf '{pkg_files}'; else return 1; fi ;;
  esac
}}
spctl() {{ log "spctl"; if [[ -n "$GK_TEXT" ]]; then printf '%s' "$GK_TEXT"; return 0; fi; return 3; }}
sudo() {{
  if [[ "$1" == "-n" ]]; then
    shift
    if [[ "$1" == "true" ]]; then log "sudo-check"; [[ '{int(sudo_n_ok)}' == 1 ]]; return; fi
  fi
  log "$1"
  return 0
}}

install_copilot_desktop
echo "CSA_TEST_DONE"
"""
        env = {"SIG_TEXT": sig, "GK_TEXT": gatekeeper, "HOME": str(home)}
        if noninteractive:
            env["NONINTERACTIVE"] = "1"
        out = run_bash(script, env_extra=env)
        order = [line for line in calls.read_text(encoding="utf-8").splitlines() if line]
        leftover = pathlib.Path(home, "Library", "Caches", "csa-desktopsetup", "Copilot.pkg").exists()
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if "CSA_TEST_DONE" not in out:
        order.append(f"<died: {out.strip()[-300:]}>")
    return order, leftover, out


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    print("\nwait_for_app_exit")
    out, status, sleeps = run_wait([], 0, always=[OTHER_APP])
    check(status == 0 and sleeps == 0 and "Waiting" not in out,
          "an app that is not running is not waited for (another app's process is not it)")

    out, status, sleeps = run_wait([MAIN, RENDERER], 3)
    check(status == 0 and sleeps >= 1 and "has exited" in out and "ASKED:" not in out,
          "a running app is waited for until it exits, with no prompt inside the first minute")

    out, status, sleeps = run_wait([], 0, always=[CRASHPAD, RENDERER], stdin="n\n")
    check(status == 0 and sleeps == 0,
          "processes under Contents/Frameworks alone (a crash handler that outlives the app) are not the app")

    out, status, sleeps = run_wait([], 0, always=AGENTS, stdin="n\n")
    check(status == 0 and sleeps == 0,
          "the vendor's background agents (LoginItems, LaunchServices, Helpers) are not waited for")

    out, status, sleeps = run_wait([], 0, always=LOOKALIKES, stdin="n\n")
    check(status == 0 and sleeps == 0,
          "a look-alike bundle (Copilot Beta.app, Copilot.app.bak, ~/Applications) is not the app")

    out, status, sleeps = run_wait([MAIN], FOREVER, noninteractive=True)
    check(status == 1 and sleeps == 0 and "Waiting" not in out,
          "with nobody at the keyboard it does not wait at all, and reports the app as still running")

    out, status, sleeps = run_wait([MAIN], FOREVER, stdin="n\n")
    check(status == 1 and out.count("ASKED: Copilot is still running. Keep waiting?") == 1 and sleeps == 30,
          "after a minute it asks, and 'n' ends the wait with the app still running")

    out, status, sleeps = run_wait([MAIN], FOREVER, stdin="y\nn\n")
    check(status == 1 and out.count("ASKED: Copilot is still running. Keep waiting?") == 2 and sleeps == 60,
          "'y' waits another minute and asks again")

    out, status, sleeps = run_wait([MAIN], 40, stdin="y\n")
    check(status == 0 and out.count("ASKED: Copilot is still running. Keep waiting?") == 1 and "has exited" in out,
          "an app that exits after the first prompt ends the wait successfully")

    # 32 ps calls: the first check, then one per poll until the minute is up. The 33rd - the
    # re-check after 'n' - finds it gone.
    out, status, sleeps = run_wait([MAIN], 32, stdin="n\n")
    check(status == 0 and out.count("ASKED: Copilot is still running. Keep waiting?") == 1 and "has exited" in out,
          "an app quit while the question was on screen counts as quit, even after 'n'")

    print("\n  control: a naive `ps | grep -q \"$bundle\"` must fail the cases above")
    _, status, sleeps = run_wait([], 0, always=AGENTS, stdin="n\n", app_running=NAIVE_APP_RUNNING)
    check(not (status == 0 and sleeps == 0), "the naive matcher waits on background agents")
    _, status, sleeps = run_wait([], 0, always=LOOKALIKES, stdin="n\n", app_running=NAIVE_APP_RUNNING)
    check(not (status == 0 and sleeps == 0), "the naive matcher waits on a look-alike bundle")

    print("\ngemini_desktop_state")
    check(run_state("gemini_desktop_state", brew_casks=("google-gemini",)) == "cask",
          "the google-gemini cask is 'cask'")
    check(run_state("gemini_desktop_state", gemini_app=True, bundle_id="com.google.GeminiMacOS") == "direct",
          "Google's Gemini.app installed outside Homebrew is 'direct'")
    check(run_state("gemini_desktop_state", gemini_app=True, bundle_id="com.macpaw.Gemini2") == "other",
          "a Gemini.app that is not Google's (MacPaw's cleaner) is 'other' - never installed over")
    check(run_state("gemini_desktop_state", brew_casks=("gemini",), gemini_app=True,
                    bundle_id="com.macpaw.Gemini2") == "other",
          "MacPaw's `gemini` cask is not mistaken for Google's `google-gemini`")
    check(run_state("gemini_desktop_state", arm=True, macos="15.1") == "absent",
          "nothing installed on Apple Silicon with macOS 15 is 'absent' (will install)")
    check(run_state("gemini_desktop_state", arm=False, macos="15.1") == "unsupported",
          "an Intel Mac is 'unsupported'")
    check(run_state("gemini_desktop_state", arm=True, macos="14.6") == "unsupported",
          "macOS 14 is 'unsupported'")
    check(run_state("gemini_desktop_state", arm=True, macos="") == "unsupported",
          "an unreadable macOS version is 'unsupported', not a guess")

    print("\ncopilot_desktop_state / copilot_app_path")
    check(run_state("copilot_desktop_state", migration="brew", copilot_app=True) == "migrate",
          "the microsoft-365-copilot cask is 'migrate', even though an app is present")
    check(run_state("copilot_desktop_state", receipt=("vol", "Applications", "Copilot.app"),
                    receipt_app_exists=True) == "installed",
          "an app named by the receipt is 'installed'")
    check(run_state("copilot_app_path", receipt=("vol", "Applications", "Microsoft 365 Copilot.app"),
                    receipt_app_exists=True) == "<root>/vol/Applications/Microsoft 365 Copilot.app",
          "the path comes from the receipt's own volume and location, spaces and all")
    check(run_state("copilot_desktop_state", receipt=("vol", "Applications", "Copilot.app"),
                    receipt_app_exists=False, macos="26.1") == "absent",
          "a receipt whose app was dragged to the Trash is not an install")
    check(run_state("copilot_desktop_state", copilot_app=True) == "installed",
          "Copilot.app without a receipt is still 'installed'")
    check(run_state("copilot_desktop_state", macos="13.7") == "unsupported",
          "macOS 13 is 'unsupported'")
    check(run_state("copilot_desktop_state", macos="14.0") == "absent",
          "nothing installed on macOS 14 is 'absent' (will install)")

    print("\ninstall_copilot_desktop: nothing is removed before its replacement is verified")
    order, leftover, _ = run_install(migrate=True)
    check(order == ["curl", "pkgutil-sig", "spctl", "brew-uninstall", "installer"] and not leftover,
          f"migration: download, verify, THEN remove the cask, then install; package cleaned up ({order})")
    order, leftover, _ = run_install(migrate=False)
    check(order == ["curl", "pkgutil-sig", "spctl", "installer"] and not leftover,
          f"fresh install: download, verify, install - no Homebrew uninstall ({order})")
    order, leftover, _ = run_install(migrate=True, curl_ok=False)
    check("brew-uninstall" not in order and "installer" not in order and not leftover,
          f"a failed download removes nothing ({order})")
    order, leftover, _ = run_install(migrate=True, sig=FORGED_SIG)
    check("brew-uninstall" not in order and "installer" not in order and not leftover,
          f"Microsoft's name on a certificate Apple did not issue is refused, and removes nothing ({order})")
    order, leftover, _ = run_install(migrate=True, gatekeeper="")
    check("brew-uninstall" not in order and "installer" not in order and not leftover,
          f"a package Gatekeeper rejects is refused, and removes nothing ({order})")
    order, leftover, _ = run_install(migrate=True, noninteractive=True, sudo_n_ok=False)
    check("curl" not in order and "brew-uninstall" not in order,
          f"with nobody to type a sudo password, nothing is downloaded or removed ({order})")
    order, leftover, _ = run_install(migrate=True, running=True, noninteractive=True)
    check("curl" not in order and "brew-uninstall" not in order and "todo" in order,
          f"a Copilot that is running is not replaced, and the person gets a to-do ({order})")
    order, leftover, _ = run_install(migrate=True, receipt=False)
    check("curl" not in order and "brew-uninstall" not in order,
          f"a Homebrew Copilot whose app cannot be found is refused, not replaced unwatched ({order})")
    order, leftover, _ = run_install(migrate=True, uninstall_ok=False)
    check("installer" not in order and not leftover,
          f"if the cask will not uninstall, nothing is installed over it ({order})")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("all desktop-app checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
