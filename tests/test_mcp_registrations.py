#!/usr/bin/env python3
"""scripts/csa-mcp-registrations.py `plan`: it finds every CSA MCP registration in Claude Code,
Claude Desktop, Codex and Gemini, says what is wrong with each, and writes nothing but its own
plan file (#179, plans/2026-11-12-registration-repair.md Task 1). And `apply` (Task 2): it
re-points only a dead registration that plan showed and that is unchanged since, changing only
its command, through Claude Code's own lock, with no backup left by a write it abandons. And
`verify` (Task 3): it launches each registered server that is a direct executable, one at a
time, with each client's env as M3 measured it, asks for an MCP `initialize`, and stops its
whole process group, bounded, within a total budget; it never launches a dead or launcher-form
registration, prints none of a server's own text (only fixed lines of its own), and launches
nothing at all without `--run` while D5 holds. Its servers are stubs.

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

`--self-test` is Task 1 Step 4 and Task 2 Step 4 kept runnable: each mutation the plan names,
and one for each guard apply added, is applied to a copy of the script, and the case named for
it must then FAIL. A case that passes a broken script is not testing anything.
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
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import unicodedata
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
# Reworded from the plan's "...is not measured yet", which M3 made untrue (P2, 2026-11-13).
R_DESKTOP_PATH = ("not checked: Claude Desktop's PATH differs from machine to machine, so a "
                  "bare command name can't be resolved here")
W_CELLAR = ("it runs from a venv built on a Homebrew Cellar Python, which the next brew "
            "upgrade deletes")
WINDOWS = "not audited: Windows support is #184 (Task 1W)"

# C0 and C1 controls, the Unicode line and paragraph separators, the bidi controls, and lone
# surrogates: anything that could break a line or reorder what a person reads.
# What may never reach a person's screen or the plan file raw, by Unicode category: every
# control (Cc), format characters (Cf: bidi, zero-width, BOM, tags), line and paragraph
# separators (Zl, Zp), lone surrogates (Cs) and private use (Co).
UNSAFE_CATEGORIES = ("Cc", "Cf", "Zl", "Zp", "Cs", "Co")


def unsafe_in(text):
    return sorted({hex(ord(c)) for c in text if unicodedata.category(c) in UNSAFE_CATEGORIES})

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
    """Line `number` of the script under test, or "" when it has no such line. Split on "\\n"
    as Python counts lines: splitlines() also splits on U+2028 and friends."""
    lines = SCRIPT.read_text(encoding="utf-8").split("\n")
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
            try:
                self.plan = json.loads(self.plan_text)
            except ValueError:
                self.plan = None  # e.g. a stale file a failed run left standing

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
        self.ledger = self.tmp / "todo.tsv"
        self.slog = self.tmp / "server.log"
        self.slog.write_text("")
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

    def run(self, *args, cwd=None, keep_out=False):
        if self.out.exists() and not keep_out:
            self.out.unlink()
        cmd = [sys.executable, "-I", str(SCRIPT), "plan", "--out", str(self.out),
               "--system-applications", str(self.apps), *args]
        r = subprocess.run(cmd, env=self.env(), cwd=str(cwd or self.tmp),
                           capture_output=True, text=True, timeout=180)
        return Result(r.returncode, r.stdout, r.stderr, self)

    def run_inproc(self, mod, *args, keep_out=False):
        """main() in this process, so a test can change a module constant first."""
        if self.out.exists() and not keep_out:
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

    def apply_argv(self, approved, args):
        argv = ["apply", "--system-applications", str(self.apps)]
        if approved == "plan":
            argv += ["--approved", str(self.out)]
        elif approved is not None:
            argv += ["--approved", str(approved)]
        return argv + list(args)

    def apply_env(self, ledger):
        env = self.env()
        if ledger:
            env["CSA_TODO_FILE"] = str(self.ledger)
        return env

    def apply(self, *args, approved="plan", ledger=True):
        """`apply --approved <the plan file>`, as the entry scripts will run it. umask 022, so a
        file created with plain open() would show as 0644."""
        cmd = [sys.executable, "-I", str(SCRIPT)] + self.apply_argv(approved, args)
        r = subprocess.run(cmd, env=self.apply_env(ledger), cwd=str(self.tmp),
                           capture_output=True, text=True, timeout=300, umask=0o022)
        return Applied(r.returncode, r.stdout, r.stderr, self)

    def apply_inproc(self, mod, *args, approved="plan", ledger=True):
        saved = dict(os.environ)
        old_umask = os.umask(0o022)
        out, err = io.StringIO(), io.StringIO()
        try:
            os.environ.clear()
            os.environ.update(self.apply_env(ledger))
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = mod.main(self.apply_argv(approved, args))
        finally:
            os.umask(old_umask)
            os.environ.clear()
            os.environ.update(saved)
        return Applied(rc, out.getvalue(), err.getvalue(), self)

    def verify_argv(self, run, args):
        return (["verify", "--system-applications", str(self.apps)] + (["--run"] if run else [])
                + list(args))

    def verify(self, *args, run=True, ledger=True):
        """`verify --run` (or, with run=False, `verify`) as a CLI, as the entry scripts run it."""
        cmd = [sys.executable, "-I", str(SCRIPT)] + self.verify_argv(run, args)
        r = subprocess.run(cmd, env=self.apply_env(ledger), cwd=str(self.tmp),
                           capture_output=True, text=True, timeout=300)
        return Applied(r.returncode, r.stdout, r.stderr, self)

    def verify_inproc(self, mod, *args, run=True, ledger=True):
        saved = dict(os.environ)
        out, err = io.StringIO(), io.StringIO()
        try:
            os.environ.clear()
            os.environ.update(self.apply_env(ledger))
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = mod.main(self.verify_argv(run, args))
        finally:
            os.environ.clear()
            os.environ.update(saved)
        return Applied(rc, out.getvalue(), err.getvalue(), self)

    # ── stub MCP servers, for verify ───────────────────────────────────────────────────────
    def server(self, path, mode="answer", name="csa-stub", version="9.9.9", interp=None, **opts):
        """A stub MCP server at `path`: a Python script whose shebang is `interp`, this test's
        own Python by default. It logs to self.slog, one JSON object a line: its start (pid,
        process group, session, working directory and its listing, its env KEY NAMES - never a
        value), each request, and its end. `mode` is what it does (STUB_SERVER).

        Its second line is a no-op to Python and, to a shell, an exec of this test's Python on
        the file: so with a shell as `interp` (partial_python) it still runs as the stub. macOS
        will not exec a script as another script's interpreter, so a sh wrapper cannot serve."""
        conf = dict(opts, mode=mode, name=name, version=version, log=str(self.slog))
        return write_exec(path, f"#!{interp or sys.executable}\n"
                                f'"exec" "{sys.executable}" "$0" "$@"\n'
                                f"CONF = {json.dumps(conf)!r}\n" + STUB_SERVER)

    def std_server(self, name, **kw):
        """The standard binary, ~/.local/bin/<entry>, as a stub server named <name>-stub."""
        kw.setdefault("name", name + "-stub")
        return self.server(self.home / ".local" / "bin" / SPEC[name][0], **kw)

    def server_log(self):
        return [json.loads(ln) for ln in self.slog.read_text().splitlines() if ln.strip()]

    def starts(self):
        return [e for e in self.server_log() if e["ev"] == "start"]

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
        path.write_text(raw, encoding="utf-8")
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
            path.write_text(raw, encoding="utf-8")
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
            path.write_text(raw, encoding="utf-8")
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

    def codex_toml(self, servers=None, raw=None, listing=None, tamper=None):
        """A real-shaped Codex config.toml, and a `codex` stub that answers `mcp list --json`
        and `mcp get <name> --json` with each entry's command and args read from that file, as
        Codex reads its config. `tamper` names a server whose other fields the stub reports
        changed once its command no longer matches the original: a read-back mismatch."""
        path = self.home / ".codex" / "config.toml"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = ['model = "gpt-5"', 'approval_policy = "on-request"', "",
                 '[projects."/somewhere"]', 'trust_level = "trusted"', ""]
        entries = []
        for name, s in (servers or {}).items():
            env = s.get("env") or {}
            lines.append(f"[mcp_servers.{name}]")
            lines.append(f"command = {json.dumps(s['command'])}")
            if "args" in s:
                lines.append(f"args = {json.dumps(s['args'])}")
            lines += ["startup_timeout_sec = 30", "enabled = true", 'env_vars = ["HOME"]']
            if env:
                lines += ["", f"[mcp_servers.{name}.env]"]
                lines += [f"{k} = {json.dumps(v)}" for k, v in env.items()]
            lines.append("")
            entries.append({"name": name, "enabled": True, "disabled_reason": None,
                            "startup_timeout_sec": 30, "tool_timeout_sec": None,
                            "auth_status": None,
                            "transport": {"type": "stdio", "command": s["command"],
                                          "args": s.get("args", []), "env": env or None,
                                          "env_vars": ["HOME"], "cwd": None}})
        lines += ["[tui]", 'theme = "dark"', ""]
        path.write_text(raw if raw is not None else "\n".join(lines))
        path.chmod(0o600)
        listing = listing if listing is not None else entries
        scenario = self.tmp / "codex-scenario.json"
        scenario.write_text(json.dumps({
            "list": listing, "tamper": tamper,
            "original": {e["name"]: e["transport"]["command"] for e in listing}}))
        stub = self.tmp / "codex_stub.py"
        stub.write_text(CODEX_STUB)
        write_exec(self.stubs / "codex",
                   f'#!/bin/sh\nexec "{sys.executable}" -I "{stub}" "{self.log}" "{scenario}" "$@"\n')
        return path


# The Codex stub for apply's cases. Codex reads its own config.toml; this reads the command and
# the args of each [mcp_servers.<name>] table from it, so an edit of the file shows in `mcp get`.
CODEX_STUB = r'''
import json, os, re, sys
log, scenario, argv = sys.argv[1], sys.argv[2], sys.argv[3:]
with open(log, "a") as f:
    f.write("codex " + " ".join(argv) + "\n")
    f.write("codex-cwd %s %d\n" % (os.getcwd(), len(os.listdir("."))))
scen = json.load(open(scenario))
home = os.environ.get("CODEX_HOME") or os.path.join(os.environ["HOME"], ".codex")
cfg = os.path.join(home, "config.toml")
text = open(cfg).read() if os.path.exists(cfg) else ""

def table(name):
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip() in ("[mcp_servers.%s]" % name, '[mcp_servers."%s"]' % name):
            region = []
            for nxt in lines[i + 1:]:
                if nxt.lstrip().startswith("["):
                    break
                region.append(nxt)
            return "\n".join(region)
    return None

def entry(e):
    e = json.loads(json.dumps(e))
    region = table(e["name"])
    if region is not None:
        m = re.search(r'^\s*command\s*=\s*"((?:[^"\\]|\\.)*)"', region, re.M)
        if m:
            e["transport"]["command"] = json.loads('"' + m.group(1) + '"')
        m = re.search(r'^\s*args\s*=\s*(\[.*?\])', region, re.M | re.S)
        if m:
            e["transport"]["args"] = json.loads(re.sub(r",\s*\]$", "]", m.group(1)))
    name = e["name"]
    if scen.get("tamper") == name and e["transport"]["command"] != scen["original"][name]:
        e["startup_timeout_sec"] = 999
    return e

if argv[:3] == ["mcp", "list", "--json"]:
    print(json.dumps([entry(e) for e in scen["list"]]))
    sys.exit(0)
if argv[:2] == ["mcp", "get"] and argv[-1:] == ["--json"]:
    for e in scen["list"]:
        if e["name"] == argv[2]:
            print(json.dumps(entry(e)))
            sys.exit(0)
    sys.exit(1)
sys.exit(2)
'''


# A stub MCP server for verify's cases (World.server). CONF is set by the line above this text.
# Its modes: answer (an initialize result), junk (lines that are not JSON, a notification and an
# answer to another id, then the answer), error (an error answer), exit (its env on stderr, then
# CONF["last"], then exit 3 before answering), silent (ignores SIGTERM, starts a grandchild in
# its own process group, and never answers). `lock` makes it hold an exclusive lock for its whole
# life and give up on contention; `delay` and `linger` hold it before its answer and after stdin
# closes; `orphan` starts a child in its group that outlives it. `leak` makes it put every value
# it was given (its CSA_ and PLAN_ env values, and its args) everywhere a server's text can go,
# in every form: raw, repr, JSON, a multi-line value on one line, an argparse error line, a
# stderr flood past any 64 KB tail, stdout lines, a notification, and its answer (its own name
# and version, an error's message and data, an unfinished stdout line at its exit).
STUB_SERVER = r'''
import fcntl, json, os, signal, subprocess, sys, time
CONF = json.loads(CONF)


def log(**ev):
    ev["pid"] = os.getpid()
    with open(CONF["log"], "a") as f:
        f.write(json.dumps(ev) + "\n")


def say(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


mode = CONF["mode"]
log(ev="start", server=CONF["name"], pgid=os.getpgid(0), sid=os.getsid(0), cwd=os.getcwd(),
    listing=len(os.listdir(".")), keys=sorted(os.environ), args=sys.argv[1:],
    blocked=sorted(int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK, [])))
vals = [v for k, v in sorted(os.environ.items()) if k.startswith(("CSA_", "PLAN_"))]
vals += sys.argv[1:]
forms = []
for v in vals:
    forms += [v, repr(v), json.dumps(v), v.replace("\n", " | ")]
if CONF.get("leak"):
    sys.stderr.write("usage: srv [-h]\nsrv: error: unrecognized arguments: %s\n"
                     % " ".join(sys.argv[1:]))
    for f in forms:
        sys.stderr.write(f + "\n")
    sys.stderr.write(("x" * 997 + "".join(vals)) * 70 + "\n")
    sys.stderr.flush()
    for f in forms:
        sys.stdout.write("note: " + f + "\n")
    say({"jsonrpc": "2.0", "method": "notifications/message", "params": {"data": vals}})
    log(ev="leaked", forms=len(forms))
if CONF.get("orphan"):
    child = subprocess.Popen(["/bin/sleep", "60"])
    log(ev="grandchild", child=child.pid)
if CONF.get("lock"):
    held = open(CONF["lock"], "a")
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log(ev="contention")
        sys.exit(1)
if mode == "exit":
    for key, value in sorted(os.environ.items()):
        sys.stderr.write("%s=%s\n" % (key, value))
    sys.stderr.write(CONF["last"] + "\n")
    sys.stderr.flush()
    if CONF.get("leak"):
        sys.stdout.write("fatal: " + " ".join(forms))  # no newline: left unfinished at its exit
        sys.stdout.flush()
    sys.exit(3)
if mode == "silent":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    child = subprocess.Popen(["/bin/sleep", "60"])
    log(ev="grandchild", child=child.pid)
    while True:
        time.sleep(1)
if mode == "junk":
    sys.stdout.write("starting up\n{not json\n")
    say({"jsonrpc": "2.0", "method": "notifications/message", "params": {}})
    say({"jsonrpc": "2.0", "id": 7, "result": {}})
for line in sys.stdin:
    msg = json.loads(line)
    params = msg.get("params") or {}
    log(ev="recv", method=msg.get("method"), id=msg.get("id"),
        protocolVersion=params.get("protocolVersion"), client=params.get("clientInfo"))
    time.sleep(CONF.get("delay", 0))
    leak = CONF.get("leak")
    if mode == "error":
        say({"jsonrpc": "2.0", "id": msg["id"],
             "error": {"code": CONF.get("code", -32602),
                       "message": " ".join(forms) if leak else CONF.get("message", "no"),
                       "data": vals if leak else None}})
    else:
        say({"jsonrpc": "2.0", "id": msg["id"],
             "result": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "serverInfo": {"name": CONF["name"] + (" " + " ".join(vals) if leak else ""),
                                       "version": repr(vals) if leak else CONF["version"]}}})
time.sleep(CONF.get("linger", 0))
log(ev="end")
'''


class Applied(object):
    """What `apply` printed, and the to-do ledger it wrote."""

    def __init__(self, rc, stdout, stderr, world):
        self.rc = rc
        self.stdout = stdout
        self.stderr = stderr
        lines = [ln.split("\t", 1) for ln in stdout.splitlines() if "\t" in ln]
        self.kinds = [k for k, _ in lines]
        self.oks = [t for k, t in lines if k == "ok"]
        self.warns = [t for k, t in lines if k == "warn"]
        self.infos = [t for k, t in lines if k == "info"]
        self.ledger_text = world.ledger.read_text() if world.ledger.exists() else ""
        self.todos = [tuple(ln.split("\t")) for ln in self.ledger_text.splitlines()]

    def ok(self):
        expect(self.rc == 0, f"exited {self.rc}: {self.stderr.strip()[-400:]}")

    def has_todo(self, order, title):
        return (str(order), title, "-", "-") in self.todos

    def todo_titles(self, order=None):
        return [t[1] for t in self.todos if order is None or t[0] == str(order)]

    def warned(self, text):
        return [w for w in self.warns if text in w]


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
        expect(mod.DESKTOP_PATH is None,
               "M3's one-Mac Desktop PATH is not applied (AI ruling 2026-11-13, P1)")
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
        # apply, with Desktop still running: not written, and the quit to-do is at order 10.
        w.std("csa-zendesk")
        cfg = w.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        before = cfg.read_bytes()
        a = w.apply()
        a.ok()
        expect(cfg.read_bytes() == before, "Desktop's config was written while it ran")
        expect(a.has_todo(10, "Quit Claude Desktop and run again"), f"ledger: {a.todos}")
        expect(not a.oks, f"apply reported a re-point: {a.oks}")
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
        # apply leaves it, and the to-do reaches the ledger at the installer's own order.
        cfg = w.home / ".claude.json"
        before = cfg.read_bytes()
        a = w.apply()
        a.ok()
        expect(cfg.read_bytes() == before, "apply changed a dead local-scope entry under D2 (d)")
        expect(a.has_todo(40, todo), f"the to-do is not in the ledger at 40: {a.todos}")
        expect(not a.oks, f"apply reported a re-point: {a.oks}")


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
        a = w.apply()
        a.ok()
        expect(snapshot(w.home, real.parent) == before, "apply changed the link or its target")
    with world() as w:
        # The config becomes a link after apply has audited it, just before the write: the
        # write itself refuses it, not only the audit (A10).
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        w.run().ok()
        dots = w.tmp / "dotfiles"
        dots.mkdir()
        real = dots / "claude.json"

        def relink(point, path):
            if point == "edit" and not os.path.islink(path):
                os.replace(path, real)
                os.symlink(real, path)

        mod.TEST_HOOK = relink
        a = w.apply_inproc(mod)
        a.ok()
        expect(os.path.islink(cfg) and os.readlink(cfg) == str(real), "the link was replaced")
        got = json.loads(real.read_text())["mcpServers"]["csa-zendesk"]["command"]
        expect(got == str(w.tmp / "gone" / "csa-zendesk-mcp"), f"written through the link: {got}")
        expect(a.warned("its config is a link to"), f"no warning: {a.warns}")
        expect(not a.oks, f"apply reported a re-point: {a.oks}")


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
        for client in ("Gemini", "Codex"):
            expect((r.client_status(client) or "").startswith("not audited: "),
                   f"{client}: {r.client_status(client)!r}")
        # Whether 100,000-deep JSON parses depends on the build: uv's 3.14.10 and Apple's 3.9
        # raise RecursionError, Homebrew's 3.14.10 parses it. Either is right here; what is
        # pinned is that it never takes the other clients down. The classification of a
        # RecursionError is pinned, on every build, by deep_nesting_is_not_audited.
        desktop = r.client_status("Claude Desktop") or ""
        expect(desktop == "ok" or "nested too deeply" in desktop, f"Desktop: {desktop!r}")
        expect(r.f("csa-zendesk")["action"] == "re-point", "Claude Code was not audited")


class _DeepJson(object):
    """json, except that every parse is too deep: the RecursionError some builds raise at
    100,000 levels and others do not, forced so the case runs the same on all of them."""
    dumps = staticmethod(json.dumps)

    @staticmethod
    def loads(*a, **k):
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")


@case
def deep_nesting_is_not_audited():
    mod = load_module()
    mod.json = _DeepJson
    try:
        data, why = mod.parse_json("[]", "its config")
    except RecursionError:
        raise Failed("a RecursionError escaped the JSON reader")
    expect(data is None and why == "its config is nested too deeply to read", f"{data}/{why!r}")
    with world() as w:
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run_inproc(mod)
        r.ok()
        status = r.client_status("Claude Code") or ""
        expect(status == "not audited: its config is nested too deeply to read", f"{status!r}")


@case
def lone_surrogate_is_malformed():
    # JSON can carry a lone surrogate (`"\ud800"`), which no UTF-8 encoder accepts. In a
    # command, an arg or an env key it is a malformed entry of that client, not a crash of all
    # four: the fingerprint and the plan file both encode to UTF-8.
    with world() as w:
        gone = str(w.tmp / "gone" / "csa-zendesk-mcp")
        w.claude(user={"csa-zendesk": reg(gone)},
                 projects={"/p\ud800": {"mcpServers": {"csa-skilljar": reg(gone)}}})
        w.gemini({"csa-zendesk": reg("/x\ud800")})
        w.desktop({"csa-zendesk": reg(gone, ["--flag\ud800"])})
        w.codex([{"name": "csa-zendesk", "transport": {"type": "stdio", "command": gone,
                                                        "env": {"K\ud800": "v"}}}])
        r = w.run()
        r.ok()
        for client in ("Gemini", "Claude Desktop", "Codex"):
            # A malformed entry, said so - not the per-client backstop's "this audit failed".
            status = r.client_status(client) or ""
            expect(status.startswith("not audited: ") and "unexpected shape" in status,
                   f"{client}: {status!r}")
        expect(r.f("csa-zendesk")["action"] == "re-point", "Claude Code was not audited")
        expect(not r.findings("csa-skilljar"), "a project path no file system can hold was audited")


@case
def failure_removes_only_its_own_plan():
    # A run that fails after creating its plan file removes that file: "nothing was written"
    # is true of --out (A4).
    with world() as w:
        mod = load_module()

        def boom(*a, **k):
            raise RuntimeError("deliberate")

        mod.show = boom
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run_inproc(mod)
        expect(r.rc == 2, f"exit {r.rc}")
        expect(not w.out.exists(), "the plan file this run created survived its failure")


@case
def existing_out_left_untouched():
    # --out must be a new file. An existing one - an earlier plan, or anything else - is
    # refused before the audit and left byte-identical, also when argparse fails first; this
    # never opens a file to learn whose it is, and never removes one it did not create.
    with world() as w:
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        w.out.write_text('{"tool": "csa-mcp-registrations", "earlier": true}\n')
        before = w.out.read_bytes()
        r = w.run(keep_out=True)
        expect(r.rc == 2, f"exit {r.rc}")
        expect("already exists" in r.stderr, f"stderr: {r.stderr!r}")
        expect(not r.rows, f"rows printed for a refused run: {r.rows}")
        expect(w.out.read_bytes() == before, "the existing file changed")
        r = w.run("--no-such-flag", keep_out=True)
        expect(r.rc == 2 and w.out.read_bytes() == before, f"argparse error: exit {r.rc}")
        w.out.unlink()
        r = w.run("--no-such-flag")
        expect(r.rc == 2 and not w.out.exists(), "an argparse error created --out")


@case
def out_never_replaced_even_after_the_check():
    # The race: --out is new when it is checked, and exists when the plan is written. The write
    # is a no-clobber link, so it fails rather than replace what appeared.
    with world() as w:
        mod = load_module()
        mod.out_refusal = lambda path, ctx: None
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        w.out.write_text("appeared after the check\n")
        r = w.run_inproc(mod, keep_out=True)
        expect(r.rc == 2, f"exit {r.rc}")
        expect(w.out.read_text() == "appeared after the check\n", "the file that appeared was replaced")
        expect(not [n for n in os.listdir(w.out.parent) if n != "plan.json"], "a temp file was left")


@case
def out_refuses_client_configs():
    # A config holding secrets must never be overwritten by a plan, nor removed by a failed
    # run (review of e62c775: `--out ~/.claude.json` replaced it). Refused by realpath, so a
    # linked directory does not hide it, and even where that config does not exist yet.
    with world() as w:
        cc = w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        desktop = w.desktop({})
        codex = w.codex([])
        (w.home / ".gemini").mkdir()
        w.stub("gemini", "exit 0")
        gemini = w.home / ".gemini" / "settings.json"        # absent: Gemini has no config yet
        (w.tmp / "gemini-link").symlink_to(w.home / ".gemini")
        alt = w.tmp / "alt-claude"
        alt.mkdir()
        cases = [(cc, True), (desktop, True), (codex, True), (gemini, False),
                 (w.tmp / "gemini-link" / "settings.json", False)]
        for path, existed in cases:
            before = path.read_bytes() if existed else None
            r = w.run("--out", str(path))
            expect(r.rc == 2, f"--out {path}: exit {r.rc}")
            if existed:
                expect(path.read_bytes() == before, f"--out {path}: the config changed")
            else:
                expect(not os.path.lexists(path), f"--out {path}: a config was created")
                # Refused by name, before any file exists - not created and then caught by
                # identity, which leaves a moment where a running client could read the plan.
                expect("on this volume" not in r.stderr and "keeps its config; refused" in r.stderr,
                       f"--out {path}: not refused before the write: {r.stderr!r}")
        w.extra_env["CLAUDE_CONFIG_DIR"] = str(alt)        # the config Claude Code would read
        r = w.run("--out", str(alt / ".claude.json"))
        expect(r.rc == 2 and not (alt / ".claude.json").exists(), f"CLAUDE_CONFIG_DIR: exit {r.rc}")
        expect("Claude Code" in r.stderr, f"stderr: {r.stderr!r}")


@case
def out_config_spelled_otherwise_refused():
    # Refused by what the file IS, not by how the name is spelled: on a case-insensitive
    # volume `~/.CLAUDE.json` is `~/.claude.json` (review of a9f9a94).
    with world() as w:
        # Every platform: the name check is bypassed, so only the identity check stands
        # between the plan and the path Gemini reads its settings from.
        mod = load_module()
        mod.out_refusal = lambda path, ctx: None
        w.gemini(config=False)
        (w.home / ".gemini").mkdir()
        settings = w.home / ".gemini" / "settings.json"
        r = w.run_inproc(mod, "--out", str(settings))
        expect(r.rc == 2, f"identity check: exit {r.rc}")
        expect(not os.path.lexists(settings), "the plan was left where Gemini reads its config")
        expect("Gemini" in r.stderr, f"stderr: {r.stderr!r}")
    with world() as w:
        probe = w.tmp / "CaseProbe"
        probe.write_text("")
        if not (w.tmp / "caseprobe").exists():
            print("        (case-sensitive volume: the respelled names are distinct files here)")
            return
        w.stub("claude", "exit 0")
        w.gemini(config=False)
        (w.home / ".gemini").mkdir()
        w.codex(config=False)
        (w.home / ".codex").mkdir()
        for spelled, real in ((".CLAUDE.json", ".claude.json"),
                              (".gemini/Settings.json", ".gemini/settings.json"),
                              (".codex/CONFIG.TOML", ".codex/config.toml")):
            r = w.run("--out", str(w.home / spelled))
            expect(r.rc == 2, f"--out ~/{spelled}: exit {r.rc}")
            expect(not os.path.lexists(w.home / real), f"--out ~/{spelled}: ~/{real} was created")


@case
def discard_spares_a_file_swapped_in():
    # The plan file's identity is taken before its name exists. If the file at --out is
    # replaced after the link and the run then fails, the replacement is not deleted.
    with world() as w:
        mod = load_module()

        class Os(object):
            def __getattr__(self, name):
                return getattr(os, name)

            @staticmethod
            def link(src, dst):
                os.link(src, dst)
                os.unlink(dst)
                Path(dst).write_text("somebody else's file\n")

        def boom(*a, **k):
            raise RuntimeError("deliberate")

        mod.os = Os()
        mod.show = boom
        w.claude(user={"csa-zendesk": reg(w.tmp / "gone" / "csa-zendesk-mcp")})
        r = w.run_inproc(mod)
        expect(r.rc == 2, f"exit {r.rc}")
        expect(w.out.exists() and w.out.read_text() == "somebody else's file\n",
               "a failed run deleted a file it did not create")


@case
def transport_type_is_text_or_malformed():
    # A `type` UTF-8 cannot encode makes that client's entry malformed; any other unexpected
    # `type` is recorded as "unknown", so the config's own text never reaches the plan file.
    with world() as w:
        gone = str(w.tmp / "gone" / "csa-zendesk-mcp")
        w.claude(user={"csa-zendesk": reg(gone)})
        w.desktop({"csa-zendesk": {"type": "x" + chr(0xD800), "url": "https://example.invalid"}})
        w.gemini({"csa-zendesk": {"type": "sse" + chr(0x202E) + chr(0x2028),
                                  "url": "https://example.invalid"}})
        w.codex([{"name": "csa-zendesk", "transport": {"type": "y" + chr(0xD800), "url": "u"}}])
        r = w.run()
        r.ok()
        for client in ("Claude Desktop", "Codex"):
            expect((r.client_status(client) or "").startswith("not audited: "),
                   f"{client}: {r.client_status(client)!r}")
        f = r.f("csa-zendesk", "Gemini")
        expect(f["transport"] == "unknown", f"Gemini transport {f['transport']!r}")
        expect(r.f("csa-zendesk")["action"] == "re-point", "Claude Code was not audited")
        expect(all(b < 0x80 for b in w.out.read_bytes()), "the plan file holds raw non-ASCII")


@case
def system_links_are_not_config_links():
    # /tmp and /var are links on macOS (to /private/...). A config directly in one belongs to
    # the machine's layout, not to a dotfiles repository, so it is not "a link" (A10).
    mod = load_module()
    for path in ("/tmp/.claude.json", "/var/.claude.json"):
        expect(mod.linked_config(path) is False, f"{path} reads as linked")
    with tempfile.TemporaryDirectory(prefix="csa-reg-link-") as t:
        real = Path(t) / "real.json"
        real.write_text("{}")
        (Path(t) / "link.json").symlink_to(real)
        expect(mod.linked_config(str(Path(t) / "link.json")) is True, "a linked file is not linked")


@case
def clean_replaces_separators_and_bidi():
    mod = load_module()
    # Controls (LF, TAB, CR, NEL), separators, bidi, a lone surrogate, the zero-width set the
    # review of e62c775 found passing (ZWSP, ZWJ, word joiner, invisible times, soft hyphen,
    # Mongolian vowel separator, interlinear annotation anchor, a tag character), private use
    # and the BOM. Every one is spelled as a code point.
    points = (0x0A, 0x09, 0x0D, 0x85, 0x2028, 0x2029, 0x202E, 0x2066, 0x200F, 0x061C, 0xD800,
              0x200B, 0x200D, 0x2060, 0x2061, 0x00AD, 0x180E, 0xFFF9, 0xE0001, 0xE000, 0xFEFF)
    hostile = "a" + "".join(chr(cp) + "a" for cp in points)
    out = mod.clean(hostile)
    expect(not unsafe_in(out), f"left in: {unsafe_in(out)}")
    expect(out == "a" + "?a" * len(points), f"cleaned to {out!r}")
    expect(mod.clean("caf" + chr(0xE9) + " ~/x y") == "caf" + chr(0xE9) + " ~/x y",
           "ordinary text was changed")


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
        # A bidi override too: the plan file must record the path exactly, but as an escape.
        proj = w.home / ("evil\nrow\tFORGED-PROJECT" + chr(0x202E))
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
                text = f[field] or ""
                expect(not unsafe_in(text), f"{field} holds {unsafe_in(text)}")
            expect(not any(unsafe_in(x) for x in f["warnings"]), "a warning does")
        expect(len(r.rows_with("FORGED-PROJECT")) >= 1, "the project's row is missing")
        raw = w.out.read_bytes()
        expect(all(b < 0x80 for b in raw), "the plan file holds raw non-ASCII; it escapes all")
        expect(r.findings("csa-zendesk", scope="local")[0]["project"] == str(proj),
               "the project path was not recorded exactly")


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
        w.claude(raw=chr(0xFEFF) + json.dumps({"mcpServers": {}}))
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
# apply (Task 2): re-point an approved dead registration in place, changing only its command
# ═════════════════════════════════════════════════════════════════════════════════════════════

# Verbatim from the plan, Task 2.
R_UNAPPROVED = "found after you agreed to the plan; not changed — run again"
R_NO_STANDARD = "its standard binary is not installed yet"
R_CHANGED = "changed while this ran; not written — run again"
R_CODEX_LAYOUT = "its Codex entry is laid out in a way this cannot edit safely; left as it is"
T_QUIT_DESKTOP = "Quit Claude Desktop and run again"
# M1's to-do, verbatim; the to-do also names the lock's path.
T_LOCKED = "Claude Code's config is locked; close Claude Code and run again"


def std_bin(w, name):
    return str(w.home / ".local" / "bin" / SPEC[name][0])


def gone(w, name):
    return str(w.tmp / "gone" / SPEC[name][0])


def desktop_cfg(w):
    return w.home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def backups(path):
    path = Path(path)
    return sorted(n for n in os.listdir(path.parent) if n.startswith(path.name + ".bak-"))


def state(path):
    """A file's identity, timestamp and bytes: what an untouched file keeps."""
    st = os.lstat(path)
    return st.st_ino, st.st_mtime_ns, Path(path).read_bytes()


def entry_of(path, name, project=None):
    data = json.loads(Path(path).read_text())
    holder = data["projects"][project] if project else data
    return holder["mcpServers"][name]


def four_dead(w):
    """A dead registration with secret settings in each client, each re-pointable."""
    for name in ("csa-zendesk", "csa-skilljar", "csa-google-workspace"):
        w.std(name)
    w.stub("claude", "exit 0")
    w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"),
                                      env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A})})
    w.desktop({"csa-skilljar": reg(gone(w, "csa-skilljar"),
                                   env={"CSA_SKILLJAR_V1_API_KEY": SECRET_B,
                                        "CSA_SKILLJAR_V2_CLIENT_SECRET": SECRET_C})})
    w.gemini({"csa-google-workspace": reg(gone(w, "csa-google-workspace"),
                                          env={"CSA_GW_CAPABILITIES": SECRET_A}, trust=True)})
    w.codex_toml({"csa-zendesk": {"command": gone(w, "csa-zendesk"),
                                  "env": {"CSA_ZD_ALLOWLIST_WRITE": SECRET_B}}})


@case
def dead_user_scope_repointed_env_kept():
    with world() as w:
        w.std("csa-zendesk")
        w.std("csa-skilljar")
        env = {"CSA_ZD_ALLOWLIST_WRITE": SECRET_A, "CSA_ZD_ALLOWLIST_READ": SECRET_B}
        cfg = w.claude(user={
            "csa-zendesk": reg(gone(w, "csa-zendesk"), env=env, timeout=30, alwaysAllow=["x"]),
            # The pinned interpreter form: args become [].
            "csa-skilljar": reg(w.tmp / "gone" / "python3", ["-m", "csa_skilljar.mcp.cli"],
                                env={"CSA_SKILLJAR_PROFILE": "p"}),
        })
        before = json.loads(cfg.read_text())
        w.run().ok()
        a = w.apply()
        a.ok()
        after = json.loads(cfg.read_text())
        for name, args in (("csa-zendesk", []), ("csa-skilljar", [])):
            old, new = before["mcpServers"][name], after["mcpServers"][name]
            expect(new["command"] == std_bin(w, name), f"{name}: command {new['command']!r}")
            expect(new["args"] == args, f"{name}: args {new['args']!r}")
            expect(list(new) == list(old), f"{name}: keys {list(new)} != {list(old)}")
            expect(new["env"] == old["env"] and type(new["env"]) is dict,
                   f"{name}: env changed: {sorted(new['env'])}")
            for k in old:
                if k not in ("command", "args"):
                    expect(new[k] == old[k], f"{name}: {k} changed")
        expect({k: v for k, v in after.items() if k != "mcpServers"}
               == {k: v for k, v in before.items() if k != "mcpServers"},
               "a field outside mcpServers changed")
        want = ("csa-zendesk re-pointed in Claude Code (user scope) at "
                "~/.local/bin/csa-zendesk-mcp; its 2 settings kept")
        expect(any(o.startswith(want) for o in a.oks), f"no ok line {want!r}: {a.oks}")
        expect(all("sessions started" in o for o in a.oks if "Claude Code" in o),
               f"the ok line claims more than M1 shows (a running session keeps its command): {a.oks}")
        expect(stat.S_IMODE(os.stat(cfg).st_mode) == 0o600, "the config's mode changed")


@case
def local_scope_repaired_when_repoint():
    with world() as w:
        mod = load_module()
        mod.LOCAL_SCOPE_ACTION = "repoint"
        w.std("csa-zendesk")
        proj = w.home / "GitHub" / "csa-zendesk"
        script = w.checkout("csa-zendesk", python=w.gone_python, home=w.gone_home, where=proj)
        user = reg(w.home / ".local/bin/csa-zendesk-mcp")
        cfg = w.claude(user={"csa-zendesk": user}, projects={str(proj): {"mcpServers": {
            "csa-zendesk": reg(script, env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A})}}})
        w.run_inproc(mod).ok()
        a = w.apply_inproc(mod)
        a.ok()
        got = entry_of(cfg, "csa-zendesk", str(proj))
        expect(got["command"] == std_bin(w, "csa-zendesk"), f"local entry: {got['command']!r}")
        expect(got["env"] == {"CSA_ZD_ALLOWLIST_WRITE": SECRET_A}, "the local entry's env changed")
        expect(entry_of(cfg, "csa-zendesk") == user, "the user entry changed")
        expect(any("local scope" in o for o in a.oks), f"ok lines: {a.oks}")


@case
def working_elsewhere_byte_identical():
    with world() as w:
        script = w.checkout("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(script, env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A})})
        before = state(cfg)
        r = w.run()
        r.ok()
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a working registration elsewhere was rewritten")
        expect(backups(cfg) == [], f"a backup was made: {backups(cfg)}")
        expect(a.has_todo(40, r.f("csa-zendesk")["todo"]), f"D1's to-do is not in the ledger: {a.todos}")
    with world() as w:
        # In a file that is rewritten for another entry, it keeps every value.
        w.std("csa-skilljar")
        script = w.checkout("csa-zendesk")
        kept = reg(script, env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A})
        cfg = w.claude(user={"csa-zendesk": kept,
                             "csa-skilljar": reg(gone(w, "csa-skilljar"))})
        w.run().ok()
        w.apply().ok()
        expect(entry_of(cfg, "csa-skilljar")["command"] == std_bin(w, "csa-skilljar"), "not re-pointed")
        expect(entry_of(cfg, "csa-zendesk") == kept, "the working entry changed")


@case
def desktop_mode_0600_kept():
    with world() as w:
        w.std("csa-skilljar")
        w.std("csa-zendesk")
        cfg = w.desktop({"csa-skilljar": reg(gone(w, "csa-skilljar"),
                                             env={"CSA_SKILLJAR_V1_API_KEY": SECRET_A})})
        gem = w.gemini({"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        gem.chmod(0o644)
        w.run().ok()
        a = w.apply()
        a.ok()
        expect(entry_of(cfg, "csa-skilljar")["command"] == std_bin(w, "csa-skilljar"), "not re-pointed")
        for path, mode in ((cfg, 0o600), (gem, 0o644)):
            got = stat.S_IMODE(os.stat(path).st_mode)
            expect(got == mode, f"{path.name}: mode {oct(got)}, was {oct(mode)}")
            for b in backups(path):
                got = stat.S_IMODE(os.stat(path.parent / b).st_mode)
                expect(got == mode, f"{b}: mode {oct(got)}, its file is {oct(mode)}")
            expect(len(backups(path)) == 1, f"{path.name}: backups {backups(path)}")


@case
def backup_same_mode_and_pruned_to_3():
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
        original = cfg.read_bytes()
        old = [f".claude.json.bak-2020010100000{i}" for i in (1, 2, 3)]
        for name in old:
            (w.home / name).write_text("{}")
            (w.home / name).chmod(0o600)
        w.run().ok()
        w.apply().ok()
        got = backups(cfg)
        new = [b for b in got if b not in old]
        expect(len(new) == 1, f"one new backup expected: {got}")
        expect(sorted(got) == sorted(new + old[1:]), f"pruned to the wrong three: {got}")
        expect((w.home / new[0]).read_bytes() == original, "the backup is not the file it replaced")
        mode = stat.S_IMODE(os.stat(w.home / new[0]).st_mode)
        expect(mode == 0o600, f"backup mode {oct(mode)}")


@case
def prune_spares_other_backup_names():
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        others = [".claude.json.bak", ".claude.json.backup", ".claude.json.bak-2020",
                  ".claude.json.bak-20200101000000.old", ".claude.json.bak-202001010000001",
                  ".claude.json.20260929-pre-fix.bak", "other.json.bak-20200101000000"]
        for i, name in enumerate(others + [f".claude.json.bak-2020010100000{n}" for n in range(4)]):
            (w.home / name).write_text(f"{i}")
        before = {n: (w.home / n).read_bytes() for n in others}
        w.run().ok()
        w.apply().ok()
        for n in others:
            expect((w.home / n).exists() and (w.home / n).read_bytes() == before[n],
                   f"{n} was pruned or changed")
        mine = [b for b in backups(cfg) if re.search(r"\.bak-\d{14}$", b)]
        expect(len(mine) == 3, f"the prune kept {len(mine)} of its own: {mine}")


@case
def json_format_preserved():
    with world() as w:
        w.std("csa-zendesk")
        # 4-space indent, no trailing newline, keys out of order, raw and escaped non-ASCII, a
        # lone surrogate (valid JSON, and JS writes it escaped), and an exponent number.
        raw = ('{\n    "zeta": "caf\u00e9 \\u2615",\n    "lone": "\\ud800",\n'
               '    "mcpServers": {\n        "csa-zendesk": {\n'
               f'            "command": "{gone(w, "csa-zendesk")}",\n'
               '            "env": {}\n        }\n    },\n    "alpha": [],\n    "n": 1.5e3\n}')
        cfg = w.claude(raw=raw)
        w.gemini(raw='{\n\t"mcpServers": {\n\t\t"csa-zendesk": {\n\t\t\t"command": "%s"\n\t\t}\n'
                     '\t}\n}\n' % gone(w, "csa-zendesk"))
        w.run().ok()
        a = w.apply()
        a.ok()
        text = cfg.read_text(encoding="utf-8")
        expect(entry_of(cfg, "csa-zendesk")["command"] == std_bin(w, "csa-zendesk"), "not re-pointed")
        expect(text.split("\n")[1].startswith('    "zeta"'), f"indent lost: {text[:40]!r}")
        expect(not text.endswith("\n"), "a trailing newline was added")
        expect(list(json.loads(text)) == ["zeta", "lone", "mcpServers", "alpha", "n"],
               "key order changed")
        expect("caf\u00e9" in text, "non-ASCII was escaped (ensure_ascii)")
        expect('"\\ud800"' in text, "a lone surrogate was not written back escaped")
        before, after = json.loads(raw), json.loads(text)
        after["mcpServers"]["csa-zendesk"]["command"] = before["mcpServers"]["csa-zendesk"]["command"]
        expect(after == before, "a value changed")
        gem = (w.home / ".gemini" / "settings.json").read_text()
        expect(gem.split("\n")[1].startswith('\t"mcpServers"') and gem.endswith("}\n"),
               f"tab indent or trailing newline lost: {gem!r}")


@case
def codex_line_edit_keeps_other_fields():
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.codex_toml({"csa-zendesk": {"command": gone(w, "csa-zendesk"),
                                            "env": {"CSA_ZD_ALLOWLIST_WRITE": SECRET_A}}})
        before = cfg.read_text().split("\n")
        w.run().ok()
        a = w.apply()
        a.ok()
        after = cfg.read_text().split("\n")
        changed = [(b, c) for b, c in zip(before, after) if b != c]
        expect(len(before) == len(after) and len(changed) == 1,
               f"more than the command line changed: {changed}")
        expect(changed[0][1] == f'command = "{std_bin(w, "csa-zendesk")}"', f"{changed}")
        for line in ("startup_timeout_sec = 30", "enabled = true", 'env_vars = ["HOME"]'):
            expect(line in after, f"{line!r} lost")
        expect(stat.S_IMODE(os.stat(cfg).st_mode) == 0o600, "the mode changed")
        expect(any(o.startswith("csa-zendesk re-pointed in Codex") for o in a.oks), f"{a.oks}")
    with world() as w:
        # The interpreter form: args become [] on its own line, and nothing else changes.
        w.std("csa-zendesk")
        cfg = w.codex_toml({"csa-zendesk": {"command": str(w.tmp / "gone" / "python3"),
                                            "args": ["-m", "csa_zendesk.server"]}})
        before = cfg.read_text().split("\n")
        w.run().ok()
        w.apply().ok()
        after = cfg.read_text().split("\n")
        changed = [c for b, c in zip(before, after) if b != c]
        expect(changed == [f'command = "{std_bin(w, "csa-zendesk")}"', "args = []"],
               f"changed lines: {changed}")


@case
def codex_quoted_table_header():
    with world() as w:
        w.std("csa-zendesk")
        listing = [{"name": "csa-zendesk", "transport": {"type": "stdio",
                                                          "command": gone(w, "csa-zendesk")}}]
        raw = ('[mcp_servers."csa-zendesk"]\n'
               f'command = "{gone(w, "csa-zendesk")}"  # set by hand\n'
               "startup_timeout_sec = 30\n")
        cfg = w.codex_toml(raw=raw, listing=listing)
        w.run().ok()
        a = w.apply()
        a.ok()
        want = (f'[mcp_servers."csa-zendesk"]\ncommand = "{std_bin(w, "csa-zendesk")}"  # set by hand\n'
                "startup_timeout_sec = 30\n")
        expect(cfg.read_text() == want, f"got {cfg.read_text()!r}")


@case
def codex_multiline_args_refused():
    with world() as w:
        w.std("csa-zendesk")
        py = str(w.tmp / "gone" / "python3")
        listing = [{"name": "csa-zendesk", "transport": {
            "type": "stdio", "command": py, "args": ["-m", "csa_zendesk.server"]}}]
        raw = (f'[mcp_servers.csa-zendesk]\ncommand = "{py}"\n'
               'args = [\n  "-m",\n  "csa_zendesk.server",\n]\n')
        cfg = w.codex_toml(raw=raw, listing=listing)
        before = state(cfg)
        w.run().ok()
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a multi-line args array was edited")
        expect(a.warned(R_CODEX_LAYOUT), f"no warning: {a.warns}")
        expect(any(R_CODEX_LAYOUT in t for t in a.todo_titles(40)), f"ledger: {a.todos}")
        expect(backups(cfg) == [], "a backup was made for a refused edit")


@case
def codex_readback_mismatch_restores():
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.codex_toml({"csa-zendesk": {"command": gone(w, "csa-zendesk")}},
                           tamper="csa-zendesk")
        original = cfg.read_bytes()
        w.run().ok()
        a = w.apply()
        a.ok()
        expect(cfg.read_bytes() == original, "a read-back mismatch did not restore the backup")
        expect(stat.S_IMODE(os.stat(cfg).st_mode) == 0o600, "the restore changed the mode")
        expect(a.warned("restored"), f"no warning: {a.warns}")
        expect(not a.oks, f"an ok line for a restored edit: {a.oks}")


@case
def gemini_extra_fields_kept():
    with world() as w:
        w.std("csa-zendesk")
        old = reg(gone(w, "csa-zendesk"), env={"K": SECRET_A}, trust=True,
                  includeTools=["get_ticket"], excludeTools=["x"], timeout=5000, cwd="/tmp")
        cfg = w.gemini({"csa-zendesk": old})
        w.run().ok()
        a = w.apply()
        a.ok()
        got = entry_of(cfg, "csa-zendesk")
        expect(got["command"] == std_bin(w, "csa-zendesk"), "not re-pointed")
        expect({k: v for k, v in got.items() if k != "command"}
               == {k: v for k, v in old.items() if k != "command"}, f"got {got}")
        expect(a.has_todo(10, "Restart Gemini"), f"ledger: {a.todos}")


@case
def unapproved_finding_not_repaired():
    with world() as w:
        # Found after the plan: not in it at all.
        w.std("csa-zendesk")
        cfg = w.claude(user={})
        w.run().ok()
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a finding the plan did not show was written")
        expect(a.warned(R_UNAPPROVED), f"no warning: {a.warns}")
    with world() as w:
        # In the plan, but left there (Desktop was running); now it could be re-pointed.
        w.std("csa-zendesk")
        w.ps("/Applications/Claude.app/Contents/MacOS/Claude")
        cfg = w.desktop({"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk", "Claude Desktop")["action"] == "leave", "fixture: not left")
        w.ps()
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a finding the plan left was re-pointed")
        expect(a.warns and not a.oks, f"warns {a.warns}, oks {a.oks}")


@case
def changed_since_plan_not_written():
    with world() as w:
        w.std("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        cfg = w.claude(user={"csa-zendesk": reg(w.tmp / "elsewhere" / "csa-zendesk-mcp")})
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a registration that changed since the plan was written")
        expect(a.warned(R_UNAPPROVED), f"no warning: {a.warns}")


@case
def unreadable_plan_file_applies_nothing():
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        before = state(cfg)
        bad = w.tmp / "bad.json"
        a_dir = w.tmp / "a-dir"
        a_dir.mkdir()
        for content, path in (("{not json", bad), ("", bad), ('{"tool": "other", "findings": []}', bad),
                              ('{"tool": "csa-mcp-registrations", "findings": {}}', bad),
                              (None, w.tmp / "missing.json"), (None, a_dir)):
            if content is not None:
                path.write_text(content)
            a = w.apply(approved=path)
            a.ok()
            expect(state(cfg) == before, f"{content!r}: the config was written")
            expect(a.warned("could not be read"), f"{content!r}: no warning: {a.warns}")
            expect(not a.oks, f"{content!r}: {a.oks}")


@case
def concurrent_change_aborts_write():
    with world() as w:
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        moved = {}

        def touch(point, path):
            if point == "written" and not moved:
                moved[path] = True
                Path(path).write_text(Path(path).read_text() + " ")

        mod.TEST_HOOK = touch
        a = w.apply_inproc(mod)
        a.ok()
        expect(moved, "the hook did not run")
        expect(entry_of(cfg, "csa-zendesk")["command"] == gone(w, "csa-zendesk"),
               "written over a change made after the read")
        expect(a.warned(R_CHANGED), f"no warning: {a.warns}")
        expect(sorted(os.listdir(w.home)) == sorted([".claude.json", ".local"]),
               f"a temp file or backup was left: {sorted(os.listdir(w.home))}")
    with world() as w:
        # The entry's settings change between the audit and the read: the in-write fingerprint.
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"A": "1"})})
        w.run().ok()

        def rekey(point, path):
            if point == "edit":
                w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"B": "1"})})

        mod.TEST_HOOK = rekey
        a = w.apply_inproc(mod)
        a.ok()
        expect(entry_of(cfg, "csa-zendesk")["command"] == gone(w, "csa-zendesk"),
               "written although its settings changed after the audit")
        expect(a.warned(R_CHANGED), f"no warning: {a.warns}")
    with world() as w:
        # Its mode is tightened after the read: the replace would have loosened it again.
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        mod.TEST_HOOK = lambda point, path: os.chmod(path, 0o400) if point == "written" else None
        a = w.apply_inproc(mod)
        a.ok()
        expect(stat.S_IMODE(os.stat(cfg).st_mode) == 0o400, "a mode tightened meanwhile was undone")
        expect(a.warned(R_CHANGED), f"no warning: {a.warns}")


@case
def abandoned_write_leaves_no_backup():
    for point in ("written", "backed-up"):  # an abort at step 5, then at step 7
        with world() as w:
            mod = load_module()
            w.std("csa-zendesk")
            cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
            for i in (1, 2, 3, 4):  # one more than the prune keeps: no prune may run either
                (w.home / f".claude.json.bak-2020010100000{i}").write_text("{}")
            w.run().ok()
            before = backups(cfg)

            def touch(at, path, point=point):
                if at == point:
                    Path(path).write_text(Path(path).read_text() + " ")

            mod.TEST_HOOK = touch
            a = w.apply_inproc(mod)
            a.ok()
            expect(a.warned(R_CHANGED), f"{point}: no warning: {a.warns}")
            expect(backups(cfg) == before, f"{point}: backups {backups(cfg)}, were {before}")
            stray = [n for n in os.listdir(w.home) if n.startswith(".csa-registrations-")]
            expect(not stray, f"{point}: temp file left: {stray}")


@case
def readback_mismatch_restores():
    with world() as w:
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
        for i in (1, 2, 3):
            (w.home / f".claude.json.bak-2020010100000{i}").write_text("{}")
        original = cfg.read_bytes()
        w.run().ok()

        def spoil(point, path):
            if point == "replaced":
                data = json.loads(Path(path).read_text())
                data["mcpServers"]["csa-zendesk"]["command"] = "/somewhere/else"
                with open(path, "r+") as f:  # in place: the file this run wrote, now wrong
                    f.write(json.dumps(data, indent=2))
                    f.truncate()

        mod.TEST_HOOK = spoil
        a = w.apply_inproc(mod)
        a.ok()
        expect(cfg.read_bytes() == original, "a read-back mismatch did not restore the backup")
        expect(stat.S_IMODE(os.stat(cfg).st_mode) == 0o600, "the restore changed the mode")
        expect(a.warned("restored"), f"no warning: {a.warns}")
        expect(len(backups(cfg)) == 4, f"pruned after a failed read-back: {backups(cfg)}")


@case
def claude_lock_honoured():
    # M1: Claude Code takes `<config>.lock`, a directory, for each write, and waits for one
    # someone else holds. apply takes it the same way, waits a bounded time, and never breaks it.
    with world() as w:
        mod = load_module()
        mod.CLAUDE_LOCK_WAIT = 0.5
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        gem = w.gemini({"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        lock = w.home / ".claude.json.lock"
        lock.mkdir()
        w.run().ok()
        before = state(cfg)
        a = w.apply_inproc(mod)
        a.ok()
        expect(state(cfg) == before, "written while Claude Code's lock was held")
        expect(lock.is_dir(), "the lock someone else held was removed")
        titles = [t for t in a.todo_titles(10) if t.startswith(T_LOCKED)]
        # Closing Claude Code does not clear a crashed process's lock: the to-do says how.
        expect(titles and titles[0].endswith(
            "; if Claude Code is not running, remove ~/.claude.json.lock"), f"ledger: {a.todos}")
        expect(entry_of(gem, "csa-zendesk")["command"] == std_bin(w, "csa-zendesk"),
               "a locked Claude Code config stopped the other clients' repairs")
    with world() as w:
        # Released while apply waits: it then writes, holding the lock across the write.
        mod = load_module()
        mod.CLAUDE_LOCK_WAIT = 20
        w.std("csa-zendesk")
        ccdir = w.tmp / "ccdir"
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))}, at=ccdir / ".claude.json")
        w.extra_env["CLAUDE_CONFIG_DIR"] = str(ccdir)
        lock = ccdir / ".claude.json.lock"
        lock.mkdir()
        w.run().ok()
        held = []
        mod.TEST_HOOK = lambda point, path: held.append((point, lock.is_dir()))
        import threading
        timer = threading.Timer(0.4, lambda: os.rmdir(lock))
        timer.start()
        try:
            a = w.apply_inproc(mod)
        finally:
            timer.cancel()
        a.ok()
        expect(entry_of(cfg, "csa-zendesk")["command"] == std_bin(w, "csa-zendesk"),
               f"not written after the lock was released: {a.warns}")
        during = [h for p, h in held if p in ("read", "written", "backed-up", "replaced")]
        expect(during and all(during), f"the lock was not held across the write: {held}")
        expect(not lock.exists(), "apply left its lock behind")


@case
def standard_binary_missing_no_repoint():
    with world() as w:
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "re-pointed at a standard binary that is not there")
        expect(a.warned(R_NO_STANDARD), f"no warning: {a.warns}")
        expect(any(R_NO_STANDARD in t for t in a.todo_titles(40)), f"ledger: {a.todos}")
    with world() as w:
        # There, but its Python is gone: not installed in any sense that runs.
        w.std("csa-zendesk", python=w.gone_python, home=w.gone_home)
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "re-pointed at a dead standard binary")
        expect(a.warned(R_NO_STANDARD), f"no warning: {a.warns}")


@case
def desktop_started_after_plan_skipped():
    with world() as w:
        # Started between the plan and apply.
        w.std("csa-zendesk")
        cfg = w.desktop({"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk", "Claude Desktop")["action"] == "re-point", "fixture")
        w.ps("/Applications/Claude.app/Contents/MacOS/Claude")
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "written after Desktop started")
        expect(a.has_todo(10, T_QUIT_DESKTOP), f"ledger: {a.todos}")
        expect(a.warned("Claude Desktop is running"), f"no warning: {a.warns}")
    with world() as w:
        # Started during apply, after its audit and before the write: `ps` answers "not
        # running" twice (the plan, then apply's audit) and "running" from then on.
        w.std("csa-zendesk")
        cfg = w.desktop({"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        count = w.tmp / "ps.count"
        w.stub("ps", f'n=$(cat "{count}" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "{count}"\n'
                     'if [ "$n" -ge 3 ]; then echo /Applications/Claude.app/Contents/MacOS/Claude; fi\n'
                     "exit 0")
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk", "Claude Desktop")["action"] == "re-point", "fixture")
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "written although Desktop started during apply")
        expect(a.has_todo(10, T_QUIT_DESKTOP), f"ledger: {a.todos}")


@case
def secret_values_never_emitted():
    with world() as w:
        four_dead(w)
        r = w.run()
        r.ok()
        a = w.apply()
        a.ok()
        expect(len(a.oks) == 4, f"expected four re-points: {a.oks} / {a.warns}")
        for s in SECRETS:
            for where, text in (("plan stdout", r.stdout), ("plan stderr", r.stderr),
                                ("plan file", r.plan_text), ("apply stdout", a.stdout),
                                ("apply stderr", a.stderr), ("ledger", a.ledger_text),
                                ("stub log", w.log.read_text())):
                expect(s not in text, f"a secret value reached the {where}")
        configs = (w.home / ".claude.json", desktop_cfg(w), w.home / ".gemini" / "settings.json",
                   w.home / ".codex" / "config.toml")
        text = "".join(p.read_text() for p in configs)
        for s in SECRETS:
            expect(s in text, "a secret value was not carried into the repaired config")


@case
def no_client_cli_writes():
    with world() as w:
        four_dead(w)
        w.run().ok()
        w.log.write_text("")
        a = w.apply()
        a.ok()
        expect(len(a.oks) == 4, f"expected four re-points: {a.oks} / {a.warns}")
        calls = [ln for ln in w.stub_log() if not ln.startswith(("codex-cwd ", "ps "))]
        allowed = re.compile(r"^codex mcp (list --json|get csa-[a-z-]+ --json)$")
        bad = [ln for ln in calls if not allowed.match(ln)]
        expect(not bad, f"client calls other than `codex mcp list|get --json`: {bad}")
        expect(any(ln.startswith("codex mcp get ") for ln in calls), "Codex was not read back")
        log = w.log.read_text()
        expect(not any(s in log for s in SECRETS), "a value reached a client's argv")
        cwds = [ln.split()[1:] for ln in w.stub_log() if ln.startswith("codex-cwd ")]
        expect(cwds and all(n == "0" and c != str(w.tmp) and not os.path.exists(c)
                            for c, n in cwds),
               f"a client call ran outside a fresh empty directory: {cwds}")


@case
def todo_per_client_restart():
    with world() as w:
        four_dead(w)
        w.run().ok()
        a = w.apply()
        a.ok()
        for client in ("Claude Code", "Claude Desktop", "Codex", "Gemini"):
            title = f"Restart {client}"
            expect(a.todos.count(("10", title, "-", "-")) == 1, f"{title}: ledger {a.todos}")
        expect(not a.infos, f"info lines with a ledger: {a.infos}")


@case
def todo_printed_without_ledger():
    with world() as w:
        four_dead(w)
        w.run().ok()
        a = w.apply(ledger=False)
        a.ok()
        for client in ("Claude Code", "Claude Desktop", "Codex", "Gemini"):
            expect(f"Restart {client}" in a.infos, f"no info line for {client}: {a.infos}")
        expect(not w.ledger.exists(), "a ledger was written though none was set")


@case
def second_run_noop():
    with world() as w:
        four_dead(w)
        w.run().ok()
        w.apply().ok()
        configs = (w.home / ".claude.json", desktop_cfg(w), w.home / ".gemini" / "settings.json",
                   w.home / ".codex" / "config.toml")
        before = {p: state(p) for p in configs}
        listing = {p: sorted(os.listdir(p.parent)) for p in configs}
        r = w.run()
        r.ok()
        expect(all(f["action"] == "none" for f in r.plan["findings"]),
               f"a second plan proposes work: {[(f['client'], f['action']) for f in r.plan['findings']]}")
        a = w.apply()
        a.ok()
        expect(not a.oks and not a.warns, f"a second apply did something: {a.oks} {a.warns}")
        for p in configs:
            expect(state(p) == before[p], f"{p.name} changed on the second run")
            expect(sorted(os.listdir(p.parent)) == listing[p], f"{p.parent}: a new file")


@case
def backup_rule_matches_connectors():
    # A13: one backup name and one prune for both tools, so one cap bounds the copies.
    mod = load_module()
    spec = importlib.util.spec_from_file_location(
        "connectors", ROOT / "scripts" / "csa-claude-connectors.py")
    conn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conn)
    expect(mod.BACKUP_RE.pattern == conn.BACKUP_RE.pattern, f"{mod.BACKUP_RE.pattern!r}")
    expect(mod.BACKUPS_KEPT == conn.BACKUPS_KEPT == 3, f"kept {mod.BACKUPS_KEPT}")


@case
def apply_by_hand_replans_and_applies():
    # Without --approved, a person running it by hand sees the plan and it is applied, as
    # csa-claude-connectors.py --apply does.
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
        a = w.apply(approved=None, ledger=False)
        a.ok()
        rows = [ln for ln in a.stdout.splitlines() if ln.startswith("row\t")]
        expect(any("will be re-pointed" in r for r in rows), f"the plan was not shown: {rows}")
        expect(entry_of(cfg, "csa-zendesk")["command"] == std_bin(w, "csa-zendesk"), "not applied")
        expect(a.kinds.index("row") < a.kinds.index("ok"), "the plan was not shown first")
        expect(SECRET_A not in a.stdout + a.stderr, "a value was printed")


# ── The review of d39f719 ────────────────────────────────────────────────────────────────────

# Runs apply with a hook that, at one point of the write, says so and then waits, so a test
# can send it a real signal from outside at exactly that point.
SIGNAL_DRIVER = r'''
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("m", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
point, marker = sys.argv[2], sys.argv[3]

def hold(at, path):
    if at == "replaced" and point == "restoring":
        with open(path, "w") as f:  # the read-back then fails, and the backup is restored
            f.write("{}\n")
    if at == point:
        open(marker, "w").close()
        time.sleep(60)

mod.TEST_HOOK = hold
sys.exit(mod.main(sys.argv[4:]))
'''

# (signal, the point it lands at, exit status, what stderr says)
SIGNAL_POINTS = [
    (signal.SIGTERM, "locked", 143, b"stopped by a signal"),     # between the mkdir and its return
    (signal.SIGHUP, "temp-made", 129, b"stopped by a signal"),   # straight after the temp's open
    (signal.SIGTERM, "written", 143, b"stopped by a signal"),
    (signal.SIGHUP, "backed-up", 129, b"stopped by a signal"),
    (signal.SIGTERM, "restoring", 143, b"stopped by a signal"),  # mid-restore of a failed read-back
    (signal.SIGHUP, "swapped", 129, b"stopped by a signal"),     # just after the replace
    (signal.SIGINT, "written", 130, b"stopped by an interrupt"),
]


def send_self(sig):
    """A real signal to this process - only while apply's own handler is in place, so a test
    of a broken handler fails its check instead of killing the test run."""
    if signal.getsignal(sig) not in (signal.SIG_DFL, signal.SIG_IGN, signal.default_int_handler, None):
        os.kill(os.getpid(), sig)


class OsWith(object):
    """`os`, with some of its functions replaced: for a module under test, as mod.os."""

    def __init__(self, **replaced):
        self.replaced = replaced

    def __getattr__(self, name):
        return self.replaced.get(name) or getattr(os, name)


STOPS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)


def apply_stopped(w, mod):
    """apply in process, to its end or to the SystemExit a stop signal raises: (exit, result,
    the stop signals apply left held). Once stopped, apply holds them to the process's end; a
    test run goes on, so it drops any still pending (SIG_IGN discards a pending signal),
    unblocks them, and puts its own handlers back. Each starts at its default, whatever this
    run inherited: apply leaves a signal its caller ignores ignored (`check-all.sh &` ignores
    SIGINT, nohup SIGHUP), which is not what these cases test."""
    saved = {s: signal.getsignal(s) for s in STOPS}
    for s in STOPS:
        signal.signal(s, signal.default_int_handler if s == signal.SIGINT else signal.SIG_DFL)
    try:
        try:
            a = w.apply_inproc(mod)
            rc = a.rc
        except SystemExit as e:
            a, rc = None, e.code
        held = set(signal.pthread_sigmask(signal.SIG_BLOCK, [])) & set(STOPS)
    finally:
        for s in STOPS:
            signal.signal(s, signal.SIG_IGN)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, STOPS)
        for s, h in saved.items():
            signal.signal(s, h if h is not None else signal.SIG_DFL)
    return rc, a, held


@case
def signal_mid_write_leaves_nothing():
    # A signal anywhere in a write: no temp copy of the config (it holds the settings' values),
    # no backup made for a write that did not happen, Claude Code's lock released, one line on
    # stderr and no traceback (reviews of d39f719 and b417a67).
    for sig, point, status, said in SIGNAL_POINTS:
        with world() as w:
            w.std("csa-zendesk")
            cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
            w.run().ok()
            before = state(cfg)
            driver = w.tmp / "driver.py"
            driver.write_text(SIGNAL_DRIVER)
            marker = w.tmp / "at-point"
            # Each signal at its default in the child, whatever the runner ignores: apply
            # leaves a signal its caller ignores ignored (nohup), which is not this case.
            p = subprocess.Popen([sys.executable, "-I", str(driver), str(SCRIPT), point,
                                  str(marker)] + w.apply_argv("plan", []),
                                 env=w.apply_env(False), cwd=str(w.tmp),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 preexec_fn=lambda: [signal.signal(s, signal.SIG_DFL) for s in
                                                     (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)])
            try:
                deadline = time.time() + 120
                while not marker.exists() and p.poll() is None and time.time() < deadline:
                    time.sleep(0.05)
                expect(marker.exists(), f"{sig.name}: the write never reached {point}")
                p.send_signal(sig)
                _, err = p.communicate(timeout=60)
            finally:
                if p.poll() is None:
                    p.kill()
                    p.communicate()
            where = f"{sig.name} at {point}"
            expect(p.returncode == status, f"{where}: exit {p.returncode}: {err[-300:]!r}")
            left = sorted(n for n in os.listdir(w.home) if n not in (".claude.json", ".local"))
            if point == "restoring":
                # The restore did not finish: the backup is the good copy, and stays.
                expect(len(left) == 1 and left[0].startswith(".claude.json.bak-"),
                       f"{where}: left behind: {left}")
            elif point == "swapped":
                # The replace happened: the config is repaired, and its backup is kept.
                expect(len(left) == 1 and left[0].startswith(".claude.json.bak-"),
                       f"{where}: left behind: {left}")
                expect(entry_of(cfg, "csa-zendesk")["command"] == std_bin(w, "csa-zendesk"),
                       f"{where}: not repaired")
            else:
                expect(not left, f"{where}: left behind: {left}")
                expect(state(cfg) == before, f"{where}: the config changed")
            expect(said in err and b"Traceback" not in err, f"{where}: stderr {err[-300:]!r}")
            expect(SECRET_A.encode() not in err, f"{where}: a value reached stderr")
    with world() as w:
        # The handlers apply sets are the caller's again once it returns.
        mod = load_module()
        w.std("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        sigs = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)
        before = [signal.getsignal(s) for s in sigs]
        w.apply_inproc(mod).ok()
        after = [signal.getsignal(s) for s in sigs]
        expect(after == before, f"handlers not restored: {after} != {before}")
    for sig, status in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
        with world() as w:
            # A second stop signal during the clean-up the first started: ignored, so the
            # clean-up runs to its end (review of 79aa251: TERM+TERM and INT+INT left the
            # unused backup). Both are real signals, sent to this process.
            mod = load_module()
            w.std("csa-zendesk")
            cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
            w.run().ok()
            before = state(cfg)
            real_unlink = mod.unlink_quietly
            sent = []

            def second(path):
                if not sent:
                    sent.append(sig)
                    send_self(sig)
                real_unlink(path)

            mod.unlink_quietly = second
            mod.TEST_HOOK = lambda point, path: send_self(sig) if point == "backed-up" else None
            rc, _, after = apply_stopped(w, mod)
            left = sorted(n for n in os.listdir(w.home) if n not in (".claude.json", ".local"))
            expect(sent, f"{sig.name}: the clean-up was never reached")
            expect(rc == status, f"{sig.name}: exit {rc}")
            expect(not left, f"{sig.name}+{sig.name}: left behind: {left}")
            expect(state(cfg) == before, f"{sig.name}: the config changed")
            # And once stopped, the stop signals stay held to the process's end: Python's own
            # shutdown gives the handlers back to SIG_DFL, and a second signal then killed the
            # exit after "stopped" was printed (-15) or raised a traceback (review of 79aa251).
            expect(after >= set(STOPS), f"{sig.name}: not held after a stop: {sorted(after)}")
    with world() as w:
        # Two different stop signals already on their way together (HUP, then TERM): the
        # first stops apply, the second lands during its clean-up and is ignored.
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
        w.run().ok()
        before = state(cfg)
        both = {signal.SIGHUP, signal.SIGTERM}

        def together(point, path):
            if point == "backed-up":
                signal.pthread_sigmask(signal.SIG_BLOCK, both)
                send_self(signal.SIGHUP)
                send_self(signal.SIGTERM)
                signal.pthread_sigmask(signal.SIG_UNBLOCK, both)

        mod.TEST_HOOK = together
        rc, _, after = apply_stopped(w, mod)
        left = sorted(n for n in os.listdir(w.home) if n not in (".claude.json", ".local"))
        expect(rc == 129, f"HUP+TERM: exit {rc}")
        expect(not left, f"HUP+TERM together: left behind: {left}")
        expect(state(cfg) == before, "HUP+TERM: the config changed")
    with world() as w:
        # A signal the caller ignores (nohup ignores SIGHUP) stays ignored while apply runs.
        mod = load_module()
        old = signal.signal(signal.SIGHUP, signal.SIG_IGN)
        try:
            with mod.exits_on_signals():
                during = signal.getsignal(signal.SIGHUP)
        finally:
            signal.signal(signal.SIGHUP, old)
        expect(during == signal.SIG_IGN, f"an ignored SIGHUP was made to stop apply: {during}")


def ended_pid():
    """The pid of a process that has exited and been reaped."""
    p = subprocess.Popen(["/bin/sh", "-c", "exit 0"])
    p.wait()
    return p.pid


@case
def stale_temp_files_swept():
    # A temp file a stopped run left holds a config's secrets. The next apply removes this
    # tool's own, older than itself, in each config's directory - and nothing else.
    with world() as w:
        w.std("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
        w.desktop({})
        w.run().ok()
        old, future = time.time() - 3600, time.time() + 3600
        dead = ended_pid()
        live = os.getpid()  # this test: a run still going
        desktop_dir = desktop_cfg(w).parent
        stale = [w.home / f".csa-registrations-{dead}-ab12cd_9",
                 desktop_dir / f".csa-registrations-{dead}-0z9y8x7w"]
        kept = [w.home / f".csa-registrations-{live}-ab12cd_9",       # its run is alive
                w.home / f".csa-registrations-{dead}-ab12cd_8\n",      # `$` would match this
                w.home / f".csa-registrations-{dead}-keep.txt",
                w.home / f".csa-registrations-{dead}-ABCDEFGH",
                w.home / ".csa-registrations-ab12cd_9",                # no pid
                w.home / f"csa-registrations-{dead}-ab12cd_9",
                w.tmp / f".csa-registrations-{dead}-elsewher"]          # not a config's directory
        for p in stale + kept:
            p.write_text(SECRET_A)
            os.utime(p, (old, old))
        newer = w.home / f".csa-registrations-{dead}-zz99zz99"  # changed after the run began
        newer.write_text("x")
        os.utime(newer, (future, future))
        outside = w.tmp / "outside.txt"
        outside.write_text("outside")
        link = w.home / f".csa-registrations-{dead}-lnk00000"
        link.symlink_to(outside)
        os.utime(link, (old, old), follow_symlinks=False)
        a = w.apply()
        a.ok()
        for p in stale:
            expect(not os.path.lexists(p), f"{p.name!r}: a stale temp file was left")
        for p in kept + [newer, link]:
            expect(os.path.lexists(p), f"{p.name!r}: removed, though it is not a stale temp file")
        expect(outside.read_text() == "outside", "a link's target was touched")
        expect(any("stopped mid-write" in i for i in a.infos), f"not said: {a.infos}")
    with world() as w:
        # Another user's file is never removed: here every file reads as someone else's.
        mod = load_module()

        class OtherUser(object):
            def __getattr__(self, name):
                return getattr(os, name)

            @staticmethod
            def getuid():
                return os.getuid() + 1

        mod.os = OtherUser()
        w.claude(user={})
        w.run().ok()
        stale = w.home / f".csa-registrations-{ended_pid()}-ab12cd_9"
        stale.write_text("x")
        os.utime(stale, (time.time() - 3600,) * 2)
        w.apply_inproc(mod).ok()
        expect(stale.exists(), "another user's file was removed")
    with world() as w:
        # A run this one may not signal (EPERM: another user's process) may be alive: kept.
        mod = load_module()
        pid = ended_pid()

        def kill(target, sig):
            if target == pid:
                raise PermissionError(1, "Operation not permitted")
            return os.kill(target, sig)

        mod.os = OsWith(kill=kill)
        w.claude(user={})
        w.run().ok()
        stale = w.home / f".csa-registrations-{pid}-ab12cd_9"
        stale.write_text("x")
        os.utime(stale, (time.time() - 3600,) * 2)
        w.apply_inproc(mod).ok()
        expect(stale.exists(), "a file whose run could not be signalled was removed")
    with world() as w:
        # A config directory that is a link (A10) is not swept: nothing of this tool's is
        # written there, and the link's target is somebody's dotfiles.
        dots = w.tmp / "dotfiles" / "gemini"
        dots.mkdir(parents=True)
        (dots / "settings.json").write_text(json.dumps({"mcpServers": {}}))
        (w.home / ".gemini").symlink_to(dots)
        w.stub("gemini", "exit 0")
        w.run().ok()
        stale = dots / f".csa-registrations-{ended_pid()}-ab12cd_9"
        stale.write_text("x")
        os.utime(stale, (time.time() - 3600,) * 2)
        w.apply().ok()
        expect(stale.exists(), "a file was removed through a linked config directory")


@case
def desktop_state_unknown_at_write_skipped():
    # D4: `ps` answers at the audit and fails just before the write. "Could not tell" is not
    # "not running", so Desktop's config is not written.
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.desktop({"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        count = w.tmp / "ps.count"
        w.stub("ps", f'n=$(cat "{count}" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "{count}"\n'
                     'if [ "$n" -ge 3 ]; then exit 1; fi\nexit 0')
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk", "Claude Desktop")["action"] == "re-point", "fixture")
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "written when it could not be told whether Desktop runs")
        expect(a.warned("could not tell whether Claude Desktop is running"), f"{a.warns}")
        expect(a.has_todo(10, T_QUIT_DESKTOP), f"ledger: {a.todos}")


@case
def backup_name_never_overwritten():
    # The backup's name is claimed exclusively: whatever is already there - an earlier backup
    # made the same second, or a link to somewhere else - is never written over.
    for kind in ("file", "link"):
        with world() as w:
            mod = load_module()
            mod.backup_stamp = lambda: "20300101000000"
            w.std("csa-zendesk")
            cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
            w.run().ok()
            taken = w.home / ".claude.json.bak-20300101000000"
            outside = w.tmp / "outside.txt"
            outside.write_text("not a backup\n")
            if kind == "file":
                taken.write_text("an earlier backup\n")
            else:
                taken.symlink_to(outside)
            before = state(cfg)
            a = w.apply_inproc(mod)
            a.ok()
            expect(state(cfg) == before, f"{kind}: written without its own backup")
            expect(outside.read_text() == "not a backup\n", f"{kind}: written through the link")
            if kind == "file":
                expect(taken.read_text() == "an earlier backup\n", "an existing backup was overwritten")
            else:
                expect(taken.is_symlink(), "the link was replaced")
            expect(SECRET_A not in outside.read_text(), "a value reached another file")
            expect(a.warns and not a.oks, f"{kind}: warns {a.warns}, oks {a.oks}")


@case
def backup_looser_than_file_abandons():
    with world() as w:
        mod = load_module()

        class LooseShutil(object):
            def __getattr__(self, name):
                return getattr(__import__("shutil"), name)

            @staticmethod
            def copy2(src, dst):
                __import__("shutil").copy2(src, dst)
                os.chmod(dst, 0o644)

        mod.shutil = LooseShutil()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
        w.run().ok()
        before = state(cfg)
        a = w.apply_inproc(mod)
        a.ok()
        expect(state(cfg) == before, "written after a backup came out more permissive")
        expect(backups(cfg) == [], f"the permissive backup was left: {backups(cfg)}")
        expect(a.warned("more permissive"), f"no warning: {a.warns}")


@case
def codex_write_time_link_refused():
    # A10 for Codex too: config.toml becomes a link after the audit, before the write.
    with world() as w:
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.codex_toml({"csa-zendesk": {"command": gone(w, "csa-zendesk")}})
        w.run().ok()
        real = w.tmp / "dotfiles" / "config.toml"
        real.parent.mkdir()

        def relink(point, path):
            if point == "edit" and not os.path.islink(path):
                os.replace(path, real)
                os.symlink(real, path)

        mod.TEST_HOOK = relink
        a = w.apply_inproc(mod)
        a.ok()
        expect(os.path.islink(cfg) and os.readlink(cfg) == str(real), "the link was replaced")
        expect(gone(w, "csa-zendesk") in real.read_text(), "written through the link")
        expect(a.warned("its config is a link to"), f"no warning: {a.warns}")
        expect(not a.oks, f"apply reported a re-point: {a.oks}")


@case
def non_finite_number_not_rewritten():
    # Python reads 1e999 as infinity and NaN as NaN; no JSON client reads `Infinity` or `NaN`
    # back. A config holding one is not rewritten.
    for name, raw_value in (("infinity", "1e999"), ("nan", "NaN")):
        with world() as w:
            w.std("csa-zendesk")
            raw = ('{\n  "big": %s,\n  "mcpServers": {\n    "csa-zendesk": {\n'
                   '      "command": "%s"\n    }\n  }\n}\n' % (raw_value, gone(w, "csa-zendesk")))
            cfg = w.claude(raw=raw)
            w.run().ok()
            before = state(cfg)
            a = w.apply()
            a.ok()
            expect(state(cfg) == before, f"{name}: rewritten")
            expect(a.warned("cannot write back exactly"), f"{name}: {a.warns}")


@case
def codex_multiline_string_refused():
    # Lines are matched one at a time, and a multi-line string can hold a line that looks
    # like the header or the command: such a file is refused, not edited.
    with world() as w:
        # Inside the table.
        w.std("csa-zendesk")
        listing = [{"name": "csa-zendesk", "transport": {"type": "stdio",
                                                          "command": gone(w, "csa-zendesk")}}]
        raw = ('[mcp_servers.csa-zendesk]\n'
               f'command = "{gone(w, "csa-zendesk")}"\n'
               'cwd = """\n/tmp"""\n')
        cfg = w.codex_toml(raw=raw, listing=listing)
        w.run().ok()
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a table holding a multi-line string was edited")
        expect(a.warned(R_CODEX_LAYOUT), f"no layout warning: {a.warns}")
        expect(any(R_CODEX_LAYOUT in t for t in a.todo_titles(40)), f"ledger: {a.todos}")
    with world() as w:
        # Above the header (review of d39f719): a look-alike header inside a string, and the
        # real table spelled `[mcp_servers.'csa-zendesk']`.
        w.std("csa-zendesk")
        g = gone(w, "csa-zendesk")
        listing = [{"name": "csa-zendesk", "transport": {"type": "stdio", "command": g}}]
        raw = ('notes = """\n[mcp_servers.csa-zendesk]\n'
               f'command = "{g}"\n[x]\n"""\n\n'
               "[mcp_servers.'csa-zendesk']\n"
               f'command = "{g}"\n')
        cfg = w.codex_toml(raw=raw, listing=listing)
        w.run().ok()
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a line inside another key's string was edited")
        expect(a.warned(R_CODEX_LAYOUT), f"no layout warning: {a.warns}")
        expect(backups(cfg) == [], "a backup was made for a refused edit")


@case
def hard_linked_config_refused():
    # A config with a second name: os.replace would give this name a new file and leave the
    # other with the old one, silently cut off.
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        toml = w.codex_toml({"csa-zendesk": {"command": gone(w, "csa-zendesk")}})
        other = [w.tmp / "claude-other-name.json", w.tmp / "codex-other-name.toml"]
        os.link(cfg, other[0])
        os.link(toml, other[1])
        w.run().ok()
        before = [state(cfg), state(toml)]
        a = w.apply()
        a.ok()
        expect([state(cfg), state(toml)] == before, "a hard-linked config was replaced")
        for path, name in ((cfg, other[0]), (toml, other[1])):
            expect(os.stat(path).st_ino == os.stat(name).st_ino, f"{path.name} was detached")
        expect(len(a.warned("hard link")) == 2, f"warns: {a.warns}")
        expect(not a.oks, f"oks: {a.oks}")
    with world() as w:
        # A hard link made after the read: the replace would still cut it off.
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        other = w.tmp / "claude-other-name.json"
        mod.TEST_HOOK = lambda point, path: os.link(path, other) if point == "written" else None
        before = Path(cfg).read_bytes()
        a = w.apply_inproc(mod)
        a.ok()
        expect(Path(cfg).read_bytes() == before, "written over a hard link made after the read")
        expect(os.stat(cfg).st_ino == os.stat(other).st_ino, "the other name was cut off")
        expect(a.warned(R_CHANGED), f"warns: {a.warns}")


@case
def confinement_check_refuses_a_damaged_entry():
    # The entry built for the write must differ from the one read in its command (and args)
    # only. The read-back compares with that built entry, so it cannot catch damage done in
    # building it: this check is what does (review of b417a67).
    def drop_env(entry, command, args):
        return {k: (command if k == "command" else v) for k, v in entry.items() if k != "env"}

    def add_key(entry, command, args):
        return dict(entry, command=command, extra=True)

    def reorder(entry, command, args):
        return dict(reversed(list(dict(entry, command=command).items())))

    def change_value(entry, command, args):
        return dict(entry, command=command, env={"K": "other"})

    for damage in (drop_env, add_key, reorder, change_value):
        with world() as w:
            mod = load_module()
            mod.repointed = damage
            w.std("csa-zendesk")
            cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
            w.run().ok()
            before = state(cfg)
            a = w.apply_inproc(mod)
            a.ok()
            name = damage.__name__
            expect(state(cfg) == before, f"{name}: the damaged entry was written")
            expect(a.warned("could not be confined to its command"), f"{name}: {a.warns}")
            expect(not a.oks, f"{name}: ok printed: {a.oks}")


@case
def lock_held_too_long_abandons():
    # Held near Claude Code's 10 s stale limit, the write is abandoned: Claude Code may take
    # the lock over, and two writers would race.
    with world() as w:
        mod = load_module()
        mod.LOCK_HOLD_MAX = 0.3
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        mod.TEST_HOOK = lambda point, path: time.sleep(0.6) if point == "backed-up" else None
        before = state(cfg)
        a = w.apply_inproc(mod)
        a.ok()
        expect(state(cfg) == before, "written after holding the lock too long")
        expect(backups(cfg) == [], f"a backup was left: {backups(cfg)}")
        temps = [n for n in os.listdir(w.home) if n.startswith(".csa-registrations-")]
        expect(not temps, f"the temp copy of the config was left: {temps}")
        expect(a.warned("held Claude Code's lock for more than"), f"{a.warns}")
        expect(not (w.home / ".claude.json.lock").exists(), "its own lock was left")


@case
def lock_taken_over_is_left():
    # Claude Code took the lock over mid-write (after its stale limit): the write is
    # abandoned, and the lock - Claude Code's now - is not removed.
    with world() as w:
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        lock = w.home / ".claude.json.lock"

        def take_over(point, path):
            if point == "written":
                os.rmdir(lock)
                os.mkdir(lock)
                t = time.time() + 5  # proper-lockfile stamps its lock's mtime
                os.utime(lock, (t, t))

        mod.TEST_HOOK = take_over
        before = state(cfg)
        a = w.apply_inproc(mod)
        a.ok()
        expect(state(cfg) == before, "written under a lock that was no longer this run's")
        expect(lock.is_dir(), "Claude Code's lock was removed")
        expect(a.warned("stopped being this run's"), f"{a.warns}")


@case
def lock_never_removed_without_proof():
    # The rule: this run removes Claude Code's lock only when it can prove it made it - the
    # identity it recorded with the mkdir. An exception on the way, a signal included, must
    # never remove a lock that is somebody else's (review of 79aa251: one removed Claude Code's
    # held lock, deterministically with an interrupt raised from os.mkdir).
    for raised in (KeyboardInterrupt(), SystemExit(143)):
        with world() as w:
            mod = load_module()
            w.std("csa-zendesk")
            w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
            w.run().ok()
            lock = w.home / ".claude.json.lock"
            lock.mkdir()  # Claude Code holds it
            held = os.lstat(lock).st_ino

            def mkdir(path, *a, **k):
                raise raised

            mod.os = OsWith(mkdir=mkdir)
            rc, _, after = apply_stopped(w, mod)
            what = type(raised).__name__
            expect(rc in (130, 143), f"{what}: exit {rc}")
            expect(lock.is_dir() and os.lstat(lock).st_ino == held,
                   f"{what} from os.mkdir removed the lock somebody else holds")
    with world() as w:
        # A real signal between this run's mkdir and the record of it: held until the record
        # exists, so the lock - this run's - is then removed, not left for every later run.
        mod = load_module()
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        w.run().ok()
        real_identity = mod.dir_identity
        sent = []

        def identity_then_signal(path):
            if not sent and str(path).endswith(".lock"):
                sent.append(path)
                send_self(signal.SIGTERM)
            return real_identity(path)

        mod.dir_identity = identity_then_signal
        before = state(cfg)
        rc, _, after = apply_stopped(w, mod)
        expect(sent, "the mkdir was never reached")
        expect(rc == 143, f"exit {rc}")
        expect(not (w.home / ".claude.json.lock").exists(), "this run's own lock was left")
        expect(state(cfg) == before, "the config changed")


@case
def signals_held_keeps_the_callers_mask():
    # signals_held holds the stop signals for its block, then puts back the mask it found: one
    # the caller had already blocked stays blocked, and the rest are free again (review of
    # f566ac2: unblocking its own set instead would unblock the caller's too).
    mod = load_module()
    old = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGHUP})
    try:
        with mod.signals_held():
            inside = set(signal.pthread_sigmask(signal.SIG_BLOCK, []))
        after = set(signal.pthread_sigmask(signal.SIG_BLOCK, []))
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old)
    expect(inside >= set(STOPS), f"not held inside: {sorted(inside)}")
    expect(signal.SIGHUP in after, "a signal the caller had blocked was unblocked")
    expect(not ({signal.SIGTERM, signal.SIGINT} & after), f"left held: {sorted(after)}")


@case
def temp_files_are_this_runs_alone():
    # A temp file is created 0600 with O_EXCL under this run's own pid, and only names this
    # run created are ever removed: never one somebody else holds (review of 79aa251).
    taken = "aaaaaaaa"

    class FirstNameTaken(object):
        """`secrets`, whose first eight choices spell the name another process holds."""

        def __init__(self):
            self.chars = iter(taken)

        def choice(self, alphabet):
            return next(self.chars, None) or secrets.choice(alphabet)

    def names_after_a_taken_one(mod):
        mod.secrets = FirstNameTaken()

    for signalled in (False, True):
        with world() as w:
            mod = load_module()
            names_after_a_taken_one(mod)
            w.std("csa-zendesk")
            cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
            w.run().ok()
            planted = w.home / f".csa-registrations-{os.getpid()}-{taken}"
            planted.write_text("somebody else's\n")
            seen = {}

            def hook(point, path):
                if point == "temp-made":
                    seen["name"] = os.path.basename(path)
                    seen["mode"] = stat.S_IMODE(os.stat(path).st_mode)
                if point == "written" and signalled:
                    send_self(signal.SIGTERM)

            mod.TEST_HOOK = hook
            before = state(cfg)
            rc, _, after = apply_stopped(w, mod)
            how = "signalled" if signalled else "plain"
            expect(planted.exists() and planted.read_text() == "somebody else's\n",
                   f"{how}: a file this run did not create was written or removed")
            expect(seen.get("mode") == 0o600, f"{how}: the temp was {oct(seen.get('mode', 0))} "
                                              "at its creation")
            expect(f"-{os.getpid()}-" in seen.get("name", ""), f"{how}: not this run's pid: {seen}")
            ours = [n for n in os.listdir(w.home) if n.startswith(".csa-registrations-")
                    and n != planted.name]
            expect(not ours, f"{how}: this run's temp file was left: {ours}")
            if signalled:
                expect(rc == 143 and state(cfg) == before, f"{how}: exit {rc}, or the config changed")
            else:
                expect(entry_of(cfg, "csa-zendesk")["command"] == std_bin(w, "csa-zendesk"),
                       f"{how}: not repaired")
    for kind in ("temp", "backup"):
        with world() as w:
            # A real signal between a create and its record: held until the record exists, so
            # the file is removed, not left holding the config's secrets (or empty).
            mod = load_module()
            w.std("csa-zendesk")
            cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
            w.run().ok()
            sent = []

            def open_then_signal(path, *a, **k):
                fd = os.open(path, *a, **k)
                mine = (os.path.basename(str(path)).startswith(".csa-registrations-")
                        if kind == "temp" else ".bak-" in str(path))
                if mine and not sent:
                    sent.append(path)
                    send_self(signal.SIGTERM)
                return fd

            mod.os = OsWith(open=open_then_signal)
            before = state(cfg)
            rc, _, after = apply_stopped(w, mod)
            left = sorted(n for n in os.listdir(w.home) if n not in (".claude.json", ".local"))
            expect(sent, f"{kind}: the create was never reached")
            expect(rc == 143, f"{kind}: exit {rc}")
            expect(not left, f"{kind}: left behind: {left}")
            expect(state(cfg) == before, f"{kind}: the config changed")


@case
def approval_binds_config_path():
    # The same registration, with the same fingerprint, in another file (another
    # CLAUDE_CONFIG_DIR) is not the one the plan showed.
    with world() as w:
        w.std("csa-zendesk")
        entry = {"csa-zendesk": reg(gone(w, "csa-zendesk"))}
        w.claude(user=entry, at=w.tmp / "a" / ".claude.json")
        other = w.claude(user=entry, at=w.tmp / "b" / ".claude.json")
        w.extra_env["CLAUDE_CONFIG_DIR"] = str(w.tmp / "a")
        r = w.run()
        r.ok()
        expect(r.f("csa-zendesk")["config"] == str(w.tmp / "a" / ".claude.json"),
               f"the plan file does not record the config: {r.f('csa-zendesk').get('config')}")
        w.extra_env["CLAUDE_CONFIG_DIR"] = str(w.tmp / "b")
        before = state(other)
        a = w.apply()
        a.ok()
        expect(state(other) == before, "a file the plan did not show was written")
        expect(a.warned(R_UNAPPROVED), f"{a.warns}")


@case
def write_failure_says_no_value():
    # A write that fails is reported by type and this script's line, never by the exception's
    # text, which can carry what it was handed - a setting's value included.
    with world() as w:
        mod = load_module()

        def fail(*a, **k):
            raise RuntimeError(f"could not write {SECRET_A}")

        mod.write_temp = fail
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"), env={"K": SECRET_A})})
        w.run().ok()
        before = state(cfg)
        a = w.apply_inproc(mod)
        a.ok()
        expect(state(cfg) == before, "the config changed")
        expect(a.warned("could not be written (RuntimeError at line"), f"{a.warns}")
        expect(SECRET_A not in a.stdout + a.stderr + a.ledger_text, "the exception's text was printed")


@case
def duplicate_plan_row_resolves_to_leave():
    # A plan file listing one registration both as a re-point and as left: left.
    with world() as w:
        w.std("csa-zendesk")
        cfg = w.claude(user={"csa-zendesk": reg(gone(w, "csa-zendesk"))})
        r = w.run()
        r.ok()
        doc = json.loads(w.out.read_text())
        row = dict(doc["findings"][0])
        expect(row["action"] == "re-point", "fixture")
        row["action"] = "leave"
        doc["findings"].append(row)
        w.out.write_text(json.dumps(doc))
        before = state(cfg)
        a = w.apply()
        a.ok()
        expect(state(cfg) == before, "a row listed as both re-point and left was re-pointed")
        expect(a.warns and not a.oks, f"warns {a.warns}, oks {a.oks}")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# verify (Task 3): each registered server answers an MCP initialize handshake, launched with its
# registered command and settings - one at a time, bounded, and with no secret in what it prints
# ═════════════════════════════════════════════════════════════════════════════════════════════

# Verbatim from the plan, Task 3, except where a comment says why not.
OK_CHECK = ("answers an MCP initialize handshake, launched with its registered command and "
            "settings")
N_LAUNCHER = "not checked: launcher form"
N_DOLLAR = "not checked: its environment uses $-expansion, which this check does not reproduce"
N_DEAD = "does not start: "
# The plan's to-do, and how to see why: the command only, never its args or env (review of
# bbb6f82).
T_NO_ANSWER = ("{name} did not answer when launched with its {client} registration's command "
               "and settings; to see its own messages, run {command} in a terminal")


def no_answer(name, client=None):
    return T_NO_ANSWER.format(name=name, client=client or "Claude Code (user scope)",
                              command=f"~/.local/bin/{SPEC[name][0]}")
# Not the plan's "...held until its effect on tokens is measured": M5 has measured it
# (2026-11-13), and the hold now waits on D5's answer. Reworded under P2, honesty.
HELD = ('server check held: whether a rerun launches the CSA servers to check them is not '
        'decided yet (#179, D5); run "verify --run" to check by hand')
CC_USER = "Claude Code (user scope)"


def ok_line(name, clients):
    return f"{name} {OK_CHECK} ({clients})"


# Every line verify may print, as a pattern whose only holes are this file's own words: a CSA
# server name, a client, an integer, the timeout, and the standard binary's command. Whatever a
# server says, of any length, has nowhere to go (review of bbb6f82).
_NAMES = "|".join(re.escape(n) for n in SPEC)
_CLIENT = r"Claude Code \(user scope\)|Claude Desktop|Codex|Gemini"
_CLIENTS = rf"(?:{_CLIENT})(?:, (?:{_CLIENT}))*"
_WHY = "|".join((
    r"did not answer within \d+(?:\.\d+)?s",
    r"exited \((?:code|signal) \d+\) before answering",
    r"answered with a JSON-RPC error \(code -\d+\)",
    r"answered with a JSON-RPC error, its code outside the range JSON-RPC reserves",
    r"answered with something that is not a valid initialize result",
    r"could not be started \([A-Z0-9]+\)",
))
_TODO = (rf"(?:{_NAMES}) did not answer when launched with its (?:{_CLIENT}) registration's "
         r"command and settings; to see its own messages, run ~/\.local/bin/[a-z-]+ in a "
         r"terminal")
FIXED_LINES = [re.compile(p) for p in (
    rf"ok\t(?:{_NAMES}) {OK_CHECK} \({_CLIENTS}\)",
    rf"warn\t(?:{_NAMES}), launched with its registered command and settings \({_CLIENTS}\): "
    rf"(?:{_WHY})",
    rf"info\t(?:{_NAMES}) \({_CLIENTS}\): \d+ lines? on its stdout (?:was|were) not JSON, and "
    r"skipped",
    rf"info\t{_TODO}",
    rf"45\t{_TODO}\t-\t-",
)]


def not_fixed(*texts):
    """The lines of `texts` that are not one of verify's fixed lines."""
    return [ln for t in texts for ln in t.splitlines()
            if not any(p.fullmatch(ln) for p in FIXED_LINES)]


def grams(value, n=4):
    """Every run of `n` characters in `value`."""
    return {value[i:i + n] for i in range(len(value) - n + 1)}


def bare_keys():
    """The env keys this interpreter, or the OS, adds to a process started with none at all:
    on macOS __CF_USER_TEXT_ENCODING, and LC_CTYPE, which Python sets when no locale is (the
    measurement record, M3's Desktop part)."""
    r = subprocess.run([sys.executable, "-c", "import json, os; print(json.dumps(sorted(os.environ)))"],
                       env={}, capture_output=True, text=True, timeout=60, check=True)
    return set(json.loads(r.stdout))


def group_members(pgid):
    """The live (not zombie) processes left in a process group, polled for up to 2 s so the
    system can reap an orphan first."""
    ps = shutil.which("ps", path="/bin:/usr/bin")
    deadline = time.time() + 2
    while True:
        out = subprocess.run([ps, "-A", "-o", "pid=,pgid=,stat="], capture_output=True,
                             text=True, timeout=30).stdout
        live = [int(f[0]) for f in (ln.split() for ln in out.splitlines())
                if len(f) >= 3 and f[1] == str(pgid) and not f[2].startswith("Z")]
        if not live or time.time() >= deadline:
            return live
        time.sleep(0.1)


def kill_stub_groups(w):
    """Whatever a broken mutant left running, gone: the stubs' groups and grandchildren."""
    for e in w.server_log() if w.slog.exists() else []:
        for target, kill in ((e.get("pgid"), os.killpg), (e.get("child"), os.kill)):
            if target:
                try:
                    kill(target, signal.SIGKILL)
                except OSError:
                    pass


def partial_python(w):
    """An "interpreter" that fails the stdlib probe the audit makes (`-I -B -c ...` is no shell
    command line), yet runs a stub: a `python3.14` that is /bin/sh, a real binary the kernel
    will exec. A registration on it is dead, and launching it would still log a start."""
    p = w.tmp / "partial" / "bin" / "python3.14"
    p.parent.mkdir(parents=True)
    p.symlink_to("/bin/sh")
    return p


@case
def answers():
    with world() as w:
        w.std_server("csa-zendesk")
        w.claude(user={"csa-zendesk": reg("~/.local/bin/csa-zendesk-mcp",
                                          env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A})})
        a = w.verify()
        a.ok()
        want = ok_line("csa-zendesk", CC_USER)
        expect(a.oks == [want], f"oks {a.oks}, warns {a.warns}, infos {a.infos}")
        starts = w.starts()
        expect(len(starts) == 1, f"{len(starts)} launches")
        s = starts[0]
        expect(s["sid"] == s["pid"] == s["pgid"], "the server was not started in a session of its own")
        held = {int(x) for x in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)} & set(s["blocked"])
        expect(not held, f"the server started with the stop signals held: {sorted(held)}")
        expect(s["listing"] == 0 and s["cwd"] != str(w.tmp), f"not run in an empty directory: {s}")
        expect(not os.path.exists(s["cwd"]), "its working directory was left behind")
        expect("CSA_ZD_ALLOWLIST_WRITE" in s["keys"], "the registration's setting was not passed")
        recv = [e for e in w.server_log() if e["ev"] == "recv"]
        version = load_module().SCRIPT_VERSION
        expect(len(recv) == 1 and recv[0]["method"] == "initialize" and recv[0]["id"] == 1
               and recv[0]["protocolVersion"] == "2025-06-18"
               and recv[0]["client"] == {"name": "csa-desktopsetup-check", "version": version},
               f"the request: {recv}")
        expect(any(e["ev"] == "end" for e in w.server_log()), "its stdin was never closed")
        expect(not a.todos, f"to-dos for a server that answered: {a.todos}")
        expect(SECRET_A not in a.stdout + a.stderr + a.ledger_text, "a value was printed")


@case
def junk_before_response_tolerated():
    with world() as w:
        w.std_server("csa-zendesk", mode="junk")
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
        a = w.verify()
        a.ok()
        expect(a.oks == [ok_line("csa-zendesk", CC_USER)],
               f"oks {a.oks}, warns {a.warns}")
        expect([i for i in a.infos if "2 lines on its stdout were not JSON" in i],
               f"the lines skipped were not counted: {a.infos}")


@case
def error_response_reported():
    with world() as w:
        w.std_server("csa-zendesk", mode="error", message=SECRET_A)
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
        a = w.verify()
        a.ok()
        expect(not a.oks and a.warned("answered with a JSON-RPC error (code -32602)"), f"warns {a.warns}")
        expect(SECRET_A not in a.stdout + a.stderr + a.ledger_text, "the error's message was printed")
        expect(a.has_todo(45, no_answer("csa-zendesk")),
               f"ledger {a.todos}")


@case
def silent_server_times_out_and_is_killed():
    # It ignores SIGTERM and has a child of its own: the whole process group goes, by SIGKILL.
    with world() as w:
        mod = load_module()
        mod.HANDSHAKE_TIMEOUT = 1
        mod.EXIT_GRACE = mod.TERM_GRACE = 0.5
        w.std_server("csa-zendesk", mode="silent")
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
        try:
            a = w.verify_inproc(mod)
            events = w.server_log()
            starts = [e for e in events if e["ev"] == "start"]
            children = [e["child"] for e in events if e["ev"] == "grandchild"]
            left = group_members(starts[0]["pgid"]) if starts else []
        finally:
            kill_stub_groups(w)
        a.ok()
        expect(a.warned("did not answer within 1s"), f"warns {a.warns}")
        expect(starts and children, "fixture: the stub and its child did not start")
        expect(not left, f"left running in its process group: {left}")
        expect(a.has_todo(45, no_answer("csa-zendesk")),
               f"ledger {a.todos}")


@case
def exits_before_answering_masked():
    # The plan's name. Masking was a deny-list a value could get through (review of bbb6f82),
    # so nothing a server printed is shown at all, masked or not: the line is fixed text and its
    # exit code, and the to-do names the command to run to see its own messages.
    with world() as w:
        w.std_server("csa-zendesk", mode="exit", last=f"fatal: refused {SECRET_A}", leak=True)
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"), ["--token", SECRET_C],
                                          env={"CSA_ZD_ALLOWLIST_WRITE": SECRET_A,
                                               "CSA_ZD_ALLOWLIST_READ": SECRET_B})})
        a = w.verify()
        a.ok()
        expect(a.warns == [f"csa-zendesk, launched with its registered command and settings "
                           f"({CC_USER}): exited (code 3) before answering"], f"warns {a.warns}")
        expect(a.has_todo(45, no_answer("csa-zendesk")), f"ledger {a.todos}")
        for s in SECRETS:
            expect(s not in a.stdout + a.stderr + a.ledger_text, "a value reached the output")


@case
def no_server_text_printed():
    # Each value a server is given - its registration's env (a multi-line one, one with quote and
    # backslash, a short one), an inherited one, and an arg - comes back from it everywhere and
    # in every form (STUB_SERVER `leak`), from a server that answers, one that answers with an
    # error, one that exits, and one that never answers. What verify prints is fixed lines only,
    # and holds no run of four characters from any of those values.
    #
    # A value shorter than four characters could appear in fixed text by chance, so absence is
    # not what guards it: FIXED_LINES is, which leaves a server's text nowhere to go.
    s_env, s_multi = "QZXJ7W3KVPQ9", "QJ8ZKXVW\nWV4QZPJK"
    s_esc, s_short = 'QW"ZK\\X7QJV', "Q7Z"
    s_arg, s_inherited = "ZKQ4XW8JVQ7P", "XQZW9KJ4VPZ7"
    s_code = 73914286  # an error code JSON-RPC does not reserve: a number of the server's own
    leaked = (s_env, s_multi, s_esc, s_arg, s_inherited, str(s_code))
    for ledger in (False, True):
        with world() as w:
            mod = load_module()
            mod.HANDSHAKE_TIMEOUT = 1
            mod.EXIT_GRACE = mod.TERM_GRACE = 0.3
            w.extra_env["PLAN_INHERITED"] = s_inherited
            env = {"CSA_LEAK_ENV": s_env, "CSA_LEAK_MULTI": s_multi, "CSA_LEAK_ESC": s_esc,
                   "CSA_LEAK_SHORT": s_short}
            user = {}
            for name, mode in (("csa-google-workspace", "answer"), ("csa-google-gmail-calendar", "error"),
                               ("csa-skilljar", "exit"), ("csa-zendesk", "silent")):
                w.std_server(name, mode=mode, leak=True, last="fatal", code=s_code)
                user[name] = reg(std_bin(w, name), ["--token", s_arg], env=env)
            w.claude(user=user)
            try:
                a = w.verify_inproc(mod, ledger=ledger)
            finally:
                kill_stub_groups(w)
            a.ok()
            said = [e for e in w.server_log() if e["ev"] == "leaked"]
            expect(len(said) == 4, f"fixture: {len(said)} of 4 stubs put their values out")
            expect(len(a.oks) == 1 and len(a.warns) == 3, f"oks {a.oks}, warns {a.warns}")
            text = a.stdout + a.stderr + a.ledger_text
            expect(not a.stderr, f"stderr: {a.stderr!r}")
            stray = not_fixed(a.stdout, a.ledger_text)
            expect(not stray, f"lines that are not verify's fixed text: {stray}")
            found = sorted(g for v in leaked for g in grams(v) if g in text)
            expect(not found, f"runs of a value in the output: {found}")
            expect(s_short not in text, "a short value reached the output")


@case
def orphan_child_is_stopped():
    # A server that exits by itself on its stdin closing, but leaves a child in its process
    # group: the child is stopped too, not only the server.
    with world() as w:
        w.std_server("csa-zendesk", orphan=True)
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
        try:
            a = w.verify()
            events = w.server_log()
            starts = [e for e in events if e["ev"] == "start"]
            children = [e["child"] for e in events if e["ev"] == "grandchild"]
            left = group_members(starts[0]["pgid"]) if starts else []
        finally:
            kill_stub_groups(w)
        a.ok()
        expect(a.oks == [ok_line("csa-zendesk", CC_USER)], f"oks {a.oks}, warns {a.warns}")
        expect(children and any(e["ev"] == "end" for e in events),
               "fixture: the stub did not leave a child and exit by itself")
        expect(not left, f"left running in its process group: {left}")


@case
def time_budget_bounds_the_launches():
    # The launches together are held to VERIFY_BUDGET: one that could run past it is reported,
    # never started (review of bbb6f82: per-client envs and local scopes made the count
    # unbounded). Scaled down here: 1 s answers, 0.3 s grace periods, a 2.5 s budget.
    with world() as w:
        mod = load_module()
        expect(mod.VERIFY_BUDGET == 120, f"VERIFY_BUDGET {mod.VERIFY_BUDGET}")
        mod.HANDSHAKE_TIMEOUT = 1
        mod.EXIT_GRACE = mod.TERM_GRACE = mod.KILL_GRACE = 0.3
        mod.VERIFY_BUDGET = 2.5
        user = {}
        for name in ("csa-google-workspace", "csa-skilljar", "csa-zendesk"):
            w.std_server(name, mode="silent")
            user[name] = reg(std_bin(w, name))
        w.claude(user=user)
        try:
            a = w.verify_inproc(mod)
        finally:
            kill_stub_groups(w)
        a.ok()
        expect(len(w.starts()) == 1, f"{len(w.starts())} launches within a 2.5s budget")
        held = [i for i in a.infos if i.endswith("not checked: the launches together are held "
                                                 "to 2.5s, and this one could run past that")]
        expect(len(held) == 2, f"infos {a.infos}")
        expect(len(a.warns) == 1, f"warns {a.warns}")


@case
def launcher_behind_another_name_left():
    # A link named otherwise to a launcher that is itself a Python console script (pipx): known
    # by the name its link resolves to, left by the plan and never launched by the check.
    with world() as w:
        pipx = write_exec(w.tmp / "pipx-venv" / "bin" / "pipx",
                          f"#!{sys.executable}\nopen({str(w.log)!r}, 'a').write('pipx ran\\n')\n")
        link = w.home / "bin" / "zd-server"
        link.parent.mkdir()
        link.symlink_to(pipx)
        w.claude(user={"csa-zendesk": reg(link)})
        r = w.run()
        r.ok()
        f = r.f("csa-zendesk")
        expect((f["state"], f["reason"]) ==
               ("launcher", "it runs through pipx, which this does not inspect; left as it is"),
               f"{f['state']}/{f['reason']}")
        a = w.verify()
        a.ok()
        expect(f"csa-zendesk in {CC_USER}: {N_LAUNCHER}" in a.infos, f"infos {a.infos}")
        expect(not [ln for ln in w.stub_log() if "pipx ran" in ln], "the launcher was run")


@case
def one_process_at_a_time():
    # Each stub holds one exclusive lock for its whole life, lingers 0.5 s after its stdin
    # closes, and gives up if the lock is taken: two at once would show as contention.
    with world() as w:
        lock = w.tmp / "one.lock"
        user = {}
        for name in ("csa-zendesk", "csa-skilljar", "csa-google-workspace"):
            w.std_server(name, lock=str(lock), delay=0.2, linger=0.5)
            user[name] = reg(std_bin(w, name))
        w.claude(user=user)
        try:
            a = w.verify()
        finally:
            kill_stub_groups(w)
        a.ok()
        contention = [e for e in w.server_log() if e["ev"] == "contention"]
        expect(not contention, f"two servers ran at once: {contention}")
        expect(len(a.oks) == 3, f"oks {a.oks}, warns {a.warns}")


@case
def deduped_launches():
    with world() as w:
        # macOS gives every process this key, whatever its parent passes (M3), so Codex's
        # allowlist leaving it out must not make a second launch. Set here, so Linux sees it too.
        w.extra_env["__CF_USER_TEXT_ENCODING"] = "0x1F5:0x0:0x0"
        w.std_server("csa-zendesk")
        cmd = std_bin(w, "csa-zendesk")
        proj = w.home / "GitHub" / "proj"
        proj.mkdir(parents=True)
        w.claude(user={"csa-zendesk": reg(cmd)},
                 projects={str(proj): {"mcpServers": {"csa-zendesk": reg(cmd)}}})
        w.gemini({"csa-zendesk": reg(cmd)})
        w.codex([{"name": "csa-zendesk", "transport": {"type": "stdio", "command": cmd}}])
        a = w.verify()
        a.ok()
        expect(len(w.starts()) == 1, f"{len(w.starts())} launches of one command, args and env")
        clients = f"{CC_USER}, Claude Code (local scope, ~/GitHub/proj), Codex, Gemini"
        expect(a.oks == [ok_line("csa-zendesk", clients)],
               f"oks {a.oks}, warns {a.warns}")


@case
def desktop_env_is_minimal():
    # M3: Claude Desktop hands a server HOME LOGNAME PATH SHELL USER and its registered env.
    with world() as w:
        added = bare_keys()
        w.extra_env.update({"LOGNAME": "u", "USER": "u", "SHELL": "/bin/zsh", "TERM": "xterm",
                            "PLAN_PLAIN": "plain", "PLAN_FAKE_TOKEN": SECRET_B})
        w.std_server("csa-skilljar")
        w.desktop({"csa-skilljar": reg(std_bin(w, "csa-skilljar"),
                                       env={"CSA_SKILLJAR_PROFILE": "prof"})})
        a = w.verify()
        a.ok()
        expect(a.oks == [ok_line("csa-skilljar", "Claude Desktop")],
               f"oks {a.oks}, warns {a.warns}, infos {a.infos}")
        got = set(w.starts()[0]["keys"]) - added
        want = {"HOME", "LOGNAME", "PATH", "SHELL", "USER", "CSA_SKILLJAR_PROFILE"}
        expect(got == want, f"extra {sorted(got - want)}, missing {sorted(want - got)}")


@case
def client_env_as_measured():
    # M3: Claude Code passes the caller's whole env; Gemini drops the names that look secret;
    # Codex passes eight keys and those its registration names in env_vars. Each adds the
    # registration's env, and none gets the installer's own keys.
    with world() as w:
        added = bare_keys()
        w.extra_env.update({"LOGNAME": "u", "USER": "u", "SHELL": "/bin/zsh", "TERM": "xterm",
                            "PLAN_PLAIN": "plain", "PLAN_FAKE_TOKEN": SECRET_B,
                            "PLAN_FAKE_API_KEY": SECRET_C, "CSA_LOG": str(w.tmp / "log"),
                            "CSA_DEBUG": "1", "CSA_NESTED": "1", "CSA_REGISTRATIONS_PY": "x",
                            # A plain name whose value Gemini's rule calls a secret.
                            "PLAN_MIRROR": "https://user:pw@mirror.invalid/simple"})
        w.std_server("csa-zendesk")
        cmd = std_bin(w, "csa-zendesk")
        w.claude(user={"csa-zendesk": reg(cmd, env={"MARK_CC": "1"})})
        w.gemini({"csa-zendesk": reg(cmd, env={"MARK_GEMINI": "1",
                                               "CSA_FAKE_CLIENT_SECRET": SECRET_A})})
        w.codex([{"name": "csa-zendesk", "transport": {
            "type": "stdio", "command": cmd, "env": {"MARK_CODEX": "1"}, "env_vars": ["PLAN_PLAIN"]}}])
        a = w.verify()
        a.ok()
        expect(len(a.oks) == 3, f"oks {a.oks}, warns {a.warns}, infos {a.infos}")
        inherited = set(w.apply_env(True)) - {"CSA_TODO_FILE", "CSA_LOG", "CSA_DEBUG",
                                              "CSA_NESTED", "CSA_REGISTRATIONS_PY"}
        want = {
            "MARK_CC": inherited | {"MARK_CC"},
            "MARK_GEMINI": (inherited - {"PLAN_FAKE_TOKEN", "PLAN_FAKE_API_KEY", "PLAN_MIRROR"})
                           | {"MARK_GEMINI", "CSA_FAKE_CLIENT_SECRET"},
            "MARK_CODEX": {"HOME", "LANG", "LOGNAME", "PATH", "SHELL", "TERM", "TMPDIR", "USER",
                           "PLAN_PLAIN", "MARK_CODEX"},
        }
        seen = set()
        for s in w.starts():
            mark = [k for k in s["keys"] if k.startswith("MARK_")]
            expect(len(mark) == 1, f"a launch with markers {mark}")
            got = set(s["keys"]) - added
            seen.add(mark[0])
            expect(got == want[mark[0]] - added,
                   f"{mark[0]}: extra {sorted(got - want[mark[0]])}, "
                   f"missing {sorted(want[mark[0]] - got)}")
        expect(seen == set(want), f"launched {sorted(seen)}")


@case
def dollar_env_not_checked():
    with world() as w:
        w.std_server("csa-zendesk")
        w.std_server("csa-skilljar")
        w.claude(user={
            "csa-zendesk": reg(std_bin(w, "csa-zendesk"), env={"K": "$HOME/x"}),
            "csa-skilljar": reg(std_bin(w, "csa-skilljar"), ["--profile", "${P}"])})
        a = w.verify()
        a.ok()
        expect(f"csa-zendesk in {CC_USER}: {N_DOLLAR}" in a.infos, f"infos {a.infos}")
        expect(f"csa-skilljar in {CC_USER}: not checked: its args use $-expansion, which this "
               "check does not reproduce" in a.infos, f"infos {a.infos}")
        expect(not w.starts(), f"launched: {w.starts()}")


@case
def dead_registration_not_launched():
    with world() as w:
        dead = w.server(w.home / "GitHub" / "zd" / "csa-zendesk-mcp", interp=partial_python(w))
        subprocess.run([str(dead)], input=b"", env=w.env(), timeout=60, capture_output=True)
        expect(w.starts(), "fixture: launched, the stub would run and log its start")
        w.slog.write_text("")
        w.claude(user={"csa-zendesk": reg(dead), "csa-skilljar": reg(gone(w, "csa-skilljar"))})
        a = w.verify()
        a.ok()
        expect(f"csa-zendesk in {CC_USER}: {N_DEAD}{R_PY_BROKEN}" in a.warns, f"warns {a.warns}")
        expect(f"csa-skilljar in {CC_USER}: {N_DEAD}{R_MISSING}" in a.warns, f"warns {a.warns}")
        expect(not w.starts(), f"a dead registration was launched: {w.starts()}")


@case
def dead_standard_binary_not_launched():
    with world() as w:
        w.std_server("csa-zendesk", interp=partial_python(w))
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
        a = w.verify()
        a.ok()
        expect(f"csa-zendesk in {CC_USER}: {N_DEAD}{R_STANDARD_DEAD}" in a.warns, f"warns {a.warns}")
        expect(not w.starts(), f"a dead standard binary was launched: {w.starts()}")


@case
def launcher_form_not_launched():
    with world() as w:
        checkout = w.home / "GitHub" / "csa-google-gmail-calendar"
        checkout.mkdir(parents=True)
        write_exec(w.stubs / "uv", f"#!{w.uv_python}\nopen({str(w.log)!r}, 'a').write('uv ran\\n')\n")
        w.stub("uvx", "exit 0")
        write_exec(w.stubs / "npx", f'#!/bin/sh\nprintf "npx ran\\n" >> "{w.log}"\n')
        w.claude(user={
            "csa-google-gmail-calendar": reg("uv", ["run", "--directory", str(checkout),
                                                    "csa-google-gmail-calendar"]),
            "csa-zendesk": reg("uvx", ["--from", "csa-zendesk[server]", "csa-zendesk-mcp"]),
            "csa-skilljar": reg("npx", ["-y", "csa-skilljar"]),
        })
        before = snapshot(checkout)
        a = w.verify()
        a.ok()
        for name in ("csa-google-gmail-calendar", "csa-zendesk", "csa-skilljar"):
            expect(f"{name} in {CC_USER}: {N_LAUNCHER}" in a.infos, f"{name}: infos {a.infos}")
        ran = [ln for ln in w.stub_log() if ln.startswith(("uv", "npx"))]
        expect(not ran, f"a launcher was run: {ran}")
        expect(snapshot(checkout) == before, "the checkout changed")


@case
def interpreter_keys_not_launched():
    # A12: a setting that changes which Python code runs - here into a checkout - is not
    # launched by the check, working or not: a launch can write into that tree.
    with world() as w:
        srv = w.server(w.home / "GitHub" / "zd" / "srv", name="zd")
        w.claude(user={"csa-zendesk": reg(srv, env={"PYTHONPATH": str(w.home / "GitHub")})})
        a = w.verify()
        a.ok()
        want = (f"csa-zendesk in {CC_USER}: not checked: its PYTHONPATH setting changes which "
                "Python code it runs, so it is not launched")
        expect(want in a.infos, f"infos {a.infos}, oks {a.oks}")
        expect(not w.starts(), f"launched: {w.starts()}")


@case
def own_cwd_not_checked():
    # Gemini and Codex can start a server in a directory of its own: not reproduced, not run.
    with world() as w:
        w.std_server("csa-zendesk")
        w.gemini({"csa-zendesk": reg(std_bin(w, "csa-zendesk"), cwd=str(w.home))})
        a = w.verify()
        a.ok()
        want = ("csa-zendesk in Gemini: not checked: it sets its own working directory, which "
                "this check does not reproduce")
        expect(want in a.infos, f"infos {a.infos}, oks {a.oks}")
        expect(not w.starts(), f"launched: {w.starts()}")


@case
def token_files_untouched():
    # Stubs only: what a real server does to its token is M5's. The check itself never opens,
    # changes or even reaches a token file, at mode 000 in a directory at mode 000.
    with world() as w:
        tokens = [w.home / ".config" / "csa-zendesk" / "tokens.json",
                  w.home / ".csa_google_workspace" / "token.json",
                  w.home / ".csa_google_gmail_calendar" / "token.json"]
        for t in tokens:
            t.parent.mkdir(parents=True)
            t.write_text('{"fake": true}')
            t.chmod(0)
        user = {}
        for name in ("csa-zendesk", "csa-google-workspace", "csa-google-gmail-calendar"):
            w.std_server(name)
            user[name] = reg(std_bin(w, name))
        w.claude(user=user)

        def stats():
            return [(st.st_ino, st.st_mtime_ns, st.st_size, st.st_mode)
                    for st in (os.stat(t) for t in tokens)]

        before = stats()
        try:
            for t in tokens:
                t.parent.chmod(0)
            a = w.verify()
        finally:
            for t in tokens:
                t.parent.chmod(0o700)
        a.ok()
        expect(len(a.oks) == 3, f"oks {a.oks}, warns {a.warns}")
        expect(stats() == before, "a token file changed")


@case
def verify_held_by_default():
    with world() as w:
        mod = load_module()
        expect(mod.VERIFY_ON_RERUN == frozenset(), "D5's safe default is (b): a rerun checks nothing")
        w.std_server("csa-zendesk")
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
        a = w.verify(run=False)
        a.ok()
        expect(a.infos == [HELD] and not a.oks and not a.warns,
               f"infos {a.infos}, oks {a.oks}, warns {a.warns}")
        expect(not w.starts(), f"a server was launched without --run: {w.starts()}")
        expect(w.stub_log() == [], f"held, it still ran something: {w.stub_log()}")


@case
def rerun_checks_only_allowed_servers():
    # D5 (c)'s mechanism: a rerun checks the servers VERIFY_ON_RERUN names, and says the rest
    # are held.
    with world() as w:
        mod = load_module()
        mod.VERIFY_ON_RERUN = frozenset({"csa-zendesk"})
        w.std_server("csa-zendesk")
        w.std_server("csa-skilljar")
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk")),
                       "csa-skilljar": reg(std_bin(w, "csa-skilljar"))})
        a = w.verify_inproc(mod, run=False)
        a.ok()
        expect(a.oks == [ok_line("csa-zendesk", CC_USER)],
               f"oks {a.oks}, warns {a.warns}")
        expect([s["server"] for s in w.starts()] == ["csa-zendesk-stub"], f"{w.starts()}")
        expect([i for i in a.infos if "held for csa-skilljar" in i], f"infos {a.infos}")


@case
def verify_run_flag_runs():
    with world() as w:
        w.std_server("csa-zendesk")
        w.std_server("csa-skilljar")
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk")),
                       "csa-skilljar": reg(std_bin(w, "csa-skilljar"))})
        a = w.verify(run=True)
        a.ok()
        expect(a.oks == [ok_line("csa-skilljar", CC_USER),
                         ok_line("csa-zendesk", CC_USER)],
               f"oks {a.oks}, warns {a.warns}, infos {a.infos}")
        expect(len(w.starts()) == 2, f"{len(w.starts())} launches")


@case
def failure_todo_and_ledger_absent_print():
    with world() as w:
        w.std_server("csa-zendesk", mode="error")
        w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
        title = no_answer("csa-zendesk")
        a = w.verify()
        a.ok()
        expect(a.has_todo(45, title), f"ledger {a.todos}")
        expect(title not in a.infos, "printed as well as written to the ledger")
        b = w.verify(ledger=False)
        b.ok()
        expect(title in b.infos, f"no ledger, and not printed: {b.infos}")


# Runs verify --run with short grace periods and the given timeout, so a test can stop it with a
# real signal while a server is running; at `point` (a TEST_HOOK point) it says so and waits.
VERIFY_DRIVER = r'''
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("m", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.EXIT_GRACE = mod.TERM_GRACE = 0.5
mod.HANDSHAKE_TIMEOUT = float(sys.argv[2])
point, marker = sys.argv[3], sys.argv[4]

def hold(at, path):
    if at == point:
        open(marker, "w").close()
        time.sleep(3)

mod.TEST_HOOK = hold
sys.exit(mod.main(sys.argv[5:]))
'''

# (signal, where it lands, the timeout, exit status, what stderr says). "asking": while verify
# waits for an answer; "ending": as it starts to stop the server, which no signal may cut short.
VERIFY_STOPS = [
    (signal.SIGTERM, "asking", 20, 143, b"stopped by a signal"),
    (signal.SIGINT, "asking", 20, 130, b"stopped by an interrupt"),
    (signal.SIGTERM, "ending", 1, 143, b"stopped by a signal"),
]


@case
def signal_during_check_leaves_no_server():
    for sig, point, timeout, status, said in VERIFY_STOPS:
        where = f"{sig.name} while {point}"
        with world() as w:
            w.std_server("csa-zendesk", mode="silent")
            w.claude(user={"csa-zendesk": reg(std_bin(w, "csa-zendesk"))})
            driver = w.tmp / "verify-driver.py"
            driver.write_text(VERIFY_DRIVER)
            marker = w.tmp / "at-point"
            p = subprocess.Popen([sys.executable, "-I", str(driver), str(SCRIPT), str(timeout),
                                  point, str(marker)] + w.verify_argv(True, []),
                                 env=w.apply_env(False),
                                 cwd=str(w.tmp), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 preexec_fn=lambda: [signal.signal(s, signal.SIG_DFL) for s in
                                                     (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)])
            try:
                deadline = time.time() + 120

                def there():
                    if point == "asking":
                        return [e for e in w.server_log() if e["ev"] == "grandchild"]
                    return marker.exists()

                while not there() and p.poll() is None and time.time() < deadline:
                    time.sleep(0.05)
                expect(w.starts() and there(), f"{where}: never got there")
                p.send_signal(sig)
                _, err = p.communicate(timeout=60)
                start = w.starts()[0]
                left = group_members(start["pgid"])
            finally:
                if p.poll() is None:
                    p.kill()
                    p.communicate()
                kill_stub_groups(w)
            expect(p.returncode == status, f"{where}: exit {p.returncode}: {err[-300:]!r}")
            expect(not left, f"{where}: the server's group is still running: {left}")
            expect(not os.path.exists(start["cwd"]), f"{where}: its working directory was left")
            expect(said in err and b"Traceback" not in err, f"{where}: stderr {err[-300:]!r}")


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
def no_invisible_characters_in_source():
    # A bidi control or a line separator written literally into source shows a reader
    # something other than what runs ("Trojan Source"), and a literal U+2028 once shifted this
    # file's own line arithmetic. Both files spell such characters as code points.
    # Read as bytes, so a CR is seen rather than translated, and judged by category, so the
    # zero-width characters a list of code points missed are caught too. Tab and newline are
    # the only controls source may hold.
    for path in (SCRIPT, Path(__file__).resolve()):
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as e:
            raise Failed(f"{path.name}: not UTF-8 at byte {e.start}")
        found = sorted({(n, hex(ord(c))) for n, line in enumerate(text.split("\n"), 1)
                        for c in line if c != "\t"
                        and unicodedata.category(c) in UNSAFE_CATEGORIES})
        expect(not found, f"{path.name}: invisible characters at {found[:5]}")


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
     "        discard(args.out, created[-1] if created else None)\n        del created[:]\n",
     "        del created[:]\n"),
    ("failure_removes_only_its_own_plan", "leave this run's plan file after a failure",
     "        discard(args.out, created[-1] if created else None)\n        if not isinstance(",
     "        if not isinstance("),
    ("lone_surrogate_is_malformed", "accept a string UTF-8 cannot encode",
     '        value.encode("utf-8")\n', "        pass\n"),
    ("deep_nesting_is_not_audited", "let a RecursionError past the JSON reader",
     '    except RecursionError:\n        return None, f"{what} is nested too deeply to read"\n', ""),
    ("no_invisible_characters_in_source", "write a line separator into the source literally",
     "# A newline or a tab in a project path", "# A newline" + chr(0x2028) + "or a tab in a project path"),
    ("no_invisible_characters_in_source", "write a zero-width space into the source literally",
     "# A newline or a tab in a project path", "# A newline" + chr(0x200B) + " or a tab in a project path"),
    ("no_invisible_characters_in_source", "end a source line with CR LF",
     "# A newline or a tab in a project path", "# A newline or a tab in a project path" + chr(13)),
    ("clean_replaces_separators_and_bidi", "clean only the controls",
     'UNSAFE_CATEGORIES = ("Cc", "Cf", "Zl", "Zp", "Cs", "Co")', 'UNSAFE_CATEGORIES = ("Cc",)'),
    ("transport_type_is_text_or_malformed", "accept a `type` UTF-8 cannot encode",
     "    if value is not None and not _text(value):\n        raise ShapeError(what)\n", ""),
    ("transport_type_is_text_or_malformed", "record the config's own `type` text",
     'return default if kind is None else (kind if kind in TRANSPORTS else "unknown")',
     "return default if kind is None else kind"),
    ("control_chars_cannot_forge_rows", "write the plan file's non-ASCII raw",
     "indent=2, ensure_ascii=True)", "indent=2, ensure_ascii=False)"),
    ("existing_out_left_untouched", "write over an existing --out",
     "    if os.path.lexists(path):\n        return (f\"--out", "    if False:\n        return (f\"--out"),
    ("out_refuses_client_configs", "allow --out to be a client's config path",
     "        if real == os.path.realpath(config_path(client, ctx)):", "        if False:"),
    ("out_never_replaced_even_after_the_check", "replace whatever appeared at --out",
     "        os.link(tmp, path)", "        os.replace(tmp, path)"),
    ("out_config_spelled_otherwise_refused", "trust the name check alone",
     "        clash = config_at(created[-1], ctx)\n", "        clash = None\n"),
    ("discard_spares_a_file_swapped_in", "take the plan file's identity after the link",
     "    return st.st_dev, st.st_ino\n\n\ndef config_at",
     "    st = os.lstat(path)\n    return st.st_dev, st.st_ino\n\n\ndef config_at"),
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
    # ── apply: Task 2 Step 4, the plan's six ──
    ("changed_since_plan_not_written", "drop the fingerprint from the approval",
     "    return (client, scope, project, name, fingerprint, config)",
     "    return (client, scope, project, name, config)"),
    ("desktop_mode_0600_kept", "write the temp file with plain open(), at the umask's mode",
     '    fd = new_temp(os.path.dirname(path), made)\n    with os.fdopen(fd, "wb") as fh:\n'
     "        os.fchmod(fh.fileno(), mode)\n",
     '    made.append(os.path.join(os.path.dirname(path), TMP_PREFIX + "plain"))\n'
     '    with open(made[-1], "wb") as fh:\n'),
    ("dead_user_scope_repointed_env_kept", "copy env through str()",
     "        else:\n            new[key] = value\n    return new\n",
     '        else:\n            new[key] = str(value) if key == "env" else value\n    return new\n'),
    ("symlinked_config_refused", "resolve the link and write its target",
     "    if linked_config(path):  # A10, again: it may have become a link since the audit\n",
     "    path = os.path.realpath(path)\n    if False:\n"),
    ("abandoned_write_leaves_no_backup", "back up before the stat check",
     "        if moved(path, before):                            # 5\n            return abandon(tmp)\n"
     "        backup = make_backup(path, stamp, mode, kept)      # 6\n",
     "        backup = make_backup(path, stamp, mode, kept)      # 6\n"
     "        if moved(path, before):                            # 5\n            return abandon(tmp)\n"),
    ("desktop_started_after_plan_skipped", "drop the apply-time Desktop re-check",
     "        running = (desktop_running(ctx, fresh=True)\n", "        running = (False\n"),
    # ── apply: the guards Task 2 added, each broken on purpose (ADR-005) ──
    ("claude_lock_honoured", "write without taking Claude Code's lock",
     "                        os.mkdir(self.lock, 0o700)\n", "                        pass\n"),
    ("claude_lock_honoured", "break a lock still held after the wait",
     "                    raise Locked(self.lock)\n",
     "                    os.rmdir(self.lock)\n                    continue\n"),
    ("concurrent_change_aborts_write", "skip the fingerprint check made under the lock",
     'if reg.transport != "stdio" or reg.fingerprint() != c.fingerprint:',
     'if reg.transport != "stdio":'),
    ("concurrent_change_aborts_write", "compare only the file type, not its permissions",
     "st.st_size, st.st_mode, st.st_nlink\n", "st.st_size, stat.S_IFMT(st.st_mode), st.st_nlink\n"),
    ("abandoned_write_leaves_no_backup", "keep the backup when the file moves after it is made",
     "            return abandon(tmp, backup)\n", "            return abandon(tmp)\n"),
    ("readback_mismatch_restores", "skip the read-back",
     "    if not verify():                                       # 9\n", "    if False:\n"),
    ("codex_readback_mismatch_restores", "skip Codex's read-back",
     "        return all(same(codex_get(c.reg.name, ctx), want, ordered=False) for c, want in kept)\n",
     "        return True\n"),
    ("prune_spares_other_backup_names", "prune every name that starts `.bak-`",
     r'BACKUP_RE = re.compile(r"\.bak-\d{14}$")', r'BACKUP_RE = re.compile(r"\.bak-")'),
    ("standard_binary_missing_no_repoint", "re-point without checking the standard binary",
     "        elif standard_dead(change.command, SERVERS[f.reg.name], ctx):\n", "        elif False:\n"),
    ("unapproved_finding_not_repaired", "act on a finding the plan showed as left",
     "        elif key not in repoint:\n", "        elif key not in every:\n"),
    ("json_format_preserved", "always indent by 2", "indent=json_indent(like),", "indent=2,"),
    ("json_format_preserved", "always end with a newline",
     '    if like.endswith("\\n"):\n        text += "\\n"\n', '    text += "\\n"\n'),
    ("json_format_preserved", "escape all non-ASCII",
     "ensure_ascii=False, allow_nan=False", "ensure_ascii=True, allow_nan=False"),
    ("json_format_preserved", "write a lone surrogate raw",
     '    text = LONE_SURROGATE.sub(lambda m: "\\\\u%04x" % ord(m.group()), text)\n', ""),
    # ── apply: the review of d39f719 ──
    ("signal_mid_write_leaves_nothing", "leave SIGTERM and SIGHUP at their defaults",
     "            saved[sig] = signal.signal(sig, stop)", "            saved[sig] = signal.getsignal(sig)"),
    ("signal_mid_write_leaves_nothing", "make a signal the caller ignores stop apply",
     "        if sig is None or signal.getsignal(sig) == signal.SIG_IGN:", "        if sig is None:"),
    ("stale_temp_files_swept", "sweep nothing", "            n = sweep_temps(directory, started)",
     "            n = 0"),
    ("stale_temp_files_swept", "sweep temp files of any age", "and st.st_mtime < since and",
     "and True and"),
    ("stale_temp_files_swept", "sweep any name with the prefix and a pid",
     r'TMP_NAME = re.compile(r"\.csa-registrations-(\d+)-[a-z0-9_]{8}")',
     r'TMP_NAME = re.compile(r"\.csa-registrations-(\d+).*")'),
    ("stale_temp_files_swept", "sweep links too", "        if (stat.S_ISREG(st.st_mode) and",
     "        if (True and"),
    ("desktop_state_unknown_at_write_skipped", "treat 'could not tell' as not running at the write",
     "        if running is not False:\n            row = ROW_DESKTOP_RUNNING if running else",
     "        if running:\n            row = ROW_DESKTOP_RUNNING if running else"),
    ("backup_name_never_overwritten", "claim the backup's name without O_EXCL",
     "os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr", "os.O_WRONLY | os.O_CREAT | getattr"),
    ("backup_looser_than_file_abandons", "accept a backup looser than its file",
     "        if stat.S_IMODE(os.lstat(backup).st_mode) & ~mode:", "        if False:"),
    ("codex_write_time_link_refused", "drop Codex's write-time link check",
     "    if linked_config(path):  # A10\n", "    if False:\n"),
    ("non_finite_number_not_rewritten", "write Infinity and NaN", "allow_nan=False", "allow_nan=True"),
    ("codex_multiline_string_refused", "allow a multi-line string inside the table",
     "    if any('\"\"\"' in body[i] or \"'''\" in body[i] for i in region):", "    if False:"),
    ("codex_multiline_string_refused", "allow a multi-line string above the header",
     "    if any('\"\"\"' in ln or \"'''\" in ln for ln in body[:heads[0]]):", "    if False:"),
    ("hard_linked_config_refused", "replace a hard-linked config", "    return st.st_nlink > 1",
     "    return False"),
    ("lock_held_too_long_abandons", "hold the lock as long as the write takes",
     "        if time.time() - self.taken > LOCK_HOLD_MAX:", "        if False:"),
    ("lock_held_too_long_abandons", "keep the backup when the lock check stops the write",
     '            unlink_quietly(tmp)\n            unlink_quietly(backup)\n            return "refused", why',
     '            unlink_quietly(tmp)\n            return "refused", why'),
    ("lock_taken_over_is_left", "write without checking the lock is still this run's",
     "        if not self.ours():\n            return R_LOCK_LOST", "        if False:\n            return R_LOCK_LOST"),
    ("lock_taken_over_is_left", "remove the lock without checking it is this run's",
     "    def release(self):\n        if self.ours():", "    def release(self):\n        if True:"),
    ("claude_lock_honoured", "drop the advice for a crashed process's lock",
     "T_LOCKED + T_LOCKED_STALE.format(lock=tilde(e.lock))", "T_LOCKED"),
    ("approval_binds_config_path", "drop the config from the approval",
     "    return (client, scope, project, name, fingerprint, config)",
     "    return (client, scope, project, name, fingerprint, None)"),
    ("duplicate_plan_row_resolves_to_leave", "let a re-point row win over a left one",
     "    return repoint - left, every, None", "    return repoint, every, None"),
    ("claude_lock_honoured", "never release the lock",
     "            try:\n                os.rmdir(self.lock)\n",
     "            try:\n                os.stat(self.lock)\n"),
    ("write_failure_says_no_value", "report a failed write by the exception's text",
     "why = e.strerror if isinstance(e, OSError) and e.strerror else describe_error(e)",
     "why = repr(e)"),
    # ── apply: the review of b417a67 ──
    ("signal_mid_write_leaves_nothing", "leave this run's lock when __enter__ is stopped",
     "            self.release()\n            raise\n", "            raise\n"),
    ("signal_mid_write_leaves_nothing", "leave the temp when a signal lands mid-restore",
     "        for n in made:\n            unlink_quietly(n)\n        if isinstance(e, OSError):",
     "        if isinstance(e, OSError):"),
    ("signal_mid_write_leaves_nothing", "let an interrupt end in a traceback",
     "        except KeyboardInterrupt:\n", "        except ZeroDivisionError:\n"),
    ("signal_mid_write_leaves_nothing", "leave the caller's signal handlers replaced",
     "        for sig, old in saved.items():\n"
     "            signal.signal(sig, old if old is not None else signal.SIG_DFL)",
     "        pass"),
    ("stale_temp_files_swept", "sweep a run's file while it is still running",
     " and not run_alive(int(m.group(1)))):", "):"),
    ("stale_temp_files_swept", "match a name by its start, not whole",
     "TMP_NAME.fullmatch(name)", "TMP_NAME.match(name)"),
    ("stale_temp_files_swept", "sweep another user's files",
     "(uid is None or st.st_uid == uid)", "True"),
    ("stale_temp_files_swept", "sweep through a linked config directory",
     "        if directory and directory not in swept and not linked_config(config):",
     "        if directory and directory not in swept:"),
    ("lock_held_too_long_abandons", "leave the temp when the lock check stops the write",
     '            unlink_quietly(tmp)\n            unlink_quietly(backup)\n            return "refused", why',
     '            unlink_quietly(backup)\n            return "refused", why'),
    ("hard_linked_config_refused", "ignore a hard link made after the read",
     "st.st_mode, st.st_nlink\n", "st.st_mode\n"),
    ("confinement_check_refuses_a_damaged_entry", "drop the in-memory confinement check",
     "        if not only_command_changed(old, new, c):", "        if False:"),
    # ── apply: the review of 79aa251 ──
    ("lock_never_removed_without_proof", "remove the lock on an exception, without proof",
     "            # __exit__ will not run: remove the lock here, but only one this run recorded.\n"
     "            self.release()\n",
     "            os.rmdir(self.lock)\n"),
    ("lock_never_removed_without_proof", "let a signal land between the mkdir and its record",
     "                with signals_held():  # the mkdir and its record, with nothing between them\n",
     "                if True:\n"),
    ("temp_files_are_this_runs_alone", "create the temp without O_EXCL",
     "os.O_WRONLY | os.O_CREAT | os.O_EXCL\n", "os.O_WRONLY | os.O_CREAT\n"),
    ("temp_files_are_this_runs_alone", "create the temp 0666, for the umask to cut down",
     'getattr(os, "O_CLOEXEC", 0), 0o600)', 'getattr(os, "O_CLOEXEC", 0), 0o666)'),
    ("temp_files_are_this_runs_alone", "record a name somebody else holds",
     "                continue  # not this run's: not recorded, so never removed\n",
     "                made.append(name)\n                continue\n"),
    ("temp_files_are_this_runs_alone", "name the temp with the parent's pid",
     "TMP_PREFIX, os.getpid(),", "TMP_PREFIX, os.getppid(),"),
    ("temp_files_are_this_runs_alone", "let a signal land between the temp's create and its record",
     "        with signals_held():\n            try:\n                fd = os.open(name,",
     "        if True:\n            try:\n                fd = os.open(name,"),
    ("temp_files_are_this_runs_alone", "let a signal land between the backup's create and its record",
     "    with signals_held():\n        fd = os.open(backup,", "    if True:\n        fd = os.open(backup,"),
    ("stale_temp_files_swept", "take EPERM to mean the run is gone",
     "    except PermissionError:\n        return True", "    except PermissionError:\n        return False"),
    ("signal_mid_write_leaves_nothing", "let a second stop signal cut the clean-up short",
     "        if stopping:\n            return  # one stop is enough",
     "        if False:\n            return  # one stop is enough"),
    ("signals_held_keeps_the_callers_mask", "unblock the held set, not restore the mask found",
     "        mask(signal.SIG_SETMASK, old)", "        mask(signal.SIG_UNBLOCK, sigs)"),
    ("signal_mid_write_leaves_nothing", "leave the stop signals unheld after a stop",
     "            mask(signal.SIG_BLOCK, {getattr(signal, n) for n in STOP_SIGNALS if hasattr(signal, n)})",
     "            pass"),
    ("signal_mid_write_leaves_nothing", "leave SIGINT out of the signals held and handled",
     'STOP_SIGNALS = ("SIGTERM", "SIGHUP", "SIGINT")', 'STOP_SIGNALS = ("SIGTERM", "SIGHUP")'),
    ("signal_mid_write_leaves_nothing", "remove the backup of a config already replaced",
     "        if any(os.path.lexists(n) for n in made):", "        if True:"),
    # ── verify: Task 3 Step 4, the plan's four ──
    ("silent_server_times_out_and_is_killed", "remove the process-group kill",
     "        os.killpg(pgid, sig)\n", "        os.kill(pgid, sig)\n"),
    # The plan's "skip masking": masking is gone (review of bbb6f82; nothing of a server's text
    # is shown), so its mutation is the leak masking stood guard against.
    ("exits_before_answering_masked", "print what the server left on stdout at its exit",
     '                return False, why, junk + (kind == "junk")',
     '                return False, why + out.decode("utf-8", "replace"), junk + (kind == "junk")'),
    ("launcher_form_not_launched", "launch launcher forms",
     'LAUNCHED_STATES = ("standard", "elsewhere")',
     'LAUNCHED_STATES = ("standard", "elsewhere", "launcher")'),
    ("verify_held_by_default", "default VERIFY_ON_RERUN to all four",
     "VERIFY_ON_RERUN = frozenset()",
     'VERIFY_ON_RERUN = frozenset(("csa-google-workspace", "csa-google-gmail-calendar", '
     '"csa-skilljar", "csa-zendesk"))'),
    # ── verify: the guards Task 3 added, each broken on purpose (ADR-005) ──
    ("error_response_reported", "print the error's own message",
     "            return False, F_ERROR.format(code=code)\n",
     '            return False, F_ERROR.format(code=code) + str(err.get("message"))\n'),
    ("no_server_text_printed", "say the server's own name in its line",
     "    return True, None\n", "    return False, name\n"),
    ("no_server_text_printed", "print any error code, not only one JSON-RPC reserves",
     "        if type(code) is int and low <= code <= high:", "        if type(code) is int:"),
    ("exits_before_answering_masked", "name the command's args in the to-do",
     "command=tilde(argv[0])", 'command=" ".join(argv)'),
    ("orphan_child_is_stopped", "take a process group to be empty without asking",
     "    try:\n        os.killpg(pgid, 0)\n    except OSError:\n        return False\n    return True\n",
     "    return False\n"),
    ("time_budget_bounds_the_launches", "launch past the budget",
     "        if now - started + launch_max() > VERIFY_BUDGET:", "        if False:"),
    ("launcher_behind_another_name_left", "know a launcher by its own name only",
     "    for name in (base, os.path.basename(os.path.realpath(path))):", "    for name in (base,):"),
    ("dead_registration_not_launched", "launch a dead registration",
     'LAUNCHED_STATES = ("standard", "elsewhere")',
     'LAUNCHED_STATES = ("standard", "elsewhere", "dead")'),
    ("dead_standard_binary_not_launched", "launch a dead standard binary",
     '    if f.state == "standard" and not f.live:\n', '    if False:\n'),
    ("dollar_env_not_checked", "launch an env that uses $-expansion",
     '    if any("$" in v for v in reg.env.values()):\n', '    if False:\n'),
    ("dollar_env_not_checked", "launch args that use $-expansion",
     '    if any("$" in a for a in reg.args):\n', '    if False:\n'),
    ("interpreter_keys_not_launched", "launch an env that changes which Python code runs",
     "    keys = interpreter_keys(reg.env)\n    if keys:\n",
     "    keys = interpreter_keys(reg.env)\n    if False:\n"),
    ("own_cwd_not_checked", "launch a registration with a working directory of its own",
     '    if reg.other.get("cwd"):\n', '    if False:\n'),
    ("deduped_launches", "launch once per registration, not once per launch",
     "        key = (tuple(argv), tuple(sorted(env.items())))",
     "        key = (tuple(argv), tuple(sorted(env.items())), id(f))"),
    ("deduped_launches", "leave the OS's own keys to the clients that pass everything",
     "    env.update({k: caller[k] for k in OS_KEYS if k in caller and k not in env})\n", ""),
    ("desktop_env_is_minimal", "hand Claude Desktop's server the caller's whole env",
     "        env = {k: caller[k] for k in DESKTOP_ENV if k in caller}", "        env = dict(caller)"),
    ("client_env_as_measured", "pass Gemini every inherited key",
     "        env = {k: v for k, v in caller.items() if not gemini_drops(k, v)}",
     "        env = dict(caller)"),
    ("client_env_as_measured", "judge Gemini's keys by name only",
     "    if GEMINI_SECRET_VALUE.search(value):\n", "    if False:\n"),
    ("client_env_as_measured", "ignore Codex's env_vars",
     "        env = {k: caller[k] for k in names if k in caller}",
     "        env = {k: caller[k] for k in CODEX_ENV if k in caller}"),
    ("client_env_as_measured", "pass the installer's own keys on",
     "              if k not in INSTALLER_KEYS and not k.startswith(INSTALLER_PREFIX)}",
     "              if True}"),
    ("one_process_at_a_time", "go on before the server has gone",
     "    stopped = gone(p, pgid, EXIT_GRACE)\n", "    stopped = True\n"),
    ("silent_server_times_out_and_is_killed", "never escalate to SIGKILL",
     "    for sig, grace in ((signal.SIGTERM, TERM_GRACE), (signal.SIGKILL, KILL_GRACE)):",
     "    for sig, grace in ((signal.SIGTERM, TERM_GRACE),):"),
    ("junk_before_response_tolerated", "give up at the first line that is not the answer",
     '                    junk += kind == "junk"\n', '                    return False, "junk", junk\n'),
    ("junk_before_response_tolerated", "count no line it skipped",
     '                    junk += kind == "junk"\n', "                    pass\n"),
    ("answers", "run the server in the caller's directory",
     "    with empty_dir() as cwd:\n        p = None\n",
     "    with contextlib.nullcontext(os.getcwd()) as cwd:\n        p = None\n"),
    ("answers", "start the server in verify's own session",
     "                            start_new_session=True,\n                            preexec_fn=",
     "                            start_new_session=False,\n                            preexec_fn="),
    ("answers", "start the server with the stop signals held",
     "preexec_fn=unhold if mask_found is not None else None)", "preexec_fn=None)"),
    ("failure_todo_and_ledger_absent_print", "leave no to-do for a server that did not answer",
     "            todos.add(TODO_CHECK, T_NO_ANSWER.format(name=f.reg.name, client=f.reg.where(),\n",
     "            pass\n            (TODO_CHECK, T_NO_ANSWER.format(name=f.reg.name, client=f.reg.where(),\n"),
    ("signal_during_check_leaves_no_server", "let a stop signal end verify where it stands",
     "            with exits_on_signals():\n", "            with contextlib.nullcontext():\n"),
    ("signal_during_check_leaves_no_server", "stop the server without holding the stop signals",
     "                with signals_held():\n                    stopped = end(p)\n",
     "                stopped = end(p)\n"),
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
