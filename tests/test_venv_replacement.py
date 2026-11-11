#!/usr/bin/env python3
"""`~/.default_venv` is a link to `~/.default_venv-3.14`, and a rerun repairs it without losing anything.

Issue #179. `~/.default_venv` is the venv document-pipeline's bash
launchers probe (`$HOME/.default_venv/bin/python3`). On real Macs it was built on whatever
`python3` was on PATH: Homebrew's 3.15, a 3.13, uv's free-threaded 3.14t, or a Homebrew Cellar
path that the next `brew upgrade` deletes. The CINO decided (2026-11-10) that it becomes a
RELATIVE symlink to a versioned directory, `~/.default_venv-3.14`, and that the installer
rebuilds it even while it is active in the calling shell (D1). His own Mac was migrated by hand
that day; `cinos_mac_state_noop` is that state, and the installer must leave it alone.

What `ensure_default_venv` must never do, each pinned by a case below:

  * **lose a venv.** Every old directory is renamed aside and kept: a real `~/.default_venv` to
    `~/.default_venv-<X.Y>` (`-unknown`, plus a timestamp on a name collision), a broken
    `-3.14` to `-3.14.broken-<ts>`. Build first, swap last: when the build fails, nothing moved.
  * **break the swap.** BSD `mv newlink ~/.default_venv`, where `~/.default_venv` is a link to a
    directory, exits 0, changes nothing and drops `newlink` INSIDE the old target (measured);
    `mv -h` replaces the link. `control_plain_mv_caught` proves the cases here notice.
  * **break the console scripts.** A venv built at one path and renamed breaks `activate` and
    every console script, because both hardcode the creation path. The `.new-$$` replacement is
    built with `uv venv --seed --relocatable` and filled with `uv pip` only, so a dependency's
    console script still runs after the rename (`replaced_target_console_script_runs`, with real
    uv and real wheels built here, offline; `control_no_relocatable_caught`).
  * **trust PATH.** The venv is built on the CSA Python (`find_csa_python`, then
    `ensure_csa_python`), never on `python3`.
  * **bring in onnxruntime** (#179's final review): its official macOS builds send Microsoft
    telemetry by default. pymupdf is pinned below 2 (2.x requires onnxruntime), every install
    passes `pymupdf>=1.24.3,<2` as ONE argument, and markitdown is not installed at all
    (`doc_deps_pinned`).

**How this is tested.** The real functions are extracted from the shipping scripts and run in
bash on a stub-only PATH: stub `uv`, `brew` and interpreters, plus the real `mv`, `ln`, `rm`,
`date` and `readlink`. The stub `uv` and the stub interpreters build venv-shaped directories
with the same `bin/` links and `pyvenv.cfg` keys the real tools write (`version_info` from
`uv venv`, `version` from `python -m venv`), and the interpreters answer the build probe with a
version and a GIL flag. HOME is a temporary directory; the real `~`, `~/.zshrc`,
`~/.local/share/uv` and Homebrew are never touched.

On Linux (CI) GNU `mv` has no `-h`; its `-T` is the same operation, and a shim in the stub PATH
translates. BSD `mv` itself is exercised when this runs on macOS (`tools/check-all.sh`).
`replaced_target_console_script_runs` needs a real `uv` and a real standard 3.14 and is SKIPPED
without them.

    python3 tests/test_venv_replacement.py
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
AI = ROOT / "scripts" / "macos-ai-tools.sh"
UPD = ROOT / "scripts" / "macos-update.sh"
THIS = pathlib.Path(__file__).resolve()
PY = sys.executable

PROBE = ('import sys, sysconfig; print("%d.%d" % sys.version_info[:2], '
         '1 if sysconfig.get_config_var("Py_GIL_DISABLED") else 0)')

# ── stubs: this file is also the stub uv / brew / interpreter helper ──────────────────────────


def _log(scen: pathlib.Path, line: str, argv: list[str] | None = None) -> None:
    with open(scen / "calls.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # calls.log joins arguments with spaces; argv.jsonl keeps their boundaries, so a test can
    # tell `"pymupdf>=1.24.3,<2"` (one argument) from `pymupdf>=1.24.3,` `<2` (two).
    if argv is not None:
        with open(scen / "argv.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(argv) + "\n")


def add_dist(site: pathlib.Path, name: str, version: str = "1.0",
             requires: tuple[str, ...] = ()) -> None:
    d = site / f"{name}-{version}.dist-info"
    d.mkdir(parents=True, exist_ok=True)
    meta = [f"Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    meta += [f"Requires-Dist: {r}" for r in requires]
    (d / "METADATA").write_text("\n".join(meta) + "\n", encoding="utf-8")


def make_venv(venv: pathlib.Path, interp: str, *, style: str, xy: str,
              relocatable: bool = False, home: str | None = None,
              dists: tuple = (), marker: str | None = None, cfg_version: bool = True) -> pathlib.Path:
    """A venv-shaped directory, laid out the way `uv venv` (style "uv") or `python -m venv`
    (style "venv") lays one out: bin/ links to the base interpreter, pyvenv.cfg, site-packages."""
    b = venv / "bin"
    b.mkdir(parents=True)
    if style == "uv":
        (b / "python").symlink_to(interp)
        (b / "python3").symlink_to("python")
        (b / f"python{xy}").symlink_to("python")
        cfg = [f"home = {home or os.path.dirname(interp)}", "implementation = CPython",
               "uv = 0.13.7", f"version_info = {xy}.10", "include-system-site-packages = false"]
        if relocatable:
            cfg.append("relocatable = true")
        cfg.append("seed = true")
    else:
        (b / f"python{xy}").symlink_to(interp)
        (b / "python").symlink_to(f"python{xy}")
        (b / "python3").symlink_to(f"python{xy}")
        cfg = [f"home = {home or os.path.dirname(interp)}", "include-system-site-packages = false"]
        if cfg_version:
            cfg.append(f"version = {xy}.1")
        cfg += [f"executable = {interp}", f"command = {interp} -m venv {venv}"]
    if not cfg_version:
        cfg = [c for c in cfg if not c.startswith("version")]
    (venv / "pyvenv.cfg").write_text("\n".join(cfg) + "\n", encoding="utf-8")
    (b / "activate").write_text(f"VIRTUAL_ENV='{venv}'\nexport VIRTUAL_ENV\n", encoding="utf-8")
    site = venv / "lib" / f"python{xy}" / "site-packages"
    site.mkdir(parents=True)
    for d in dists:
        if isinstance(d, str):
            add_dist(site, d)
        else:
            add_dist(site, d[0], requires=tuple(d[1]))
    if marker:
        (venv / "MARKER").write_text(marker, encoding="utf-8")
    return venv


def _probe_xy(interp: str) -> str | None:
    try:
        p = subprocess.run([interp, "-I", "-c", PROBE], capture_output=True, text=True, timeout=60)
    except OSError:
        return None
    if p.returncode != 0 or not p.stdout.split():
        return None
    return p.stdout.split()[0]


def _install_into(venv: pathlib.Path, pkgs: list[str]) -> None:
    sites = sorted(venv.glob("lib/python*/site-packages"))
    site = sites[0] if sites else venv / "lib" / "python3.14" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    for p in pkgs:
        add_dist(site, re.split(r"[\[<>=!~; ]", p, maxsplit=1)[0])


def stub_main(argv: list[str]) -> int:
    scen, tool, args = pathlib.Path(argv[0]), argv[1], argv[2:]
    _log(scen, f"{tool} {' '.join(args)}", [tool] + args)
    if tool == "uv":
        if args[:1] == ["--version"]:
            print("uv 0.13.7")
            return 0
        if args[:2] == ["python", "find"]:
            # Measured on uv 0.13.7: with VIRTUAL_ENV set, `uv python find` returns the active
            # venv's interpreter unless --system is given.
            if os.environ.get("VIRTUAL_ENV") and "--system" not in args:
                print(os.environ["VIRTUAL_ENV"] + "/bin/python3")
                return 0
            if (scen / "find").exists():
                print((scen / "find").read_text(encoding="utf-8").strip())
                return 0
            print("error: No interpreter found", file=sys.stderr)
            return 2
        if args[:2] == ["python", "list"]:
            f = scen / "list.json"
            print(f.read_text(encoding="utf-8") if f.exists() else "[]")
            return 0
        if args[:2] == ["python", "install"]:
            print("uv-chatter: installing Python (on stdout, on purpose)")
            if (scen / "install.fails").exists():
                print("error: network unreachable", file=sys.stderr)
                return 1
            for src, dst in (("after.find", "find"), ("after.json", "list.json")):
                if (scen / src).exists():
                    shutil.copy(scen / src, scen / dst)
            return 0
        if args[:1] == ["venv"]:
            py, target, i = None, None, 1
            while i < len(args):
                if args[i] == "--python":
                    py, i = args[i + 1], i + 2
                    continue
                if not args[i].startswith("-"):
                    target = args[i]
                i += 1
            if (scen / "venv.fails").exists() or not py or not target:
                pathlib.Path(target or scen / "nowhere").mkdir(parents=True, exist_ok=True)
                print("error: could not create the venv", file=sys.stderr)
                return 1
            xy = _probe_xy(py)
            if xy is None:
                return 1
            make_venv(pathlib.Path(target), py, style="uv", xy=xy,
                      relocatable="--relocatable" in args)
            return 0
        if args[:2] == ["pip", "install"]:
            if (scen / "pip.fails").exists():
                print("error: no network", file=sys.stderr)
                return 1
            vpy = args[args.index("--python") + 1]
            pkgs = [a for i, a in enumerate(args[2:], 2)
                    if not a.startswith("-") and args[i - 1] != "--python"]
            _install_into(pathlib.Path(vpy).parent.parent, pkgs)
            return 0
        if args[:2] == ["tool", "dir"]:
            f = scen / "tooldir"
            if not f.exists():
                return 2
            print(f.read_text(encoding="utf-8").strip())
            return 0
        return 0
    if tool == "brew":
        if args[:1] == ["--prefix"]:
            print(scen / "brew")
            return 0
        if args[:1] == ["install"]:
            print(f"brew-chatter: installing {' '.join(args[1:])} (on stdout, on purpose)")
            return 1 if (scen / "brew-install.fails").exists() else 0
        if args[:1] == ["list"]:
            return 1
        return 0
    if tool == "active-py":          # PATH's python3 inside an activated venv (update_pip's)
        cfg = json.loads((scen / "active.json").read_text(encoding="utf-8"))
        if args[:2] == ["-m", "pip"]:
            if "list" in args and "--outdated" in args:
                print(json.dumps(cfg["outdated"]))
            elif "install" in args:
                c = os.environ.get("PIP_CONSTRAINT", "")
                seen = (pathlib.Path(c).read_text(encoding="utf-8").strip().replace("\n", " ")
                        if c and os.path.isfile(c) else "<none>")
                _log(scen, f"constraint {seen} file={c}")
            return 0
        if "-c" in args and "sys.prefix" in args[args.index("-c") + 1]:
            print(cfg["prefix"])
            return 0
        os.execv(sys.executable, [sys.executable] + args)   # the JSON filter: run it for real
    if tool == "py-venv":            # <interp as invoked> -m venv <dir>
        self_path, target = args[0], args[1]
        if (scen / "pyvenv.fails").exists():
            pathlib.Path(target).mkdir(parents=True, exist_ok=True)
            return 1
        xy = _probe_xy(self_path)
        if xy is None:
            return 1
        make_venv(pathlib.Path(target), self_path, style="venv", xy=xy)
        return 0
    if tool == "py-pip":             # <venv python> -m pip ...
        self_path, rest = args[0], args[3:]
        if "--version" in rest:
            print("pip 24.0 (stub)")
            return 0
        if rest[:1] == ["install"]:
            if (scen / "pip.fails").exists():
                return 1
            _install_into(pathlib.Path(self_path).parent.parent,
                          [a for a in rest[1:] if not a.startswith("-")])
        return 0
    return 0


# Stub mode dispatches HERE, before the module goes on to extract functions from the scripts: an
# extraction that fails prints a FAIL line, and in a stub that line would land in the stub's own
# stdout (a fake `uv python find` answer, say) and corrupt it.
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--stub":
    sys.exit(stub_main(sys.argv[2:]))


# ── the harness ────────────────────────────────────────────────────────────────────────────────


def _posix_bash() -> str:
    override = os.environ.get("CSA_TEST_BASH")
    if override:
        return override
    return "/bin/bash"


BASH = _posix_bash()

failures: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    print(f"    {'ok  ' if cond else 'FAIL'}  {label}")
    if not cond:
        failures.append(label)
        for line in detail.splitlines()[-60:]:
            print(f"          {line}")


def _text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def extract(name: str, path: pathlib.Path = AI) -> str:
    """A function's text out of a shipping script. A missing one is a FAILURE, replaced by a
    stand-in that returns 99, so every case that needs it reports instead of one crash."""
    text = _text(path)
    m = (re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
         or re.search(rf"^{re.escape(name)}\(\) \{{.*\}}$", text, re.M))
    if not m:
        label = f"{path.name} defines {name}()"
        if label not in failures:
            check(False, label)
        return f'{name}() {{ echo "{name}: MISSING FROM THE SCRIPT" >&2; return 99; }}'
    return m.group(0)


def assignment(name: str, path: pathlib.Path = AI) -> str:
    m = re.search(rf"^{re.escape(name)}=(\"[^\"]*\"|\([^)]*\))$", _text(path), re.M)
    if not m:
        check(False, f"{path.name} assigns {name}")
        return ""
    return m.group(0)


def code_only(block: str) -> str:
    return "\n".join(l for l in block.splitlines() if not l.lstrip().startswith("#"))


PREF = assignment("CSA_PYTHON_PREFERRED").split('"')[1]
FT = f"{PREF}t"
VERSIONED = f".default_venv-{PREF}"
TODO_TERMINAL = "Open a new terminal to use the rebuilt ~/.default_venv"

# The functions ensure_default_venv is built from, shared byte-identically by both scripts.
SHARED = ["has_command", "python_is_csa_build", "find_csa_python", "ensure_csa_python",
          "csa_venv_pip_install", "venv_cfg_get", "venv_rebuild_reason", "venv_aside_name",
          "venv_extra_packages", "default_venv_state", "default_venv_plan", "default_venv_build",
          "ensure_default_venv"]
OUTPUT = ['info()    { echo "INFO: $*"; }',
          'success() { echo "SUCCESS: $*"; }',
          'warn()    { echo "WARN: $*" >&2; }',
          'error()   { echo "ERROR: $*" >&2; }',
          'abort()   { error "$@"; exit 1; }']


def harness(script: pathlib.Path) -> str:
    parts = [assignment("CSA_PYTHON_PREFERRED", script), assignment("CSA_VENV", script),
             assignment("CSA_DOC_PY_DEPS", script)]
    parts += [extract(n, script) for n in SHARED]
    if script == AI:
        parts.append(assignment("CSA_INTERNAL_SETUPS"))
        parts += [extract(n) for n in ("install_doc_python_deps", "csa_tool_repairs",
                                       "csa_todo_add")]
    else:
        parts += [extract(n, UPD) for n in ("update_default_venv", "csa_venv_held_names",
                                            "pip_upgrades", "update_pip")]
    return "\n".join(parts + OUTPUT)


HARNESS = {"ai": harness(AI), "update": harness(UPD)}


def entry(path: pathlib.Path | str, variant: str = "default") -> dict:
    """One element of `uv python list --output-format json`, in the shape uv 0.13.7 prints."""
    return {"key": f"cpython-{PREF}.10-macos-aarch64-none", "version": f"{PREF}.10",
            "path": str(path), "symlink": None, "url": None, "os": "macos",
            "variant": variant, "implementation": "cpython", "arch": "aarch64", "libc": "none"}


INTERP = """#!/bin/sh
case "$*" in
  *Py_GIL_DISABLED*) echo "{ver} {gil}"; exit 0 ;;
esac
if [ "$1" = "-m" ] && [ "$2" = "venv" ]; then exec "{py}" "{this}" --stub "{scen}" py-venv "$0" "$3"; fi
if [ "$1" = "-m" ] && [ "$2" = "pip" ]; then exec "{py}" "{this}" --stub "{scen}" py-pip "$0" "$@"; fi
if [ "$1" = "-m" ] && [ "$2" = "ensurepip" ]; then exit 0; fi
exec "{py}" "$@"
"""

TOOL = """#!/bin/sh
exec "{py}" "{this}" --stub "{scen}" {tool} "$@"
"""

PATH_PY = """#!/bin/sh
printf 'pathpy %s %s\\n' "$0" "$*" >> "{scen}/calls.log"
case "$*" in
  *"pip list --outdated"*) echo "[]"; exit 0 ;;
  *Py_GIL_DISABLED*) echo "{ver} 0"; exit 0 ;;
esac
exit 0
"""


class World:
    """One scenario: a stub-only PATH (bin/ + tools/), a scenario dir the stubs read and log to,
    uv- and Homebrew-shaped interpreter trees, and a HOME that is not the real one."""

    def __init__(self, root: pathlib.Path, name: str, home: str = "home"):
        self.dir = root / name
        self.bin, self.tools, self.scen = self.dir / "bin", self.dir / "tools", self.dir / "scen"
        self.uvpy, self.home = self.dir / "uv python", self.dir / home
        for d in (self.bin, self.tools, self.scen, self.uvpy, self.home):
            d.mkdir(parents=True, exist_ok=True)
        (self.scen / "calls.log").write_text("", encoding="utf-8")
        for t in ("ln", "rm", "date", "readlink", "mktemp", "basename"):
            found = shutil.which(t)
            if found:
                (self.tools / t).symlink_to(found)
        real_mv = shutil.which("mv") or "/bin/mv"
        if sys.platform == "darwin":
            (self.tools / "mv").symlink_to(real_mv)
        else:
            # GNU mv has no -h; -T ("treat DEST as a normal file") is the same operation.
            (self.tools / "mv").write_text(
                "#!/bin/sh\n"
                f'if [ "$1" = "-h" ]; then shift; exec "{real_mv}" -T "$@"; fi\n'
                f'exec "{real_mv}" "$@"\n', encoding="utf-8")
            (self.tools / "mv").chmod(0o755)

    # interpreters
    def interp(self, path: pathlib.Path, version: str, gil: int = 0) -> pathlib.Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(INTERP.format(ver=version, gil=gil, py=PY, this=THIS, scen=self.scen),
                        encoding="utf-8")
        path.chmod(0o755)
        return path

    def std(self) -> pathlib.Path:
        p = self.uvpy / f"cpython-{PREF}-macos-aarch64-none" / "bin" / f"python{PREF}"
        return p if p.exists() else self.interp(p, PREF, 0)

    def ft(self) -> pathlib.Path:
        p = self.uvpy / f"cpython-{PREF}+freethreaded-macos-aarch64-none" / "bin" / f"python{FT}"
        return p if p.exists() else self.interp(p, PREF, 1)

    def other(self, xy: str) -> pathlib.Path:
        p = self.uvpy / f"cpython-{xy}-macos-aarch64-none" / "bin" / f"python{xy}"
        return p if p.exists() else self.interp(p, xy, 0)

    def dead(self) -> pathlib.Path:
        """A path that is not there: the interpreter a venv was built on, since deleted."""
        return self.dir / "deleted" / f"cpython-{PREF}-macos-aarch64-none" / "bin" / f"python{PREF}"

    def broken_runs(self) -> pathlib.Path:
        p = self.dir / "noexec" / f"python{PREF}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        p.chmod(0o755)
        return p

    def cellar(self, prefix: pathlib.Path | None = None) -> tuple[pathlib.Path, pathlib.Path]:
        """Homebrew's layout: opt/python@3.14 -> ../Cellar/python@3.14/3.14.10. Returns the
        Cellar interpreter and the opt one (whose realpath is the Cellar one)."""
        brew = prefix or (self.scen / "brew")
        cel = self.interp(brew / "Cellar" / f"python@{PREF}" / f"{PREF}.10" / "bin" / f"python{PREF}",
                          PREF, 0)
        opt = brew / "opt" / f"python@{PREF}"
        if not opt.exists():
            opt.parent.mkdir(parents=True, exist_ok=True)
            opt.symlink_to(f"../Cellar/python@{PREF}/{PREF}.10")
        return cel, opt / "bin" / f"python{PREF}"

    # tools
    def _tool(self, name: str) -> None:
        f = self.bin / name
        f.write_text(TOOL.format(py=PY, this=THIS, scen=self.scen, tool=name), encoding="utf-8")
        f.chmod(0o755)

    def uv(self, *, find=None, listing=None, after_find=None, after_listing=None,
           install_fails=False, venv_fails=False, pip_fails=False, tooldir=None) -> None:
        self._tool("uv")
        for fname, val in (("find", find), ("after.find", after_find)):
            if val is not None:
                (self.scen / fname).write_text(f"{val}\n", encoding="utf-8")
        for fname, val in (("list.json", listing), ("after.json", after_listing)):
            if val is not None:
                (self.scen / fname).write_text(json.dumps(val), encoding="utf-8")
        for fname, on in (("install.fails", install_fails), ("venv.fails", venv_fails),
                          ("pip.fails", pip_fails)):
            if on:
                (self.scen / fname).write_text("", encoding="utf-8")
        if tooldir is not None:
            (self.scen / "tooldir").write_text(str(tooldir), encoding="utf-8")

    def uv_std(self, **kw) -> pathlib.Path:
        std = self.std()
        self.uv(find=std, listing=[entry(std)], **kw)
        return std

    def brew(self) -> None:
        self._tool("brew")

    def active_python(self, prefix: pathlib.Path | str, outdated: list[dict]) -> None:
        """PATH's python3 is a venv's: sys.prefix is `prefix`, and pip reports `outdated`."""
        (self.scen / "active.json").write_text(
            json.dumps({"prefix": str(prefix), "outdated": outdated}), encoding="utf-8")
        f = self.bin / "python3"
        f.write_text(TOOL.format(py=PY, this=THIS, scen=self.scen, tool="active-py"),
                     encoding="utf-8")
        f.chmod(0o755)

    def path_python(self, name: str, version: str) -> None:
        f = self.bin / name
        f.write_text(PATH_PY.format(scen=self.scen, ver=version), encoding="utf-8")
        f.chmod(0o755)

    # venvs under HOME
    def venv(self, name: str, interp, *, style: str = "uv", xy: str | None = None, **kw) -> pathlib.Path:
        return make_venv(self.home / name, str(interp), style=style, xy=xy or PREF, **kw)

    def link(self, target: str | pathlib.Path) -> pathlib.Path:
        p = self.home / ".default_venv"
        p.symlink_to(target)
        return p

    # running
    def run(self, call: str, *, script: str = "ai", env: dict | None = None,
            override: str = "") -> tuple[str, str, int]:
        harness_file = self.dir / "harness.sh"
        harness_file.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + HARNESS[script]
                                + "\n" + override + "\n" + call + "\n", encoding="utf-8")
        e = {"PATH": f"{self.bin}:{self.tools}", "HOME": str(self.home)}
        e.update(env or {})
        p = subprocess.run([BASH, str(harness_file)], capture_output=True, text=True, env=e,
                           timeout=300)
        return p.stdout, p.stderr, p.returncode

    def calls(self) -> list[str]:
        return _text(self.scen / "calls.log").splitlines()

    def argvs(self) -> list[list[str]]:
        f = self.scen / "argv.jsonl"
        return [json.loads(l) for l in _text(f).splitlines()] if f.exists() else []

    def snapshot(self) -> dict:
        """Everything under HOME: links by target, files by content."""
        out = {}
        for dirpath, dirnames, filenames in os.walk(self.home):
            for n in dirnames + filenames:
                p = pathlib.Path(dirpath) / n
                rel = str(p.relative_to(self.home))
                if p.is_symlink():
                    out[rel] = ("L", os.readlink(p))
                elif p.is_file():
                    out[rel] = ("F", p.read_bytes())
                else:
                    out[rel] = ("D",)
        return out

    def default(self) -> pathlib.Path:
        return self.home / ".default_venv"

    def versioned(self) -> pathlib.Path:
        return self.home / VERSIONED


def show(out: str, err: str, rc: int, calls: list[str] | None = None) -> str:
    text = f"rc={rc}\nstdout:\n{out}\nstderr:\n{err}"
    if calls is not None:
        text += "\ncalls:\n" + "\n".join(calls)
    return text


def home_of(venv: pathlib.Path) -> str:
    if not (venv / "pyvenv.cfg").is_file():
        return ""
    for line in _text(venv / "pyvenv.cfg").splitlines():
        if line.startswith("home"):
            return line.split("=", 1)[1].strip()
    return ""


def marker(v: pathlib.Path) -> str:
    f = v / "MARKER"
    return _text(f).strip() if f.exists() else "<absent>"


def link_target(p: pathlib.Path) -> str | None:
    return os.readlink(p) if p.is_symlink() else None


def siblings(w: World, pattern: str) -> list[pathlib.Path]:
    return sorted(w.home.glob(pattern))


def venv_calls(w: World) -> list[str]:
    return [c for c in w.calls() if c.startswith("uv venv") or c.startswith("py-venv")]


def installs(w: World) -> list[str]:
    return [c for c in w.calls() if c.startswith("uv python install") or c.startswith("brew install")]


def sound_on_std(w: World) -> bool:
    v = w.versioned()
    return v.is_dir() and not v.is_symlink() and home_of(v) == str(w.std().parent)


TS = re.compile(r"\d{14}$")


# ── layout ─────────────────────────────────────────────────────────────────────────────────────


def layout_cases(root: pathlib.Path) -> None:
    print("\nreal_dir_migrated_to_versioned_and_linked")
    w = World(root, "real_dir_migrated")
    w.uv_std()
    w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13", marker="ORIGINAL")
    out, err, rc = w.run("ensure_default_venv")
    old = w.home / ".default_venv-3.13"
    check(rc == 0 and link_target(w.default()) == VERSIONED,
          f"~/.default_venv is now a link to {VERSIONED}", show(out, err, rc, w.calls()))
    check(marker(old) == "ORIGINAL" and old.is_dir() and not old.is_symlink(),
          "the old directory is kept, renamed to ~/.default_venv-3.13", show(out, err, rc))
    check(sound_on_std(w), f"{VERSIONED} is built on the CSA Python", show(out, err, rc, w.calls()))
    check(".default_venv-3.13" in err, "the warning names where the old venv went", err)
    check(any(c.startswith("uv venv") and "--seed" in c and "--relocatable" not in c
              and c.endswith(VERSIONED) for c in w.calls()),
          "a fresh build is `uv venv --seed` straight at the final path (not --relocatable)",
          "\n".join(w.calls()))

    print("\nlink_is_relative")
    w = World(root, "link_is_relative")
    w.uv_std()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED,
          f"a fresh machine gets ~/.default_venv -> {VERSIONED}, relative",
          show(out, err, rc, w.calls()))
    moved = w.dir / "home-moved"
    w.home.rename(moved)
    check((moved / ".default_venv" / "bin" / "python3").exists(),
          "the link still resolves when the home directory itself moves")
    moved.rename(w.home)

    print("\nlink_current_noop")
    w = World(root, "link_current_noop")
    w.uv_std()
    w.venv(VERSIONED, w.std(), marker="CURRENT")
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before, "a link to a sound -3.14 changes nothing",
          show(out, err, rc, w.calls()))
    check(not venv_calls(w) and not installs(w) and "WARN" not in err,
          "no build, no install, no warning", show(out, err, rc, w.calls()))

    print("\ndangling_link_reflipped")
    w = World(root, "dangling_link_reflipped")
    w.uv_std()
    w.link(".default_venv-3.13")
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED and sound_on_std(w),
          "a dangling link is rebuilt and flipped", show(out, err, rc, w.calls()))
    check("no longer exists" in err, "the warning says the old target no longer exists", err)
    w = World(root, "dangling_link_to_314")
    w.uv_std()
    w.link(VERSIONED)                   # -3.14 itself was deleted
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED and sound_on_std(w)
          and "no longer existed; it is rebuilt" in err and "kept" not in err,
          f"a link to a deleted {VERSIONED} rebuilds it, and does not claim it was kept",
          show(out, err, rc, w.calls()))

    print("\nbroken_314_target_replaced")
    w = World(root, "broken_314_target_replaced")
    w.uv_std()
    w.venv(VERSIONED, w.broken_runs(), marker="BROKEN")
    w.link(VERSIONED)
    out, err, rc = w.run("ensure_default_venv")
    broken = siblings(w, VERSIONED + ".broken-*")
    check(rc == 0 and sound_on_std(w) and link_target(w.default()) == VERSIONED,
          f"{VERSIONED} is replaced in place; the link is unchanged", show(out, err, rc, w.calls()))
    check(len(broken) == 1 and TS.search(broken[0].name) and marker(broken[0]) == "BROKEN",
          f"the broken one is kept at {VERSIONED}.broken-<timestamp>", str(broken))
    new = [c for c in w.calls() if c.startswith("uv venv")]
    check(len(new) == 1 and "--relocatable" in new[0] and "--seed" in new[0]
          and re.search(re.escape(VERSIONED) + r"\.new-\d+$", new[0]) is not None,
          "the replacement is built with `uv venv --seed --relocatable` at .new-$$", "\n".join(new))
    check(not siblings(w, VERSIONED + ".new-*"), "no .new-$$ build is left behind")
    check("its Python does not run" in err, "the reason is named", err)

    print("\nold_versions_kept")
    w = World(root, "old_versions_kept")
    w.uv_std()
    w.venv(".default_venv-3.13", w.other("3.13"), xy="3.13", marker="313")
    w.venv(".default_venv-3.12", w.other("3.12"), xy="3.12", marker="312")
    w.link(".default_venv-3.13")
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED, "flipped to -3.14",
          show(out, err, rc, w.calls()))
    check(marker(w.home / ".default_venv-3.13") == "313"
          and marker(w.home / ".default_venv-3.12") == "312",
          "older versioned directories are kept, never deleted")

    print("\nmigration_name_collision")
    w = World(root, "migration_name_collision")
    w.uv_std()
    w.venv(".default_venv-3.13", w.other("3.13"), xy="3.13", marker="OLDER")
    w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13", marker="REAL")
    out, err, rc = w.run("ensure_default_venv")
    moved = [p for p in siblings(w, ".default_venv-3.13-*") if TS.search(p.name)]
    check(rc == 0 and marker(w.home / ".default_venv-3.13") == "OLDER",
          "the existing -3.13 is not overwritten", show(out, err, rc, w.calls()))
    check(len(moved) == 1 and marker(moved[0]) == "REAL",
          "the real directory goes to -3.13-<timestamp>", str(siblings(w, ".default_venv*")))
    w = World(root, "migration_name_collision_314")
    w.uv_std()
    w.venv(".default_venv", w.std(), style="venv", marker="REAL314")
    out, err, rc = w.run("ensure_default_venv")
    moved = [p for p in siblings(w, VERSIONED + "-*") if TS.search(p.name)]
    check(rc == 0 and len(moved) == 1 and marker(moved[0]) == "REAL314" and sound_on_std(w)
          and marker(w.versioned()) == "<absent>",
          f"a real 3.14 directory never takes the {VERSIONED} name; it goes to -3.14-<timestamp>",
          show(out, err, rc, w.calls()))

    print("\nzshrc_d_test_passes_on_link")
    w = World(root, "zshrc_d_test")
    w.uv_std()
    w.link(".default_venv-3.13")       # dangling: the CINO's stanza would run `-m venv` and fail
    shell = shutil.which("zsh") or "/bin/sh"
    test = ['[ -d "$HOME/.default_venv" ] && [ -f "$HOME/.default_venv/bin/activate" ]']
    rc0 = subprocess.run([shell, "-f", "-c", test[0]], env={"HOME": str(w.home), "PATH": "/usr/bin:/bin"}).returncode
    out, err, rc = w.run("ensure_default_venv")
    rc1 = subprocess.run([shell, "-f", "-c", test[0]], env={"HOME": str(w.home), "PATH": "/usr/bin:/bin"}).returncode
    check(rc0 != 0 and rc == 0 and rc1 == 0,
          f"{os.path.basename(shell)}: `[ -d ~/.default_venv ]` fails on the dangling link and "
          f"passes on the repaired one", f"before={rc0} after={rc1}\n" + show(out, err, rc))

    print("\nlink_to_older_version_flipped")
    w = World(root, "link_to_older_version_flipped")
    w.uv_std()
    w.venv(".default_venv-3.13", w.other("3.13"), xy="3.13", marker="313")
    w.link(".default_venv-3.13")
    before = sorted(os.listdir(w.home / ".default_venv-3.13"))
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED, "the link now points at -3.14",
          show(out, err, rc, w.calls()))
    check(sorted(os.listdir(w.home / ".default_venv-3.13")) == before,
          "the old directory gains no stray entry (the plain-`mv` trap)",
          str(sorted(os.listdir(w.home / ".default_venv-3.13"))))
    check(not (w.home / ".default_venv.link-new").exists()
          and not (w.home / ".default_venv.link-new").is_symlink(),
          "no .link-new is left behind")

    print("\nabsolute_link_to_sound_314_noop")
    w = World(root, "absolute_link_noop")
    w.uv_std()
    w.venv(VERSIONED, w.std())
    w.link(w.versioned())
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before and not venv_calls(w),
          "an absolute link to a sound -3.14 is left exactly as it is",
          show(out, err, rc, w.calls()))

    print("\nusers_own_link_sound_left_alone")
    w = World(root, "users_own_link_sound")
    w.uv_std()
    mine = make_venv(w.home / "envs" / "work", str(w.std()), style="uv", xy=PREF, marker="MINE")
    w.link(mine)
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before and not venv_calls(w),
          "a sound venv of the person's own is left alone", show(out, err, rc, w.calls()))
    check(str(mine) in out + err, "with a one-line note naming it", out + err)

    print("\nusers_own_link_broken_flipped_named")
    w = World(root, "users_own_link_broken")
    w.uv_std()
    mine = make_venv(w.home / "envs" / "work", str(w.ft()), style="uv", xy=PREF, marker="MINE")
    w.link(mine)
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED and sound_on_std(w),
          "a broken venv of the person's own is replaced by the link flip",
          show(out, err, rc, w.calls()))
    check(marker(mine) == "MINE", "and is never deleted")
    check(str(mine) in err and "free-threaded" in err, "the warning names it and why", err)

    print("\nversion_key_from_python_m_venv")
    w = World(root, "version_key_venv")
    w.uv_std()
    w.venv(".default_venv", w.other("3.12"), style="venv", xy="3.12", marker="M")
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and marker(w.home / ".default_venv-3.12") == "M",
          "`version = 3.12.1` (python -m venv) names the directory -3.12",
          show(out, err, rc, w.calls()))
    w = World(root, "version_key_unknown")
    w.uv_std()
    w.venv(".default_venv", w.other("3.12"), style="venv", xy="3.12", marker="U", cfg_version=False)
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and marker(w.home / ".default_venv-unknown") == "U",
          "no version key names it -unknown", show(out, err, rc, w.calls()))

    print("\nhome_with_space")
    w = World(root, "home_with_space", home="Kurt Home")
    std = w.uv_std()
    w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13", marker="SP")
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED
          and marker(w.home / ".default_venv-3.13") == "SP" and sound_on_std(w),
          "a HOME with a space migrates and links", show(out, err, rc, w.calls()))
    check(" " in str(std) and home_of(w.versioned()) == str(std.parent),
          "a pyvenv.cfg home with a space ('uv python/...') is read whole")
    out, err, rc = w.run(f'venv_rebuild_reason "$HOME/{VERSIONED}" || echo SOUND')
    check(out.strip() == "SOUND", "and is not mistaken for a broken venv", show(out, err, rc))
    cel, _ = w.cellar(w.dir / "home brew")
    make_venv(w.home / "cellar venv", str(cel), style="venv", xy=PREF)
    out, err, rc = w.run('venv_rebuild_reason "$HOME/cellar venv"')
    check(rc == 0 and "Cellar" in out, "a Cellar home under a prefix with a space is still seen",
          show(out, err, rc))

    print("\nvirtual_env_creation_path_matches")
    for label, ve in (("the creation path ~/.default_venv-3.14", VERSIONED),
                      ("~/.default_venv/ with a trailing slash", ".default_venv/")):
        w = World(root, "venv_active_" + re.sub(r"\W", "_", ve))
        w.uv_std()
        w.venv(VERSIONED, w.ft())
        w.link(VERSIONED)
        ledger = w.dir / "todo.tsv"
        out, err, rc = w.run("ensure_default_venv",
                             env={"VIRTUAL_ENV": str(w.home / ve), "CSA_TODO_FILE": str(ledger)})
        got = _text(ledger) if ledger.exists() else ""
        check(rc == 0 and f"10\t{TODO_TERMINAL}" in got and sound_on_std(w),
              f"VIRTUAL_ENV={label}: matched by -ef, rebuilt, to-do added",
              show(out, err, rc) + "\nledger:\n" + got)
    # The link points outside ~/.default_venv-*, so only the -ef against ~/.default_venv itself
    # can see that the trailing-slash spelling is the same directory.
    w = World(root, "venv_active_own_link")
    w.uv_std()
    mine = make_venv(w.home / "envs" / "work", str(w.ft()), style="uv", xy=PREF)
    w.link(mine)
    ledger = w.dir / "todo.tsv"
    out, err, rc = w.run("ensure_default_venv", env={"VIRTUAL_ENV": str(w.default()) + "/",
                                                     "CSA_TODO_FILE": str(ledger)})
    got = _text(ledger) if ledger.exists() else ""
    check(rc == 0 and f"10\t{TODO_TERMINAL}" in got and link_target(w.default()) == VERSIONED,
          "VIRTUAL_ENV=~/.default_venv/ while it links to the person's own venv: still matched",
          show(out, err, rc) + "\nledger:\n" + got)
    w = World(root, "venv_active_other")
    w.uv_std()
    w.venv(VERSIONED, w.ft())
    w.link(VERSIONED)
    other = make_venv(w.dir / "other-venv", str(w.std()), style="uv", xy=PREF)
    ledger = w.dir / "todo.tsv"
    out, err, rc = w.run("ensure_default_venv",
                         env={"VIRTUAL_ENV": str(other), "CSA_TODO_FILE": str(ledger)})
    check(rc == 0 and not ledger.exists(), "an unrelated active venv adds no to-do",
          show(out, err, rc))

    print("\ncinos_mac_state_noop")
    w = World(root, "cinos_mac_state")
    w.uv_std()
    w.venv(VERSIONED, w.std(), marker="314")
    w.venv(".default_venv-3.13", w.other("3.13"), xy="3.13", marker="313")
    (w.home / ".default_venv-3.13" / "pyvenv.cfg").write_text(
        f"home = {w.other('3.13').parent}\nimplementation = CPython\nversion_info = 3.13.1\n",
        encoding="utf-8")
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before and not venv_calls(w) and not installs(w)
          and "WARN" not in err,
          "link to a sound -3.14 plus a real -3.13: nothing changes, nothing is said",
          show(out, err, rc, w.calls()))
    out, err, rc = w.run("ensure_default_venv", env={"VIRTUAL_ENV": str(w.default())})
    check(rc == 0 and w.snapshot() == before and "terminal" not in out + err,
          "and the same while it is active", show(out, err, rc))


# ── repair cases ───────────────────────────────────────────────────────────────────────────────


def repair_cases(root: pathlib.Path) -> None:
    print("\ndangling_interpreter")
    w = World(root, "dangling_interpreter")
    w.uv_std()
    w.venv(VERSIONED, w.dead(), marker="DEAD")
    w.link(VERSIONED)
    out, err, rc = w.run(f'venv_rebuild_reason "$HOME/{VERSIONED}"')
    check(rc == 0 and out.strip() == "its Python no longer exists",
          "a dangling interpreter is BROKEN, never absent", show(out, err, rc))
    out, err, rc = w.run("ensure_default_venv")
    broken = siblings(w, VERSIONED + ".broken-*")
    check(rc == 0 and sound_on_std(w) and len(broken) == 1 and marker(broken[0]) == "DEAD",
          "it is replaced, and the dead one kept aside", show(out, err, rc, w.calls()))

    print("\nvenv_on_315_rebuilt")
    w = World(root, "venv_on_315")
    w.uv_std()
    w.venv(".default_venv", w.other("3.15"), xy="3.15", marker="315")
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and link_target(w.default()) == VERSIONED and sound_on_std(w)
          and marker(w.home / ".default_venv-3.15") == "315",
          "a 3.15 venv (Homebrew's PATH python3) is moved to -3.15 and replaced",
          show(out, err, rc, w.calls()))
    check("it is Python 3.15, not 3.14" in err, "the reason is named", err)

    print("\nvenv_on_313_rebuilt")
    w = World(root, "venv_on_313")
    w.uv_std()
    w.venv(VERSIONED, w.other("3.13"), xy="3.13", marker="313")
    w.link(VERSIONED)
    out, err, rc = w.run("ensure_default_venv")
    broken = siblings(w, VERSIONED + ".broken-*")
    check(rc == 0 and sound_on_std(w) and len(broken) == 1 and marker(broken[0]) == "313",
          "a -3.14 directory holding a 3.13 is replaced", show(out, err, rc, w.calls()))
    check("it is Python 3.13, not 3.14" in err, "the reason is named", err)

    print("\nfreethreaded_venv_rebuilt")
    w = World(root, "freethreaded")
    ft, std = w.ft(), w.std()
    w.uv(find=ft, listing=[entry(ft, "freethreaded")],
         after_find=std, after_listing=[entry(std), entry(ft, "freethreaded")])
    w.venv(VERSIONED, ft, marker="FT")
    w.link(VERSIONED)
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and sound_on_std(w), "a 3.14t venv is rebuilt on the standard build",
          show(out, err, rc, w.calls()))
    check(f"uv python install {PREF}" in w.calls(),
          "with only 3.14t installed, ensure_csa_python installed the standard build",
          "\n".join(w.calls()))
    check("it is the free-threaded build" in err, "the reason is named", err)

    print("\ncellar_with_uv_python_rebuilt")
    w = World(root, "cellar_with_uv")
    w.uv_std()
    cel, _ = w.cellar()
    w.venv(VERSIONED, cel, style="venv", marker="CELLAR")
    w.link(VERSIONED)
    out, err, rc = w.run(f'venv_rebuild_reason "$HOME/{VERSIONED}"')
    check(rc == 0 and out.strip() ==
          "it is built on a Homebrew Cellar path, which the next brew upgrade deletes",
          "a Cellar recorded path is a rebuild reason", show(out, err, rc))
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and sound_on_std(w) and len(siblings(w, VERSIONED + ".broken-*")) == 1,
          "rebuilt onto uv's 3.14", show(out, err, rc, w.calls()))

    print("\ncellar_without_uv_python_warns_only")
    w = World(root, "cellar_without_uv")
    cel, _ = w.cellar()
    w.venv(VERSIONED, cel, style="venv", marker="CELLAR")
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before and not venv_calls(w),
          "no CSA Python to rebuild on: the working Cellar venv is not touched",
          show(out, err, rc, w.calls()))
    check("Cellar" in err and "left as it is" in err, "a warning names the Cellar reason", err)

    print("\nbrew_fallback_stable")
    w = World(root, "brew_fallback_stable")
    w.brew()
    _, opt = w.cellar()
    out, err, rc = w.run("ensure_default_venv")
    v = w.versioned()
    check(rc == 0 and link_target(w.default()) == VERSIONED and v.is_dir()
          and home_of(v) == str(opt.parent),
          "no uv: built with Homebrew's opt/python@3.14 -m venv, recording the opt path",
          show(out, err, rc, w.calls()))
    out, err, rc = w.run(f'venv_rebuild_reason "$HOME/{VERSIONED}" || echo SOUND')
    check(out.strip() == "SOUND",
          "an opt/ recorded path is NOT Cellar-pinned, though its realpath is", show(out, err, rc))
    before, n = w.snapshot(), len(venv_calls(w))
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before and len(venv_calls(w)) == n,
          "so a second run on a Homebrew-fallback machine changes nothing",
          show(out, err, rc, w.calls()))

    print("\nhealthy_314_untouched")
    w = World(root, "healthy_314")
    w.uv_std()
    w.venv(VERSIONED, w.std(), marker="HEALTHY")
    w.link(VERSIONED)
    out, err, rc = w.run("install_doc_python_deps")
    check(rc == 0 and marker(w.versioned()) == "HEALTHY" and not venv_calls(w)
          and not siblings(w, VERSIONED + ".*"),
          "install_doc_python_deps on a healthy venv rebuilds nothing", show(out, err, rc, w.calls()))
    pips = [a for a in w.argvs() if a[:3] == ["uv", "pip", "install"]]
    check(len(pips) == 1 and PIN in pips[0],
          f"and installs the deps once, with {PIN} as one argument", "\n".join(w.calls()))

    print("\nsecond_run_noop")
    w = World(root, "second_run_noop")
    w.uv_std()
    w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13")
    out, err, rc = w.run("ensure_default_venv")
    before, n = w.snapshot(), len(venv_calls(w))
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before and len(venv_calls(w)) == n and "WARN" not in err,
          "a second run after a repair changes nothing", show(out, err, rc, w.calls()))

    print("\nno_csa_python_leaves_venv")
    w = World(root, "no_csa_python")
    ft = w.ft()
    w.uv(find=ft, listing=[entry(ft, "freethreaded")], install_fails=True)
    w.venv(VERSIONED, ft, marker="FT")
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before and not venv_calls(w),
          "offline, with only 3.14t: nothing is moved or rebuilt", show(out, err, rc, w.calls()))
    check("no Python" in err and "left as it is" in err, "and it says so", err)

    print("\nuses_csa_python_not_path_python3")
    w = World(root, "uses_csa_python")
    std = w.uv_std()
    w.path_python("python3", "3.15")
    w.path_python(f"python{PREF}", PREF)
    out, err, rc = w.run("install_doc_python_deps")
    check(rc == 0 and sound_on_std(w), "the venv is built on uv's managed 3.14",
          show(out, err, rc, w.calls()))
    check(not any(c.startswith("pathpy") for c in w.calls()),
          "PATH's python3 / python3.14 are never run", "\n".join(w.calls()))

    print("\nmoved_packages_reported")
    for ledger_on in (False, True):
        w = World(root, f"moved_packages_{ledger_on}")
        w.uv_std()
        w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13",
               dists=("pyyaml", ("requests", ["urllib3>=1.21"]), "urllib3", "mytool", "pip"))
        ledger = w.dir / "todo.tsv"
        env = {"CSA_TODO_FILE": str(ledger)} if ledger_on else {}
        out, err, rc = w.run("ensure_default_venv", env=env)
        got = _text(ledger) if ledger.exists() else ""
        text = got if ledger_on else err
        line = next((l for l in text.splitlines() if "mytool" in l), "")
        check(rc == 0 and "mytool" in line and "requests" in line
              and "urllib3" not in line and "pyyaml" not in line
              and re.search(r"\bpip\b(?! install)", line) is None,
              ("with a ledger, a to-do" if ledger_on else "without one, a warning")
              + " names what the old venv had and the new one lacks (top-level only)",
              show(out, err, rc) + "\nledger:\n" + got)
        if not ledger_on:
            check(".default_venv-3.13" in err, "and where the old venv is", err)

    print("\nactive_venv_flipped_with_todo")
    w = World(root, "active_flipped")
    w.uv_std()
    w.venv(".default_venv-3.13", w.other("3.13"), xy="3.13", marker="313")
    w.link(".default_venv-3.13")
    ledger = w.dir / "todo.tsv"
    out, err, rc = w.run("ensure_default_venv",
                         env={"VIRTUAL_ENV": str(w.default()), "CSA_TODO_FILE": str(ledger)})
    got = _text(ledger) if ledger.exists() else ""
    check(rc == 0 and link_target(w.default()) == VERSIONED,
          "an ACTIVE venv is still flipped (D1)", show(out, err, rc, w.calls()))
    check(marker(w.home / ".default_venv-3.13") == "313",
          "the active shell's real directory did not move")
    check(f"10\t{TODO_TERMINAL}" in got, "the ledger gets the order-10 to-do", got)

    print("\nbuilder_fails_keeps_old")
    w = World(root, "builder_fails_real_dir")
    w.uv_std(venv_fails=True)
    w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13", marker="ORIGINAL")
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before,
          "uv venv fails: the real directory is untouched and no partial -3.14 is left",
          show(out, err, rc, w.calls()))
    w = World(root, "builder_fails_broken_target")
    w.uv_std(venv_fails=True)
    w.venv(VERSIONED, w.ft(), marker="FT")
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before,
          "uv venv fails for the .new-$$ build: the broken -3.14 stays, nothing is left over",
          show(out, err, rc, w.calls()))
    w = World(root, "pip_fails_broken_target")
    w.uv_std(pip_fails=True)
    w.venv(VERSIONED, w.ft(), marker="FT")
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before,
          "uv pip fails for the .new-$$ build: .new-$$ is deleted, the broken -3.14 kept",
          show(out, err, rc, w.calls()))
    check(not any(c.startswith("py-pip") for c in w.calls()),
          "and the .new-$$ build never falls back to the venv's own pip", "\n".join(w.calls()))
    w = World(root, "pyvenv_fails_no_uv")
    w.brew()
    w.cellar()
    w.venv(VERSIONED, w.ft(), marker="FT")
    w.link(VERSIONED)
    (w.scen / "pyvenv.fails").write_text("", encoding="utf-8")
    before = w.snapshot()
    out, err, rc = w.run("ensure_default_venv")
    check(rc == 0 and w.snapshot() == before,
          "no uv, and `python -m venv` fails at the final path: the broken one is put back",
          show(out, err, rc, w.calls()))


def core_present(v: pathlib.Path) -> bool:
    names = {d.name.split("-")[0] for d in v.glob("lib/python*/site-packages/*.dist-info")}
    return {"pyyaml", "pymupdf", "csa"}.issubset(names)


PIN = "pymupdf>=1.24.3,<2"
NEVER = ("onnxruntime", "markitdown", "magika")


def dep_argvs(w: World) -> list[list[str]]:
    """Every install of packages: `uv pip install ...` and `<venv python> -m pip install ...`."""
    return [a for a in w.argvs()
            if a[:3] == ["uv", "pip", "install"] or (a[:1] == ["py-pip"] and "install" in a[4:5])]


def doc_deps_cases(root: pathlib.Path) -> None:
    """pymupdf 2.x requires onnxruntime (Microsoft telemetry on by default) and markitdown pulls it
    in through magika. Every path that installs the document deps passes the pin as ONE argument
    (`<2` unquoted would be a redirection), and nothing installs markitdown or onnxruntime."""
    print("\ndoc_deps_pinned")

    def pinned(w: World, label: str, out: str, err: str, rc: int, want: int = 1) -> None:
        calls = dep_argvs(w)
        check(rc == 0 and len(calls) >= want and all(PIN in a for a in calls),
              f"{label}: every deps install carries {PIN!r} as one argument",
              show(out, err, rc) + "\nargv:\n" + "\n".join(map(json.dumps, w.argvs())))
        check(not any(n in arg.lower() for a in calls for arg in a for n in NEVER),
              f"{label}: no install names onnxruntime, markitdown or magika",
              "\n".join(map(json.dumps, calls)))

    w = World(root, "pin_fresh")
    w.uv_std()
    out, err, rc = w.run("install_doc_python_deps")
    pinned(w, "fresh build (uv venv at the final path, then the caller's refresh)", out, err, rc, 2)
    check(core_present(w.versioned()), "the deps are in it", str(list(w.versioned().glob("lib/*/*/*"))))

    w = World(root, "pin_replacement")
    w.uv_std()
    w.venv(VERSIONED, w.ft())
    w.link(VERSIONED)
    out, err, rc = w.run("ensure_default_venv")
    pinned(w, "the .new-$$ replacement (uv pip only)", out, err, rc)

    w = World(root, "pin_update")
    w.uv_std()
    w.venv(VERSIONED, w.std())
    w.link(VERSIONED)
    out, err, rc = w.run("update_default_venv", script="update")
    pinned(w, "update_default_venv's refresh", out, err, rc)

    w = World(root, "pin_no_uv")
    w.brew()
    w.cellar()
    out, err, rc = w.run("install_doc_python_deps")
    pinned(w, "no uv: python -m venv, then the venv's own pip", out, err, rc, 2)
    check(all(a[0] == "py-pip" for a in dep_argvs(w)), "(through pip, as expected without uv)",
          "\n".join(map(json.dumps, w.argvs())))


# ── the real entry points ──────────────────────────────────────────────────────────────────────


def update_main_harness() -> str:
    """macos-update.sh's own main(), with every step stubbed except the two under test."""
    text = _text(UPD)
    main_src = extract("main", UPD)
    defined = set(re.findall(r"^([a-z_][a-z0-9_]*)\(\) \{", text, re.M))
    body = main_src.split("\n")[1:-1]
    steps = [l.strip() for l in body if l.strip() in defined]
    stubs = [f'{s}() {{ echo "STEP {s}"; }}' for s in steps
             if s not in ("update_default_venv", "update_pip")]
    return "\n".join(['SCRIPT_VERSION="test"', 'confirm() { return 0; }'] + stubs + [main_src])


def entry_point_cases(root: pathlib.Path) -> None:
    print("\nupdate_default_venv_runs_without_outdated_pip")
    w = World(root, "update_main")
    w.uv_std()
    w.path_python("python3", "3.15")        # update_pip's python3: nothing outdated
    w.venv(".default_venv-3.13", w.other("3.13"), xy="3.13")
    w.link(".default_venv-3.13")
    out, err, rc = w.run("main", script="update", override=update_main_harness())
    check(rc == 0 and "All pip packages are up to date" in out,
          "macos-update.sh main() runs, and update_pip returns early (nothing outdated)",
          show(out, err, rc, w.calls()))
    check(link_target(w.default()) == VERSIONED and sound_on_std(w),
          "the venv was repaired anyway: update_default_venv is its own main() step",
          show(out, err, rc, w.calls()))
    steps = extract("main", UPD)
    check(steps.find("update_default_venv") != -1
          and steps.find("update_default_venv") < steps.find("update_pip"),
          "update_default_venv runs before update_pip")
    check("default_venv" not in code_only(extract("update_pip", UPD)),
          "update_pip's unreachable venv block is gone")

    print("\nupdate_never_creates_venv")
    w = World(root, "update_never_creates")
    w.uv_std()
    w.brew()
    w.path_python("python3", "3.15")
    out, err, rc = w.run("main", script="update", override=update_main_harness())
    check(rc == 0 and not list(w.home.glob(".default_venv*")) and not venv_calls(w)
          and not installs(w),
          "no ~/.default_venv: -update creates nothing and installs nothing",
          show(out, err, rc, w.calls()))
    w = World(root, "update_no_install")
    ft = w.ft()
    std = w.std()
    w.uv(find=ft, listing=[entry(ft, "freethreaded")],
         after_find=std, after_listing=[entry(std)])
    w.brew()
    w.venv(VERSIONED, ft, marker="FT")
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("update_default_venv", script="update")
    check(rc == 0 and w.snapshot() == before and not installs(w),
          "a broken venv with only 3.14t installed: -update installs no Python (no "
          "`uv python install`, no brew fallback) and leaves it", show(out, err, rc, w.calls()))

    print("\nupdate_prints_todo_without_ledger")
    w = World(root, "update_todo")
    w.uv_std()
    w.venv(VERSIONED, w.ft())
    w.link(VERSIONED)
    out, err, rc = w.run('if declare -F csa_todo_add >/dev/null; then echo "HAS_LEDGER_FN"; fi\n'
                         "update_default_venv", script="update",
                         env={"VIRTUAL_ENV": str(w.default())})
    check(rc == 0 and "HAS_LEDGER_FN" not in out and TODO_TERMINAL in out + err
          and sound_on_std(w),
          "macos-update.sh has no csa_todo_add; the to-do is printed instead",
          show(out, err, rc, w.calls()))

    print("\nai_tools_prints_todo_when_ledger_unset")
    w = World(root, "ai_todo_unset")
    w.uv_std()
    w.venv(VERSIONED, w.ft())
    w.link(VERSIONED)
    out, err, rc = w.run('if declare -F csa_todo_add >/dev/null; then echo "HAS_LEDGER_FN"; fi\n'
                         "ensure_default_venv", env={"VIRTUAL_ENV": str(w.default())})
    check(rc == 0 and "HAS_LEDGER_FN" in out and TODO_TERMINAL in out + err,
          "csa_todo_add exists but CSA_TODO_FILE is unset: the to-do is printed",
          show(out, err, rc, w.calls()))

    print("\nai_tools_installs_python_once")
    w = World(root, "ai_installs_once")
    w.uv_std()
    out, err, rc = w.run(extract("install_python") + "\nensure_brew_in_path() { :; }\n"
                         "get_version() { echo Python; }\ninstall_python\ninstall_doc_python_deps")
    n = [c for c in w.calls() if c.startswith("uv python install")]
    check(rc == 0 and len(n) == 1 and sound_on_std(w),
          "install_python then install_doc_python_deps: one `uv python install`, not two",
          show(out, err, rc, w.calls()))


def outdated(name: str, ver: str, latest: str) -> dict:
    return {"name": name, "version": ver, "latest_version": latest, "latest_filetype": "wheel"}


OUTDATED = [outdated("PyMuPDF", "1.28.2", "2.1"), outdated("PyYAML", "6.0.2", "6.0.3"),
            outdated("requests", "2.31.0", "2.32.5")]


def upgrades_of(w: World) -> list[str]:
    return [c.split()[-1] for c in w.calls()
            if c.startswith("active-py -m pip install --upgrade") and not c.endswith(" pip")]


def constraints_of(w: World) -> dict[str, str]:
    """package -> the PIP_CONSTRAINT contents its `pip install --upgrade` ran with."""
    calls, out = w.calls(), {}
    for i, c in enumerate(calls[:-1]):
        if c.startswith("active-py -m pip install --upgrade") and calls[i + 1].startswith("constraint "):
            out[c.split()[-1]] = calls[i + 1].split(" file=")[0][len("constraint "):]
    return out


def update_pip_cases(root: pathlib.Path) -> None:
    """`python3 -m pip list --outdated` in ~/.default_venv reports pymupdf 1.28.2 against 2.1 on every
    run, and `pip install --upgrade pymupdf` brings 2.1 back, with onnxruntime. On the CINO's Mac
    ~/.zshrc activates ~/.default_venv, so update_pip would undo the pin on every -update."""
    print("\nupdate_pip_leaves_the_pinned_deps_alone_in_the_csa_venv")
    for label, prefix_of in (("sys.prefix is ~/.default_venv-3.14", lambda w: w.versioned()),
                             ("sys.prefix is ~/.default_venv (the link)", lambda w: w.default())):
        w = World(root, "update_pip_csa_" + re.sub(r"\W", "_", label))
        w.uv_std()
        w.venv(VERSIONED, w.std())
        w.link(VERSIONED)
        w.active_python(prefix_of(w), OUTDATED)
        tmp = w.dir / "tmp"
        tmp.mkdir()
        out, err, rc = w.run("update_pip", script="update",
                             env={"VIRTUAL_ENV": str(w.default()), "TMPDIR": str(tmp)})
        ups = upgrades_of(w)
        check(rc == 0 and "pymupdf" not in [u.lower() for u in ups]
              and "pyyaml" not in [u.lower() for u in ups],
              f"{label}: no `pip install --upgrade` of pymupdf or PyYAML (names compared as pip does)",
              show(out, err, rc, w.calls()))
        check(ups == ["requests"], f"{label}: everything else is still upgraded", str(ups))
        seen = constraints_of(w)
        check(seen.get("requests") == PIN,
              f"{label}: and held to the pin by a PIP_CONSTRAINT file, so no other upgrade "
              "can pull pymupdf 2 back", "\n".join(w.calls()))
        check(not list(tmp.iterdir()), f"{label}: the constraints file (mktemp) is removed",
              str(list(tmp.iterdir())))

    print("\nupdate_pip_preview_agrees")
    w = World(root, "update_pip_preview")
    w.uv_std()
    w.venv(VERSIONED, w.std())
    w.link(VERSIONED)
    w.active_python(w.versioned(), OUTDATED)
    pre = ('ensure_brew_in_path() { :; }\nSNAPSHOT_FILE=/dev/null\n'
           + extract("preflight", UPD))
    out, err, rc = w.run("preflight", script="update", override=pre,
                         env={"VIRTUAL_ENV": str(w.default())})
    block = out[out.find("pip packages"):]
    block = block[:block.find("\n\n")]
    check(rc == 0 and "requests 2.31.0 -> 2.32.5" in block and "PyMuPDF" not in block
          and "PyYAML" not in block,
          "the plan lists what update_pip upgrades: requests, not pymupdf or PyYAML",
          show(out, err, rc))
    check("not upgraded here: pyyaml pymupdf csa-google-workspace" in block,
          "and names the pinned ones it leaves to the Default venv step", block)
    for fn in ("preflight", "update_pip"):
        check("pip_upgrades" in code_only(extract(fn, UPD)),
              f"{fn} reads pip_upgrades (one list for the plan and the run)")

    print("\ncontrol_other_venv_upgrades_everything")
    w = World(root, "update_pip_other_venv")
    w.uv_std()
    w.venv(VERSIONED, w.std())
    w.link(VERSIONED)
    other = make_venv(w.dir / "work-venv", str(w.std()), style="uv", xy=PREF)
    w.active_python(other, OUTDATED)
    out, err, rc = w.run("update_pip", script="update", env={"VIRTUAL_ENV": str(other)})
    ups = upgrades_of(w)
    check(rc == 0 and sorted(u.lower() for u in ups) == ["pymupdf", "pyyaml", "requests"]
          and set(constraints_of(w).values()) == {"<none>"},
          "in a venv that is not ~/.default_venv, everything outdated is upgraded, unconstrained "
          "(so the case above can fail)", show(out, err, rc, w.calls()))


def tool_repair_cases(root: pathlib.Path) -> None:
    print("\ncsa_tool_repairs_lists_freethreaded_tool")
    w = World(root, "tool_repairs")
    tools = w.dir / "uv tools"
    w.uv_std(tooldir=tools)
    make_venv(tools / "csa-zendesk", str(w.ft()), style="uv", xy=PREF)
    cel, _ = w.cellar()
    make_venv(tools / "csa-skilljar", str(cel), style="venv", xy=PREF)
    make_venv(tools / "csa-google-workspace", str(w.dead()), style="uv", xy=PREF)
    make_venv(tools / "csa-google-gmail-calendar", str(w.other("3.15")), style="uv", xy="3.15")
    make_venv(tools / "csa-other", str(w.ft()), style="uv", xy=PREF)   # no setup owns it
    make_venv(tools / "ruff", str(w.ft()), style="uv", xy=PREF)
    before = {p: p.stat().st_mtime_ns for p in tools.rglob("*") if not p.is_symlink()}
    out, err, rc = w.run("csa_tool_repairs")
    want = {"csa-zendesk: it is the free-threaded build",
            "csa-google-workspace: its Python no longer exists",
            "csa-google-gmail-calendar: it is Python 3.15",
            "csa-skilljar: it is on a Homebrew Cellar path"}
    check(rc == 0 and set(out.splitlines()) == want,
          "each broken tool a CSA_INTERNAL_SETUPS entry owns is listed, with its reason",
          show(out, err, rc))
    check("csa-other" not in out and "ruff" not in out,
          "a csa-* tool no listed setup owns is NOT listed (its setup would not rebuild it), "
          "nor is a non-CSA tool", out)
    check(not venv_calls(w) and not installs(w)
          and before == {p: p.stat().st_mtime_ns for p in tools.rglob("*") if not p.is_symlink()},
          "read-only")
    w2 = World(root, "tool_repairs_sound")
    tools2 = w2.dir / "uv tools"
    w2.uv_std(tooldir=tools2)
    make_venv(tools2 / "csa-zendesk", str(w2.std()), style="uv", xy=PREF)
    out, err, rc = w2.run("csa_tool_repairs")
    check(rc == 0 and out == "", "a sound tool is not listed", show(out, err, rc))
    pre = code_only(extract("preflight"))
    check("csa_tool_repairs" in pre, "the Internal MCP servers row lists them")


def plan_cases(root: pathlib.Path) -> None:
    print("\nplan rows name this machine's repair")
    w = World(root, "plan_ft")
    w.uv_std()
    w.venv(VERSIONED, w.ft())
    w.link(VERSIONED)
    before = w.snapshot()
    out, err, rc = w.run("default_venv_plan")
    check(rc == 0 and "rebuild" in out and "free-threaded" in out and w.snapshot() == before
          and not venv_calls(w) and not installs(w),
          "a 3.14t venv: the plan says rebuild, and why, and changes nothing", show(out, err, rc))
    w = World(root, "plan_real_dir")
    w.uv_std()
    w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13")
    out, err, rc = w.run("default_venv_plan")
    check(rc == 0 and ".default_venv-3.13" in out and "3.13" in out,
          "a real 3.13 directory: the plan names where it goes", show(out, err, rc))
    w = World(root, "plan_absent")
    w.uv_std()
    out, err, rc = w.run("default_venv_plan --no-create", script="update")
    check(rc == 0 and "never creates" in out, "-update, nothing there: the plan says it creates none",
          show(out, err, rc))
    pre = code_only(extract("preflight"))
    check(re.search(r'"\s{2}Preflight deps \.+ \$\(default_venv_plan\)"', pre) is not None,
          "macos-ai-tools.sh's Preflight deps row is default_venv_plan")
    pre = code_only(extract("preflight", UPD))
    check(re.search(r'"\s{2}Default venv.*\$\(default_venv_plan --no-create\)', pre) is not None,
          "macos-update.sh's Default venv row is default_venv_plan --no-create")


def layout(w: World) -> dict:
    """What a repair changes: HOME's top-level entries, link targets, and each venv's pyvenv.cfg.
    A deps refresh (site-packages) is not a layout change."""
    out = {}
    for p in sorted(w.home.iterdir()):
        if p.is_symlink():
            out[p.name] = ("L", os.readlink(p))
        else:
            cfg = p / "pyvenv.cfg"
            out[p.name] = ("D", cfg.read_text(encoding="utf-8") if cfg.is_file() else "")
    return out


def dep_installs(w: World) -> list[str]:
    return [c for c in w.calls() if c.startswith("uv pip install")
            or (c.startswith("py-pip") and " install" in c)]


def plan_agreement_cases(root: pathlib.Path) -> None:
    """The plan row is what the person agrees to, so it must name what the run then does: a row
    that says leave/install/refresh/none changes no venv, a row that says build/rebuild/link/move
    changes one, and "nothing is installed" installs nothing. Each scenario runs the plan, then the
    step behind the row (install_doc_python_deps / update_default_venv), and compares."""
    print("\nplan_agrees_with_run")

    def healthy(w):
        w.uv_std()
        w.venv(VERSIONED, w.std())
        w.link(VERSIONED)

    def ft_link(w):
        w.venv(VERSIONED, w.ft())
        w.link(VERSIONED)

    def ft_with_std(w):
        w.uv_std()
        ft_link(w)

    def ft_only(w):                       # the #179 machine: only 3.14t is installed
        ft, std = w.ft(), w.std()
        w.uv(find=ft, listing=[entry(ft, "freethreaded")],
             after_find=std, after_listing=[entry(std)])
        ft_link(w)

    def real313_no_python(w):
        w.uv(listing=[])
        w.venv(".default_venv", w.other("3.13"), style="venv", xy="3.13")

    def real314_no_python(w):
        w.uv(listing=[])
        w.venv(".default_venv", w.std(), style="venv")

    def cellar_only(w):                   # the only Python 3.14 found is on a Cellar path
        cel, _ = w.cellar()
        w.uv(find=cel, listing=[])
        w.venv(VERSIONED, cel, style="venv")
        w.link(VERSIONED)

    def cellar_with_std(w):
        w.uv_std()
        cel, _ = w.cellar()
        w.venv(VERSIONED, cel, style="venv")
        w.link(VERSIONED)

    def absent_std(w):
        w.uv_std()

    def dangling_std(w):
        w.uv_std()
        w.link(".default_venv-3.13")

    def dangling_no_python(w):
        w.uv(listing=[])
        w.link(".default_venv-3.13")

    scenarios = [
        ("healthy", healthy, "ai"), ("healthy", healthy, "update"),
        ("ft_with_std", ft_with_std, "ai"), ("ft_with_std", ft_with_std, "update"),
        ("ft_only", ft_only, "ai"), ("ft_only", ft_only, "update"),
        ("real313_no_python", real313_no_python, "update"),
        ("real314_no_python", real314_no_python, "update"),
        ("cellar_only", cellar_only, "ai"), ("cellar_only", cellar_only, "update"),
        ("cellar_with_std", cellar_with_std, "update"),
        ("absent_std", absent_std, "ai"), ("absent_std", absent_std, "update"),
        ("dangling_std", dangling_std, "update"), ("dangling_no_python", dangling_no_python, "update"),
    ]
    for name, setup, script in scenarios:
        w = World(root, f"plan_agrees_{name}_{script}")
        setup(w)
        plan_call = "default_venv_plan" + (" --no-create" if script == "update" else "")
        plan, perr, prc = w.run(plan_call, script=script)
        plan = plan.strip()
        n_plan_calls = len(w.calls())
        before = layout(w)
        step = "install_doc_python_deps" if script == "ai" else "update_default_venv"
        out, err, rc = w.run(step, script=script)
        w_calls = w.calls()[n_plan_calls:]
        changed = layout(w) != before
        installed = any(c.startswith("uv pip install") or (c.startswith("py-pip") and " install" in c)
                        for c in w_calls)
        says_no_change = plan.startswith(("leave", "install/refresh", "none", "skip"))
        detail = f"plan: {plan}\n" + show(out, err, rc, w_calls)
        check(rc == 0 and prc == 0 and says_no_change == (not changed),
              f"{script} {name}: the plan {'changes nothing' if says_no_change else 'repairs'}"
              f", and so does the run", detail)
        if "nothing is installed" in plan or plan.startswith("none"):
            check(not installed, f"{script} {name}: the plan says nothing is installed; nothing is",
                  detail)
        elif "install/refresh" in plan:
            check(installed, f"{script} {name}: the plan says install/refresh; the run installs",
                  detail)
        if name == "ft_only" and script == "update":
            check("macos-ai-tools.sh" in plan and "rebuild" not in plan,
                  "-update with only 3.14t: the row points at macos-ai-tools.sh, not a rebuild", plan)
        if name == "cellar_only":
            check("Cellar path too" in plan, f"{script}: a Cellar-only Python is named as why", plan)


def static_cases() -> None:
    print("\nwhat the scripts declare")
    for name in SHARED:
        check(re.search(rf"^{name}\(\) \{{", _text(UPD), re.M) is not None,
              f"macos-update.sh carries {name}() (byte-identity: check-duplication.py)")
    for script in (AI, UPD):
        deps = assignment("CSA_DOC_PY_DEPS", script)
        check(f'"{PIN}"' in deps and not any(n in deps for n in NEVER),
              f"{script.name}: CSA_DOC_PY_DEPS pins pymupdf below 2, quoted, and names no "
              "markitdown or onnxruntime", deps)
        check("CSA_DOC_PY_DEPS_OPTIONAL" not in _text(script)
              and "csa_venv_optional_install" not in _text(script),
              f"{script.name}: no best-effort markitdown list or installer is left", "")
    body = code_only(extract("install_doc_python_deps"))
    check("ensure_default_venv" in body and "already available" not in body,
          "install_doc_python_deps goes through ensure_default_venv; no PATH-python3 early return")
    ens = code_only(extract("ensure_default_venv"))
    check(ens.find("find_csa_python") != -1 and ens.find("find_csa_python") < ens.find("ensure_csa_python"),
          "ensure_default_venv tries find_csa_python before ensure_csa_python")
    check("mv -h" in code_only(extract("ensure_default_venv")), "the flip uses `mv -h`")


# ── controls: the cases above must be able to fail ─────────────────────────────────────────────


def controls(root: pathlib.Path) -> None:
    print("\ncontrol_plain_mv_caught")
    w = World(root, "control_plain_mv")
    w.uv_std()
    w.venv(".default_venv-3.13", w.other("3.13"), xy="3.13")
    w.link(".default_venv-3.13")
    mutated = extract("ensure_default_venv").replace("mv -h ", "mv ")
    out, err, rc = w.run("ensure_default_venv", override=mutated)
    stray = sorted(os.listdir(w.home / ".default_venv-3.13"))
    check(link_target(w.default()) == ".default_venv-3.13" and ".default_venv.link-new" in stray,
          "with plain `mv`, the link is unchanged and .link-new lands inside the old target "
          "(so link_to_older_version_flipped can fail)",
          f"link={link_target(w.default())} entries={stray}\n" + show(out, err, rc))


# ── real uv: the replacement's console scripts survive the rename ──────────────────────────────


def _wheel(dirpath: pathlib.Path, name: str, version: str, src: str, script: str) -> None:
    di = f"{name}-{version}.dist-info"
    files = {
        f"{name}/__init__.py": src,
        f"{di}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        f"{di}/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{di}/entry_points.txt": f"[console_scripts]\n{script} = {name}:main\n",
    }
    record = []
    with zipfile.ZipFile(dirpath / f"{name}-{version}-py3-none-any.whl", "w") as z:
        for path, content in files.items():
            data = content.encode()
            z.writestr(path, data)
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            record.append(f"{path},sha256={digest},{len(data)}")
        record.append(f"{di}/RECORD,,")
        z.writestr(f"{di}/RECORD", "\n".join(record) + "\n")


def _real_314() -> str | None:
    probe = PROBE.replace("print(", "print(sys.prefix == sys.base_prefix, ")
    for c in (shutil.which(f"python{PREF}"), f"/opt/homebrew/bin/python{PREF}",
              f"/usr/local/bin/python{PREF}", sys.executable):
        if not c or not os.path.exists(c):
            continue
        p = subprocess.run([c, "-I", "-c", probe], capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.split() == ["True", PREF, "0"]:
            return c
    return None


def real_uv_cases(root: pathlib.Path) -> None:
    print("\nreplaced_target_console_script_runs")
    uv, real = shutil.which("uv"), _real_314()
    if not uv or not real:
        # The macOS CI job sets this, so a runner that lost uv or 3.14 fails instead of passing
        # a check that did not run.
        if os.environ.get("CSA_TEST_REQUIRE_REAL_UV"):
            check(False, f"CSA_TEST_REQUIRE_REAL_UV is set, but there is no real uv and standard "
                         f"{PREF} here (uv={uv}, python={real})")
            return
        print(f"    SKIP  needs a real uv and a real standard {PREF} (uv={uv}, python={real})")
        return

    def attempt(name: str, override: str) -> tuple[World, str, str, int]:
        w = World(root, name)
        (w.bin / "uv").symlink_to(uv)
        wheels = w.dir / "wheels"
        wheels.mkdir()
        _wheel(wheels, "pip", "99.0", "def main():\n    print('pip 99.0 (stub)')\n", "pip")
        _wheel(wheels, "stubdep", "1.0", "def main():\n    print('stubdep 1.0')\n", "stubdep")
        make_venv(w.versioned(), str(w.dead()), style="uv", xy=PREF, marker="DEAD")
        w.link(VERSIONED)
        env = {"UV_CACHE_DIR": str(w.dir / "uv-cache"), "UV_NO_INDEX": "1", "UV_OFFLINE": "1",
               "UV_FIND_LINKS": str(wheels), "UV_PYTHON_DOWNLOADS": "never", "UV_NO_CONFIG": "1"}
        pre = f"find_csa_python() {{ printf '%s\\n' \"{real}\"; }}\nCSA_DOC_PY_DEPS=(stubdep)\n"
        out, err, rc = w.run("ensure_default_venv", env=env, override=pre + override)
        return w, out, err, rc

    def runs(cmd: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"})
        except OSError as e:
            return subprocess.CompletedProcess(cmd, 127, "", str(e))

    w, out, err, rc = attempt("real_uv_replacement", "")
    dep = runs([str(w.default() / "bin" / "stubdep")])
    seed = runs([str(w.default() / "bin" / "pip"), "--version"])
    check(rc == 0 and len(siblings(w, VERSIONED + ".broken-*")) == 1,
          "real uv: the broken -3.14 was replaced, the old one kept", show(out, err, rc))
    check(dep.returncode == 0 and "stubdep 1.0" in dep.stdout,
          "a DEPENDENCY's console script (installed by uv pip into .new-$$) runs after the rename",
          f"rc={dep.returncode}\n{dep.stdout}{dep.stderr}")
    check(seed.returncode == 0, "the seed pip script runs too", f"{seed.stdout}{seed.stderr}")
    act = subprocess.run([BASH, "-c", f'. "{w.default()}/bin/activate" && echo "$VIRTUAL_ENV" '
                          '&& command -v python3'], capture_output=True, text=True,
                         env={"PATH": "/usr/bin:/bin", "HOME": str(w.home)})
    lines = act.stdout.splitlines()
    check(act.returncode == 0 and len(lines) == 2
          and os.path.samefile(lines[0], w.versioned()) and ".new-" not in act.stdout,
          "`activate` names the final directory, not .new-$$", act.stdout + act.stderr)

    print("\ncontrol_no_relocatable_caught")
    mutated = extract("default_venv_build").replace(" --relocatable", "")
    w, out, err, rc = attempt("real_uv_control", mutated)
    dep = runs([str(w.default() / "bin" / "stubdep")])
    check(dep.returncode != 0,
          "without --relocatable the same console script fails after the rename "
          "(so the case above can fail)", f"rc={dep.returncode}\n{dep.stdout}{dep.stderr}")


def main() -> int:
    if os.name == "nt":
        print("SKIP: ~/.default_venv is a POSIX layout (bin/, symlinks); Windows document deps "
              "are #183")
        return 77
    print(f"CSA_PYTHON_PREFERRED declared by the script: {PREF}")
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        layout_cases(root)
        repair_cases(root)
        entry_point_cases(root)
        doc_deps_cases(root)
        update_pip_cases(root)
        tool_repair_cases(root)
        plan_cases(root)
        plan_agreement_cases(root)
        controls(root)
        real_uv_cases(root)
    static_cases()
    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
