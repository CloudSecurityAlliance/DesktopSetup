#!/usr/bin/env python3
"""macOS names the AI clients that are running by the path of their image, never by their name.

TODO.md H1. `check_running_tools` in scripts/macos-ai-tools.sh asked `pgrep -x claude`,
`pgrep -x codex` and `pgrep -x gemini`, then stopped every such run at a `Continue anyway?`.
Measured on a Mac on 2026-11-12, the name failed three ways:

  - `pgrep -x` reads argv[0], what somebody typed. `exec -a fakename /bin/sleep` is found by
    `pgrep -x fakename` and not by `pgrep -x sleep`. The live check at the end shows it again on
    whatever Mac runs this file.
  - It found the wrong program. `pgrep -x codex` called ChatGPT.app's bundled codex, and the
    Codex CLI's app-server daemon, "Codex CLI"; and Claude Desktop and ChatGPT Desktop were never
    looked for at all.
  - It named the installer's own ancestors: run from Claude Code, it reported Claude Code.

The fix reads each process's image path with `lsof -d txt`, excludes `$$` and its ancestors
(walked with `ps -o ppid=`, bounded), and asks nothing - Get-RunningAiClients and
Check-RunningTools on Windows (#109). lsof is bounded at 5 s, and when it gives no answer the
check says so instead of reporting that nothing runs. The functions are extracted from the
shipping script, not copied, and run against `ps` and `lsof` stubs built from a process table,
so the logic runs anywhere bash does, Git Bash included (FRICTION-003).

The measured table below is the one from that Mac, with the home directory renamed. The cases
added at review each kill a mutation that the first version of this file let through: widening
Claude Desktop's match to all of Claude.app, dropping the `/codex$` anchor, and dropping the
`|| true` that keeps lsof's exit status out of the answer.

A CONTROL, as ADR-005 asks: the cases are re-run against check_running_tools as it stood at
36e76b4, with a `pgrep` stub that matches the basename of argv[0] as macOS's does. It must FAIL
them. A test the old function would pass is not testing the defect.

    python3 tests/test_running_clients.py
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time


def _posix_bash() -> str:
    r"""Absolute path to a POSIX bash, never a bare "bash": on Windows that resolves to
    C:\Windows\System32\bash.exe, the WSL launcher. Git Bash is preferred; CSA_TEST_BASH
    overrides. The same helper as the other tests/*.py files."""
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
TEXT = SOURCE.read_text(encoding="utf-8")
HOME = "/Users/someone"

# check_running_tools as it stood at 36e76b4, verbatim: the control.
OLD_CHECK_RUNNING_TOOLS = """check_running_tools() {
  local running=()
  pgrep -x claude >/dev/null 2>&1 && running+=("Claude Code")
  pgrep -x codex >/dev/null 2>&1 && running+=("Codex CLI")
  pgrep -x gemini >/dev/null 2>&1 && running+=("Gemini CLI")

  if [[ ${#running[@]} -gt 0 ]]; then
    warn "These tools are currently running: ${running[*]}"
    echo "  It's safe to continue, but running sessions will stay on the old version."
    echo "  For a clean migration, close them first and re-run this script."
    echo ""
    if ! confirm "Continue anyway?"; then
      abort "Aborted. Close running tools and try again."
    fi
  fi
}"""

# A process: (pid, ppid, argv[0], image path, another mapped file or "").
Row = tuple[str, str, str, str, str]

CLAUDE_APP = "/Applications/Claude.app/Contents"
CLAUDE_DESKTOP = f"{CLAUDE_APP}/MacOS/Claude"
CLAUDE_HELPER = f"{CLAUDE_APP}/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper"
CLAUDE_CRASHPAD = f"{CLAUDE_APP}/Frameworks/Electron Framework.framework/Helpers/chrome_crashpad_handler"
CLAUDE_DISCLAIMER = f"{CLAUDE_APP}/Helpers/disclaimer"
CHATGPT_DESKTOP = "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"
CHATGPT_CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
CLAUDE_CODE = f"{HOME}/.local/share/claude/versions/2.1.322"
NODE = f"{HOME}/.nvm/versions/node/v23.7.0/bin/node"
CODEX_VENDOR = (f"{HOME}/.nvm/versions/node/v23.7.0/lib/node_modules/@openai/codex/node_modules/"
                "@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin")
CODEX_NPM = f"{CODEX_VENDOR}/bin/codex"
# Where lsof found the same session's image after npm, updating the package, renamed its directory.
CODEX_NPM_RENAMED = CODEX_NPM.replace("@openai/codex/", "@openai/.codex-gS3DM69j/", 1)
CODEX_DAEMON = f"{HOME}/.codex/packages/app-server-daemon/releases/0.167.2-aarch64-apple-darwin/bin/codex"

# Measured 2026-11-12 (pids, parents, argv[0] and images as ps and lsof reported them).
MEASURED: list[Row] = [
    ("1771", "1", CLAUDE_DESKTOP, CLAUDE_DESKTOP, ""),
    ("1955", "1771", CLAUDE_HELPER, CLAUDE_HELPER, ""),
    ("1945", "1", CLAUDE_CRASHPAD, CLAUDE_CRASHPAD, ""),
    ("4506", "1", "-zsh", "/bin/zsh", ""),
    ("4721", "4506", "claude", CLAUDE_CODE, ""),
    ("73748", "1", "-zsh", "/bin/zsh", ""),
    ("73964", "73748", "node", NODE, ""),
    ("73966", "73964", CODEX_NPM, CODEX_NPM_RENAMED, ""),
    ("73968", "73966", CODEX_DAEMON, CODEX_DAEMON, ""),
    ("74168", "73968", "/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node",
     "/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node", ""),
    ("74272", "74168", "/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node_repl",
     "/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node_repl", ""),
    ("60796", "74272", CHATGPT_CODEX, CHATGPT_CODEX, ""),
]

DRIVER = r"""#!/usr/bin/env bash
set -euo pipefail
TABLE='@@TABLE@@'
LSOF_MODE='@@LSOF_MODE@@'
info()  { echo "INFO $*"; }
warn()  { echo "WARN $*"; }
abort() { echo "ABORT $*"; exit 1; }
confirm() { echo "ASKED: $1"; return 0; }
id() { if [[ "${1:-}" == "-u" ]]; then echo 501; else command id "$@"; fi; }
# Only the form the code under test may use: ps -o ppid= -p PID, padded as real ps pads it.
ps() {
  if [[ $# -ne 4 || "$1" != "-o" || "$2" != "ppid=" || "$3" != "-p" ]]; then
    echo "UNEXPECTED ps $*" >> "$TABLE.log"
    return 2
  fi
  awk -F'\t' -v p="$4" '$1 == p { printf "%6s\n", $2; found = 1 } END { exit !found }' "$TABLE"
}
# -Fpn output: a p record per process, then each txt file, executable first. In every mode that
# answers, it then exits 1, which real lsof can do after a full answer: the status must not
# cost the list.
lsof() {
  echo "lsof $*" >> "$TABLE.log"
  case "$LSOF_MODE" in
    absent) echo "lsof: command not found" >&2; return 127 ;;
    empty)  return 1 ;;
    hang)   exec sleep 30 ;;
  esac
  awk -F'\t' '{
    printf "p%s\nftxt\nn%s\n", $1, $4
    if ($5 != "") printf "ftxt\nn%s\n", $5
    printf "ftxt\nn/usr/lib/dyld\n"
  }' "$TABLE"
  return 1
}
# macOS semantics, measured: -x matches the basename of argv[0], not the image.
pgrep() {
  if [[ "$1" != "-x" ]]; then echo "UNEXPECTED pgrep $*" >> "$TABLE.log"; return 2; fi
  awk -F'\t' -v n="$2" '{ b = $3; sub(/.*\//, "", b); if (b == n) found = 1 } END { exit !found }' "$TABLE"
}
@@FUNCTIONS@@
# This shell is the installer: it joins the table under the parent the case gave it.
printf '%s\t%s\t%s\t%s\t\n' "$$" '@@SELF_PPID@@' "bash" "/bin/bash" >> "$TABLE"
echo "CSA_TEST_BEGIN"
@@INVOKE@@
echo "CSA_TEST_END rc=$rc"
"""
# Called inside `||`, where bash ignores set -e in the function, or as a plain statement, where
# set -e applies to everything it runs - which is how a failing step would kill an installer.
GUARDED = "rc=0\n@@CALL@@ || rc=$?"
PLAIN = "@@CALL@@\nrc=0"


def extract(text: str, name: str) -> str:
    match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not match:
        raise SystemExit(f"could not find {name}() in {SOURCE.name}")
    return match.group(0)


NEW_FUNCTIONS = "\n".join(extract(TEXT, n) for n in
                          ("csa_ancestor_pids", "running_ai_clients", "check_running_tools"))


class Result:
    def __init__(self, out: str, log: str, rc: int, seconds: float, leftovers: list[str]):
        self.out, self.log, self.rc, self.seconds, self.leftovers = out, log, rc, seconds, leftovers

    @property
    def lines(self) -> list[str]:
        return [line for line in self.out.splitlines() if line]


def run(rows: list[Row], call: str, *, self_ppid: str = "1", old: bool = False,
        lsof_mode: str = "table", plain: bool = False, home: str = HOME,
        stdin: str = "n\n") -> Result:
    """Run one call against the stubs. rc is -1 when it hung, or never reached its end."""
    work = tempfile.mkdtemp(prefix="csa-running-")
    try:
        table = pathlib.Path(work, "table")
        table.write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
        tmpdir = pathlib.Path(work, "tmp")
        tmpdir.mkdir()
        invoke = (PLAIN if plain else GUARDED).replace("@@CALL@@", call)
        script = (DRIVER.replace("@@TABLE@@", str(table))
                  .replace("@@LSOF_MODE@@", lsof_mode)
                  .replace("@@SELF_PPID@@", self_ppid)
                  .replace("@@FUNCTIONS@@", OLD_CHECK_RUNNING_TOOLS if old else NEW_FUNCTIONS)
                  .replace("@@INVOKE@@", invoke))
        path = pathlib.Path(work, "driver.sh")
        path.write_text(script, encoding="utf-8")
        env = {"PATH": "/usr/bin:/bin", "HOME": home, "TMPDIR": str(tmpdir)}
        start = time.monotonic()
        try:
            proc = subprocess.run([BASH, str(path)], input=stdin, capture_output=True, text=True,
                                  env=env, timeout=60)
        except subprocess.TimeoutExpired:
            return Result("TIMEOUT", "", -1, time.monotonic() - start, [])
        seconds = time.monotonic() - start
        log_path = pathlib.Path(str(table) + ".log")
        log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        leftovers = sorted(p.name for p in tmpdir.iterdir())
        out = proc.stdout + proc.stderr
        body = re.search(r"CSA_TEST_BEGIN\n(.*)CSA_TEST_END rc=(\d+)", out, re.S)
        if not body:
            return Result(out, log, -1, seconds, leftovers)
        return Result(body.group(1), log, int(body.group(2)), seconds, leftovers)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def clients(rows: list[Row], **kw) -> list[str]:
    r = run(rows, "running_ai_clients", **kw)
    return r.lines if r.rc == 0 else [f"<rc={r.rc}: {r.out!r}>"]


def old_named(rows: list[Row], **kw) -> tuple[list[str], bool]:
    """What the old check named, and whether it asked."""
    r = run(rows, "check_running_tools", old=True, **kw)
    m = re.search(r"These tools are currently running: (.*)", r.out)
    names = re.findall(r"Claude Code|Codex CLI|Gemini CLI", m.group(1)) if m else []
    return names, "ASKED:" in r.out


# Cases shared by the new code and the control: (label, rows, self_ppid, expected).
ANCESTRY: list[Row] = [
    ("400", "1", "claude", CLAUDE_CODE, ""),      # the Claude Code session running the installer
    ("500", "400", "/bin/zsh", "/bin/zsh", ""),
]
LOOKALIKES: list[Row] = [
    ("801", "1", "/Applications/Claude.app.bak/Contents/MacOS/Claude",
     "/Applications/Claude.app.bak/Contents/MacOS/Claude", ""),
    ("802", "1", "/Applications/Claude Beta.app/Contents/MacOS/Claude",
     "/Applications/Claude Beta.app/Contents/MacOS/Claude", ""),
    ("803", "1", "claude", f"{HOME}/Downloads/claude", ""),           # some file named claude
    ("804", "1", "bash", "/bin/bash", ""),                            # running clone-and-claude.sh
    ("805", "1", "codex", "/usr/local/bin/codex", ""),                # not one this installer manages
]
CASES: list[tuple[str, list[Row], str, list[str]]] = [
    ("the measured Mac: Claude Desktop by its main executable, Claude Code typed as `claude`, and "
     "the Codex CLI after npm renamed its directory; ChatGPT.app's bundled processes are not "
     "ChatGPT Desktop, and the CLI's daemon is not counted",
     MEASURED, "1", ["Claude Code", "Claude Desktop", "Codex CLI"]),
    ("ChatGPT Desktop with its bundled codex is ChatGPT Desktop, not the Codex CLI",
     [("3000", "1", CHATGPT_DESKTOP, CHATGPT_DESKTOP, ""),
      ("3001", "3000", CHATGPT_CODEX, CHATGPT_CODEX, "")], "1", ["ChatGPT Desktop"]),
    ("run from Claude Code, the session running the installer is not named",
     ANCESTRY, "500", []),
    ("look-alikes are not clients: Claude.app.bak, Claude Beta.app, a file named claude, a script "
     "with claude in its name, an unmanaged codex",
     LOOKALIKES, "1", []),
]


def live_macos_check() -> tuple[bool, str]:
    """On a Mac: the two facts the fix rests on, measured on the machine running this.

    argv[0] is what `pgrep -x` matches (the old check's flaw), and the executable is the first
    txt file lsof lists (what the new one reads). One `sleep`, a bounded wait, always killed.
    """
    import uuid
    name = f"csa-h1-probe-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(["/bin/bash", "-c", f"exec -a {name} /bin/sleep 30"])
    try:
        pid = str(proc.pid)
        deadline = time.time() + 5
        by_name = ""
        while time.time() < deadline:
            by_name = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True).stdout
            if pid in by_name.split():
                break
            time.sleep(0.1)
        by_image = subprocess.run(["pgrep", "-x", "sleep"], capture_output=True, text=True).stdout
        txt = subprocess.run(["lsof", "-n", "-P", "-a", "-d", "txt", "-p", pid, "-Fn"],
                             capture_output=True, text=True).stdout
        first = next((line[1:] for line in txt.splitlines() if line.startswith("n")), "")
        ok = pid in by_name.split() and pid not in by_image.split() and first == "/bin/sleep"
        return ok, (f"pgrep -x <argv0> found it: {pid in by_name.split()}; pgrep -x sleep found it: "
                    f"{pid in by_image.split()}; lsof's first txt: {first!r}")
    finally:
        proc.kill()
        proc.wait(timeout=10)


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    print("\nrunning_ai_clients")
    for label, rows, self_ppid, want in CASES:
        got = clients(rows, self_ppid=self_ppid)
        check(got == want, f"{label} ({got})")

    got = clients(ANCESTRY + [("600", "1", "claude", CLAUDE_CODE, "")], self_ppid="500")
    check(got == ["Claude Code"], f"another Claude Code session is still named ({got})")

    got = clients([("1771", "1", CLAUDE_DESKTOP, CLAUDE_DESKTOP, ""),
                   ("4", "1771", "claude", f"{HOME}/Library/Application Support/Claude/claude-code/2.1/claude", "")],
                  self_ppid="4")
    check(got == [], f"an ancestor desktop app is not named either ({got})")

    got = clients([("1945", "1", CLAUDE_CRASHPAD, CLAUDE_CRASHPAD, ""),
                   ("1955", "1", CLAUDE_HELPER, CLAUDE_HELPER, ""),
                   ("2166", "1", CLAUDE_DISCLAIMER, CLAUDE_DISCLAIMER, "")])
    check(got == [], f"Claude Desktop quit, its helpers still alive: not Claude Desktop ({got})")

    got = clients([("900", "1", f"{CODEX_VENDOR}/codex-path/rg", f"{CODEX_VENDOR}/codex-path/rg", ""),
                   ("901", "1", f"{CODEX_VENDOR}/bin/codex-code-mode-host",
                    f"{CODEX_VENDOR}/bin/codex-code-mode-host", "")])
    check(got == [], f"the npm Codex package's other binaries (rg, codex-code-mode-host) are not the CLI ({got})")

    got = clients([("900", "1", "/usr/bin/mdworker", "/usr/bin/mdworker", CLAUDE_DESKTOP)])
    check(got == [], f"a process that merely maps a client's binary is not that client ({got})")

    got = clients([("900", "1", "codex", "/opt/homebrew/Caskroom/codex/0.167.0/codex-aarch64-apple-darwin", ""),
                   ("901", "1", "codex", "/opt/homebrew/Cellar/codex/0.47.0/bin/codex", "")])
    check(got == ["Codex CLI"], f"Homebrew's Codex, cask or formula, is the Codex CLI ({got})")

    got = clients([("900", "1", "node", "/opt/homebrew/Cellar/node@24/24.11.0/bin/node", ""),
                   ("901", "1", "/Applications/Gemini.app/Contents/MacOS/Gemini",
                    "/Applications/Gemini.app/Contents/MacOS/Gemini", ""),
                   ("902", "1", "/Applications/Copilot.app/Contents/MacOS/Copilot",
                    "/Applications/Copilot.app/Contents/MacOS/Copilot", "")])
    check(got == [], f"not listed, as on Windows: the Gemini CLI (it is node), Gemini Desktop, Copilot ({got})")

    # A $HOME that is a symlink: lsof reports the resolved path. On macOS the temporary directory
    # is itself under /var -> /private/var, so this is the real shape, not only the test's.
    links = tempfile.mkdtemp(prefix="csa-home-")
    try:
        real = pathlib.Path(links, "real")
        (real / ".local").mkdir(parents=True)
        link = pathlib.Path(links, "link")
        link.symlink_to(real)
        image = os.path.realpath(real) + "/.local/share/claude/versions/2.1.322"
        got = clients([("700", "1", "claude", image, "")], home=str(link))
        check(got == ["Claude Code"], f"a symlinked $HOME still finds Claude Code at its resolved path ({got})")
    finally:
        shutil.rmtree(links, ignore_errors=True)

    r = run(MEASURED, "running_ai_clients")
    check(r.rc == 0 and "-d txt" in r.log and "-u 501" in r.log and "-Fpn" in r.log
          and "UNEXPECTED" not in r.log,
          f"lsof is asked for executables, for this user only, and ps only for parents ({r.log.strip()!r})")

    r = run(MEASURED, "running_ai_clients", plain=True)
    check(r.rc == 0 and r.lines == ["Claude Code", "Claude Desktop", "Codex CLI"],
          f"lsof exiting 1 after a full answer costs nothing, even where set -e applies ({r.rc}, {r.lines})")

    print("\nwhen lsof gives no answer")
    for mode, why in (("absent", "no lsof"), ("empty", "lsof failing with no output")):
        r = run(MEASURED, "running_ai_clients", lsof_mode=mode)
        check(r.rc == 1 and r.lines == [], f"{why}: it returns 1 and names nothing ({r.rc}, {r.lines})")
    r = run(MEASURED, "running_ai_clients", lsof_mode="hang")
    check(r.rc == 1 and r.lines == [] and r.seconds < 15,
          f"an lsof that hangs is given up on (5 s bound): it returns 1 after {r.seconds:.1f} s")
    check(r.leftovers == [], f"and leaves no temporary file behind ({r.leftovers})")
    r = run(MEASURED, "running_ai_clients")
    check(r.leftovers == [], f"nor does a normal run ({r.leftovers})")
    r = run(MEASURED, "check_running_tools", lsof_mode="absent", plain=True)
    check(r.rc == 0 and r.out.strip() == "INFO Could not tell which AI clients are running "
                                         "(lsof gave no answer) - carrying on.",
          f"check_running_tools says it could not tell, and carries on ({r.out.strip()!r})")

    print("\ncsa_ancestor_pids is bounded")
    r = run([("700", "800", "a", "/bin/a", ""), ("800", "700", "b", "/bin/b", "")],
            "csa_ancestor_pids", self_ppid="700")
    check(r.rc == 0 and 0 < len(r.lines) <= 12,
          f"a cycle in the parent chain ends within 12 hops ({len(r.lines)} pids)")
    r = run([("900", "900", "a", "/bin/a", "")], "csa_ancestor_pids", self_ppid="900")
    check(r.rc == 0 and r.lines[1:] == ["900"], f"a process that is its own parent ends the walk ({r.lines})")

    print("\ncheck_running_tools")
    r = run(MEASURED, "check_running_tools", plain=True)
    check(r.rc == 0 and r.lines == ["INFO Found Claude Code, Claude Desktop, Codex CLI running - no need "
                                    "to close anything. Restart them once this finishes, so they use "
                                    "what it installs."],
          f"one line naming what was found ({r.lines})")
    check("ASKED:" not in r.out and "ABORT" not in r.out, "it asks nothing, and a 'n' on stdin stops nothing")
    r = run(ANCESTRY, "check_running_tools", self_ppid="500", plain=True)
    check(r.rc == 0 and r.out.strip() == "", f"nothing found prints nothing ({r.out.strip()!r})")

    # The same expectation as above, so a broken stub cannot make the control pass: a pgrep stub
    # that never matched would leave the old check naming nothing, and the cases expecting
    # nothing would then agree with it.
    print("\n  control: check_running_tools at 36e76b4 must fail the cases above")
    for label, rows, self_ppid, want in CASES:
        names, _ = old_named(rows, self_ppid=self_ppid)
        check(names != want, f"the old check fails: {label.split(':')[0]} (it named {names}, not {want})")
    _, asked = old_named(MEASURED)
    check(asked, "the old check stops the run with a prompt")

    print("\nlive, on this machine")
    if sys.platform == "darwin" and shutil.which("lsof") and shutil.which("pgrep"):
        ok, detail = live_macos_check()
        check(ok, f"pgrep -x matches argv[0], not the image; lsof lists the executable first ({detail})")
    else:
        print("    not run  (needs macOS's pgrep and lsof; the stubbed cases above ran)")

    print()
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("all running-client checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
