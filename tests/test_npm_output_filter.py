#!/usr/bin/env python3
"""`csa_npm` must hide npm's install-scripts noise without hiding npm's failures.

The report this exists for (issue #51), from a clean Mac being set up from scratch:

    ==> Updating Gemini CLI

    changed 1 package in 726ms

    15 packages are looking for funding
      run `npm fund` for details
    npm warn install-scripts 2 packages have install scripts not yet covered by allowScripts:
    npm warn install-scripts   node-pty@1.0.0 (postinstall: node scripts/post-install.js; ...)
    npm warn install-scripts   @github/keytar@7.10.6 (install: node script/install.js || ...)
    npm warn install-scripts
    npm warn install-scripts Run `npm install -g --allow-scripts=node-pty,@github/keytar` ...

Nothing was wrong. Measured on npm 11.19.0 / node 26.8.1 (what Homebrew ships, so what a clean
machine gets): the install scripts still RAN — `node-pty/build/` holds the node-gyp Makefiles
afterwards and `require('node-pty')` succeeds — and npm is pre-announcing a future release that
will run them only from an allowlist. But the person reading it has just been handed a laptop,
does not use npm, and sees five lines of `npm warn` under "Updating Gemini CLI".

Why this is a test and not just a `sed`: the obvious filter is `npm … | grep -v`, and it is
wrong in a way that passes every casual check. These scripts run under `set -o pipefail`, and a
`grep -v` that matches nothing exits 1. So on the day npm stops printing the block, a perfectly
clean run starts reporting failure — `npm update -g X || npm install -g X` takes its fallback
for no reason, and `macos-update.sh` warns about an update that worked. `sed` exits 0 whatever
it matches, so npm's own status is what propagates. `grep -v` is kept below as a control, so
this test proves it can still detect the regression rather than merely passing.

The functions under test are extracted from the shipping scripts rather than copied, so this
cannot drift from what actually runs.

    python3 tests/test_npm_output_filter.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = [
    ROOT / "scripts" / "macos-ai-tools.sh",
    ROOT / "scripts" / "macos-update.sh",
    ROOT / "scripts" / "macos-work-tools.sh",
]

# Verbatim from issue #51. npm sends `npm warn` to stderr and the rest to stdout, and the
# stub below reproduces that split, because `csa_npm` merges the two and a filter that only
# ever saw stdout would look fine here and fail in the field.
NPM_STDOUT = """
changed 1 package in 726ms

15 packages are looking for funding
  run `npm fund` for details
"""
NPM_STDERR = """npm warn install-scripts 2 packages have install scripts not yet covered by allowScripts:
npm warn install-scripts   node-pty@1.0.0 (postinstall: node scripts/post-install.js; install: node-gyp rebuild)
npm warn install-scripts   @github/keytar@7.10.6 (install: node script/install.js || npm run build)
npm warn install-scripts
npm warn install-scripts Run `npm install -g --allow-scripts=node-pty,@github/keytar` to allow these scripts once, or `npm config set allow-scripts=node-pty,@github/keytar --location=user` to allow them for all global installs.
"""

# A real npm failure, which must survive the filter in every mode.
NPM_ERROR = """npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/@google/gemini-cli
"""

MUST_GO = ["npm warn install-scripts", "looking for funding", "npm fund"]
MUST_STAY = ["changed 1 package"]

# The control: what a naive fix looks like. Identical output, different exit status.
GREP_FILTER = """csa_npm() {
  if csa_debug_requested; then
    npm "$@"
    return
  fi
  npm "$@" 2>&1 | grep -v -e 'npm warn install-scripts' -e 'looking for funding' -e 'npm fund'
}"""


def extract(text: str, name: str) -> str:
    """A shell function, or the CSA_SED_UNBUF block, exactly as the script defines it."""
    if name == "CSA_SED_UNBUF":
        match = re.search(r"^CSA_SED_UNBUF=\"\".*?^fi$", text, re.S | re.M)
    else:
        match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not match:
        raise SystemExit(f"could not find {name}")
    return match.group(0)


def run(source: pathlib.Path, *, debug: bool, npm_exit: int, output: str = "warnings",
        override: str | None = None) -> tuple[str, int]:
    """Run the extracted csa_npm against a stubbed npm. Returns (merged output, exit status)."""
    text = source.read_text()
    csa_npm = override if override is not None else extract(text, "csa_npm")
    # "warnings": a normal noisy success.  "error": npm actually failed.
    # "silent":   npm succeeded but printed ONLY lines the filter removes — the pipefail trap.
    stdout, stderr = {
        "warnings": (NPM_STDOUT, NPM_STDERR),
        "error": ("", NPM_ERROR),
        "silent": ("", NPM_STDERR),
    }[output]

    def heredoc(content: str, redirect: str, tag: str) -> str:
        """Emit nothing at all for an empty stream — a stray blank line would defeat the
        `silent` case, which is the only one where the pipefail trap can be observed."""
        if not content:
            return ""
        return f"  cat {redirect}<<'{tag}'\n{content.lstrip(chr(10))}{tag}\n"

    harness = f"""#!/usr/bin/env bash
set -euo pipefail
{extract(text, "CSA_SED_UNBUF")}
{extract(text, "csa_debug_requested")}
{csa_npm}

# Stand in for the real npm: same stream split, chosen exit status.
npm() {{
{heredoc(stdout, "", "STDOUT_EOF")}{heredoc(stderr, ">&2 ", "STDERR_EOF")}  return {npm_exit}
}}

status=0
csa_npm update -g @google/gemini-cli || status=$?
echo "CSA_TEST_EXIT=$status"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(harness)
        path = fh.name
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/tmp"}
    if debug:
        env["CSA_DEBUG"] = "1"
    proc = subprocess.run(["bash", path], capture_output=True, text=True, env=env)
    merged = proc.stdout + proc.stderr
    match = re.search(r"CSA_TEST_EXIT=(\d+)", merged)
    return merged, int(match.group(1)) if match else -1


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    for source in SCRIPTS:
        print(f"\n{source.name}")

        out, status = run(source, debug=False, npm_exit=0)
        for needle in MUST_GO:
            check(needle not in out, f"default run drops {needle!r}")
        for needle in MUST_STAY:
            check(needle in out, f"default run keeps {needle!r}")
        check(status == 0, "a successful npm still reports success")

        out, status = run(source, debug=True, npm_exit=0)
        for needle in MUST_GO:
            check(needle in out, f"CSA_DEBUG=1 keeps {needle!r}")
        check(status == 0, "CSA_DEBUG=1 preserves the success status")

        # The whole point: a filter must not invent a failure, nor swallow a real one.
        out, status = run(source, debug=False, npm_exit=1)
        check(status == 1, "a failing npm still reports failure")

        out, status = run(source, debug=False, npm_exit=1, output="error")
        check("npm error code E404" in out, "a real npm error is never filtered")
        check(status == 1, "a real npm error keeps its status")

        # The pipefail trap, in the exact shape it bites: npm succeeds and prints ONLY lines
        # the filter removes. `grep -v` exits 1 here and turns a clean run into a failure.
        out, status = run(source, debug=False, npm_exit=0, output="silent")
        check(status == 0, "npm printing only filtered lines is still a success")

    print("\ncontrol: the naive `grep -v` filter, which this test must still catch")
    _, status = run(SCRIPTS[0], debug=False, npm_exit=0, output="silent",
                    override=GREP_FILTER)
    check(status != 0, "grep -v turns a clean run into a failure (regression detectable)")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
