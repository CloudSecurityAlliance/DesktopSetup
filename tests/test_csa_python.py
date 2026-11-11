#!/usr/bin/env python3
"""macOS names exactly one CSA Python: the uv-managed 3.14 standard build, verified by running it.

Issue #179. `find_usable_python` returned the first interpreter that cleared a floor, from PATH
first and then from `uv python find`. On a real Mac that was Homebrew's 3.15 (PATH `python3`),
or uv's free-threaded `python3.14t`: when 3.14t is the only uv-managed 3.14,
`uv python find 3.14` returns it. All four CSA servers landed on 3.14t that way.

The replacement is three functions in `scripts/macos-ai-tools.sh`:

  * `python_is_csa_build <exe>` runs the interpreter and accepts it only when it reports
    `CSA_PYTHON_PREFERRED` and `sysconfig.get_config_var("Py_GIL_DISABLED")` is falsy;
  * `find_csa_python` asks uv (`--system`, because with `VIRTUAL_ENV` set uv otherwise returns
    the active venv's Python), then uv's JSON listing (`variant == "default"`), then Homebrew's
    `opt/python@3.14`, and prints the first one that verifies. It never installs anything,
    because the preflight calls it before the person has agreed to anything;
  * `ensure_csa_python` runs `uv python install 3.14` (then `brew install python@3.14` as the
    fallback) and prints what `find_csa_python` then finds. Only the path goes to stdout.

**How this is tested.** The real functions are extracted from the shipping script and run
in bash on a stub-only PATH. A stub `uv` answers `python find`, `python list --output-format
json`, `python install` and `self update` from a per-case scenario directory and logs every
call. Stub interpreters answer the build probe with a version and a GIL flag, and hand any
other invocation (the JSON parse) to the real Python running this test. The stub `uv`, `brew`
and `info` all write chatter to stdout, so a function that leaks it fails here.
`python_is_csa_build` is also run against the real interpreters on this machine.

What this cannot prove: what real uv does. The stub reproduces behaviour measured on uv
0.13.7 (the `--system` effect, the JSON keys), and a uv that changes it will not show up here.

    python3 tests/test_csa_python.py
"""
from __future__ import annotations

import json
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


# Windows needs these to locate its own per-user directories. Handing subprocess a minimal
# env is reasonable on POSIX and actively dangerous here: without LOCALAPPDATA the Python
# Install Manager roots itself at "Python" RELATIVE TO THE WORKING DIRECTORY, decides no
# interpreter is installed, and installs a 167 MB one into the repo -- while the test passes.
# Keep these; control only PATH and HOME, which is what these tests are actually about.
_KEEP_NT = ("SystemRoot", "SystemDrive", "ComSpec", "PATHEXT",
            "LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP")


def base_env() -> dict[str, str]:
    """Platform floor an env= dict must start from. Empty on POSIX, by design."""
    if os.name != "nt":
        return {}
    return {k: os.environ[k] for k in _KEEP_NT if k in os.environ}


ROOT = pathlib.Path(__file__).resolve().parent.parent
AI = ROOT / "scripts" / "macos-ai-tools.sh"
WIN = ROOT / "scripts" / "windows-ai-tools.ps1"
TEXT = AI.read_text(encoding="utf-8")

failures: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
    if not cond:
        failures.append(label)
        for line in detail.splitlines():
            print(f"          {line}")


def extract(name: str) -> str:
    """A function's text out of the shipping script. A missing one is a FAILURE, and is replaced
    by a stand-in that returns 99, so every case that needs it reports instead of one crash."""
    m = (re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", TEXT, re.S | re.M)
         or re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", TEXT, re.M))
    if not m:
        check(False, f"macos-ai-tools.sh defines {name}()")
        return f'{name}() {{ echo "{name}: MISSING FROM THE SCRIPT" >&2; return 99; }}'
    return m.group(0)


def extract_assignment(name: str) -> str:
    m = re.search(rf'^{re.escape(name)}="[^"]*"$', TEXT, re.M)
    if not m:
        raise SystemExit(f"could not find {name} in {AI.name}")
    return m.group(0)


def code_only(block: str) -> str:
    """Full-line comments removed, so a check cannot be satisfied by prose about the code."""
    return "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("#"))


PREF_LINE = extract_assignment("CSA_PYTHON_PREFERRED")
PREF = PREF_LINE.split('"')[1]
FT = f"{PREF}t"   # the free-threaded executable suffix: python3.14t


def interp(path: pathlib.Path, version: str, gil: int) -> pathlib.Path:
    """A stand-in interpreter. It answers the build probe with `<version> <gil>`; anything else -
    the JSON parse - runs on the real Python running this test, so parsing is real."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        f'  *Py_GIL_DISABLED*) echo "{version} {gil}"; exit 0 ;;\n'
        "esac\n"
        f'exec "{sys.executable}" "$@"\n', encoding="utf-8")
    path.chmod(0o755)
    return path


def entry(path: pathlib.Path | str, variant: str = "default", symlink: str | None = None,
          impl: str = "cpython") -> dict:
    """One element of `uv python list --output-format json`, in the shape uv 0.13.7 prints."""
    suffix = "+freethreaded" if variant == "freethreaded" else ""
    return {"key": f"{impl}-{PREF}.10{suffix}-macos-aarch64-none", "version": f"{PREF}.10",
            "path": str(path), "symlink": symlink, "url": None, "os": "macos",
            "variant": variant, "implementation": impl, "arch": "aarch64", "libc": "none"}


UV_STUB = """#!/bin/sh
PATH=/usr/bin:/bin
S='{scen}'
printf 'uv %s\\n' "$*" >> "$S/calls.log"
case "$1 $2" in
  "python find")
    # Measured on uv 0.13.7: with VIRTUAL_ENV set, `uv python find` returns the active venv's
    # interpreter unless --system is given.
    if [ -n "$VIRTUAL_ENV" ]; then
      case " $* " in
        *" --system "*) ;;
        *) printf '%s\\n' "$VIRTUAL_ENV/bin/python3"; exit 0 ;;
      esac
    fi
    if [ -f "$S/find" ]; then cat "$S/find"; exit 0; fi
    echo "error: No interpreter found" >&2; exit 2 ;;
  "python list")
    if [ -f "$S/list.json" ]; then cat "$S/list.json"; else echo "[]"; fi
    exit 0 ;;
  "python install")
    echo "uv-chatter: installing Python $3 (on stdout, on purpose)"
    if [ -f "$S/install.fails" ]; then echo "error: network unreachable" >&2; exit 1; fi
    if [ -f "$S/after.find" ]; then cp "$S/after.find" "$S/find"; fi
    if [ -f "$S/after.json" ]; then cp "$S/after.json" "$S/list.json"; fi
    exit 0 ;;
  "self update")
    echo "uv-chatter: self update (on stdout, on purpose)"
    if [ -f "$S/self-update.fails" ]; then echo "error: self-update is not available" >&2; exit 1; fi
    exit 0 ;;
esac
case "$1" in --version) echo "uv 0.13.7"; exit 0 ;; esac
exit 0
"""

BREW_STUB = """#!/bin/sh
PATH=/usr/bin:/bin
S='{scen}'
printf 'brew %s\\n' "$*" >> "$S/calls.log"
case "$1" in
  --prefix) printf '%s\\n' "$S/brew"; exit 0 ;;
  install)
    echo "brew-chatter: installing $2 (on stdout, on purpose)"
    if [ -f "$S/brew-install.fails" ]; then exit 1; fi
    if [ -f "$S/brew-install.creates" ]; then
      mkdir -p "$S/brew/opt/python@{pref}/bin"
      cp "$S/brew-install.creates" "$S/brew/opt/python@{pref}/bin/python{pref}"
      chmod 755 "$S/brew/opt/python@{pref}/bin/python{pref}"
    fi
    exit 0 ;;
  list)
    if [ -f "$S/brew-owns-uv" ]; then echo "uv 0.13.7"; exit 0; fi
    exit 1 ;;
  upgrade) echo "brew-chatter: upgrade (on stdout, on purpose)"; exit 0 ;;
esac
exit 0
"""


def harness() -> str:
    return "\n".join([
        PREF_LINE,
        extract("has_command"),
        extract("get_version"),
        extract("csa_brew_upgrade"),
        extract("python_is_csa_build"),
        extract("find_csa_python"),
        extract("ensure_csa_python"),
        extract("install_uv"),
        extract("install_python"),
        # Chatty on stdout, like the real info/success: a resolver that forgets `>&2` on them
        # fails stdout_is_only_the_path.
        'info()    { echo "INFO: $*"; }',
        'success() { echo "SUCCESS: $*"; }',
        'warn()    { echo "WARN: $*" >&2; }',
        "ensure_brew_in_path() { :; }",
    ])


HARNESS = harness()


class Case:
    """One scenario: a stub-only PATH (bin/), a tools dir holding only `head`, a scenario dir
    the stubs read and log to, and a HOME that is not the real one."""

    def __init__(self, root: pathlib.Path, name: str):
        self.dir = root / name
        self.bin = self.dir / "bin"
        self.tools = self.dir / "tools"
        self.scen = self.dir / "scen"
        self.home = self.dir / "home"
        self.uvpy = self.dir / "uvpy"
        for d in (self.bin, self.tools, self.scen, self.home, self.uvpy):
            d.mkdir(parents=True, exist_ok=True)
        head = shutil.which("head")
        if head:
            (self.tools / "head").symlink_to(head)
        (self.scen / "calls.log").write_text("", encoding="utf-8")

    # uv-managed interpreters, laid out the way uv lays them out
    def std(self, base: pathlib.Path | None = None) -> pathlib.Path:
        return interp((base or self.uvpy) / f"cpython-{PREF}-macos-aarch64-none" / "bin"
                      / f"python{PREF}", PREF, 0)

    def ft(self) -> pathlib.Path:
        return interp(self.uvpy / f"cpython-{PREF}+freethreaded-macos-aarch64-none" / "bin"
                      / f"python{FT}", PREF, 1)

    def uv(self, *, find: pathlib.Path | str | None = None, listing: list | None = None,
           after_find: pathlib.Path | str | None = None, after_listing: list | None = None,
           install_fails: bool = False, self_update_fails: bool = False) -> None:
        f = self.bin / "uv"
        f.write_text(UV_STUB.format(scen=self.scen), encoding="utf-8")
        f.chmod(0o755)
        if find is not None:
            (self.scen / "find").write_text(f"{find}\n", encoding="utf-8")
        if listing is not None:
            (self.scen / "list.json").write_text(json.dumps(listing), encoding="utf-8")
        if after_find is not None:
            (self.scen / "after.find").write_text(f"{after_find}\n", encoding="utf-8")
        if after_listing is not None:
            (self.scen / "after.json").write_text(json.dumps(after_listing), encoding="utf-8")
        if install_fails:
            (self.scen / "install.fails").write_text("", encoding="utf-8")
        if self_update_fails:
            (self.scen / "self-update.fails").write_text("", encoding="utf-8")

    def brew(self, *, opt_python: tuple[str, int] | None = None,
             install_creates: tuple[str, int] | None = None, owns_uv: bool = False) -> pathlib.Path:
        f = self.bin / "brew"
        f.write_text(BREW_STUB.format(scen=self.scen, pref=PREF), encoding="utf-8")
        f.chmod(0o755)
        opt = self.scen / "brew" / "opt" / f"python@{PREF}" / "bin" / f"python{PREF}"
        if opt_python is not None:
            interp(opt, *opt_python)
        if install_creates is not None:
            interp(self.scen / "brew-install.creates", *install_creates)
        if owns_uv:
            (self.scen / "brew-owns-uv").write_text("", encoding="utf-8")
        return opt

    def path_python(self, name: str, version: str, gil: int = 0) -> pathlib.Path:
        return interp(self.bin / name, version, gil)

    def run(self, call: str, *, extra_env: dict[str, str] | None = None) -> tuple[str, str, int]:
        script = self.dir / "harness.sh"
        script.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + HARNESS + "\n" + call + "\n",
                          encoding="utf-8")
        env = {**base_env(), "PATH": f"{self.bin}:{self.tools}", "HOME": str(self.home)}
        env.update(extra_env or {})
        p = subprocess.run([BASH, str(script)], capture_output=True, text=True, env=env,
                           timeout=120)
        return p.stdout, p.stderr, p.returncode

    def calls(self) -> list[str]:
        return (self.scen / "calls.log").read_text(encoding="utf-8").splitlines()


def show(out: str, err: str, rc: int, calls: list[str] | None = None) -> str:
    text = f"rc={rc}\nstdout:\n{out}\nstderr:\n{err}"
    if calls is not None:
        text += "\ncalls:\n" + "\n".join(calls)
    return text


def only_line(out: str) -> str | None:
    lines = out.splitlines()
    return lines[0] if len(lines) == 1 else None


def resolver_cases() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)

        print("\nstandard_found")
        c = Case(root, "standard_found")
        std = c.std()
        c.uv(find=std, listing=[entry(std)])
        out, err, rc = c.run("ensure_csa_python")
        check(rc == 0 and only_line(out) == str(std),
              "ensure_csa_python prints the uv-managed standard build, one line, exit 0",
              show(out, err, rc, c.calls()))
        out, err, rc = c.run("find_csa_python")
        check(rc == 0 and only_line(out) == str(std), "find_csa_python prints the same path",
              show(out, err, rc))
        finds = [l for l in c.calls() if l.startswith("uv python find")]
        check(bool(finds) and all(l == f"uv python find --system --managed-python {PREF}"
                                  for l in finds),
              f"uv is asked exactly `python find --system --managed-python {PREF}`",
              "\n".join(c.calls()))
        check(f"uv python install {PREF}" in c.calls(),
              f"ensure_csa_python ran `uv python install {PREF}` even though it was present "
              "(the uv-managed build is always ensured)", "\n".join(c.calls()))

        print("\nonly_freethreaded_installed")
        c = Case(root, "only_freethreaded_installed")
        ft = c.ft()
        std = c.std()
        c.uv(find=ft, listing=[entry(ft, "freethreaded")],
             after_find=std, after_listing=[entry(std), entry(ft, "freethreaded")])
        out, err, rc = c.run("find_csa_python")
        check(rc == 1 and out == "",
              f"find_csa_python refuses {FT} when it is the only uv-managed {PREF}",
              show(out, err, rc))
        out, err, rc = c.run("ensure_csa_python")
        check(rc == 0 and only_line(out) == str(std),
              "ensure_csa_python installs the standard build and returns it",
              show(out, err, rc, c.calls()))
        check(str(ft) not in out and f"python{FT}" not in out,
              f"the {FT} path is never printed", out)

        print("\npath_python_ignored")
        c = Case(root, "path_python_ignored")
        std = c.std()
        c.path_python("python3", "3.15")
        c.path_python(f"python{PREF}", PREF)     # even a standard 3.14 on PATH is not asked
        c.uv(find=std, listing=[entry(std)])
        out, err, rc = c.run("find_csa_python")
        check(rc == 0 and only_line(out) == str(std),
              "PATH python3 (3.15) is not the CSA Python; uv's managed build is",
              show(out, err, rc))
        c2 = Case(root, "path_python_ignored_no_uv_python")
        c2.path_python("python3", "3.15")
        c2.path_python(f"python{PREF}", PREF)
        c2.uv(listing=[])
        out, err, rc = c2.run("find_csa_python")
        check(rc == 1 and out == "",
              "with no uv or Homebrew 3.14, a PATH python3/python3.14 is still not accepted",
              show(out, err, rc))

        print("\nwrong_minor_rejected")
        for version in ("3.13", "3.15"):
            c = Case(root, f"wrong_minor_{version}")
            wrong = interp(c.uvpy / f"cpython-{version}-macos-aarch64-none" / "bin"
                           / f"python{version}", version, 0)
            c.uv(find=wrong, listing=[entry(wrong)])
            out, err, rc = c.run("find_csa_python")
            check(rc == 1 and out == "", f"a {version} that uv offers is rejected",
                  show(out, err, rc))

        print("\ndead_interpreter_rejected")
        c = Case(root, "dead_interpreter_rejected")
        dead = c.uvpy / f"cpython-{PREF}-macos-aarch64-none" / "bin" / f"python{PREF}"
        dead.parent.mkdir(parents=True)
        dead.symlink_to(c.dir / "deleted" / f"python{PREF}")   # dangling: -x false, -L true
        c.uv(find=dead, listing=[entry(dead)], after_find=dead, after_listing=[entry(dead)])
        out, err, rc = c.run("find_csa_python")
        check(rc == 1 and out == "", "a dangling interpreter uv still reports is rejected",
              show(out, err, rc))
        out, err, rc = c.run("ensure_csa_python")
        check(rc == 1 and out == "" and "WARN" in err,
              "ensure_csa_python warns and exits 1 when the only candidate is dead",
              show(out, err, rc))
        # The JSON listing is parsed by the step-1 interpreter when it runs, else by
        # /usr/bin/python3. A dead step-1 interpreter leaves only the latter.
        if os.path.exists("/usr/bin/python3"):
            c = Case(root, "dead_first_listing_good")
            std = c.std()
            dead = c.dir / "elsewhere" / f"python{PREF}"
            dead.parent.mkdir(parents=True)
            dead.symlink_to(c.dir / "deleted" / f"python{PREF}")
            c.uv(find=dead, listing=[entry(dead), entry(std)])
            out, err, rc = c.run("find_csa_python")
            check(rc == 0 and only_line(out) == str(std),
                  "a dead `uv python find` result falls through to the JSON listing",
                  show(out, err, rc))
        else:
            print("    SKIP  dead_first_listing_good (no /usr/bin/python3 here to parse with)")

        print("\npath_with_space")
        c = Case(root, "path_with_space")
        spaced = c.dir / "Application Support" / "uv" / "python"
        std = c.std(spaced)
        c.uv(find=std, listing=[entry(std)])
        out, err, rc = c.run("find_csa_python")
        check(rc == 0 and only_line(out) == str(std),
              "a path with a space comes back whole from `uv python find`", show(out, err, rc))
        c = Case(root, "path_with_space_listing")
        ft = c.ft()
        std = c.std(c.dir / "Application Support" / "uv" / "python")
        c.uv(find=ft, listing=[entry(ft, "freethreaded"), entry(std)])
        out, err, rc = c.run("find_csa_python")
        check(rc == 0 and only_line(out) == str(std),
              "and whole from the JSON listing (parsed by Python, not split by awk)",
              show(out, err, rc))

        print("\nbrew_fallback_accepted")
        c = Case(root, "brew_fallback_accepted")
        opt = c.brew(opt_python=(PREF, 0))
        out, err, rc = c.run("ensure_csa_python")
        check(rc == 0 and only_line(out) == str(opt),
              f"uv absent, Homebrew's opt/python@{PREF} verifies -> it is the CSA Python",
              show(out, err, rc, c.calls()))
        check(not any(l.startswith("brew install") for l in c.calls()),
              "no brew install when the opt interpreter already verifies", "\n".join(c.calls()))
        c = Case(root, "brew_fallback_installs")
        opt = c.brew(install_creates=(PREF, 0))
        c.uv(install_fails=True, listing=[])
        out, err, rc = c.run("ensure_csa_python")
        check(rc == 0 and only_line(out) == str(opt),
              f"uv cannot install -> `brew install python@{PREF}` and its opt path is returned",
              show(out, err, rc, c.calls()))
        check(f"brew install python@{PREF}" in c.calls(),
              f"the fallback is the versioned formula python@{PREF}", "\n".join(c.calls()))
        c = Case(root, "brew_fallback_wrong_build")
        c.brew(opt_python=(PREF, 1))
        out, err, rc = c.run("find_csa_python")
        check(rc == 1 and out == "", "a free-threaded Homebrew opt interpreter is rejected too",
              show(out, err, rc))

        print("\nuv_install_fails")
        c = Case(root, "uv_install_fails")
        ft = c.ft()
        c.uv(find=ft, listing=[entry(ft, "freethreaded")], install_fails=True)
        out, err, rc = c.run("ensure_csa_python")
        check(rc == 1 and out == "" and "WARN" in err,
              "exit 1, nothing on stdout, a warning on stderr", show(out, err, rc))
        out, err, rc = c.run(
            'if p="$(ensure_csa_python)"; then echo "GOT $p"; else echo "NONE"; fi\n'
            "install_python\n"
            'echo "SURVIVED"')
        check(rc == 0 and "NONE" in out and "SURVIVED" in out,
              "callers (an `if` and install_python) survive set -e", show(out, err, rc))

        print("\nfind_never_installs")
        for name, setup in (
            ("nothing", lambda c: c.uv(listing=[])),
            ("only_ft", lambda c: c.uv(find=c.ft(), listing=[entry(c.ft(), "freethreaded")],
                                         after_find=c.std(), after_listing=[entry(c.std())])),
            ("brew_missing", lambda c: (c.uv(listing=[]), c.brew(install_creates=(PREF, 0)))),
        ):
            c = Case(root, f"find_never_installs_{name}")
            setup(c)
            out, err, rc = c.run("find_csa_python || true")
            bad = [l for l in c.calls() if " install" in l or "upgrade" in l or "self update" in l]
            check(not bad, f"find_csa_python ({name}) installs nothing",
                  "\n".join(c.calls()))

        print("\nfind_passes_system_flag")
        c = Case(root, "find_passes_system_flag")
        std = c.std()
        venv = c.home / ".default_venv-3.14"
        interp(venv / "bin" / "python3", PREF, 0)   # a venv Python that WOULD verify
        c.uv(find=std, listing=[entry(std)])
        out, err, rc = c.run("find_csa_python", extra_env={"VIRTUAL_ENV": str(venv)})
        finds = [l for l in c.calls() if l.startswith("uv python find")]
        check(bool(finds) and all(" --system" in l for l in finds),
              "with VIRTUAL_ENV set, every `uv python find` carries --system",
              "\n".join(c.calls()))
        check(rc == 0 and only_line(out) == str(std),
              "and the managed interpreter comes back, not the active venv's",
              show(out, err, rc))

        print("\nstdout_is_only_the_path")
        c = Case(root, "stdout_is_only_the_path")
        ft = c.ft()
        # uv's install "succeeds" without producing a standard build, so the run goes through
        # uv's chatter, info's, and brew's on its way to the Homebrew fallback.
        c.uv(find=ft, listing=[entry(ft, "freethreaded")])
        opt = c.brew(install_creates=(PREF, 0))
        out, err, rc = c.run("ensure_csa_python")
        check(rc == 0 and only_line(out) == str(opt),
              "chatty uv, brew and info: stdout is exactly the one path",
              show(out, err, rc, c.calls()))

        print("\nuv's paths are returned as printed")
        c = Case(root, "minor_version_path")
        patch_dir = c.uvpy / f"cpython-{PREF}.10-macos-aarch64-none"
        interp(patch_dir / "bin" / f"python{PREF}", PREF, 0)
        minor_dir = c.uvpy / f"cpython-{PREF}-macos-aarch64-none"
        minor_dir.symlink_to(patch_dir.name)
        minor = minor_dir / "bin" / f"python{PREF}"
        c.uv(find=minor, listing=[entry(minor)])
        out, err, rc = c.run("find_csa_python")
        check(rc == 0 and only_line(out) == str(minor),
              f"the minor-version path (cpython-{PREF}-<platform>), never the patch directory",
              show(out, err, rc))
        c = Case(root, "listing_shim")
        ft = c.ft()
        std = c.std()
        shim = c.home / ".local" / "bin" / f"python{PREF}"
        shim.parent.mkdir(parents=True)
        shim.symlink_to(std)
        c.uv(find=ft, listing=[entry(shim, symlink=str(std)), entry(std),
                               entry(ft, "freethreaded")])
        out, err, rc = c.run("find_csa_python")
        check(rc == 0 and only_line(out) == str(std),
              "a listing whose `path` is uv's ~/.local/bin shim yields the managed path",
              show(out, err, rc))
        c = Case(root, "listing_shim_only")
        ft = c.ft()
        std = c.std()
        shim = c.home / ".local" / "bin" / f"python{PREF}"
        shim.parent.mkdir(parents=True)
        shim.symlink_to(std)
        c.uv(find=ft, listing=[entry(shim), entry(ft, "freethreaded")])
        out, err, rc = c.run("find_csa_python")
        check(rc == 0 and only_line(out) == str(shim),
              "a shim that verifies is accepted when it is all the listing offers",
              show(out, err, rc))
        c = Case(root, "listing_variant_filter")
        ft = c.ft()
        liar = interp(c.uvpy / "liar" / f"python{FT}", PREF, 0)
        c.uv(find=ft, listing=[entry(liar, "freethreaded"), entry(ft, "freethreaded")])
        out, err, rc = c.run("find_csa_python")
        check(rc == 1 and out == "", "listing entries whose variant is not `default` are skipped",
              show(out, err, rc))

        print("\npython_is_csa_build is silent")
        c = Case(root, "silent")
        std = c.std()
        dead = c.dir / "dead-python"
        dead.symlink_to(c.dir / "nowhere")
        for target in (std, dead):
            out, err, rc = c.run(f'python_is_csa_build "{target}" || true')
            check(out == "" and err == "", f"no output for {target.name}",
                  show(out, err, rc))


def install_uv_cases() -> None:
    print("\ninstall_uv keeps uv current")
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        c = Case(root, "uv_brew_owned")
        c.uv()
        c.brew(owns_uv=True)
        out, err, rc = c.run('install_uv\necho "AFTER"')
        check(rc == 0 and "AFTER" in out and "brew upgrade --formula uv" in c.calls(),
              "Homebrew owns uv -> `brew upgrade --formula uv`", show(out, err, rc, c.calls()))
        check(not any(l.startswith("uv self update") for l in c.calls()),
              "and never `uv self update`, which fails on a Homebrew install",
              "\n".join(c.calls()))

        c = Case(root, "uv_standalone")
        c.uv()
        c.brew()
        out, err, rc = c.run('install_uv\necho "AFTER"')
        check(rc == 0 and "AFTER" in out and "uv self update" in c.calls(),
              "a standalone uv -> `uv self update`", show(out, err, rc, c.calls()))
        check(not any(l.startswith("brew upgrade") for l in c.calls()),
              "and no brew upgrade", "\n".join(c.calls()))

        c = Case(root, "uv_update_fails")
        c.uv(self_update_fails=True)
        out, err, rc = c.run('install_uv\necho "AFTER"')
        check(rc == 0 and "AFTER" in out and "WARN" in err,
              "a failed update only warns; the run continues", show(out, err, rc, c.calls()))


def real_interpreters() -> None:
    print("\npython_is_csa_build vs. real interpreters")
    body = PREF_LINE + "\n" + extract("python_is_csa_build")
    candidates = ["/usr/bin/python3", sys.executable]
    for minor in range(9, 16):
        for name in (f"python3.{minor}", f"python3.{minor}t"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
    tested = 0
    probe = ("import sys, sysconfig; print('%d.%d' % sys.version_info[:2], "
             "1 if sysconfig.get_config_var('Py_GIL_DISABLED') else 0)")
    for path in dict.fromkeys(candidates):
        if not os.path.exists(path):
            continue
        real = subprocess.run([path, "-I", "-c", probe], capture_output=True, text=True)
        if real.returncode != 0:
            continue
        version, gil = real.stdout.split()
        expected = version == PREF and gil == "0"
        with tempfile.TemporaryDirectory() as td:
            script = pathlib.Path(td) / "h.sh"
            script.write_text(f'set -euo pipefail\n{body}\n'
                              f'if python_is_csa_build "{path}"; then exit 0; else exit 1; fi\n',
                              encoding="utf-8")
            rc = subprocess.run([BASH, str(script)], capture_output=True, text=True,
                                env={**base_env(), "PATH": os.environ.get("PATH", ""),
                                     "HOME": td}).returncode
        build = "free-threaded" if gil == "1" else "standard"
        check((rc == 0) == expected,
              f"{path} is {version} {build} -> {'accepted' if expected else 'rejected'}")
        tested += 1
        if path == "/usr/bin/python3" and version != PREF:
            check(rc != 0, f"THE #53 CASE: stock /usr/bin/python3 {version} is rejected")
    check(tested > 0, "at least one real interpreter was exercised")


def floor_vs_real_interpreters() -> None:
    """python_meets_floor still gates the venv rebuild in install_doc_python_deps."""
    print("\npython_meets_floor vs. real interpreters")
    min_line = extract_assignment("CSA_PYTHON_MIN")
    min_v = tuple(int(p) for p in min_line.split('"')[1].split("."))
    check(min_v >= (3, 10), "the floor is at least 3.10 (what csa-google-workspace requires)")
    body = "\n".join([min_line, PREF_LINE, extract("python_meets"), extract("python_meets_floor")])
    candidates = ["/usr/bin/python3", sys.executable]
    for name in ("python3", "python3.9", "python3.10", "python3.11", "python3.12", "python3.13"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    tested = 0
    for path in dict.fromkeys(candidates):
        if not os.path.exists(path):
            continue
        real = subprocess.run([path, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                              capture_output=True, text=True)
        if real.returncode != 0:
            continue
        actual = tuple(int(p) for p in real.stdout.strip().split("."))
        expected = actual >= min_v
        with tempfile.TemporaryDirectory() as td:
            script = pathlib.Path(td) / "h.sh"
            script.write_text(f'set -euo pipefail\n{body}\n'
                              f'if python_meets_floor "{path}"; then exit 0; else exit 1; fi\n',
                              encoding="utf-8")
            rc = subprocess.run([BASH, str(script)], capture_output=True, text=True,
                                env={**base_env(), "PATH": os.environ.get("PATH", ""),
                                     "HOME": td}).returncode
        check((rc == 0) == expected,
              f"{path} is {'.'.join(map(str, actual))} -> {'accepts' if expected else 'rejects'}")
        tested += 1
    check(tested > 0, "at least one real interpreter was exercised")


def _function_body(text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    return m.group(0) if m else ""


def static_checks() -> None:
    print("\nwhat the script calls, and where")
    code = code_only(TEXT)
    check("find_usable_python" not in code,
          "find_usable_python is gone: one resolver, not two that can disagree")
    pre = code_only(_function_body(TEXT, "preflight"))
    check("find_csa_python" in pre, "the preflight's Python row asks find_csa_python")
    check("ensure_csa_python" not in pre and "python install" not in pre
          and "brew install" not in pre,
          "the preflight installs nothing: it runs before the person has agreed")
    check(re.search(r'"\s{2}uv \.+.*keep current', pre) is not None,
          "the uv plan row says uv is kept current")
    check("ensure_csa_python" in code_only(_function_body(TEXT, "install_python")),
          "install_python provisions through ensure_csa_python")
    check("ensure_csa_python" in code_only(_function_body(TEXT, "install_doc_python_deps")),
          "install_doc_python_deps builds on ensure_csa_python's interpreter")
    check(re.search(r"brew install python(\s|\"|$)", code, re.M) is None,
          "the unversioned Homebrew `python` (whatever minor it is today) is never installed")


def windows_twin() -> None:
    print("\nwindows_twin_exists")
    ps = WIN.read_text(encoding="utf-8")
    names = ["Test-CsaPythonBuild", "Find-CsaPython", "Install-CsaPython"]
    have = [n for n in names
            if re.search(rf"^\s*function\s+{re.escape(n)}\b", ps, re.M | re.I)]
    if not have:
        print("    SKIP  windows_twin_exists (Windows twin pending #184)")
        return
    check(have == names, "windows-ai-tools.ps1 defines all three twins: " + ", ".join(names),
          f"found only: {', '.join(have)}")


def main() -> int:
    print(f"CSA_PYTHON_PREFERRED declared by the script: {PREF}")
    resolver_cases()
    install_uv_cases()
    real_interpreters()
    floor_vs_real_interpreters()
    static_checks()
    windows_twin()
    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
