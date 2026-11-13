#!/usr/bin/env python3
"""scripts/csa-mcp-registrations.py `plan`: it finds every CSA MCP registration in Claude Code,
Claude Desktop, Codex and Gemini, says what is wrong with each, and writes nothing but its own
plan file (#179, plans/2026-11-12-registration-repair.md Task 1).

What matters most about an auditor that will later drive a repair is what it refuses to
claim: a dead standard binary is never a re-point aimed at itself; a launcher form, an
interpreter-shaping setting or an unknown module is left; a client whose config cannot be read
is "not audited", never "fine"; a failing `codex` is never "no registrations"; and no secret
value reaches the screen or the plan file. Most cases below check one of those.

Every fixture is fake and lives under a fresh `tempfile` directory: a fixture HOME, stub
`codex`/`gemini`/`claude`/`ps`/`uv` first on PATH, and real-shaped interpreter chains (uv's
`cpython-3.14-...` link, Homebrew's `opt/python@3.14 -> ../Cellar/...`, a deleted Cellar
directory). The "interpreters" at the end of those chains are tiny sh scripts that exec the
Python running this test, so a probe of them runs a real interpreter without needing a real
install at a fixture path. Secret values are unique strings this file greps for.

The script is run as a CLI (`python3 -I scripts/csa-mcp-registrations.py plan`), the way the
entry scripts will run it. Cases that change a decision constant (D1, D2, D4, D5) or simulate
Windows import the shipping file with importlib and run its `main()` in process instead.

    python3 tests/test_mcp_registrations.py               # every case
    python3 tests/test_mcp_registrations.py --only NAME   # one case
    python3 tests/test_mcp_registrations.py --self-test   # each planned mutation must be caught

`--self-test` is Task 1 Step 4 kept runnable: each mutation the plan names is applied to a copy
of the script, and the case named for it must then FAIL. A case that passes a broken script is
not testing anything.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = Path(os.environ.get("CSA_TEST_REGISTRATIONS_PY")
              or ROOT / "scripts" / "csa-mcp-registrations.py")

# The spec's table (plan Task 1, Interfaces): canonical name -> (entry point, module). The
# modules are the import path of each server's console-script target in its pyproject.toml.
SPEC = {
    "csa-google-workspace": ("csa-google-workspace-mcp", "csa_google_workspace.mcp"),
    "csa-google-gmail-calendar": ("csa-google-gmail-calendar", "csa_google_gmail_calendar.mcp"),
    "csa-skilljar": ("csa-skilljar-mcp", "csa_skilljar.mcp.cli"),
    "csa-zendesk": ("csa-zendesk-mcp", "csa_zendesk.server"),
}

SECRET_A = "fake-secret-a-7f3a9c1e44d0-not-real"
SECRET_B = "fake-secret-b-2b6e0d9a81f5-not-real"
SECRET_C = "fake-secret-c-90ce13f7aa42-not-real"
SECRETS = (SECRET_A, SECRET_B, SECRET_C)

# Verbatim reasons from the plan. A change to one of these is a change to what the person reads.
R_STANDARD_DEAD = "its standard binary does not run yet; its setup reinstalls it"
R_MISSING = "its command does not exist"
R_NOT_EXEC = "its command is not executable"
R_PY_GONE = "its Python no longer exists"
R_PY_BROKEN = "its Python does not run"
R_MODULE = "its args run a module this does not recognise"
R_DESKTOP_PATH = "not checked: Claude Desktop's PATH is not measured yet"
W_CELLAR = ("it runs from a venv built on a Homebrew Cellar Python, which the next brew "
            "upgrade deletes")
WINDOWS = "not audited: Windows support is #184 (Task 1W)"

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")

INTERPRETER_KEYS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
                    "PYTHONEXECUTABLE", "VIRTUAL_ENV", "CONDA_PREFIX", "UV_PROJECT_ENVIRONMENT")

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


class Failed(Exception):
    pass


def expect(cond, msg):
    if not cond:
        raise Failed(msg)


def load_module():
    spec = importlib.util.spec_from_file_location("csa_mcp_registrations", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def script_line(number):
    """Line `number` of the script under test, or "" when it has no such line."""
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    n = int(number)
    return lines[n - 1] if 0 < n <= len(lines) else ""


def tilde(path, home):
    path = str(path)
    home = str(home)
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def write_exec(path, text, mode=0o755):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)
    return path


def python_ok(path):
    """An "interpreter" that is a real one: it execs the Python running this test."""
    return write_exec(path, f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')


def reg(command, args=None, env=None, **extra):
    entry = {"type": "stdio", "command": str(command), "args": args or [], "env": env or {}}
    entry.update(extra)
    return entry


class Result(object):
    def __init__(self, rc, stdout, stderr, world):
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr
        self.world = world
        lines = [ln.split("\t", 1) for ln in stdout.splitlines() if "\t" in ln]
        self.rows = [t for k, t in lines if k == "row"]
        self.logs = [t for k, t in lines if k == "log"]
        self.plan = None
        self.plan_text = None
        if world.out.exists():
            self.plan_text = world.out.read_text(encoding="utf-8")
            self.plan = json.loads(self.plan_text)

    def ok(self):
        expect(self.rc == 0, f"plan exited {self.rc}: {self.stderr.strip()[-400:]}")
        expect(self.plan is not None, "plan wrote no --out file")

    def findings(self, name=None, client=None, scope=None):
        return [f for f in (self.plan or {}).get("findings", [])
                if (name is None or f["name"] == name)
                and (client is None or f["client"] == client)
                and (scope is None or f["scope"] == scope)]

    def f(self, name, client="Claude Code", scope="user"):
        found = self.findings(name, client, scope)
        expect(len(found) == 1, f"expected one finding for {name} in {client} ({scope}), "
                                f"got {len(found)}; rows: {self.rows}")
        return found[0]

    def rows_with(self, text):
        return [r for r in self.rows if text in r]

    def client_status(self, client):
        for c in (self.plan or {}).get("clients", []):
            if c["client"] == client:
                return c["status"]
        return None

    def count_line(self):
        return self.rows[-1] if self.rows else ""


class World(object):
    """A fixture machine under one temporary directory."""

    def __init__(self, tmp):
        self.tmp = Path(tmp)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.stubs = self.tmp / "stubs"
        self.stubs.mkdir()
        self.apps = self.tmp / "Applications"
        self.apps.mkdir()
        self.tmpdir = self.tmp / "t"
        self.tmpdir.mkdir()
        self.log = self.tmp / "stub.log"
        self.log.write_text("")
        self.out = self.tmp / "out" / "plan.json"
        self.out.parent.mkdir()
        self.extra_env = {}
        self.unset = set()

        # uv's managed Python: a versioned directory and uv's minor-version link to it.
        real = self.tmp / "uvpy" / "cpython-3.14.10-macos-aarch64-none"
        python_ok(real / "bin" / "python3.14")
        (self.tmp / "uvpy" / "cpython-3.14-macos-aarch64-none").symlink_to(
            "cpython-3.14.10-macos-aarch64-none")
        self.uv_home = self.tmp / "uvpy" / "cpython-3.14-macos-aarch64-none" / "bin"
        self.uv_python = self.uv_home / "python3.14"

        # Homebrew: the Cellar keg is a real directory, `opt/` a relative link into it.
        self.cellar_home = self.tmp / "homebrew" / "Cellar" / "python@3.14" / "3.14.0" / "bin"
        python_ok(self.cellar_home / "python3.14")
        self.cellar_python = self.cellar_home / "python3.14"
        (self.tmp / "homebrew" / "opt").mkdir()
        (self.tmp / "homebrew" / "opt" / "python@3.14").symlink_to("../Cellar/python@3.14/3.14.0")
        self.opt_home = self.tmp / "homebrew" / "opt" / "python@3.14" / "bin"
        self.opt_python = self.opt_home / "python3.14"

        # A Cellar keg `brew upgrade` deleted: never created.
        self.gone_home = self.tmp / "homebrew" / "Cellar" / "python@3.13" / "3.13.1" / "bin"
        self.gone_python = self.gone_home / "python3.13"

        self.stub("ps", "exit 0")

    # ── the environment the CLI runs in ──────────────────────────────────────────────────
    def env(self):
        e = {
            "HOME": str(self.home),
            "PATH": f"{self.stubs}:/usr/bin:/bin",
            "LANG": "en_US.UTF-8",
            "TMPDIR": str(self.tmpdir),
        }
        e.update(self.extra_env)
        for k in self.unset:
            e.pop(k, None)
        return e

    def run(self, *args, cwd=None):
        if self.out.exists():
            self.out.unlink()
        cmd = [sys.executable, "-I", str(SCRIPT), "plan", "--out", str(self.out),
               "--system-applications", str(self.apps), *args]
        r = subprocess.run(cmd, env=self.env(), cwd=str(cwd or self.tmp),
                           capture_output=True, text=True, timeout=180)
        return Result(r.returncode, r.stdout, r.stderr, self)

    def run_inproc(self, mod, *args):
        """main() in this process, so a test can change a module constant first."""
        if self.out.exists():
            self.out.unlink()
        saved = dict(os.environ)
        out, err = io.StringIO(), io.StringIO()
        try:
            os.environ.clear()
            os.environ.update(self.env())
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = mod.main(["plan", "--out", str(self.out),
                               "--system-applications", str(self.apps), *args])
        finally:
            os.environ.clear()
            os.environ.update(saved)
        return Result(rc, out.getvalue(), err.getvalue(), self)

    # ── stubs ──────────────────────────────────────────────────────────────────────────────
    def stub(self, name, body):
        return write_exec(self.stubs / name,
                          f'#!/bin/sh\nprintf "%s\\n" "{name} $*" >> "{self.log}"\n{body}\n')

    def stub_log(self):
        return self.log.read_text().splitlines()

    def ps(self, *lines):
        text = "".join(ln + "\n" for ln in lines)
        (self.tmp / "ps.out").write_text(text)
        self.stub("ps", f'cat "{self.tmp / "ps.out"}"')

    # ── interpreters, venvs and entry points ─────────────────────────────────────────────
    def venv(self, venv, python, home, entry=None, sh_exec=False):
        venv = Path(venv)
        (venv / "bin").mkdir(parents=True, exist_ok=True)
        (venv / "pyvenv.cfg").write_text(
            f"home = {home}\ninclude-system-site-packages = false\nversion = 3.14.10\n")
        (venv / "bin" / "python").symlink_to(str(python))
        (venv / "bin" / "python3").symlink_to("python")
        (venv / "bin" / "python3.14").symlink_to("python")
        if entry is None:
            return venv / "bin" / "python"
        if sh_exec:
            head = f"#!/bin/sh\n'''exec' \"{venv}/bin/python\" \"$0\" \"$@\"\n' '''\n"
        else:
            head = f"#!{venv}/bin/python\n"
        return write_exec(venv / "bin" / entry,
                          head + "# -*- coding: utf-8 -*-\nimport sys\nsys.exit(0)\n")

    def std(self, name, python=None, home=None):
        """The standard install: a uv tool venv, linked from ~/.local/bin."""
        entry = SPEC[name][0]
        venv = self.home / ".local" / "share" / "uv" / "tools" / name
        script = self.venv(venv, python or self.uv_python, home or self.uv_home, entry)
        link = self.home / ".local" / "bin" / entry
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(script)
        return link

    def checkout(self, name, python=None, home=None, where=None, sh_exec=False):
        """A developer's source checkout with its own .venv."""
        entry = SPEC[name][0]
        venv = Path(where or self.home / "GitHub" / name) / ".venv"
        return self.venv(venv, python or self.uv_python, home or self.uv_home, entry,
                         sh_exec=sh_exec)

    # ── client configs ───────────────────────────────────────────────────────────────────
    def claude(self, user=None, projects=None, raw=None, at=None):
        path = Path(at or self.home / ".claude.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw is None:
            data = {"numStartups": 3, "theme": "dark"}
            if user is not None:
                data["mcpServers"] = user
            if projects is not None:
                data["projects"] = projects
            raw = json.dumps(data, indent=2)
        path.write_text(raw)
        path.chmod(0o600)
        return path

    def desktop(self, servers=None, raw=None, installed=True, config=True):
        if installed:
            (self.apps / "Claude.app" / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
        path = self.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        if config:
            path.parent.mkdir(parents=True, exist_ok=True)
            if raw is None:
                raw = json.dumps({"mcpServers": servers or {}, "preferences": {"x": 1}}, indent=2)
            path.write_text(raw)
            path.chmod(0o600)
        return path

    def gemini(self, servers=None, raw=None, installed=True, config=True):
        if installed:
            self.stub("gemini", "exit 0")
        path = self.home / ".gemini" / "settings.json"
        if config:
            path.parent.mkdir(parents=True, exist_ok=True)
            if raw is None:
                raw = json.dumps({"mcpServers": servers or {}, "theme": "x"}, indent=2)
            path.write_text(raw)
        return path

    def codex(self, listing=None, rc=0, err="", config=True, raw=None):
        out = raw if raw is not None else json.dumps(listing if listing is not None else [])
        (self.tmp / "codex.out").write_text(out)
        (self.tmp / "codex.err").write_text(err)
        self.stub("codex",
                  f'printf "%s\\n" "codex-cwd $PWD $(ls -A | wc -l | tr -d " ")" >> "{self.log}"\n'
                  f'cat "{self.tmp / "codex.out"}"\n'
                  f'cat "{self.tmp / "codex.err"}" >&2\n'
                  f'exit {rc}')
        path = self.home / ".codex" / "config.toml"
        if config:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# fixture\n")
        return path


@contextlib.contextmanager
def world():
    with tempfile.TemporaryDirectory(prefix="csa-reg-test-") as t:
        # realpath: on macOS the temp dir is under /var, a link to /private/var, and a link in
        # the fixture HOME's own path would make every ~-path comparison below meaningless.
        yield World(os.path.realpath(t))


def snapshot(*roots):
    """Every file and link under the roots: bytes or link target, mode, mtime."""
    snap = {}
    for root in roots:
        root = Path(root)
        if not root.exists() and not root.is_symlink():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            for n in dirnames + filenames:
                p = Path(dirpath) / n
                st = os.lstat(p)
                if stat.S_ISLNK(st.st_mode):
                    snap[str(p)] = ("link", os.readlink(p))
                elif stat.S_ISREG(st.st_mode):
                    snap[str(p)] = ("file", p.read_bytes(), st.st_mode, st.st_mtime_ns)
                else:
                    snap[str(p)] = ("dir", st.st_mode)
    return snap


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Classification
# ═════════════════════════════════════════════════════════════════════════════════════════════

@case
def standard_registration_is_fine():
    with world() as w:
        w.std("csa-zendesk")
        w.std("csa-skilljar")
        uv_tool_path = w.home / ".local/share/uv/tools/csa-skilljar/bin/csa-skilljar-mcp"
        w.claude(user={
            "csa-zendesk": reg("~/.local/bin/csa-zendesk-mcp"),
            "csa-skilljar": reg(uv_tool_path, env={"CSA_SKILLJAR_V2_CLIENT_SECRET": SECRET_A}),
        })
        r = w.run()
        r.ok()
        for name in ("csa-zendesk", "csa-skilljar"):
            f = r.f(name)
            expect(f["state"] == "standard" and f["action"] == "none",
                   f"{name}: {f['state']}/{f['action']}, expected standard/none")
            expect(not r.rows_with(name), f"{name}: a standard registration printed a row")
        expect(r.count_line() == "2 CSA registrations in 1 client; 2 need nothing",
               f"count line: {r.count_line()!r}")


@case
def dead_standard_binary_no_self_repoint():
    with world() as w:
        # The incident before Plan 1's rebuild: the standard binary's own Python is gone.
        w.std("csa-zendesk", python=w.gone_python, home=w.gone_home)
        w.claude(user={"csa-zendesk": reg(w.home / ".local/bin/csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect(f["state"] == "standard", f"state {f['state']}, expected standard")
        expect(f["action"] == "none", f"action {f['action']}: a dead standard binary was "
                                      "given a re-point aimed at itself")
        expect(f["reason"] == R_STANDARD_DEAD, f"reason {f['reason']!r}")
        expect(r.rows_with(R_STANDARD_DEAD), f"no row says {R_STANDARD_DEAD!r}: {r.rows}")
        expect(not r.rows_with("re-pointed"), f"a row offers a re-point: {r.rows}")


@case
def dead_command_missing():
    with world() as w:
        w.std("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "bin" / "csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["reason"], f["action"]) == ("dead", R_MISSING, "re-point"),
               f"{f['state']}/{f['reason']}/{f['action']}")
        rows = r.rows_with("csa-zendesk in Claude Code (user scope)")
        expect(rows and "re-pointed at ~/.local/bin/csa-zendesk-mcp" in rows[0],
               f"row: {rows}")


@case
def dead_command_not_executable():
    with world() as w:
        script = w.checkout("csa-zendesk")
        script.chmod(0o644)
        w.claude(user={"csa-zendesk": reg(script)})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["reason"], f["action"]) == ("dead", R_NOT_EXEC, "re-point"),
               f"{f['state']}/{f['reason']}/{f['action']}")


@case
def dead_shebang_interpreter():
    with world() as w:
        # The incident's second stage: the entry point's shebang names a dangling link.
        script = w.checkout("csa-zendesk", python=w.gone_python, home=w.uv_home)
        w.claude(user={"csa-zendesk": reg(script)})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["reason"], f["action"]) == ("dead", R_PY_GONE, "re-point"),
               f"{f['state']}/{f['reason']}/{f['action']}")


@case
def sh_exec_launcher_shebang_parsed():
    with world() as w:
        live = w.checkout("csa-zendesk", where=w.home / "My Checkouts" / "zd", sh_exec=True)
        dead = w.checkout("csa-skilljar", python=w.gone_python, home=w.uv_home,
                          where=w.home / "My Checkouts" / "sj", sh_exec=True)
        w.claude(user={"csa-zendesk": reg(live), "csa-skilljar": reg(dead)})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect(f["state"] == "elsewhere",
               f"a working '''exec' entry point is {f['state']} ({f['reason']}), not elsewhere: "
               "its interpreter was not parsed")
        f = r.f("csa-skilljar")
        expect((f["state"], f["reason"]) == ("dead", R_PY_GONE),
               f"a dead '''exec' entry point is {f['state']}/{f['reason']}")


@case
def dead_venv_home_missing():
    with world() as w:
        # The CINO's local-scope shape: `home` is a Cellar directory that no longer exists,
        # and bin/python dangles into it.
        a = w.checkout("csa-zendesk", python=w.gone_python, home=w.gone_home)
        # The same with bin/python still resolving: `home` alone being gone is enough.
        b = w.checkout("csa-skilljar", python=w.uv_python, home=w.gone_home)
        w.claude(user={"csa-zendesk": reg(a), "csa-skilljar": reg(b)})
        r = w.run()
        r.ok()
        for name in ("csa-zendesk", "csa-skilljar"):
            f = r.f(name)
            expect((f["state"], f["reason"], f["action"]) == ("dead", R_PY_GONE, "re-point"),
                   f"{name}: {f['state']}/{f['reason']}/{f['action']}")


@case
def python_stdlib_partly_missing():
    with world() as w:
        # The incident's first stage: `import sys` works (it is built in), the stdlib does not.
        partial = write_exec(w.tmp / "partial" / "bin" / "python3.14",
                             f'#!/bin/sh\nprintf "%s\\n" "probe $*" >> "{w.log}"\n'
                             'case "$*" in *importlib.resources*) exit 1;; esac\nexit 0\n')
        script = w.checkout("csa-zendesk", python=partial, home=partial.parent)
        w.claude(user={"csa-zendesk": reg(script)})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["reason"]) == ("dead", R_PY_BROKEN), f"{f['state']}/{f['reason']}")
        probes = [ln for ln in w.stub_log() if ln.startswith("probe ")]
        expect(probes and "-I -B -c" in probes[0]
               and "import json, importlib.resources" in probes[0],
               f"the probe was not `-I -B -c \"import json, importlib.resources\"`: {probes}")


@case
def probe_writes_no_bytecode():
    # The review of fba8c54 found the probe wrote 55 .pyc files into a fresh interpreter's
    # stdlib. Here the interpreter is a private one whose bytecode cache is redirected into a
    # tree of its own (-X pycache_prefix), so any .pyc the probe would write is seen; the
    # control proves that the same interpreter, probed without -B, does write.
    with world() as w:
        probed_pyc, control_pyc = w.tmp / "pyc-probed", w.tmp / "pyc-control"
        probed = write_exec(w.tmp / "private" / "bin" / "python3.14",
                            f'#!/bin/sh\nexec "{sys.executable}" -X pycache_prefix="{probed_pyc}" "$@"\n')
        control = write_exec(w.tmp / "control" / "python3.14",
                             f'#!/bin/sh\nexec "{sys.executable}" -X pycache_prefix="{control_pyc}" "$@"\n')
        subprocess.run([str(control), "-I", "-c", "import json, importlib.resources"],
                       env=w.env(), check=True, timeout=60)
        written = [p for p in control_pyc.rglob("*.pyc")] if control_pyc.exists() else []
        expect(written, "fixture: without -B the private interpreter wrote no bytecode")
        script = w.checkout("csa-zendesk", python=probed, home=probed.parent)
        w.claude(user={"csa-zendesk": reg(script)})
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk")["state"] == "elsewhere", "the private interpreter was not probed")
        left = [str(p) for p in probed_pyc.rglob("*")] if probed_pyc.exists() else []
        expect(not left, f"the probe wrote bytecode: {len(left)} file(s)")


@case
def working_elsewhere_left_and_warned():
    with world() as w:
        mod = load_module()
        expect(mod.REPOINT_WORKING_ELSEWHERE is False, "D1's safe default is (a): leave it")
        script = w.checkout("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(script, env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A})})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        want = (f"it points at {tilde(script, w.home)}, not ~/.local/bin/csa-zendesk-mcp")
        expect((f["state"], f["action"]) == ("elsewhere", "leave"), f"{f['state']}/{f['action']}")
        expect(f["reason"] == want, f"reason {f['reason']!r}, expected {want!r}")
        expect(r.rows_with(want), f"no row warns about it: {r.rows}")
        expect(f["todo"], "a working registration elsewhere gets a to-do")


@case
def cellar_venv_warned():
    with world() as w:
        script = w.checkout("csa-zendesk", python=w.cellar_python, home=w.cellar_home)
        w.claude(user={"csa-zendesk": reg(script)})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect(f["state"] == "elsewhere", f"state {f['state']}")
        expect(W_CELLAR in f["warnings"], f"warnings {f['warnings']}")
        expect(r.rows_with(W_CELLAR), f"no row carries the Cellar warning: {r.rows}")


@case
def homebrew_opt_is_not_cellar():
    with world() as w:
        # The fixture is only worth something if a realpath WOULD land in the Cellar.
        expect("/Cellar/" in os.path.realpath(w.opt_python), "fixture: opt/ must resolve into Cellar")
        script = w.checkout("csa-zendesk", python=w.opt_python, home=w.opt_home)
        w.claude(user={"csa-zendesk": reg(script)})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect(f["state"] == "elsewhere", f"state {f['state']}")
        expect(W_CELLAR not in f["warnings"],
               "a venv on Homebrew's opt/ link was warned about as Cellar-pinned")


@case
def launcher_form_left():
    with world() as w:
        checkout = w.home / "GitHub" / "csa-google-gmail-calendar"
        checkout.mkdir(parents=True)
        # A uv written as a Python console script, the way pip installs pipx or poetry: the
        # shebang parse alone would call it a direct executable.
        write_exec(w.stubs / "uv", f"#!{w.uv_python}\nopen({str(w.log)!r}, 'a').write('uv ran\\n')\n")
        w.stub("uvx", "exit 0")
        write_exec(w.stubs / "npx", f'#!/usr/bin/env node\nrequire("fs").appendFileSync({json.dumps(str(w.log))}, "npx ran\\n")\n')
        w.claude(user={
            "csa-google-gmail-calendar": reg("uv", ["run", "--directory", str(checkout),
                                                    "csa-google-gmail-calendar"]),
            "csa-zendesk": reg("uvx", ["--from", "csa-zendesk[server]", "csa-zendesk-mcp"]),
            "csa-skilljar": reg("npx", ["-y", "csa-skilljar"]),
        })
        before = snapshot(checkout)
        r = w.run()
        r.ok()
        for name, base in (("csa-google-gmail-calendar", "uv"), ("csa-zendesk", "uvx"),
                           ("csa-skilljar", "npx")):
            f = r.f(name)
            want = f"it runs through {base}, which this does not inspect; left as it is"
            expect((f["state"], f["action"]) == ("launcher", "leave"),
                   f"{name}: {f['state']}/{f['action']}")
            expect(f["reason"] == want, f"{name}: reason {f['reason']!r}")
        ran = [ln for ln in w.stub_log() if ln.startswith(("uv", "npx"))]
        expect(not ran, f"a launcher was run: {ran}")
        expect(snapshot(checkout) == before, "the checkout changed")


@case
def interpreter_env_keys_left():
    with world() as w:
        servers = list(SPEC)
        keys = list(INTERPRETER_KEYS)
        for start in range(0, len(keys), len(servers)):
            batch = keys[start:start + len(servers)]
            user = {}
            for name, key in zip(servers, batch):
                user[name] = reg(w.tmp / "gone" / SPEC[name][0], env={key: SECRET_B})
            w.claude(user=user)
            r = w.run()
            r.ok()
            for name, key in zip(servers, batch):
                f = r.f(name)
                want = (f"{name} in Claude Code (user scope) is dead, and its {key} setting "
                        "would point the release binary at another tree; fix it by hand")
                expect((f["state"], f["action"]) == ("dead", "leave"),
                       f"{key}: {f['state']}/{f['action']}")
                expect(f["todo"] == want, f"{key}: to-do {f['todo']!r}")
        # The control: an env that does not shape the interpreter does not block a re-point.
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp",
                                          env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_B})})
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk")["action"] == "re-point", "an ordinary setting blocked a re-point")


@case
def unknown_module_left():
    with world() as w:
        w.claude(user={"csa-zendesk": reg(w.uv_python, ["-m", "csa_zendesk.cli"])})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect(f["action"] == "leave" and f["reason"] == R_MODULE, f"{f['action']}/{f['reason']}")


@case
def desktop_bare_name_unmeasured_left():
    with world() as w:
        mod = load_module()
        expect(mod.DESKTOP_PATH is None, "Desktop's PATH is not measured yet (M2/M3)")
        w.desktop({"csa-google-workspace": reg("csa-google-workspace-mcp"),
                   "csa-zendesk": reg("csa-zendesk-mcp", env={"K": SECRET_A})})
        r = w.run()
        r.ok()
        for name in ("csa-google-workspace", "csa-zendesk"):
            f = r.f(name, "Claude Desktop")
            expect((f["action"], f["reason"]) == ("leave", R_DESKTOP_PATH),
                   f"{name}: {f['action']}/{f['reason']}")


@case
def bare_name_desktop_uses_measured_path():
    # The mechanism for when M3's Desktop PATH is recorded: one constant changes.
    with world() as w:
        mod = load_module()
        measured = w.tmp / "desktop-path"
        measured.mkdir()
        mod.DESKTOP_PATH = f"{measured}:/usr/bin:/bin"
        w.std("csa-zendesk")
        (measured / "csa-zendesk-mcp").symlink_to(w.home / ".local/bin/csa-zendesk-mcp")
        w.desktop({"csa-zendesk": reg("csa-zendesk-mcp"),
                   "csa-skilljar": reg("csa-skilljar-mcp")})
        r = w.run_inproc(mod)
        r.ok()
        f = r.f("csa-zendesk", "Claude Desktop")
        expect(f["state"] == "standard", f"resolves on the measured PATH: {f['state']}")
        f = r.f("csa-skilljar", "Claude Desktop")
        expect((f["state"], f["reason"], f["action"]) == ("dead", R_MISSING, "re-point"),
               f"does not resolve: {f['state']}/{f['reason']}/{f['action']}")


@case
def bare_name_cli_resolves_on_inherited_path():
    # M3: Claude Code, Codex and Gemini hand a server the PATH of the shell that started them.
    with world() as w:
        w.std("csa-zendesk")
        w.extra_env["PATH"] = f"{w.stubs}:{w.home / '.local/bin'}:/usr/bin:/bin"
        w.claude(user={"csa-zendesk": reg("csa-zendesk-mcp"),
                       "csa-skilljar": reg("csa-skilljar-mcp")})
        w.gemini({"csa-zendesk": reg("csa-zendesk-mcp")})
        w.codex([{"name": "csa-skilljar", "transport": {"type": "stdio",
                                                         "command": "csa-skilljar-mcp"}}])
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk")["state"] == "standard", "Claude Code: bare name on PATH")
        expect(r.f("csa-zendesk", "Gemini")["state"] == "standard", "Gemini: bare name on PATH")
        for client in ("Claude Code", "Codex"):
            f = r.f("csa-skilljar", client)
            expect((f["state"], f["reason"], f["action"]) == ("dead", R_MISSING, "re-point"),
                   f"{client}: {f['state']}/{f['reason']}/{f['action']}")


@case
def inherited_interpreter_key_warned():
    # M3: Claude Code and Gemini pass their own inherited env on (PYTHONPATH included); Codex
    # passes an allowlist that holds none of A12's keys.
    with world() as w:
        w.extra_env["PYTHONPATH"] = SECRET_C
        gone = w.tmp / "gone" / "csa-zendesk-mcp"
        w.claude(user={"csa-zendesk": reg(gone)})
        w.gemini({"csa-zendesk": reg(gone)})
        w.codex([{"name": "csa-zendesk", "transport": {"type": "stdio", "command": str(gone)}}])
        r = w.run()
        r.ok()
        for client in ("Claude Code", "Gemini"):
            f = r.f("csa-zendesk", client)
            expect(f["action"] == "re-point", f"{client}: an inherited key blocked a re-point")
            expect(any("PYTHONPATH" in x for x in f["warnings"]), f"{client}: {f['warnings']}")
        f = r.f("csa-zendesk", "Codex")
        expect(not any("PYTHONPATH" in x for x in f["warnings"]), f"Codex: {f['warnings']}")
        expect(SECRET_C not in r.stdout + r.stderr + (r.plan_text or ""), "the value was printed")


@case
def desktop_running_skipped_with_quit_todo():
    with world() as w:
        mod = load_module()
        expect(mod.WRITE_DESKTOP_WHILE_RUNNING is False, "D4's safe default is (b)")
        w.ps("/usr/sbin/cfprefsd", "/Applications/Claude.app/Contents/MacOS/Claude")
        w.desktop({"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk", "Claude Desktop")
        want = ("Claude Desktop is running; csa-zendesk will not be re-pointed there this run "
                "— quit it and run again")
        expect(f["action"] == "leave", f"action {f['action']}")
        expect(f["todo"] == "Quit Claude Desktop and run again", f"to-do {f['todo']!r}")
        expect(r.rows_with(want), f"no row says {want!r}: {r.rows}")
    with world() as w:
        # The same under ~/Applications.
        w.ps(str(w.home / "Applications/Claude.app/Contents/MacOS/Claude"))
        w.desktop({"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk", "Claude Desktop")["action"] == "leave", "~/Applications Desktop")
    with world() as w:
        # `ps` fails: not known to be quit, so not written, and the row does not claim it runs.
        w.stub("ps", "exit 1")
        w.desktop({"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk", "Claude Desktop")
        expect(f["action"] == "leave", f"a failing ps was read as 'not running': {f['action']}")
        expect(r.rows_with("could not tell whether Claude Desktop is running"), f"rows: {r.rows}")
    with world() as w:
        # Running, but nothing would be re-pointed: no row.
        w.std("csa-zendesk")
        w.ps("/Applications/Claude.app/Contents/MacOS/Claude")
        w.desktop({"csa-zendesk": reg(w.home / ".local/bin/csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        expect(not r.rows_with("Claude Desktop is running"), f"a needless row: {r.rows}")


@case
def desktop_detected_by_path_not_name():
    with world() as w:
        w.ps("Claude", "claude", "/opt/other/Claude",
             "/Applications/Claude.app/Contents/MacOS/Claude Helper",
             "/Applications/Claude.app/Contents/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper",
             str(w.home / ".local/share/claude/versions/2.1.323"),
             "claude.exe.old.1790878548618.45752")
        w.desktop({"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk", "Claude Desktop")
        expect(f["action"] == "re-point",
               f"a look-alike process counted as Claude Desktop: {f['action']} ({r.rows})")
        expect(any(ln.startswith("ps -axo comm=") for ln in w.stub_log()),
               f"ps was not run as `ps -axo comm=`: {w.stub_log()}")


@case
def local_scope_found_and_reported():
    with world() as w:
        proj = w.home / "work" / "proj"
        proj.mkdir(parents=True)
        script = w.checkout("csa-zendesk")
        w.claude(user={}, projects={str(proj): {"mcpServers": {"csa-zendesk": reg(script)}}})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk", scope="local")
        expect(f["project"] == str(proj), f"project {f['project']!r}")
        label = f"csa-zendesk in Claude Code (local scope, {tilde(proj, w.home)})"
        expect(r.rows_with(label), f"no row names {label!r}: {r.rows}")


@case
def dead_local_scope_todo_names_rebuild_or_remove():
    with world() as w:
        mod = load_module()
        expect(mod.LOCAL_SCOPE_ACTION == "todo", "D2's safe default is (d)")
        proj = w.home / "GitHub" / "csa-zendesk"
        script = w.checkout("csa-zendesk", python=w.gone_python, home=w.gone_home, where=proj)
        w.claude(user={}, projects={str(proj): {"mcpServers": {
            "csa-zendesk": reg(script, env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A})}}})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk", scope="local")
        expect((f["state"], f["action"]) == ("dead", "leave"), f"{f['state']}/{f['action']}")
        todo = f["todo"] or ""
        for part in ("rebuild that checkout's venv", "remove the local entry",
                     "CSA_ZD_ALLOWLIST_WRITE"):
            expect(part in todo, f"to-do lacks {part!r}: {todo!r}")
        expect(SECRET_A not in r.stdout + (r.plan_text or ""), "the setting's value was printed")


@case
def local_scope_action_values():
    for value, action, needle in (("report", "leave", "by hand"),
                                  ("todo", "leave", "rebuild that checkout's venv"),
                                  ("repoint", "re-point", None)):
        with world() as w:
            mod = load_module()
            mod.LOCAL_SCOPE_ACTION = value
            proj = w.home / "p"
            proj.mkdir()
            w.claude(user={}, projects={str(proj): {"mcpServers": {
                "csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")}}})
            r = w.run_inproc(mod)
            r.ok()
            f = r.f("csa-zendesk", scope="local")
            expect(f["action"] == action, f"{value}: action {f['action']}")
            if needle:
                expect(needle in (f["todo"] or ""), f"{value}: to-do {f['todo']!r}")


@case
def local_scope_missing_project_skipped():
    with world() as w:
        gone = w.home / "deleted-project"
        w.claude(user={}, projects={str(gone): {"mcpServers": {
            "csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")}}})
        r = w.run()
        r.ok()
        expect(not r.findings("csa-zendesk"), "a project that no longer exists was audited")
        expect(not r.rows_with("deleted-project"), f"it was shown: {r.rows}")
        expect(any("deleted-project" in ln for ln in r.logs), f"it was not logged: {r.logs}")


@case
def interpreter_module_form_repairable():
    with world() as w:
        # bin/python still resolves; the venv's `home` is gone. (A dangling bin/python is
        # "its command does not exist": the command itself is checked first.)
        dead_venv = w.venv(w.home / "old" / ".venv", w.uv_python, w.gone_home)
        w.claude(user={
            "csa-zendesk": reg(w.tmp / "gone" / "python3", ["-m", "csa_zendesk.server"]),
            "csa-skilljar": reg(dead_venv, ["-m", "csa_skilljar.mcp.cli"]),
            "csa-google-workspace": reg(w.uv_python, ["-m", "csa_google_workspace.mcp"]),
        })
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["action"]) == ("dead", "re-point"), f"missing python -m: "
                                                                   f"{f['state']}/{f['action']}")
        f = r.f("csa-skilljar")
        expect((f["state"], f["reason"], f["action"]) == ("dead", R_PY_GONE, "re-point"),
               f"dead venv python -m: {f['state']}/{f['reason']}/{f['action']}")
        f = r.f("csa-google-workspace")
        expect(f["state"] == "elsewhere", f"a working python -m <its module> is {f['state']}")


@case
def other_args_not_repairable():
    with world() as w:
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp", ["--profile", "x"])})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["action"]) == ("dead", "leave"), f"{f['state']}/{f['action']}")
        expect("args" in (f["todo"] or ""), f"to-do {f['todo']!r}")


@case
def relative_command_not_checked():
    # Where a relative path points depends on the directory the client starts in, which this
    # cannot know, so it is never called dead.
    with world() as w:
        w.claude(user={"csa-zendesk": reg("bin/csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["action"]) == ("unchecked", "leave"), f"{f['state']}/{f['action']}")


@case
def symlinked_config_refused():
    with world() as w:
        real = w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")},
                        at=w.tmp / "dotfiles" / "claude.json")
        (w.home / ".claude.json").symlink_to(real)
        before = snapshot(w.home, real.parent)
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        want = f"its config is a link to {real}; not changed — edit it there"
        expect(f["action"] == "leave", f"action {f['action']}")
        expect(r.rows_with(want), f"no row says {want!r}: {r.rows}")
        expect(snapshot(w.home, real.parent) == before, "the link or its target changed")


@case
def linked_parent_dir_refused():
    # A10 reaches every directory between the config and HOME, not just the last component:
    # `~/.gemini` linked into a dotfiles repository must not be written through.
    with world() as w:
        dots = w.tmp / "dotfiles"
        gone = w.tmp / "gone" / "csa-zendesk-mcp"
        (dots / "gemini").mkdir(parents=True)
        (dots / "gemini" / "settings.json").write_text(json.dumps({"mcpServers": {
            "csa-zendesk": reg(gone)}}))
        (w.home / ".gemini").symlink_to(dots / "gemini")
        w.stub("gemini", "exit 0")
        (dots / "claude").mkdir()
        w.claude(user={"csa-zendesk": reg(gone)}, at=dots / "claude" / ".claude.json")
        (w.tmp / "cc-link").symlink_to(dots / "claude")
        w.extra_env["CLAUDE_CONFIG_DIR"] = str(w.tmp / "cc-link")
        (dots / "desktop").mkdir()
        (w.home / "Library" / "Application Support").mkdir(parents=True)
        (w.home / "Library" / "Application Support" / "Claude").symlink_to(dots / "desktop")
        w.desktop({"csa-zendesk": reg(gone)})
        before = snapshot(dots)
        r = w.run()
        r.ok()
        for client, real in (("Gemini", dots / "gemini" / "settings.json"),
                             ("Claude Code", dots / "claude" / ".claude.json"),
                             ("Claude Desktop", dots / "desktop" / "claude_desktop_config.json")):
            f = r.f("csa-zendesk", client)
            expect(f["config_is_link"] is True, f"{client}: a linked directory read as no link")
            expect(f["action"] == "leave", f"{client}: {f['action']} through a linked directory")
            want = f"its config is a link to {real}; not changed — edit it there"
            expect(r.rows_with(want), f"{client}: no row says {want!r}: {r.rows}")
        expect(snapshot(dots) == before, "the dotfiles directory changed")
    with world() as w:
        # The control: a HOME that is itself a link (a home on another volume) is the
        # machine's, and a config inside it is not "linked".
        (w.tmp / "home-link").symlink_to(w.home)
        w.extra_env["HOME"] = str(w.tmp / "home-link")
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect(f["config_is_link"] is False and f["action"] == "re-point",
               f"a linked HOME made its config a link: {f['config_is_link']}/{f['action']}")


@case
def hostile_input_contained():
    # Whatever one client's config holds, only THAT client is "not audited" (B9); the run
    # still exits 0 and the other clients are audited.
    with world() as w:
        gone = str(w.tmp / "gone" / "csa-zendesk-mcp")
        w.claude(user={"csa-zendesk": reg(gone)})
        w.gemini({"csa-zendesk": reg("/x\u0000y")})
        w.desktop(raw='{"mcpServers": {}, "deep": ' + "[" * 100000 + "]" * 100000 + "}")
        w.codex(raw='{"csa-zendesk": ' + "[" * 100000 + "]" * 100000 + "}")
        r = w.run()
        r.ok()
        for client in ("Gemini", "Claude Desktop", "Codex"):
            expect((r.client_status(client) or "").startswith("not audited: "),
                   f"{client}: {r.client_status(client)!r}")
        expect("nested too deeply" in (r.client_status("Claude Desktop") or ""),
               f"Desktop: {r.client_status('Claude Desktop')!r}")
        expect(r.f("csa-zendesk")["action"] == "re-point", "Claude Code was not audited")


@case
def client_failure_contained():
    # An unexpected failure classifying one client's registrations is reported against that
    # client, with this script's line - not a stdlib frame's, nor the test's - and no message.
    with world() as w:
        mod = load_module()

        def boom(*a, **k):
            raise RuntimeError(f"deliberate {SECRET_A}")

        mod.classify = boom
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        w.gemini({})
        r = w.run_inproc(mod)
        r.ok()
        status = r.client_status("Claude Code") or ""
        m = re.search(r"RuntimeError at line (\d+)", status)
        expect(status.startswith("not audited: ") and m, f"Claude Code: {status!r}")
        line = script_line(m.group(1))
        expect("classify(reg, ctx)" in line, f"line {m.group(1)} is not the script's own: {line!r}")
        expect(r.client_status("Gemini") == "ok", f"Gemini: {r.client_status('Gemini')!r}")
        expect(SECRET_A not in r.stdout + r.stderr + (r.plan_text or ""), "the message was printed")


@case
def control_chars_cannot_forge_rows():
    with world() as w:
        proj = w.home / "evil\nrow\tFORGED-PROJECT"
        proj.mkdir()
        gone_proj = w.home / "gone\nrow\tFORGED-LOG"
        key = "K\nrow\tFORGED-KEY"
        gone = w.tmp / "gone" / "csa-zendesk-mcp"
        w.claude(user={"csa-zendesk": reg(gone, env={key: SECRET_A})},
                 projects={str(proj): {"mcpServers": {"csa-zendesk": reg(gone, env={key: "v"})}},
                           str(gone_proj): {"mcpServers": {"csa-skilljar": reg(gone)}}})
        r = w.run()
        r.ok()
        for line in r.stdout.splitlines():
            expect(line.startswith(("row\t", "log\t")), f"a stray line: {line!r}")
            expect(not line.split("\t", 1)[1].startswith("FORGED"), f"a forged line: {line!r}")
        for f in r.plan["findings"]:
            for field in ("reason", "todo"):
                expect(not CONTROL.search(f[field] or ""), f"{field} holds a control character")
            expect(not any(CONTROL.search(x) for x in f["warnings"]), "a warning does")
        expect(len(r.rows_with("FORGED-PROJECT")) >= 1, "the project's row is missing")


@case
def stdout_closed_writes_no_plan():
    with world() as w:
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        cmd = [sys.executable, "-I", str(SCRIPT), "plan", "--out", str(w.out),
               "--system-applications", str(w.apps)]
        # Started with fd 1 closed.
        p = subprocess.run(cmd, env=w.env(), cwd=str(w.tmp), stderr=subprocess.PIPE,
                           preexec_fn=lambda: os.close(1), timeout=180)
        expect(p.returncode == 2, f"closed stdout: exit {p.returncode}")
        expect(not w.out.exists(), "closed stdout: the plan file was left")
        # A reader that has gone away.
        p = subprocess.Popen(cmd, env=w.env(), cwd=str(w.tmp), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)
        p.stdout.close()
        _, err = p.communicate(timeout=180)
        expect(p.returncode == 2, f"broken pipe: exit {p.returncode}: {err[-300:]!r}")
        expect(not w.out.exists(), "broken pipe: the plan file was left")


@case
def bom_has_its_own_reason():
    with world() as w:
        w.claude(raw="﻿" + json.dumps({"mcpServers": {}}))
        r = w.run()
        r.ok()
        status = r.client_status("Claude Code") or ""
        expect(status.startswith("not audited: ") and "byte-order mark" in status,
               f"status {status!r}")


@case
def http_registration_not_audited():
    with world() as w:
        w.claude(user={"csa-zendesk": {"type": "http", "url": "https://example.invalid/mcp"}})
        w.gemini({"csa-skilljar": {"httpUrl": "https://example.invalid/mcp"}})
        r = w.run()
        r.ok()
        for name, client in (("csa-zendesk", "Claude Code"), ("csa-skilljar", "Gemini")):
            f = r.f(name, client)
            expect((f["state"], f["action"]) == ("not-audited", "leave"),
                   f"{client}: {f['state']}/{f['action']}")
            expect(r.rows_with(f"{name} in {client}"), f"{client}: no row")


@case
def client_absent_not_installed():
    with world() as w:
        r = w.run()
        r.ok()
        for client in ("Claude Code", "Claude Desktop", "Codex", "Gemini"):
            expect(r.client_status(client) == "not installed",
                   f"{client}: status {r.client_status(client)!r}")
            expect(r.rows_with(f"{client}: not installed"), f"{client}: no row")
        expect(not r.findings(), "findings from clients that are not installed")
        expect(r.count_line().startswith("0 CSA registrations"), r.count_line())


@case
def desktop_config_dir_absent():
    with world() as w:
        w.desktop(config=False)
        w.codex(config=False)
        w.gemini(config=False)
        w.stub("claude", "exit 0")
        r = w.run()
        r.ok()
        for client in ("Claude Code", "Claude Desktop", "Codex", "Gemini"):
            expect(r.client_status(client) == "no config yet", f"{client}: "
                                                                f"{r.client_status(client)!r}")
            expect(r.rows_with(f"{client}: no config yet (#156)"), f"{client}: no row")
        expect(not any(ln.startswith("codex ") for ln in w.stub_log()),
               "codex was run with no config to read")


@case
def torn_claude_json_untouched():
    with world() as w:
        good = json.dumps({"mcpServers": {"csa-zendesk": reg("/x/csa-zendesk-mcp")}}, indent=2)
        path = w.claude(raw=good[: len(good) // 2])
        before = path.read_bytes()
        r = w.run()
        r.ok()
        expect((r.client_status("Claude Code") or "").startswith("not audited: "),
               f"status {r.client_status('Claude Code')!r}")
        expect(r.rows_with("Claude Code: not audited: "), f"no row: {r.rows}")
        expect(not r.findings(client="Claude Code"), "a torn config yielded findings")
        expect(path.read_bytes() == before, "the torn config was changed")


@case
def duplicate_key_is_unreadable():
    with world() as w:
        entry = json.dumps(reg(w.tmp / "gone" / "csa-zendesk-mcp"))
        raw = '{"mcpServers": {"csa-zendesk": %s, "csa-zendesk": %s}}' % (entry, entry)
        path = w.claude(raw=raw)
        r = w.run()
        r.ok()
        expect((r.client_status("Claude Code") or "").startswith("not audited: "),
               f"status {r.client_status('Claude Code')!r}")
        expect(not r.findings(client="Claude Code"), "a duplicate key yielded findings")
        expect(path.read_text() == raw, "the config was changed")


@case
def jsonc_gemini_not_audited():
    with world() as w:
        raw = '{\n  // my servers\n  "mcpServers": {}\n}\n'
        path = w.gemini(raw=raw)
        r = w.run()
        r.ok()
        expect((r.client_status("Gemini") or "").startswith("not audited: "),
               f"status {r.client_status('Gemini')!r}")
        expect(r.rows_with("Gemini: not audited: "), f"no row: {r.rows}")
        expect(path.read_text() == raw, "the settings were changed")


# ── Codex ───────────────────────────────────────────────────────────────────────────────────

@case
def codex_json_unsupported_not_audited():
    with world() as w:
        w.codex(raw="", rc=2, err="error: unexpected argument '--json' found\n")
        r = w.run()
        r.ok()
        status = r.client_status("Codex") or ""
        expect(status.startswith("not audited: ") and "--json" in status, f"status {status!r}")


@case
def codex_list_failure_is_not_absence():
    with world() as w:
        w.codex(raw="", rc=1, err=f"failed to load config: {SECRET_A}\n")
        r = w.run()
        r.ok()
        status = r.client_status("Codex") or ""
        expect(status.startswith("not audited: "), f"a failing codex read as {status!r}")
        expect(r.rows_with("Codex: not audited: "), f"no row: {r.rows}")
        expect(SECRET_A not in r.stdout + r.stderr + (r.plan_text or ""),
               "codex's stderr was echoed")


@case
def codex_json_shapes():
    with world() as w:
        w.std("csa-skilljar")
        gone = str(w.tmp / "gone" / "csa-zendesk-mcp")
        nested = [{"name": "csa-zendesk", "enabled": True, "disabled_reason": None,
                   "startup_timeout_sec": 30, "tool_timeout_sec": None, "auth_status": None,
                   "transport": {"type": "stdio", "command": gone, "args": [],
                                 "env": {"CSA_ZD_ALLOWLIST_WRITE": SECRET_A},
                                 "env_vars": ["HOME"], "cwd": None}},
                  {"name": "csa-google-workspace",
                   "transport": {"type": "streamable_http", "url": "https://example.invalid"}},
                  {"name": "not-csa", "transport": {"type": "stdio", "command": "/x"}}]
        w.codex(nested)
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk", "Codex")
        expect((f["state"], f["action"]) == ("dead", "re-point"), f"list/nested: {f['state']}")
        expect(r.f("csa-google-workspace", "Codex")["state"] == "not-audited", "http in Codex")
        expect(not r.findings("not-csa"), "a non-CSA server was audited")

        flat = {"csa-skilljar": {"command": str(w.home / ".local/bin/csa-skilljar-mcp"),
                                 "args": None, "env": None, "startup_timeout_sec": 10}}
        w.codex(flat)
        r = w.run()
        r.ok()
        expect(r.f("csa-skilljar", "Codex")["state"] == "standard", "dict/flat")

        w.codex([{"name": "csa-zendesk", "transport": {"type": "stdio", "command": 7}}])
        r = w.run()
        r.ok()
        expect((r.client_status("Codex") or "").startswith("not audited: "),
               f"a malformed entry: {r.client_status('Codex')!r}")

        w.codex(raw="this is not json")
        r = w.run()
        r.ok()
        expect((r.client_status("Codex") or "").startswith("not audited: "),
               f"non-JSON output: {r.client_status('Codex')!r}")


@case
def codex_home_respected():
    with world() as w:
        codex_home = w.tmp / "codex-home"
        codex_home.mkdir()
        (codex_home / "config.toml").write_text("# fixture\n")
        w.codex([])
        (w.home / ".codex" / "config.toml").unlink()
        w.extra_env["CODEX_HOME"] = str(codex_home)
        r = w.run()
        r.ok()
        expect(r.client_status("Codex") == "ok",
               f"CODEX_HOME's config was not found: {r.client_status('Codex')!r}")
        expect(any(ln.startswith("codex mcp list") for ln in w.stub_log()), "codex was not run")
    with world() as w:
        # And the other way round: ~/.codex has a config, CODEX_HOME does not.
        w.codex([])
        empty = w.tmp / "codex-home-empty"
        empty.mkdir()
        w.extra_env["CODEX_HOME"] = str(empty)
        r = w.run()
        r.ok()
        expect(r.client_status("Codex") == "no config yet",
               f"~/.codex was read instead of CODEX_HOME: {r.client_status('Codex')!r}")


@case
def codex_timeout_kills_its_group():
    # S2: on a timeout the whole process group dies. An npm `codex` is a Node wrapper around a
    # native child, and killing only the wrapper left the child running (measurements).
    with world() as w:
        mod = load_module()
        mod.CLIENT_TIMEOUT = 2
        pidfile = w.tmp / "grandchild.pid"
        w.codex([])
        w.stub("codex", f'sleep 30 >/dev/null 2>&1 &\necho $! > "{pidfile}"\n'
                        "exec sleep 25 >/dev/null 2>&1")
        pid, alive = None, False
        try:
            r = w.run_inproc(mod)
            r.ok()
            status = r.client_status("Codex") or ""
            expect(status.startswith("not audited: ") and "within 2s" in status,
                   f"status {status!r}")
            pid = int(pidfile.read_text().strip())
            alive, deadline = True, time.time() + 5
            while alive and time.time() < deadline:
                try:
                    os.kill(pid, 0)
                    time.sleep(0.1)
                except ProcessLookupError:
                    alive = False
            expect(not alive, "codex's child survived the timeout: only the wrapper was killed")
        finally:
            if pid is not None and alive:  # bounded: never leave the survivor running
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass


@case
def client_reads_run_in_empty_dir():
    with world() as w:
        busy = w.tmp / "busy"
        (busy / ".codex").mkdir(parents=True)
        (busy / ".codex" / "config.toml").write_text("[mcp_servers.csa-zendesk]\n")
        w.codex([])
        r = w.run(cwd=busy)
        r.ok()
        runs = [ln.split() for ln in w.stub_log() if ln.startswith("codex-cwd ")]
        expect(len(runs) == 1, f"codex runs: {runs}")
        _, cwd, entries = runs[0]
        expect(cwd != str(busy) and os.path.realpath(cwd) != os.path.realpath(busy),
               "codex ran in the caller's directory")
        expect(entries == "0", f"codex's directory was not empty: {entries} entries")
        expect(not os.path.exists(cwd), "the empty directory was left behind")
        expect(any(ln.startswith("codex mcp list --json") for ln in w.stub_log()),
               f"not `codex mcp list --json`: {w.stub_log()}")


@case
def claude_config_dir_respected():
    with world() as w:
        ccdir = w.tmp / "ccdir"
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")},
                 at=ccdir / ".claude.json")
        w.claude(user={"csa-skilljar": reg(w.tmp / "gone" / "csa-skilljar-mcp")})
        w.extra_env["CLAUDE_CONFIG_DIR"] = str(ccdir)
        r = w.run()
        r.ok()
        expect(r.findings("csa-zendesk", "Claude Code"), "CLAUDE_CONFIG_DIR's config was not read")
        expect(not r.findings("csa-skilljar", "Claude Code"), "~/.claude.json was read instead")


# ── What it prints, what it writes, what it never touches ──────────────────────────────────

@case
def plan_file_has_no_values():
    with world() as w:
        gone = w.tmp / "gone" / "csa-zendesk-mcp"
        env = {"CSA_ZD_ALLOWLIST_WRITE": SECRET_A, "CSA_ZENDESK_TOKEN_FILE": SECRET_B}
        w.claude(user={"csa-zendesk": reg(gone, env=env)})
        w.desktop({"csa-zendesk": reg(gone, env={"CSA_SKILLJAR_V1_API_KEY": SECRET_C})})
        # Args can carry a secret too (`--api-key …`): only the fingerprint covers them.
        w.gemini({"csa-zendesk": reg(gone, ["--api-key", SECRET_C], env={"K": SECRET_A})})
        w.codex([{"name": "csa-zendesk", "transport": {"type": "stdio", "command": str(gone),
                                                        "env": {"K": SECRET_B}}}])
        r = w.run()
        r.ok()
        expect(not any("args" in f for f in r.plan["findings"]), "the plan file records args")
        for s in SECRETS:
            for where, text in (("stdout", r.stdout), ("stderr", r.stderr),
                                ("plan file", r.plan_text)):
                expect(s not in text, f"a secret value reached the {where}")
        mode = stat.S_IMODE(os.stat(w.out).st_mode)
        expect(mode == 0o600, f"plan file mode {oct(mode)}")
        f = r.f("csa-zendesk")
        blob = json.dumps([str(gone), [], sorted(env)], separators=(",", ":"), ensure_ascii=False)
        expect(f["fingerprint"] == hashlib.sha256(blob.encode("utf-8")).hexdigest(),
               "the fingerprint is not sha256 of command, args and sorted key names")
        expect(f["env_keys"] == sorted(env), f"env_keys {f['env_keys']}")
        first = f["fingerprint"]
        w.claude(user={"csa-zendesk": reg(gone, env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_C,
                                                     "CSA_ZENDESK_TOKEN_FILE": SECRET_A})})
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk")["fingerprint"] == first, "a changed VALUE changed the fingerprint")
        w.claude(user={"csa-zendesk": reg(gone, env={"OTHER": SECRET_A})})
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk")["fingerprint"] != first, "a changed KEY kept the fingerprint")


@case
def token_keys_recorded():
    # M0: a registration env can move a server's token. The plan shows which keys do, by name.
    with world() as w:
        w.std("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(w.home / ".local/bin/csa-zendesk-mcp",
                                          env={"CSA_ZENDESK_TOKEN_FILE": SECRET_A,
                                               "XDG_CONFIG_HOME": SECRET_B, "PLAIN": "x"})})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect(f["token_keys"] == ["CSA_ZENDESK_TOKEN_FILE", "XDG_CONFIG_HOME"],
               f"token_keys {f['token_keys']}")
        mod = load_module()
        expect(set(mod.TOKEN_PATH_KEYS) == {
            "CSA_ZENDESK_TOKEN_FILE", "XDG_CONFIG_HOME", "CSA_GW_TOKEN", "CSA_GW_CLIENT_SECRETS",
            "CSA_GGC_TOKEN_PATH", "CSA_GGC_CLIENT_SECRETS", "CSA_SKILLJAR_ENV_FILE"},
            f"TOKEN_PATH_KEYS {mod.TOKEN_PATH_KEYS}")


@case
def no_check_rows_while_held():
    with world() as w:
        mod = load_module()
        expect(mod.VERIFY_ON_RERUN == frozenset(), "D5's safe default is (b): nothing checked")
        w.std("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(w.home / ".local/bin/csa-zendesk-mcp")})
        r = w.run()
        r.ok()
        expect(not r.rows_with("handshake"), f"a check row while held: {r.rows}")
        mod.VERIFY_ON_RERUN = frozenset({"csa-zendesk"})
        r = w.run_inproc(mod)
        r.ok()
        rows = r.rows_with("handshake")
        expect(len(rows) == 1 and "csa-zendesk" in rows[0], f"check rows: {rows}")


def rich_world(w):
    """Every client, with dead, standard, elsewhere, local and launcher registrations."""
    w.std("csa-zendesk")
    w.std("csa-skilljar")
    proj = w.home / "GitHub" / "csa-zendesk"
    dead_local = w.checkout("csa-zendesk", python=w.gone_python, home=w.gone_home, where=proj)
    w.claude(user={"csa-zendesk": reg(w.home / ".local/bin/csa-zendesk-mcp"),
                   "csa-skilljar": reg(w.tmp / "gone" / "csa-skilljar-mcp",
                                       env={"CSA_SKILLJAR_V2_CLIENT_SECRET": SECRET_A}),
                   "csa-google-workspace": reg(w.checkout("csa-google-workspace"))},
             projects={str(proj): {"mcpServers": {"csa-zendesk": reg(
                 dead_local, env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_B})}}})
    w.desktop({"csa-skilljar": reg(w.tmp / "gone" / "csa-skilljar-mcp",
                                   env={"CSA_SKILLJAR_V1_API_KEY": SECRET_C}),
               "csa-google-workspace": reg("csa-google-workspace-mcp")})
    w.gemini({"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp", trust=True,
                                 includeTools=["a"], timeout=5)})
    w.codex([{"name": "csa-zendesk", "transport": {"type": "stdio",
                                                    "command": str(w.tmp / "gone" / "z")}}])


@case
def plan_writes_nothing():
    with world() as w:
        rich_world(w)
        roots = [w.home, w.apps, w.tmp / "homebrew", w.tmp / "uvpy", w.stubs]
        before = snapshot(*roots)
        r = w.run()
        r.ok()
        expect(snapshot(*roots) == before, "a fixture file changed, or a new one appeared")
        expect(sorted(os.listdir(w.out.parent)) == ["plan.json"], "a stray file beside --out")
        expect(os.listdir(w.tmpdir) == [], f"left in TMPDIR: {os.listdir(w.tmpdir)}")


@case
def token_dirs_unreadable_still_plans():
    with world() as w:
        rich_world(w)
        dirs = [w.home / ".csa_google_workspace", w.home / ".csa_google_gmail_calendar",
                w.home / ".config" / "csa-zendesk"]
        for d in dirs:
            d.mkdir(parents=True)
            (d / "token.json").write_text('{"fake": true}')
        stats = [os.stat(d) for d in dirs]
        try:
            for d in dirs:
                d.chmod(0)
            r = w.run()
        finally:
            for d in dirs:
                d.chmod(0o700)
        r.ok()
        expect(r.findings(), "nothing was planned")
        for d, st in zip(dirs, stats):
            now = os.stat(d)
            expect((now.st_ino, now.st_mtime_ns) == (st.st_ino, st.st_mtime_ns), f"{d} changed")


@case
def internal_error_exits_2():
    # A failure outside any one client: exit 2, no plan file, and stderr names the type and
    # this script's own line, never the exception's message.
    with world() as w:
        mod = load_module()

        def boom(*a, **k):
            raise RuntimeError(f"deliberate {SECRET_A}")

        mod.render = boom
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run_inproc(mod)
        expect(r.rc == 2, f"exit {r.rc}, expected 2")
        expect(not w.out.exists(), "the plan file was written after an internal error")
        expect(SECRET_A not in r.stdout + r.stderr, "the exception's message was printed")
        m = re.search(r"RuntimeError at line (\d+)", r.stderr)
        expect(m, f"stderr: {r.stderr!r}")
        line = script_line(m.group(1))
        expect("render(clients, findings)" in line,
               f"line {m.group(1)} is not this script's own frame: {line!r}")


@case
def windows_not_audited():
    with world() as w:
        mod = load_module()
        mod.on_windows = lambda: True
        w.claude(user={"csa-zendesk": reg("/x")})
        r = w.run_inproc(mod)
        r.ok()
        for client in ("Claude Code", "Claude Desktop", "Codex", "Gemini"):
            expect(r.client_status(client) == WINDOWS, f"{client}: {r.client_status(client)!r}")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# The file itself
# ═════════════════════════════════════════════════════════════════════════════════════════════

@case
def py39_syntax():
    src = SCRIPT.read_text(encoding="utf-8")
    try:
        ast.parse(src, filename=str(SCRIPT), feature_version=(3, 9))
    except SyntaxError as e:
        raise Failed(f"not Python 3.9 syntax: line {e.lineno}: {e.msg}")
    imports = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib:
        expect(imports <= set(stdlib), f"not stdlib: {sorted(imports - set(stdlib))}")
    expect("tomllib" not in imports, "tomllib is 3.11+; Apple's /usr/bin/python3 is 3.9")


@case
def servers_table_matches_spec():
    mod = load_module()
    got = {k: (v.entry, v.module) for k, v in mod.SERVERS.items()}
    expect(got == SPEC, f"SERVERS {got}")


@case
def servers_match_internal_setups():
    spec = importlib.util.spec_from_file_location(
        "internal_lists", ROOT / "tests" / "test_internal_setup_lists.py")
    lists = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lists)
    mod = load_module()
    want = list(mod.SERVERS)
    for name in lists.COPIES:
        got = ["csa-" + n for n in lists.servers_in(ROOT / name)]
        expect(got == want, f"{name}: {got} != SERVERS {want}")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Runner, and the mutation self-test (Task 1 Step 4)
# ═════════════════════════════════════════════════════════════════════════════════════════════

# (the case that must catch it, what the mutation does, the exact text, its replacement)
MUTATIONS = [
    ("homebrew_opt_is_not_cellar", "classify Cellar by realpath, not the recorded path",
     "hop = first_hop_out(interp, venv)", "hop = os.path.realpath(interp)"),
    ("codex_list_failure_is_not_absence", "swallow a codex failure as no registrations",
     'return "not audited: " + codex_failure(rc, err), []', 'return "ok", []'),
    ("plan_file_has_no_values", "hash the env values into the fingerprint",
     "sorted(self.env)]", "sorted(self.env.items())]"),
    ("dead_standard_binary_no_self_repoint", "test liveness before the standard path",
     "if resolved is not None and same_file(resolved, std):",
     "if resolved is not None and same_file(resolved, std) and not standard_dead(resolved, server, ctx):"),
    ("launcher_form_left", "treat uv as a direct executable",
     'LAUNCHERS = ("uv", ', "LAUNCHERS = ("),
    ("interpreter_env_keys_left", "drop the UV_ prefix rule",
     ' or key.startswith("UV_")', ""),
    ("desktop_detected_by_path_not_name", "detect Claude Desktop by process name",
     "ctx.running = any(line.strip() in targets for line in lines)",
     'ctx.running = any(os.path.basename(line.strip()) == "Claude" for line in lines)'),
    # Found by the review of fba8c54.
    ("probe_writes_no_bytecode", "probe without -B",
     '[interp, "-I", "-B", "-c", PROBE]', '[interp, "-I", "-c", PROBE]'),
    ("linked_parent_dir_refused", "check only the config's last component for a link",
     "self.config_is_link = linked_config(config)", "self.config_is_link = os.path.islink(config)"),
    ("client_failure_contained", "let one client's failure abort the audit",
     "        except Exception as e:\n            status, found =",
     "        except ZeroDivisionError as e:\n            status, found ="),
    ("control_chars_cannot_forge_rows", "show key names uncleaned",
     "return sep.join(clean(k) for k in keys)", "return sep.join(keys)"),
    ("stdout_closed_writes_no_plan", "leave the plan file when the plan was not shown",
     "        if args.out and os.path.exists(args.out):\n            os.unlink(args.out)\n"
     "        say(", "        say("),
    ("plan_file_has_no_values", "record args in the plan file",
     '"env_keys": sorted(f.reg.env),', '"args": f.reg.args, "env_keys": sorted(f.reg.env),'),
    ("internal_error_exits_2", "print the exception's message",
     'return f"{type(exc).__name__} at line {own_line(exc)}"',
     'return f"{type(exc).__name__}: {exc} at line {own_line(exc)}"'),
    ("internal_error_exits_2", "report the innermost frame, whosever it is",
     "if os.path.abspath(tb.tb_frame.f_code.co_filename) == me:", "if True:"),
    ("codex_home_respected", "ignore CODEX_HOME",
     'codex_home = ctx.environ.get("CODEX_HOME") or os.path.join(ctx.home, ".codex")',
     'codex_home = os.path.join(ctx.home, ".codex")'),
    ("codex_timeout_kills_its_group", "kill only the child on a timeout, not its group",
     "os.killpg(p.pid, signal.SIGKILL)", "p.kill()"),
]


def run_cases(only=None):
    if not SCRIPT.exists():
        print(f"FAIL  {SCRIPT.relative_to(ROOT) if ROOT in SCRIPT.parents else SCRIPT} does not exist")
        return 1
    failed = []
    selected = [c for c in CASES if only is None or c.__name__ == only]
    if only and not selected:
        print(f"no case named {only}")
        return 1
    for c in selected:
        try:
            c()
            print(f"  ok    {c.__name__}")
        except Failed as e:
            failed.append(c.__name__)
            print(f"  FAIL  {c.__name__}: {e}")
        except Exception:
            failed.append(c.__name__)
            print(f"  FAIL  {c.__name__}: unexpected error")
            print("        " + traceback.format_exc().replace("\n", "\n        "))
    print()
    if failed:
        print(f"FAILED: {len(failed)} of {len(selected)} case(s): {', '.join(failed)}")
        return 1
    print(f"all {len(selected)} case(s) passed")
    return 0


def self_test():
    src = SCRIPT.read_text(encoding="utf-8")
    ok = True
    for name, what, old, new in MUTATIONS:
        if src.count(old) != 1:
            print(f"  FAIL  {what}: the text to mutate occurs {src.count(old)} times, not once")
            ok = False
            continue
        with tempfile.TemporaryDirectory(prefix="csa-reg-mutant-") as t:
            mutant = Path(t) / "csa-mcp-registrations.py"
            mutant.write_text(src.replace(old, new), encoding="utf-8")
            env = dict(os.environ, CSA_TEST_REGISTRATIONS_PY=str(mutant))
            r = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--only", name],
                               env=env, capture_output=True, text=True, timeout=300)
        why = next((ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith("FAIL")),
                   "")
        if r.returncode == 0:
            print(f"  FAIL  {what}: {name} still passes")
            ok = False
        elif "unexpected error" in why:
            # A mutant that crashes the case proves nothing about the assertion.
            print(f"  FAIL  {what}: {name} crashed instead of failing its check")
            ok = False
        else:
            print(f"  ok    {what}: caught by {name}\n          {why[:150]}")
    print()
    print("self-test " + ("passed" if ok else "FAILED"))
    return 0 if ok else 1


def main():
    if sys.platform == "win32":
        print("skipped: these fixtures need POSIX symlinks and /bin/sh (Windows: #184, Task 1W)")
        return 77
    if "--self-test" in sys.argv:
        return self_test()
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    print("csa-mcp-registrations.py plan\n")
    return run_cases(only)


if __name__ == "__main__":
    sys.exit(main())
