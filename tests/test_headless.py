#!/usr/bin/env python3
"""A headless run must never block on a prompt. This is tier 2's primary path.

[DEC-013](CINO-Platform-Engineering) commits CSA to Linux as a supported tier — "the machine AI
works on", where **non-interactive is the primary path, not a fallback**. Nothing enforced that:
before this file, `grep -rn NONINTERACTIVE tests/ tools/` returned nothing at all. A commitment
in a decision record with no check behind it is a convention, and this repo's own doctrine is
that conventions drift.

The failure being prevented is specific and nasty: an agent-driven VM has no TTY and no person.
If any prompt reads stdin there, the run does not fail — it **hangs**, holding a CI job or an
agent session open until something times out. That is strictly worse than an error, because
there is nothing to report. It is also the exact shape of the bug behind
`test_prompt_visibility.py` (a prompt nobody could see, looking like a hang), approached from
the other side: that file proves a prompt is *visible* when there is a terminal; this one proves
no prompt is *reached* when there is not.

Two properties, checked against the real code in every script:

  1. With stdin not a TTY, NONINTERACTIVE is set by the script itself — nobody has to pass it.
  2. `confirm` then returns success WITHOUT reading stdin. Reading is what hangs; returning is
     what does not. The test proves stdin was untouched by leaving a sentinel on it and
     asserting it is still there afterwards.

    python3 tests/test_headless.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = sorted((ROOT / "scripts").glob("macos-*.sh"))

AUTODETECT = re.compile(r'^if \[\[ -z "\$\{NONINTERACTIVE-\}" \]\]; then.*?^fi$', re.S | re.M)


def extract_fn(text: str, name: str) -> str:
    m = (re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
         or re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", text, re.M))
    if not m:
        raise SystemExit(f"could not find {name}")
    return m.group(0)


def run(body: str, *, stdin: str, tty: bool = False, env_extra: dict | None = None):
    script = "#!/usr/bin/env bash\nset -euo pipefail\n" + body
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(script)
        path = fh.name
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
    if env_extra:
        env.update(env_extra)
    # A pipe for stdin: not a TTY, which is exactly the tier-2 condition.
    p = subprocess.run(["/bin/bash", path], input=stdin, capture_output=True, text=True, env=env)
    return (p.stdout + p.stderr), p.returncode


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, label: str) -> None:
        print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    for source in SCRIPTS:
        text = source.read_text()
        print(f"\n{source.name}")

        block = AUTODETECT.search(text)
        if not block:
            check(False, "has the NONINTERACTIVE auto-detect block")
            continue
        auto = block.group(0)
        confirm = extract_fn(text, "confirm")
        warn = 'warn() { echo "WARN: $*"; }'

        # 1. the script decides for itself that it is headless
        out, rc = run(f'{warn}\n{auto}\necho "NONINTERACTIVE=${{NONINTERACTIVE-unset}}"',
                      stdin="")
        check("NONINTERACTIVE=1" in out, "stdin not a TTY -> the script sets NONINTERACTIVE itself")
        check("stdin is not a TTY" in out, "and says why, so a hung-looking run is explicable")

        # 2. confirm must return success without consuming stdin. The sentinel proves it: if
        #    `read` ran, it would swallow the line and `cat` would come back empty.
        body = (f'{warn}\n{auto}\n{confirm}\n'
                'if confirm "Proceed?"; then echo "CONFIRMED"; else echo "DECLINED"; fi\n'
                'echo "STDIN_LEFT=[$(cat)]"')
        out, rc = run(body, stdin="SENTINEL\n")
        check("CONFIRMED" in out, "confirm returns success when headless (does not decline)")
        check("STDIN_LEFT=[SENTINEL]" in out,
              f"confirm did NOT read stdin — the thing that would hang (got {out.strip()[-40:]!r})")
        check(rc == 0, "the run exits 0")

        # 3. an explicit NONINTERACTIVE=1 needs no TTY reasoning at all
        out, rc = run(f'{warn}\n{auto}\necho "NONINTERACTIVE=${{NONINTERACTIVE-unset}}"',
                      stdin="", env_extra={"NONINTERACTIVE": "1"})
        check("NONINTERACTIVE=1" in out and "stdin is not a TTY" not in out,
              "an explicit NONINTERACTIVE=1 is respected without re-deciding")

        # 4. $CI alone is enough, even with a TTY-shaped invocation
        out, rc = run(f'{warn}\n{auto}\necho "NONINTERACTIVE=${{NONINTERACTIVE-unset}}"',
                      stdin="", env_extra={"CI": "true"})
        check("$CI is set" in out, "$CI is honoured, and named as the reason")

    print("\ncontrol: a confirm that reads stdin unconditionally must be caught")
    naive = ('confirm() { local r; read -r -p "$1 [Y/n] " r; case "${r:-Y}" in [Yy]*) return 0;; '
             '*) return 1;; esac; }')
    out, rc = run('warn() { :; }\n' + naive +
                  '\nif confirm "Proceed?"; then echo CONFIRMED; fi\necho "STDIN_LEFT=[$(cat)]"',
                  stdin="SENTINEL\n")
    check("STDIN_LEFT=[SENTINEL]" not in out,
          f"a prompting confirm eats stdin (regression detectable) — got {out.strip()[-40:]!r}")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
