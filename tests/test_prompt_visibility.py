#!/usr/bin/env python3
"""Debug mode must not swallow interactive prompts.

The bug this exists to prevent, reported from a real Mac:

    CSA_DEBUG=1 bash -c "$(curl ... macos-ai-tools.sh)"
    ==> debug logging to /Users/kurt/desktopsetup-20260825-171402.log
    ==> Cloud Security Alliance - macOS AI Tools Setup
    Warning: These tools are currently running: Claude Code Codex CLI
    <nothing, apparently hung>

It was waiting at a `[Y/n]` prompt nobody could see. `read -r -p` writes its prompt with **no
trailing newline**, and the debug redirection ran the terminal's output through a line-buffered
`sed`, which by definition holds anything without a newline. Ctrl-C flushed the pipe and the
question appeared on the way out.

The fix is ordering: `tee` feeds the terminal directly and the redactor sits on a branch that
only writes the log file. `tee` writes what it reads when it reads it, so a partial line arrives
at once, and line-buffering then only has to be good enough for a file. This matters beyond one
prompt - there are eleven `read -p` sites and about fifteen partial-line `printf`s (progress
markers like "Testing... ") across these scripts, so a fix at the call sites would have to be
remembered by every future one.

**Why a pty.** Three simpler harnesses failed to reproduce this, each for its own reason, and
each looked like evidence that nothing was wrong:

  * stdout to a file - bash block-buffers, so even a script with NO redirection showed nothing.
  * `script -q` - buffers its own capture file, same false negative.
  * a fifo on stdin - `read -p` prints its prompt ONLY when stdin is a terminal, so the prompt
    was never written at all, in either the broken or the fixed pipeline.

Only a real pty on both ends reproduces it. That is what this does.

The functions under test are extracted from the shipping script rather than copied, so this
cannot drift from what actually runs.

    python3 tests/test_prompt_visibility.py
"""
from __future__ import annotations

import os
import pathlib
import pty
import re
import select
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "scripts" / "macos-ai-tools.sh"

# The two orderings. `new` is what ships; `old` is kept so the test can prove it still detects
# the regression, rather than merely passing.
PIPELINES = {
    "old": 'exec > >(csa_redact | tee -a "$CSA_LOG") 2>&1',
    "new": 'exec > >(tee -a >(csa_redact >> "$CSA_LOG")) 2>&1',
}
PROMPT = "Proceed with installation"


def extract(text: str, name: str) -> str:
    """A shell function (or the CSA_SED_UNBUF block) exactly as the script defines it."""
    if name == "CSA_SED_UNBUF":
        match = re.search(r"^CSA_SED_UNBUF=\"\".*?^fi$", text, re.S | re.M)
    else:
        match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not match:
        raise SystemExit(f"could not find {name} in {SOURCE}")
    return match.group(0)


def build(pipeline: str, log: str) -> str:
    text = SOURCE.read_text()
    return "\n".join([
        "#!/usr/bin/env bash",
        "set -uo pipefail",
        f'CSA_LOG={log}; : > "$CSA_LOG"',
        extract(text, "CSA_SED_UNBUF"),
        extract(text, "csa_redact"),
        extract(text, "confirm"),
        pipeline,
        'echo "banner line"',
        f'if confirm "{PROMPT}?"; then echo ANSWERED-yes; else echo ANSWERED-no; fi',
    ]) + "\n"


def drain(fd: int, seconds: float) -> bytes:
    out, deadline = b"", time.time() + seconds
    while time.time() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        try:
            chunk = os.read(fd, 4096)
        except OSError:                       # the child closed the pty
            break
        if not chunk:
            break
        out += chunk
    return out


def run_under_pty(script: str) -> tuple[str, str]:
    """Return (what was on screen before answering, everything)."""
    pid, fd = pty.fork()
    if pid == 0:                              # child: both ends are the pty
        os.execvp("bash", ["bash", script])
    before = drain(fd, 2.0)
    try:
        os.write(fd, b"y\n")
    except OSError:
        pass
    everything = before + drain(fd, 3.0)
    os.waitpid(pid, 0)
    os.close(fd)
    return before.decode(errors="replace"), everything.decode(errors="replace")


def main() -> int:
    problems = []
    with tempfile.TemporaryDirectory() as work:
        for name, pipeline in PIPELINES.items():
            script = pathlib.Path(work, f"{name}.sh")
            script.write_text(build(pipeline, f"{work}/{name}.log"))
            before, everything = run_under_pty(str(script))
            visible = PROMPT in before
            answered = "ANSWERED-yes" in everything

            if name == "new" and not visible:
                problems.append("the shipping pipeline hides the prompt: debug mode looks like "
                                "a hang, which is the whole bug this guards against.")
            if name == "old" and visible:
                problems.append("the known-broken pipeline no longer hides the prompt, so this "
                                "test can no longer detect the regression. Check the harness "
                                "before trusting a pass.")
            # Only for the shipping pipeline. The broken one is expected to behave badly,
            # and on Linux it also holds its FINAL line past this window - which is a symptom
            # of the same buffering, not a separate fact worth asserting. Requiring it made
            # the test fail in CI for the wrong reason.
            if name == "new" and not answered:
                problems.append("the shipping pipeline did not complete after the prompt was "
                                "answered.")
            print(f"  {name:4} prompt visible before answering: "
                  f"{'yes' if visible else 'no'};  completed: {'yes' if answered else 'no'}")

    for problem in problems:
        print(f"    {problem}")
    if problems:
        return 1
    print("debug mode shows interactive prompts, and the broken ordering is still detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
