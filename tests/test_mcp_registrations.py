#!/usr/bin/env python3
"""scripts/csa-mcp-registrations.py `plan`: it finds every CSA MCP registration in Claude Code,
Claude Desktop, Codex and Gemini, says what is wrong with each, and writes nothing but its own
plan file (#179, plans/2026-11-12-registration-repair.md Task 1). And `apply` (Task 2): it
re-points only a dead registration that plan showed and that is unchanged since, changing only
its command, through Claude Code's own lock, with no backup left by a write it abandons.

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
        expect(self.rc == 0, f"apply exited {self.rc}: {self.stderr.strip()[-400:]}")

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
    (signal.SIGINT, "written", 130, b"stopped by an interrupt"),
]


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
        sigs = (signal.SIGTERM, signal.SIGHUP)
        before = [signal.getsignal(s) for s in sigs]
        w.apply_inproc(mod).ok()
        after = [signal.getsignal(s) for s in sigs]
        expect(after == before, f"handlers not restored: {after} != {before}")
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
     "                os.mkdir(self.lock, 0o700)\n", ""),
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
     "    def __exit__(self, *exc):\n        if self.ours():", "    def __exit__(self, *exc):\n        if True:"),
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
    ("signal_mid_write_leaves_nothing", "leave the lock when a signal lands before __enter__ returns",
     "                try:\n                    os.rmdir(self.lock)\n                except OSError:\n"
     "                    pass\n                raise", "                raise"),
    ("signal_mid_write_leaves_nothing", "learn the temp's name only once it exists",
     "        made.append(name)\n        try:\n"
     '            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL\n'
     '                         | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o600)\n'
     '            hook("temp-made", name)\n',
     "        try:\n"
     '            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL\n'
     '                         | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o600)\n'
     '            hook("temp-made", name)\n            made.append(name)\n'),
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
