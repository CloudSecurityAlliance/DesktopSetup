#!/usr/bin/env python3
"""Find every CSA MCP server registration, in four clients, and say what is wrong with each (#179).

The four internal CSA MCP servers (csa-google-workspace, csa-google-gmail-calendar,
csa-skilljar, csa-zendesk) are registered with Claude Code, Claude Desktop, Codex and Gemini by
the private gate repo's setup scripts. Those scripts leave a working registration alone, which
is right for policy, but it also means a registration that has since DIED stays dead: in the
incident behind #179 a source checkout's venv lost its Homebrew Python to `brew upgrade`, and
Claude Code went on launching a binary that could not start. Claude Code's narrowest scope wins,
so a dead local-scope entry breaks a project even when the user entry is healthy.

`plan` reads every client's own config and reports each CSA registration as one of:

  standard    it is ~/.local/bin/<entry>, or the same file - nothing to do. If that binary
              cannot start, its setup reinstalls it; this never "repairs" it into itself.
  dead        its command, or the Python behind it, is gone or cannot run.
  launcher    it runs through uv, uvx, npx or another wrapper. Left alone and never launched:
              launching one can rebuild a venv, download Python or write into a checkout.
  elsewhere   it works, but is not the standard binary - usually a developer's checkout, and
              a choice. Left alone, and said so.

A dead one is planned for a re-point at the standard binary, changing only its command (`apply`,
a later task), unless the plan's decisions leave it: a local-scope entry, an env that would
point the release binary at another tree, a config that is a symlink, or Claude Desktop running.

It writes nothing but the plan file it is asked for. It never opens a token, OAuth state or
credential file, never runs a server, and never prints an env VALUE - only key names and
counts. The values it reads stay in memory. Its own client calls (`codex mcp list --json`, the
probe of each interpreter) run from a fresh, empty directory, so a project config in the
caller's directory cannot stand in for the user's.

The plan's decisions are the constants below, each at its safe default until the CINO answers
(plans/2026-11-12-registration-repair.md, D1-D5); measurements it relies on are in
plans/reviews/2026-11-12-registration-repair-measurements.md (M0, M3, M7).

    python3 -I scripts/csa-mcp-registrations.py plan                   # print the plan
    python3 -I scripts/csa-mcp-registrations.py plan --out plan.json   # and record it

Output is one `row<TAB>text` line per row of the plan, and `log<TAB>text` for what is only
logged. Exit 0, or 2 on an internal error, in which case --out is not written.
"""
import argparse
import collections
import contextlib
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile

SCRIPT_VERSION = "2026-11-12T23:56Z"

# ── The plan's decisions (D1-D5). Each is pinned by one test; an answer changes the constant. ──

# D1. A registration that works but is not the standard binary: left and warned about (a).
#     True is (b): re-point it too. Pinned by working_elsewhere_left_and_warned.
REPOINT_WORKING_ELSEWHERE = False

# D2. A dead Claude Code local-scope entry: "todo" (d) leaves it, with a to-do naming the two
#     fixes that keep a checkout's policy with that checkout's code. "report" (a) leaves it with
#     a to-do naming the manual re-point; "repoint" (b) re-points it in place.
#     Pinned by dead_local_scope_todo_names_rebuild_or_remove.
LOCAL_SCOPE_ACTION = "todo"

# D4. Claude Desktop writes its own config. While it runs, a re-point there is not written (b),
#     until M2 shows a running Desktop never writes an old copy back.
#     Pinned by desktop_running_skipped_with_quit_todo.
WRITE_DESKTOP_WHILE_RUNNING = False

# D5. The servers a rerun checks with an MCP `initialize` handshake. Empty (b) until M5 shows
#     what a server touches at startup; while a server is held, the plan prints no check row for
#     it, so the plan claims nothing the run will not do. Pinned by no_check_rows_while_held.
VERIFY_ON_RERUN = frozenset()

# ── The servers ────────────────────────────────────────────────────────────────────────────────

Server = collections.namedtuple("Server", ["entry", "module"])

# Canonical name -> its console-script entry point, and the module of that console-script
# target, as `python -m <module>` would name it. Read from each server's pyproject.toml
# [project.scripts], at the tag installed when this was written (the same at each main):
#   CloudSecurityAlliance/csa-google-workspace      v0.55.1 cfb27bb  csa_google_workspace.mcp:main
#   CloudSecurityAlliance/csa-google-gmail-calendar v0.5.1  fb38d7a  csa_google_gmail_calendar.mcp:main
#   CloudSecurityAlliance/csa-skilljar              v0.16.1 aee5ca4  csa_skilljar.mcp.cli:main
#   CloudSecurityAlliance/csa-zendesk               v0.3.1  dca5b92  csa_zendesk.server:main
# Order and names match CSA_INTERNAL_SETUPS in all six entry scripts (servers_match_internal_setups).
SERVERS = collections.OrderedDict([
    ("csa-google-workspace", Server("csa-google-workspace-mcp", "csa_google_workspace.mcp")),
    ("csa-google-gmail-calendar", Server("csa-google-gmail-calendar", "csa_google_gmail_calendar.mcp")),
    ("csa-skilljar", Server("csa-skilljar-mcp", "csa_skilljar.mcp.cli")),
    ("csa-zendesk", Server("csa-zendesk-mcp", "csa_zendesk.server")),
])

CLAUDE_CODE = "Claude Code"
DESKTOP = "Claude Desktop"
CODEX = "Codex"
GEMINI = "Gemini"
CLIENTS = (CLAUDE_CODE, DESKTOP, CODEX, GEMINI)

# M3: the PATH each client hands a stdio server. Claude Code and Gemini pass their caller's PATH
# unchanged; Codex prepends two directories of its own that hold no CSA binary. So for those
# three a bare command name resolves on the PATH of the shell that started the client - here,
# this one. Claude Desktop's is not measured yet (M2's session): until it is, DESKTOP_PATH is
# None and a bare-name Desktop entry is left, never called dead (A8). When M3 records it, it
# goes here, as a PATH string.
INHERITS_PATH = (CLAUDE_CODE, CODEX, GEMINI)
DESKTOP_PATH = None

# M3: the clients that pass their own inherited environment on to every server they start, so
# an interpreter-shaping key set in it reaches a re-pointed binary too. Codex passes only an
# allowlist (HOME, LANG, LOGNAME, PATH, SHELL, TERM, TMPDIR, USER), which holds none of them.
PASSES_INHERITED_ENV = (CLAUDE_CODE, GEMINI)

# A12. Env keys that change which interpreter or which tree a Python entry point runs. A dead
# registration carrying one is left: re-pointed, the release binary would import that tree.
INTERPRETER_KEYS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE",
                    "PYTHONEXECUTABLE", "VIRTUAL_ENV", "CONDA_PREFIX")

# M0: registration env keys that move a server's token or credentials (XDG_CONFIG_HOME moves
# csa-zendesk's). Recorded by name in the plan file, so a launch under a scratch HOME can be
# known not to be isolated from a real token.
TOKEN_PATH_KEYS = ("CSA_ZENDESK_TOKEN_FILE", "XDG_CONFIG_HOME", "CSA_GW_TOKEN",
                   "CSA_GW_CLIENT_SECRETS", "CSA_GGC_TOKEN_PATH", "CSA_GGC_CLIENT_SECRETS",
                   "CSA_SKILLJAR_ENV_FILE")

# A12. Launchers, by name, checked before any shebang is parsed: pipx, poetry, pdm and hatch
# are themselves Python console scripts with an absolute shebang, and a pip-installed uv can be
# too, so the shebang alone would call them direct executables.
LAUNCHERS = ("uv", "uvx", "npx", "pipx", "poetry", "pdm", "hatch", "conda", "mamba", "pixi",
             "node", "bun", "bunx", "deno", "docker")

PYTHON_RE = re.compile(r"^python(\d+(\.\d+)*t?)?$")
# The `#!/bin/sh` form installers write when the interpreter's path is long or has spaces.
EXEC_RE = re.compile(r"""^'''exec' (?:"([^"]+)"|'([^']+)'|(\S+)) "\$0" "\$@"\s*$""")
# Both are stdlib packages on every supported version; `import sys` alone is built in and
# proves nothing (#179: the incident's interpreter started, then failed on its stdlib).
PROBE = "import json, importlib.resources"
PROBE_TIMEOUT = 10
CLIENT_TIMEOUT = 30

DESKTOP_EXECUTABLE = "Applications/Claude.app/Contents/MacOS/Claude"

# ── What the person reads. The reasons are the plan's, verbatim. ────────────────────────────────

R_STANDARD_DEAD = "its standard binary does not run yet; its setup reinstalls it"
R_MISSING = "its command does not exist"
R_NOT_EXEC = "its command is not executable"
R_LAUNCHER = "it runs through {base}, which this does not inspect; left as it is"
R_PY_GONE = "its Python no longer exists"
R_PY_BROKEN = "its Python does not run"
R_ELSEWHERE = "it points at {path}, not ~/.local/bin/{entry}"
R_DESKTOP_PATH = "not checked: Claude Desktop's PATH is not measured yet"
R_LINK = "its config is a link to {path}; not changed — edit it there"
R_MODULE = "its args run a module this does not recognise"
R_NOT_STDIO = "it is not a stdio registration, which is all this audits"
R_RELATIVE = "not checked: its command is a relative path, which depends on where the client starts"
R_ARGS = "its args are not a form this re-points"
R_KEYS = "its {keys} setting{s} would point the release binary at another tree"
W_CELLAR = ("it runs from a venv built on a Homebrew Cellar Python, which the next brew "
            "upgrade deletes")
W_INHERITED = ("{keys} {verb} set in this shell, and {client} passes {pron} on to every server "
               "it starts, so the re-pointed binary would get {pron} too")
ROW_DESKTOP_RUNNING = ("Claude Desktop is running; {name} will not be re-pointed there this run "
                       "— quit it and run again")
ROW_DESKTOP_UNKNOWN = ("could not tell whether Claude Desktop is running; {name} will not be "
                       "re-pointed there this run — quit it and run again")
T_QUIT_DESKTOP = "Quit Claude Desktop and run again"
WINDOWS = "not audited: Windows support is #184 (Task 1W)"


def on_windows():
    return sys.platform == "win32"


class ShapeError(Exception):
    pass


class DuplicateKey(Exception):
    pass


def _unique(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise DuplicateKey()
        d[k] = v
    return d


def home_dir():
    return os.path.expanduser("~")


def tilde(path):
    path = str(path)
    home = home_dir()
    if path == home or path.startswith(home.rstrip("/") + "/"):
        return "~" + path[len(home.rstrip("/")):]
    return path


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


@contextlib.contextmanager
def empty_dir():
    """A fresh empty directory for a child's working directory (A11), removed afterwards."""
    d = tempfile.mkdtemp(prefix="csa-registrations-")
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_bounded(argv, timeout, env, capture):
    """Run one child in its own process group, from an empty directory, stdin closed.

    On timeout the whole group is killed and the child reaped (S2): an npm-installed `codex` is
    a Node wrapper around a native child, and killing only the wrapper left the child running
    (measurements, "Bounded").
    """
    out = subprocess.PIPE if capture else subprocess.DEVNULL
    with empty_dir() as cwd:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                             stderr=out, start_new_session=True)
        try:
            o, e = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.communicate()
            raise
    return p.returncode, o or b"", e or b""


# ── Registrations ──────────────────────────────────────────────────────────────────────────────

class Registration(object):
    """One CSA registration as a client holds it. `env` is held in memory only."""

    def __init__(self, client, scope, project, name, config, command, args, env,
                 transport="stdio", other=None):
        self.client = client
        self.scope = scope
        self.project = project
        self.name = name
        self.config = config
        self.command = command
        self.args = list(args)
        self.env = dict(env)
        self.transport = transport
        self.other = dict(other or {})
        self.config_is_link = os.path.islink(config)

    def label(self):
        if self.client == CLAUDE_CODE:
            where = "user scope" if self.scope == "user" else f"local scope, {tilde(self.project)}"
            return f"{self.name} in Claude Code ({where})"
        return f"{self.name} in {self.client}"

    def fingerprint(self):
        """sha256 of the command, the args and the SORTED KEY NAMES of the env - never a value."""
        blob = json.dumps([self.command, self.args, sorted(self.env)],
                          separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _strings(value, what):
    if not isinstance(value, list) or not all(isinstance(a, str) for a in value):
        raise ShapeError(what)
    return value


def _env(value, what):
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                              for k, v in value.items()):
        raise ShapeError(what)
    return value


def json_entry(client, scope, project, name, entry, config):
    """A Claude Code, Claude Desktop or Gemini entry: {command, args, env, ...}."""
    what = f"{name}'s entry"
    if not isinstance(entry, dict):
        raise ShapeError(what)
    kind = entry.get("type")
    if "command" in entry and kind in (None, "stdio"):
        command = entry["command"]
        if not isinstance(command, str) or not command:
            raise ShapeError(what)
        args = entry.get("args")
        args = [] if args is None else _strings(args, what)
        env = _env(entry.get("env"), what)
        other = {k: v for k, v in entry.items() if k not in ("command", "args", "env")}
        return Registration(client, scope, project, name, config, command, args, env, "stdio",
                            other)
    if kind not in (None, "stdio") or "url" in entry or "httpUrl" in entry:
        return Registration(client, scope, project, name, config, None, [], {},
                            str(kind or "http"), entry)
    raise ShapeError(what)


def load_json(path, what):
    """(data, None) or (None, why). Duplicate keys, torn files and comments are all unreadable."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None, f"its {what} could not be read"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"its {what} is not UTF-8"
    try:
        return json.loads(text, object_pairs_hook=_unique), None
    except DuplicateKey:
        return None, f"its {what} has a duplicate key, so which value the client uses is unclear"
    except ValueError:
        return None, f"its {what} is not plain JSON (cut short, or with comments)"


def csa_entries(servers, what):
    """The CSA names in an `mcpServers` object, in SERVERS order."""
    if servers is None:
        return []
    if not isinstance(servers, dict):
        raise ShapeError(what)
    return [(name, servers[name]) for name in SERVERS if name in servers]


def which(name, path):
    return shutil.which(name, path=path)


# ── Readers. Each returns (status, [Registration]). ──────────────────────────────────────────

def read_claude_code(ctx):
    if on_windows():
        return WINDOWS, []
    cfg_dir = ctx.environ.get("CLAUDE_CONFIG_DIR")
    path = os.path.join(cfg_dir, ".claude.json") if cfg_dir else os.path.join(ctx.home, ".claude.json")
    ctx.configs[CLAUDE_CODE] = path
    if not os.path.lexists(path):
        installed = which("claude", ctx.path) or os.path.isfile(
            os.path.join(ctx.home, ".local", "bin", "claude"))
        return ("no config yet" if installed else "not installed"), []
    data, why = load_json(path, "config")
    if why:
        return "not audited: " + why, []
    try:
        if not isinstance(data, dict):
            raise ShapeError("the file")
        regs = [json_entry(CLAUDE_CODE, "user", None, name, entry, path)
                for name, entry in csa_entries(data.get("mcpServers"), "mcpServers")]
        projects = data.get("projects") or {}
        if not isinstance(projects, dict):
            raise ShapeError("projects")
        for project, pdata in projects.items():
            if not isinstance(pdata, dict):
                raise ShapeError("a project")
            for name, entry in csa_entries(pdata.get("mcpServers"), "a project's mcpServers"):
                reg = json_entry(CLAUDE_CODE, "local", project, name, entry, path)
                if not os.path.isdir(project):
                    ctx.logs.append(f"{reg.label()}: its project directory no longer exists; "
                                    "skipped")
                    continue
                regs.append(reg)
    except ShapeError as e:
        return f"not audited: its config has an unexpected shape ({e})", []
    return "ok", regs


def read_desktop(ctx):
    if on_windows():
        return WINDOWS, []
    apps = (os.path.join(ctx.system_applications, "Claude.app"),
            os.path.join(ctx.home, "Applications", "Claude.app"))
    path = os.path.join(ctx.home, "Library", "Application Support", "Claude",
                        "claude_desktop_config.json")
    ctx.configs[DESKTOP] = path
    if not any(os.path.isdir(a) for a in apps):
        return "not installed", []
    if not os.path.lexists(path):
        return "no config yet", []
    data, why = load_json(path, "config")
    if why:
        return "not audited: " + why, []
    try:
        if not isinstance(data, dict):
            raise ShapeError("the file")
        regs = [json_entry(DESKTOP, "user", None, name, entry, path)
                for name, entry in csa_entries(data.get("mcpServers"), "mcpServers")]
    except ShapeError as e:
        return f"not audited: its config has an unexpected shape ({e})", []
    return "ok", regs


def read_gemini(ctx):
    if on_windows():
        return WINDOWS, []
    path = os.path.join(ctx.home, ".gemini", "settings.json")
    ctx.configs[GEMINI] = path
    if not which("gemini", ctx.path):
        return "not installed", []
    if not os.path.lexists(path):
        return "no config yet", []
    data, why = load_json(path, "settings")
    if why:
        return "not audited: " + why, []
    try:
        if not isinstance(data, dict):
            raise ShapeError("the file")
        regs = [json_entry(GEMINI, "user", None, name, entry, path)
                for name, entry in csa_entries(data.get("mcpServers"), "mcpServers")]
    except ShapeError as e:
        return f"not audited: its settings have an unexpected shape ({e})", []
    return "ok", regs


def codex_failure(rc, err):
    """Why `codex mcp list --json` failed. Its stderr is matched, never echoed: it can hold values."""
    text = err.decode("utf-8", "replace")
    if "--json" in text and ("unexpected" in text or "unrecognized" in text or "unknown" in text):
        return "this Codex's `mcp list` has no --json, so its registrations cannot be read safely"
    return f"`codex mcp list --json` failed (exit {rc})"


def codex_items(data):
    """(name, entry) pairs from `codex mcp list --json`: a list of {name, ...}, or a dict."""
    if isinstance(data, dict) and len(data) == 1:
        (key, value), = data.items()
        if key in ("servers", "mcp_servers") and isinstance(value, (list, dict)):
            data = value
    if isinstance(data, list):
        items = []
        for e in data:
            if not isinstance(e, dict) or not isinstance(e.get("name"), str):
                raise ShapeError("an entry")
            items.append((e["name"], e))
        return items
    if isinstance(data, dict):
        for value in data.values():
            if not isinstance(value, dict):
                raise ShapeError("an entry")
        return list(data.items())
    raise ShapeError("the output")


def codex_entry(name, entry, config):
    what = f"{name}'s entry"
    transport = entry.get("transport")
    if isinstance(transport, dict):
        fields = transport
        kind = transport.get("type")
    elif transport is None or isinstance(transport, str):
        fields = entry
        kind = transport or entry.get("type")
    else:
        raise ShapeError(what)
    if fields.get("command") is not None and kind in (None, "stdio"):
        command = fields["command"]
        if not isinstance(command, str) or not command:
            raise ShapeError(what)
        args = fields.get("args")
        args = [] if args is None else _strings(args, what)
        env = _env(fields.get("env"), what)
        other = {k: v for k, v in entry.items() if k != "transport"}
        other.update({k: v for k, v in fields.items() if k not in ("command", "args", "env")})
        return Registration(CODEX, "user", None, name, config, command, args, env, "stdio", other)
    if kind not in (None, "stdio") or fields.get("url") is not None:
        return Registration(CODEX, "user", None, name, config, None, [], {}, str(kind or "http"))
    raise ShapeError(what)


def read_codex(ctx):
    """`codex mcp list --json`, since Apple's Python 3.9 has no tomllib (A7). A failing CLI is
    "not audited", never "no registrations"."""
    if on_windows():
        return WINDOWS, []
    codex_home = ctx.environ.get("CODEX_HOME") or os.path.join(ctx.home, ".codex")
    config = os.path.join(codex_home, "config.toml")
    ctx.configs[CODEX] = config
    exe = which("codex", ctx.path)
    if not exe:
        return "not installed", []
    if not os.path.lexists(config):
        return "no config yet", []
    try:
        rc, out, err = run_bounded([exe, "mcp", "list", "--json"], CLIENT_TIMEOUT, ctx.environ,
                                   capture=True)
    except subprocess.TimeoutExpired:
        return f"not audited: `codex mcp list --json` did not finish within {CLIENT_TIMEOUT}s", []
    except OSError:
        return "not audited: codex could not be run", []
    if rc != 0:
        return "not audited: " + codex_failure(rc, err), []
    try:
        data = json.loads(out.decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, DuplicateKey, UnicodeDecodeError):
        return "not audited: `codex mcp list --json` printed something this cannot read", []
    try:
        regs = [codex_entry(name, entry, config)
                for name, entry in codex_items(data) if name in SERVERS]
    except ShapeError as e:
        return f"not audited: `codex mcp list --json` has an unexpected shape ({e})", []
    order = list(SERVERS)
    return "ok", sorted(regs, key=lambda r: order.index(r.name))


READERS = ((CLAUDE_CODE, read_claude_code), (DESKTOP, read_desktop), (CODEX, read_codex),
           (GEMINI, read_gemini))


# ── Classification ─────────────────────────────────────────────────────────────────────────────

class Context(object):
    def __init__(self, environ, system_applications):
        self.environ = dict(environ)
        self.home = home_dir()
        self.path = self.environ.get("PATH", os.defpath)
        self.system_applications = system_applications
        self.configs = {}
        self.logs = []
        self.live = {}
        self.running = None
        self.asked_running = False


class Finding(object):
    def __init__(self, reg):
        self.reg = reg
        self.state = None
        self.reason = None
        self.live = None
        self.warnings = []
        self.action = "none"
        self.todo = None
        self.row = None

    def leave(self, state, reason):
        self.state = state
        self.reason = reason
        self.action = "leave"
        self.row = f"{self.reg.label()}: {reason}"
        return self

    def dead(self, reason):
        self.state = "dead"
        self.reason = reason


def client_path(client, ctx):
    """The PATH a client hands a server, as M3 measured it; None where it is not measured."""
    if client in INHERITS_PATH:
        return ctx.path
    if client == DESKTOP:
        return DESKTOP_PATH
    return None


def expand_home(command, home):
    if command == "~" or command.startswith("~/"):
        return home.rstrip("/") + command[1:]
    return command


def same_file(path, std):
    return path == std or os.path.realpath(path) == os.path.realpath(std)


def interpreter_keys(keys):
    return sorted(key for key in keys if key in INTERPRETER_KEYS or key.startswith("UV_"))


def venv_of(interp):
    d = os.path.dirname(os.path.dirname(interp))
    return d if os.path.isfile(os.path.join(d, "pyvenv.cfg")) else None


def pyvenv_home(venv):
    try:
        with open(os.path.join(venv, "pyvenv.cfg"), encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.partition("=")
                if sep and key.strip().lower() == "home":
                    return value.strip()
    except (OSError, UnicodeDecodeError):
        return None
    return None


def first_hop_out(path, venv):
    """The first link target outside the venv, read one hop at a time, never resolved further.

    Plan 1's recorded-path rule: Homebrew's `opt/python@3.14` is itself a link into the Cellar,
    so a realpath would call every venv built on `opt/` Cellar-pinned, which it is not.
    """
    inside = os.path.normpath(venv) + os.sep
    p = path
    for _ in range(40):
        if not os.path.islink(p):
            return None
        nxt = os.path.normpath(os.path.join(os.path.dirname(p), os.readlink(p)))
        if not nxt.startswith(inside):
            return nxt
        p = nxt
    return None


def cellar_pinned(interp):
    venv = venv_of(interp)
    if not venv:
        return False
    hop = first_hop_out(interp, venv)
    home = pyvenv_home(venv)
    return any(p and "/Cellar/" in p for p in (hop, home))


def shebang(path):
    """("interpreter", <absolute Python path>) or ("launcher", <basename>)."""
    base = os.path.basename(path)
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return "launcher", base
    if not head.startswith(b"#!"):
        return "launcher", base
    lines = head.split(b"\n")
    parts = lines[0][2:].decode("utf-8", "replace").split()
    if not parts:
        return "launcher", base
    interp = parts[0]
    if os.path.basename(interp) == "sh" and len(lines) > 1:
        m = EXEC_RE.match(lines[1].decode("utf-8", "replace"))
        if m:
            interp = next(g for g in m.groups() if g)
    if os.path.isabs(interp) and PYTHON_RE.match(os.path.basename(interp)):
        return "interpreter", interp
    return "launcher", os.path.basename(interp)


def executable_kind(path, args, server):
    """A12: ("interpreter", <path>), ("launcher", <basename>) or ("module", None)."""
    base = os.path.basename(path)
    if base in LAUNCHERS:
        return "launcher", base
    if PYTHON_RE.match(base):
        if args == ["-m", server.module]:
            return "interpreter", path
        if args[:1] == ["-m"]:
            return "module", None
        return "launcher", base
    return shebang(path)


def interpreter_runs(interp, ctx):
    try:
        rc, _, _ = run_bounded([interp, "-I", "-c", PROBE], PROBE_TIMEOUT, ctx.environ,
                               capture=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return rc == 0


def interpreter_dead(interp, ctx):
    """R_PY_GONE, R_PY_BROKEN, or None when it runs. Cached: one probe per interpreter."""
    if interp in ctx.live:
        return ctx.live[interp]
    why = None
    if not os.path.exists(interp):
        why = R_PY_GONE
    else:
        venv = venv_of(interp)
        if venv:
            home = pyvenv_home(venv)
            if home is not None and not os.path.isdir(home):
                why = R_PY_GONE
            elif not os.path.exists(os.path.join(venv, "bin", "python3")):
                why = R_PY_GONE
        if why is None and not interpreter_runs(interp, ctx):
            why = R_PY_BROKEN
    ctx.live[interp] = why
    return why


def standard_dead(path, server, ctx):
    """True when the standard binary cannot start. It is never launched: only its Python is."""
    if not os.path.exists(path):
        return True
    if not os.path.isfile(path) or not os.access(path, os.X_OK):
        return True
    kind, detail = executable_kind(path, [], server)
    return kind == "interpreter" and interpreter_dead(detail, ctx) is not None


def desktop_running(ctx):
    """True, False, or None when it cannot be told. By executable path, never process name:
    `claude` is also Claude Code, whose updater renames its running image (AGENTS.md)."""
    if ctx.asked_running:
        return ctx.running
    ctx.asked_running = True
    exe = which("ps", ctx.path)
    if not exe:
        return None
    try:
        rc, out, _ = run_bounded([exe, "-axo", "comm="], CLIENT_TIMEOUT, ctx.environ, capture=True)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if rc != 0:
        return None
    targets = {"/" + DESKTOP_EXECUTABLE, os.path.join(ctx.home, DESKTOP_EXECUTABLE)}
    lines = out.decode("utf-8", "replace").splitlines()
    ctx.running = any(line.strip() in targets for line in lines)
    return ctx.running


def classify(reg, ctx):
    f = Finding(reg)
    if reg.transport != "stdio":
        return f.leave("not-audited", R_NOT_STDIO)
    server = SERVERS[reg.name]
    std = os.path.join(ctx.home, ".local", "bin", server.entry)
    command = expand_home(reg.command, ctx.home)
    if "/" not in command:
        path = client_path(reg.client, ctx)
        if path is None:
            return f.leave("unchecked", R_DESKTOP_PATH)
        resolved = which(command, path)
    elif not os.path.isabs(command):
        return f.leave("unchecked", R_RELATIVE)
    else:
        resolved = command

    # 1. standard, before any liveness check: a dead standard binary is reinstalled by its
    #    setup, never re-pointed at itself.
    if resolved is not None and same_file(resolved, std):
        f.state = "standard"
        f.live = not standard_dead(resolved, server, ctx)
        if not f.live:
            f.reason = R_STANDARD_DEAD
            f.row = f"{reg.label()}: {R_STANDARD_DEAD}"
        return f

    # 2. dead: the command itself.
    if resolved is None or not os.path.exists(resolved):
        f.dead(R_MISSING)
    elif not os.path.isfile(resolved) or not os.access(resolved, os.X_OK):
        f.dead(R_NOT_EXEC)
    else:
        # 3. a launcher form, or a module this does not know, is left and never launched.
        kind, detail = executable_kind(resolved, reg.args, server)
        if kind == "launcher":
            return f.leave("launcher", R_LAUNCHER.format(base=detail))
        if kind == "module":
            return f.leave("unrecognised", R_MODULE)
        # 4. dead: its interpreter.
        why = interpreter_dead(detail, ctx)
        if why:
            f.dead(why)
        else:
            # 5. it works, elsewhere.
            f.state = "elsewhere"
            f.live = True
            f.reason = R_ELSEWHERE.format(path=tilde(resolved), entry=server.entry)
            if cellar_pinned(detail):
                f.warnings.append(W_CELLAR)
    if f.state == "dead":
        f.live = False
    decide(f, reg, ctx, server)
    return f


def decide(f, reg, ctx, server):
    """re-point, or leave with the reason and a to-do where somebody has to act."""
    label = reg.label()
    target = f"~/.local/bin/{server.entry}"
    if f.state == "elsewhere" and not REPOINT_WORKING_ELSEWHERE:
        f.action = "leave"
        f.row = f"{label}: {f.reason}; its Python runs, so it is left as it is"
        f.todo = (f"{label} points at {tilde(expand_home(reg.command, ctx.home))}, not {target}; "
                  "if that is not deliberate, re-point it")
        return
    who = f"{label} is dead" if f.state == "dead" else f"{label} {f.reason}"
    block = todo = None
    if reg.scope == "local" and LOCAL_SCOPE_ACTION != "repoint":
        if LOCAL_SCOPE_ACTION == "report":
            block = f"re-point it at {target} by hand"
        else:
            keys = sorted(reg.env)
            lose = (f"removing it drops its settings ({', '.join(keys)})" if keys
                    else "it has no settings to lose")
            block = ("rebuild that checkout's venv, or remove the local entry so your user entry "
                     f"applies there; {lose}")
        todo = f"{who}: {block}"
    elif reg.args and reg.args != ["-m", server.module]:
        block = R_ARGS
        todo = f"{who}, and {block}; fix it by hand"
    elif interpreter_keys(reg.env):
        keys = interpreter_keys(reg.env)
        block = R_KEYS.format(keys=" and ".join(keys), s="" if len(keys) == 1 else "s")
        todo = f"{who}, and {block}; fix it by hand"
    elif reg.config_is_link:
        block = R_LINK.format(path=tilde(os.path.realpath(reg.config)))
        todo = f"{who}, and {block}"
    elif reg.client == DESKTOP and not WRITE_DESKTOP_WHILE_RUNNING:
        running = desktop_running(ctx)
        if running is not False:
            f.action = "leave"
            f.row = (ROW_DESKTOP_RUNNING if running else ROW_DESKTOP_UNKNOWN).format(name=reg.name)
            f.todo = T_QUIT_DESKTOP
            return
    if block:
        f.action = "leave"
        f.row = f"{label}: {f.reason}; left as it is: {block}"
        f.todo = todo
        return
    f.action = "re-point"
    keys = sorted(reg.env)
    keep = f", keeping its settings ({', '.join(keys)})" if keys else ""
    f.row = f"{label}: {f.reason}; it will be re-pointed at {target}{keep}"
    if reg.client in PASSES_INHERITED_ENV:
        inherited = interpreter_keys(ctx.environ)
        if inherited:
            many = len(inherited) > 1
            f.warnings.append(W_INHERITED.format(keys=" and ".join(inherited),
                                                 verb="are" if many else "is", client=reg.client,
                                                 pron="them" if many else "it"))


# ── The plan ───────────────────────────────────────────────────────────────────────────────────

def audit(ctx):
    clients = []
    findings = []
    for client, reader in READERS:
        status, regs = reader(ctx)
        clients.append((client, status))
        findings.extend(classify(reg, ctx) for reg in regs)
    return clients, findings


def render(clients, findings):
    rows = []
    for client, status in clients:
        if status == "no config yet":
            rows.append(f"{client}: no config yet (#156)")
        elif status != "ok":
            rows.append(f"{client}: {status}")
        for f in findings:
            if f.reg.client != client:
                continue
            if f.row:
                rows.append(f.row)
            rows.extend(f"{f.reg.label()}: {w}" for w in f.warnings)
    for name in SERVERS:
        if name in VERIFY_ON_RERUN and any(f.reg.name == name and f.reg.transport == "stdio"
                                           for f in findings):
            rows.append(f"after the repair, check that {name} answers an MCP initialize "
                        "handshake, launched with its registered command and settings")
    n = len(findings)
    m = len({f.reg.client for f in findings})
    k = sum(1 for f in findings if not f.row and not f.warnings)
    rows.append(f"{plural(n, 'CSA registration')} in {plural(m, 'client')}; "
                f"{k} need{'s' if k == 1 else ''} nothing")
    return rows


def plan_document(ctx, clients, findings):
    """What --out records: findings with fingerprints and key NAMES, never a value or an arg."""
    return {
        "tool": "csa-mcp-registrations",
        "version": SCRIPT_VERSION,
        "clients": [{"client": c, "status": s,
                     "config": tilde(ctx.configs[c]) if c in ctx.configs else None}
                    for c, s in clients],
        "findings": [{
            "client": f.reg.client,
            "scope": f.reg.scope,
            "project": f.reg.project,
            "name": f.reg.name,
            "transport": f.reg.transport,
            "fingerprint": f.reg.fingerprint(),
            "env_keys": sorted(f.reg.env),
            "token_keys": sorted(k for k in f.reg.env if k in TOKEN_PATH_KEYS),
            "config_is_link": f.reg.config_is_link,
            "state": f.state,
            "live": f.live,
            "reason": f.reason,
            "warnings": f.warnings,
            "action": f.action,
            "todo": f.todo,
        } for f in findings],
    }


def write_private(path, text):
    """mkstemp (0600) beside the target, fsync, then os.replace: never a torn or wider file."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".csa-registrations-")
    try:
        if hasattr(os, "fchmod"):  # mkstemp is 0600 already; this says so, and keeps it so
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def plan(args):
    ctx = Context(os.environ, args.system_applications)
    clients, findings = audit(ctx)
    rows = render(clients, findings)
    if args.out:
        text = json.dumps(plan_document(ctx, clients, findings), indent=2, ensure_ascii=False)
        write_private(args.out, text + "\n")
    for line in ctx.logs:
        print(f"log\t{line}")
    for row in rows:
        print(f"row\t{row}")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--version", action="version", version=SCRIPT_VERSION)
    sub = ap.add_subparsers(dest="command")
    p = sub.add_parser("plan", help="report every CSA registration and what would change; "
                                    "writes nothing but --out")
    p.add_argument("--out", metavar="FILE", help="record the findings (no values) for apply")
    p.add_argument("--system-applications", default="/Applications", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if args.command != "plan":
        ap.print_usage(sys.stderr)
        return 2
    try:
        return plan(args)
    except Exception as e:
        # The type and the line only: an exception's message can carry what it was handed.
        tb = e.__traceback__
        while tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
        line = tb.tb_lineno if tb is not None else "?"
        print(f"csa-mcp-registrations: internal error ({type(e).__name__} at line {line}); "
              "nothing was written", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
