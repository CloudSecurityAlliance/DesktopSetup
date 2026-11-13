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

A dead one is planned for a re-point at the standard binary, changing only its command, unless
the plan's decisions leave it: a local-scope entry, an env that would point the release binary
at another tree, a config that is a symlink, or Claude Desktop running.

`plan` writes nothing but the plan file it is asked for. `apply` re-audits, and re-points only
what that plan file showed as a re-point and is unchanged since (same client, scope, project,
name and fingerprint), and only when the standard binary is there. It edits the client's own
file, never through a client CLI (argv is visible to every account): `command`, plus `args` in
the pinned `-m <module>` form, and nothing else. A write to Claude Code's config takes Claude
Code's own lock (M1), never breaks one, abandons the write if it has held it 5 s, and removes
only the lock it made. Every write makes no backup until the file is known unchanged since it
was read, keeps the file's mode, refuses a config with a second name (a hard link), and reads
back what it wrote, restoring the backup if that differs. Backups are `<file>.bak-<14 digits>`,
pruned to three, as csa-claude-connectors.py names and prunes them; each holds the same secrets
as its file, at its mode. SIGTERM and SIGHUP stop apply through its clean-ups, and each apply
removes this tool's own temp files older than itself that a run stopped mid-write left.

Re-serialising a JSON config keeps every value, the key order, the indent width (tabs too), the
trailing newline or its absence, and CRLF. What it can change is spelling only: the whitespace
between tokens becomes json.dumps's (one item per line, `": "`); a `\\u` escape of a printable
character is written as the character (`\\u00e9`), while a lone surrogate stays escaped; and a
number is written in Python's form (`1.5e3` as `1500.0`, `-0` as `0`). A config holding a
number no JSON client can read back (`1e999`, NaN) is not rewritten. mkstemp plus os.replace
keeps the mode, not the file's extended attributes or ACLs. Codex's config.toml is edited line
by line: only the `command` line, and the `args` line for the `-m` form, change.

Neither ever opens a token, OAuth state or credential file, runs a server, or prints an env
VALUE - only key names and counts. The values it reads stay in memory, and a value is written
only back into the file it came from and that file's backup. Its own client calls (`codex mcp
list|get --json`, the probe of each interpreter) run from a fresh, empty directory, so a project
config in the caller's directory cannot stand in for the user's.

The plan's decisions are the constants below, each at its safe default until the CINO answers
(plans/2026-11-12-registration-repair.md, D1-D5); measurements it relies on are in
plans/reviews/2026-11-12-registration-repair-measurements.md (M0, M3, M7).

    python3 -I scripts/csa-mcp-registrations.py plan                   # print the plan
    python3 -I scripts/csa-mcp-registrations.py plan --out plan.json   # and record it
    python3 -I scripts/csa-mcp-registrations.py apply --approved plan.json
    python3 -I scripts/csa-mcp-registrations.py apply                  # by hand: plan, then apply

`plan` prints one `row<TAB>text` line per row of the plan, and `log<TAB>text` for what is only
logged. --out must be a new file: an existing one, or the path of any client's config, is
refused and left as it is. Exit 0, or 2 on an error, in which case no plan file is left.

`apply` prints `ok<TAB>`, `warn<TAB>` and `info<TAB>` lines. Its to-dos (restart a client, quit
Claude Desktop, a registration left for somebody to fix) go to CSA_TODO_FILE when it is set, and
are printed as `info` lines when it is not. Exit 0, or 2 on an internal error.
"""
import argparse
import collections
import contextlib
import copy
import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata

SCRIPT_VERSION = "2026-11-13T14:57Z"

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
# this one. Claude Desktop's PATH has no value that holds for every machine, so DESKTOP_PATH is
# None and a bare-name Desktop entry is left, never called dead (A8). M3 recorded one Mac's
# Desktop PATH on 2026-11-13; it is not applied: AI ruling 2026-11-13, P1, machine-specific
# (nvm and pyenv directories) and possibly Desktop's fallback PATH.
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
# Not the plan's verbatim text ("...is not measured yet"): M3 has since measured one Mac's, so
# that would be untrue. Reworded 2026-11-13 under P2, honesty of what we claim.
R_DESKTOP_PATH = ("not checked: Claude Desktop's PATH differs from machine to machine, so a "
                  "bare command name can't be resolved here")
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


# A newline or a tab in a project path or an env key name would let a config forge a
# `row<TAB>` line of its own, so every piece of a config that reaches a row, a to-do or a log
# line passes through clean(): label(), tilde() and keys_text(). By Unicode category, not by a
# list of code points, because a list misses the next one (review of e62c775: zero-width
# spaces and joiners, word joiner, soft hyphen, tag characters):
#   Cc  every control, the tab and the newline included - they are what forges a row;
#   Cf  format characters: bidi marks and controls, zero-width characters, the BOM, tags;
#   Zl, Zp  the line and paragraph separators;
#   Cs  lone surrogates, which no UTF-8 encoder accepts;
#   Co  private use, whose look is whatever a font makes of it.
# Each is shown as `?`.
UNSAFE_CATEGORIES = ("Cc", "Cf", "Zl", "Zp", "Cs", "Co")


def clean(text):
    return "".join("?" if unicodedata.category(c) in UNSAFE_CATEGORIES else c
                   for c in str(text))


def keys_text(keys, sep=", "):
    return sep.join(clean(k) for k in keys)


def tilde(path):
    """`path` with the home directory shown as `~` (either spelling of it), cleaned."""
    path = str(path)
    for home in (home_dir(), os.path.realpath(home_dir())):
        home = home.rstrip("/")
        if home and (path == home or path.startswith(home + "/")):
            return clean("~" + path[len(home):])
    return clean(path)


def linked_config(path):
    """A10: True when the config, or any directory between it and its anchor, is a link.

    `os.path.islink` sees the last component only, so a `~/.gemini` linked into a dotfiles
    repository read as a plain file, and a repair would have written into that repository. The
    anchor is the home directory for a config under it, else the directory that holds the
    config's own directory (a CLAUDE_CONFIG_DIR elsewhere). Links above the anchor, such as a
    home directory on another volume, belong to the machine, not to the config - and so does a
    top-level directory: macOS's /tmp and /var are links to /private/..., so for a config
    directly in one, the anchor is that directory itself.

    The limit, kept: outside HOME, a link ABOVE the config's own directory (its grandparent or
    higher) is not detected. Such a path is the machine's layout or the person's explicit
    CLAUDE_CONFIG_DIR / CODEX_HOME, not a dotfile linked in.
    """
    path = os.path.abspath(path)
    home = os.path.abspath(home_dir()).rstrip("/")
    if home and path.startswith(home + "/"):
        anchor = home
    else:
        anchor = os.path.dirname(os.path.dirname(path))
        if os.path.dirname(anchor) == anchor:  # the root: the config's directory is top-level
            anchor = os.path.dirname(path)
    expected = os.path.join(os.path.realpath(anchor), os.path.relpath(path, anchor))
    return os.path.realpath(path) != expected


def own_line(exc):
    """The line in THIS file nearest a failure. A stdlib frame's line number means nothing to
    someone reading this script, so the innermost frame of this file is the one reported."""
    me = os.path.abspath(__file__)
    line = "?"
    tb = exc.__traceback__
    while tb is not None:
        if os.path.abspath(tb.tb_frame.f_code.co_filename) == me:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line


def describe_error(exc):
    """The type and this file's line only: an exception's message can carry what it was handed."""
    return f"{type(exc).__name__} at line {own_line(exc)}"


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
        self.config_is_link = linked_config(config)

    def where(self):
        if self.client == CLAUDE_CODE:
            scope = "user scope" if self.scope == "user" else f"local scope, {tilde(self.project)}"
            return clean(f"Claude Code ({scope})")
        return clean(self.client)

    def label(self):
        return clean(f"{self.name} in {self.where()}")

    def fingerprint(self):
        """sha256 of the command, the args and the SORTED KEY NAMES of the env - never a value."""
        blob = json.dumps([self.command, self.args, sorted(self.env)],
                          separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _text(value):
    """A string a client could pass to exec. No client can run one holding a NUL, or a lone
    surrogate (JSON's `"\\ud800"`), which no UTF-8 encoder accepts; the path calls, the
    fingerprint and the plan file would all raise on one. So it is a malformed entry of that
    client, not a dead one, and not a failure of the whole audit."""
    if not isinstance(value, str) or "\x00" in value:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _strings(value, what):
    if not isinstance(value, list) or not all(_text(a) for a in value):
        raise ShapeError(what)
    return value


def _env(value, what):
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(_text(k) and _text(v) for k, v in value.items()):
        raise ShapeError(what)
    return value


# The transports the plan file may name. A `type` the config spells otherwise is recorded as
# "unknown": the config's own text never reaches the plan file (review of e62c775).
TRANSPORTS = ("stdio", "http", "sse", "streamable_http", "streamable-http", "ws")


def transport_name(kind, default):
    return default if kind is None else (kind if kind in TRANSPORTS else "unknown")


def entry_kind(value, what):
    """An entry's `type`: absent, or text a client could hold. Anything else is malformed."""
    if value is not None and not _text(value):
        raise ShapeError(what)
    return value


def json_entry(client, scope, project, name, entry, config):
    """A Claude Code, Claude Desktop or Gemini entry: {command, args, env, ...}."""
    what = f"{name}'s entry"
    if not isinstance(entry, dict):
        raise ShapeError(what)
    kind = entry_kind(entry.get("type"), what)
    if "command" in entry and kind in (None, "stdio"):
        command = entry["command"]
        if not _text(command) or not command:
            raise ShapeError(what)
        args = entry.get("args")
        args = [] if args is None else _strings(args, what)
        env = _env(entry.get("env"), what)
        other = {k: v for k, v in entry.items() if k not in ("command", "args", "env")}
        return Registration(client, scope, project, name, config, command, args, env, "stdio",
                            other)
    if kind not in (None, "stdio") or "url" in entry or "httpUrl" in entry:
        return Registration(client, scope, project, name, config, None, [], {},
                            transport_name(kind, "http"), entry)
    raise ShapeError(what)


def load_json(path, what):
    """(data, None) or (None, why). Duplicate keys, torn files and comments are all unreadable."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None, f"its {what} could not be read"
    if raw.startswith(b"\xef\xbb\xbf"):
        return None, f"its {what} starts with a byte-order mark, which this does not read"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"its {what} is not UTF-8"
    return parse_json(text, f"its {what}")


def parse_json(text, what):
    """(data, None) or (None, why), for a config file or a CLI's output."""
    try:
        return json.loads(text, object_pairs_hook=_unique), None
    except DuplicateKey:
        return None, f"{what} has a duplicate key, so which value the client uses is unclear"
    except RecursionError:
        return None, f"{what} is nested too deeply to read"
    except ValueError:
        return None, f"{what} is not plain JSON (cut short, or with comments)"


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

def config_path(client, ctx):
    """Where each client keeps the config this reads. One function, so the readers and the
    --out check cannot disagree about it."""
    if client == CLAUDE_CODE:
        cfg_dir = ctx.environ.get("CLAUDE_CONFIG_DIR")
        return os.path.join(cfg_dir or ctx.home, ".claude.json")
    if client == DESKTOP:
        return os.path.join(ctx.home, "Library", "Application Support", "Claude",
                            "claude_desktop_config.json")
    if client == CODEX:
        codex_home = ctx.environ.get("CODEX_HOME") or os.path.join(ctx.home, ".codex")
        return os.path.join(codex_home, "config.toml")
    return os.path.join(ctx.home, ".gemini", "settings.json")


def read_claude_code(ctx):
    if on_windows():
        return WINDOWS, []
    path = config_path(CLAUDE_CODE, ctx)
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
    path = config_path(DESKTOP, ctx)
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
    path = config_path(GEMINI, ctx)
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
        kind = entry_kind(transport.get("type"), what)
    elif transport is None or isinstance(transport, str):
        fields = entry
        kind = entry_kind(transport or entry.get("type"), what)
    else:
        raise ShapeError(what)
    if fields.get("command") is not None and kind in (None, "stdio"):
        command = fields["command"]
        if not _text(command) or not command:
            raise ShapeError(what)
        args = fields.get("args")
        args = [] if args is None else _strings(args, what)
        env = _env(fields.get("env"), what)
        other = {k: v for k, v in entry.items() if k != "transport"}
        other.update({k: v for k, v in fields.items() if k not in ("command", "args", "env")})
        return Registration(CODEX, "user", None, name, config, command, args, env, "stdio", other)
    if kind not in (None, "stdio") or fields.get("url") is not None:
        return Registration(CODEX, "user", None, name, config, None, [], {},
                            transport_name(kind, "http"))
    raise ShapeError(what)


def read_codex(ctx):
    """`codex mcp list --json`, since Apple's Python 3.9 has no tomllib (A7). A failing CLI is
    "not audited", never "no registrations"."""
    if on_windows():
        return WINDOWS, []
    config = config_path(CODEX, ctx)
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
        text = out.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    data, why = parse_json(text, "its output") if text is not None else (None, "not UTF-8")
    if why:
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
        self.fingerprint = None

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
    """The PATH a client hands a server, as M3 measured it; None where no single value holds."""
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
    """Does the interpreter start and import its stdlib? `-B` because without it a fresh
    interpreter writes a .pyc for every module the probe imports into its own stdlib (review of
    fba8c54: 55 files), and `plan` writes nothing. PYTHONDONTWRITEBYTECODE as well, for an
    "interpreter" that is a wrapper: `-I` makes a real Python ignore it."""
    env = dict(ctx.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        rc, _, _ = run_bounded([interp, "-I", "-B", "-c", PROBE], PROBE_TIMEOUT, env,
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


def desktop_running(ctx, fresh=False):
    """True, False, or None when it cannot be told. By executable path, never process name:
    `claude` is also Claude Code, whose updater renames its running image (AGENTS.md).
    Asked once per run, unless `fresh`: apply asks again just before it writes Desktop's
    config, since Desktop can start while the run waits on a lock or a client."""
    if ctx.asked_running and not fresh:
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
        # A8: a bare name resolves on the client's own PATH, as M3 measured it. One that does
        # not resolve there - its own `<entry>` name included - cannot start, so it is dead and
        # re-pointed at the absolute standard binary, by design: the plan's #176 row, "a
        # bare-name ... entry that does not resolve on [the client's] measured PATH is dead and
        # re-pointed at the absolute binary". Where no single PATH holds (Desktop), it is left.
        path = client_path(reg.client, ctx)
        if path is None:  # Desktop: M3's one-Mac PATH not applied (AI ruling 2026-11-13, P1)
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
            return f.leave("launcher", R_LAUNCHER.format(base=clean(detail)))
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
            lose = (f"removing it drops its settings ({keys_text(keys)})" if keys
                    else "it has no settings to lose")
            block = ("rebuild that checkout's venv, or remove the local entry so your user entry "
                     f"applies there; {lose}")
        todo = f"{who}: {block}"
    elif reg.args and reg.args != ["-m", server.module]:
        block = R_ARGS
        todo = f"{who}, and {block}; fix it by hand"
    elif interpreter_keys(reg.env):
        keys = interpreter_keys(reg.env)
        block = R_KEYS.format(keys=keys_text(keys, " and "), s="" if len(keys) == 1 else "s")
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
    keep = f", keeping its settings ({keys_text(keys)})" if keys else ""
    f.row = f"{label}: {f.reason}; it will be re-pointed at {target}{keep}"
    if reg.client in PASSES_INHERITED_ENV:
        inherited = interpreter_keys(ctx.environ)
        if inherited:
            many = len(inherited) > 1
            f.warnings.append(W_INHERITED.format(keys=keys_text(inherited, " and "),
                                                 verb="are" if many else "is", client=reg.client,
                                                 pron="them" if many else "it"))


# ── The plan ───────────────────────────────────────────────────────────────────────────────────

def audit(ctx):
    """Each client is read and classified on its own: whatever one client's config holds, a
    failure there makes THAT client "not audited" (B9), and the other three are still audited."""
    clients = []
    findings = []
    for client, reader in READERS:
        try:
            status, regs = reader(ctx)
            found = [classify(reg, ctx) for reg in regs]
            for f in found:  # here, so a value it cannot hash is this client's failure only
                f.fingerprint = f.reg.fingerprint()
        except Exception as e:
            status, found = f"not audited: this audit failed on it ({describe_error(e)})", []
        clients.append((client, status))
        findings.extend(found)
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
    # The plan's text is `<n> CSA registrations in <m> clients; <k> need nothing`. That template
    # was written in the plural, and taken literally it prints "1 clients" and "1 need": the
    # error is the plan's, so the words here agree with their numbers (the AI's decision, under
    # P4, wording quality; the plural reads exactly as the plan's text).
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
            # The file it is in, resolved: apply's approval binds it (A4). A path, not a value.
            "config": os.path.realpath(f.reg.config),
            "transport": f.reg.transport,
            "fingerprint": f.fingerprint,
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


def out_refusal(path, ctx):
    """Why --out may not be written, or None.

    --out must be a NEW file. An existing one is refused whatever it is - a client's config, a
    plan from an earlier run, anything - and left exactly as it was: telling a plan file from a
    secret would mean opening the file, and this never opens one it was not asked to read
    (review of e62c775: `--out ~/.claude.json` replaced that config). The path of a config any
    client reads is refused even before that config exists. The entry scripts always pass a
    path in a fresh `mktemp -d` directory, so neither ever happens to them.
    """
    if os.path.lexists(path):
        return (f"--out {tilde(path)} already exists; a plan is written only as a new file, so "
                "it was left as it is")
    real = os.path.realpath(path)
    for client in CLIENTS:
        if real == os.path.realpath(config_path(client, ctx)):
            return f"--out {tilde(path)} is where {client} keeps its config; refused"
    return None


def create_private(path, text):
    """Create `path` whole, at 0600, and never over anything: mkstemp beside it, fsync, then
    os.link, which fails if the name exists by then, where os.replace would silently replace
    whatever had appeared there since out_refusal looked. Returns the new file's identity,
    taken from the open file before the name exists: an lstat of `path` after the link could
    name a file swapped in since, which discard() would then delete (review of a9f9a94)."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".csa-registrations-")
    try:
        if hasattr(os, "fchmod"):  # mkstemp is 0600 already; this says so, and keeps it so
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
            st = os.fstat(f.fileno())
        os.link(tmp, path)
    finally:
        if os.path.lexists(tmp):
            os.unlink(tmp)
    return st.st_dev, st.st_ino


def config_at(identity, ctx):
    """The client whose config IS the file this run just created, or None.

    By device and inode, not by name: on a case-insensitive volume `~/.CLAUDE.json` is
    `~/.claude.json`, and out_refusal's comparison of realpath strings says it is not (review of
    a9f9a94); a Unicode-normalising volume does the same with other spellings. lstat and stat
    both, so a config path that is itself a link to the new file is caught too.
    """
    for client in CLIENTS:
        path = config_path(client, ctx)
        for look in (os.lstat, os.stat):
            try:
                st = look(path)
            except OSError:
                continue
            if (st.st_dev, st.st_ino) == identity:
                return client
    return None


def discard(path, identity):
    """Remove the plan file THIS run created, and only that file: when --out no longer is it
    (somebody replaced it since), it is left. Nothing a failed run created passes for a plan."""
    if not path or identity is None:
        return
    try:
        st = os.lstat(path)
        if (st.st_dev, st.st_ino) == identity:
            os.unlink(path)
    except OSError:
        pass


class OutputLost(Exception):
    """The plan could not be shown, so no plan file may stand for it."""


def say(message):
    """A line on stderr, when there is a stderr. print(file=None) would fall back to stdout."""
    if sys.stderr is not None:
        print(f"csa-mcp-registrations: {message}", file=sys.stderr)


def show(lines):
    """Write and flush each (kind, text), or raise OutputLost. Flushed here, not at exit: a
    failed flush at exit is exit 120 with the plan file already written (review of fba8c54).
    Every text is cleaned once more on the way out, whatever built it."""
    out = sys.stdout
    if out is None:  # started with stdout closed
        raise OutputLost()
    try:
        for kind, text in lines:
            out.write(f"{kind}\t{clean(text)}\n")
        out.flush()
    except (OSError, ValueError):
        # Point fd 1 at /dev/null, so the flush the interpreter makes at exit cannot fail a
        # second time and turn exit 2 into 120.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 1)
            os.close(devnull)
        except OSError:
            pass
        raise OutputLost()


def plan(args, created):
    """`created` receives the identity of the plan file this run makes, for main() to remove
    it if the run then fails."""
    ctx = Context(os.environ, args.system_applications)
    if args.out:
        why = out_refusal(args.out, ctx)
        if why:
            say(why)
            return 2
    clients, findings = audit(ctx)
    rows = render(clients, findings)
    lines = [("log", line) for line in ctx.logs] + [("row", row) for row in rows]
    if args.out:
        # ensure_ascii: a project path or a key name is recorded exactly, as escapes, so no
        # invisible or reordering character from a config is ever written raw (and a value
        # that UTF-8 cannot encode cannot fail the write).
        text = json.dumps(plan_document(ctx, clients, findings), indent=2, ensure_ascii=True)
        created.append(create_private(args.out, text + "\n"))
        clash = config_at(created[-1], ctx)
        if clash:
            discard(args.out, created[-1])
            del created[:]
            say(f"--out {tilde(args.out)} is, on this volume, where {clash} keeps its config; "
                "refused, and nothing was written")
            return 2
    try:
        show(lines)
    except OutputLost:
        # Nobody saw this plan, so nothing may later act on it as the one agreed to (A4).
        discard(args.out, created[-1] if created else None)
        del created[:]
        say("the plan could not be printed; nothing was written")
        return 2
    return 0


# ── apply: re-point an approved dead registration in place, changing only its command ────────────

# M1: Claude Code takes `<config>.lock`, a DIRECTORY, around each write of its config, and waits
# for one somebody else holds. apply takes it the same way and holds it across the read, the
# checks, the backup and the replace: milliseconds, well under the 10 s after which
# proper-lockfile, which Claude Code bundles, calls a lock stale. It waits at most
# CLAUDE_LOCK_WAIT for a held lock and NEVER breaks one (the measurement review's ruling,
# 2026-11-12, P1): breaking a lock a live session holds lets two writers race. So a crashed
# session's leftover lock blocks Claude Code's repair until somebody removes it; the to-do names
# the lock, and every other client is still repaired.
CLAUDE_LOCK_WAIT = 10.0
LOCK_POLL = 0.05
# Held longer than this (a slow disk, or a Mac that slept mid-write), the write is abandoned:
# past 10 s Claude Code may call the lock stale and take it over, and two writers would race.
# Wall-clock time, as proper-lockfile measures staleness: a monotonic clock stops in sleep.
LOCK_HOLD_MAX = 5.0

# A13: the same backup name, regex and cap as csa-claude-connectors.py, deliberately, so one
# prune bounds both tools' copies of a file that holds secrets (backup_rule_matches_connectors).
# The regex matches ONLY `<name>.bak-` plus fourteen digits: no other tool's backup is pruned.
BACKUPS_KEPT = 3
BACKUP_RE = re.compile(r"\.bak-\d{14}$")
TMP_PREFIX = ".csa-registrations-"
# The names mkstemp gives this tool's temp files: the prefix and eight of its characters. A run
# killed mid-write can leave one, holding the config's secrets; the next apply removes those
# older than itself, and nothing else.
TMP_NAME = re.compile(r"^\.csa-registrations-[a-z0-9_]{8}$")

# The tests set this to see, or move, a file between the steps of a write. Never set in a run.
TEST_HOOK = None

# The to-do ledger's orders (ENGINEERING.md, "The to-do ledger"): 10 restart, 40+ the installer's.
TODO_RESTART = 10
TODO_LEFT = 40

R_UNAPPROVED = "found after you agreed to the plan; not changed — run again"
R_NOT_PLANNED = "the plan you agreed to left it as it was; not changed — run again"
R_NO_PLAN = "not changed, because the plan you agreed to could not be read — run again"
R_NO_STANDARD = "its standard binary is not installed yet"
R_CHANGED = "changed while this ran; not written — run again"
R_NOT_CONFINED = "the edit could not be confined to its command; not changed"
R_UNWRITABLE_VALUE = "its config holds a value this cannot write back exactly; not changed"
R_UNWRITTEN = "its config could not be written ({why}); not changed"
R_RESTORED = ("its config did not read back as written, so it was restored from its backup; "
              "not changed")
R_UNRESTORED = ("its config did not read back as written, and restoring it failed; its backup "
                "is {backup}")
R_CODEX_LAYOUT = "its Codex entry is laid out in a way this cannot edit safely; left as it is"
R_CODEX_UNREAD = "Codex could not show it (`codex mcp get --json` failed); not changed"
R_LOCKED = ("Claude Code's config stayed locked for {secs:g}s, so it was not changed; the lock "
            "was left as it is")
R_LOCK_SLOW = ("the write held Claude Code's lock for more than {secs:g}s, near when Claude Code "
               "may take it over; not written — run again")
R_LOCK_LOST = "Claude Code's lock stopped being this run's during the write; not written — run again"
R_HARD_LINK = ("its config has another name too (a hard link), which a replace would cut off; "
               "not changed — edit it by hand")
T_LOCKED = "Claude Code's config is locked; close Claude Code and run again"
# A crashed process's lock outlives it, and closing Claude Code does not clear that one.
T_LOCKED_STALE = "; if Claude Code is not running, remove {lock}"
T_NO_STANDARD = "{label} is dead, and its standard binary is not installed yet; run this again once its setup has installed it"
T_RESTART = "Restart {client}"
OK_LINE = "{name} re-pointed in {where} at ~/.local/bin/{entry}; its {settings} kept"
# M1 (and M2 for Desktop): a running client keeps the command it started with, so a repair
# reaches what starts after it. The Claude Code line says so; every client also gets a restart.
OK_CLAUDE_CODE = "; Claude Code sessions started after this use it"


def emit(kind, text):
    show([(kind, text)])


def hook(point, path):
    if TEST_HOOK is not None:
        TEST_HOOK(point, path)


def unlink_quietly(path):
    try:
        os.unlink(path)
    except OSError:
        pass


def approval_key(client, scope, project, name, fingerprint, config):
    """What must match between the plan agreed to and this run (A4): the same registration, in
    the same place, with the same command, args and setting NAMES, in the same file (`config`,
    its realpath): a run under another HOME or CLAUDE_CONFIG_DIR is another file."""
    return (client, scope, project, name, fingerprint, config)


def key_of(f):
    return approval_key(f.reg.client, f.reg.scope, f.reg.project, f.reg.name, f.fingerprint,
                        os.path.realpath(f.reg.config))


def load_approved(path):
    """(the keys planned as re-points, every key planned, None), or (None, None, why). A key
    the file lists both as a re-point and as anything else counts as left: the safe side."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None, None, "it could not be opened"
    try:
        data, why = parse_json(raw.decode("utf-8"), "it")
    except UnicodeDecodeError:
        why = "not UTF-8"
    foreign = (None, None, "it is not a plan this tool wrote")
    if why or not isinstance(data, dict) or data.get("tool") != "csa-mcp-registrations":
        return foreign
    findings = data.get("findings")
    if not isinstance(findings, list):
        return foreign
    repoint, left, every = set(), set(), set()
    for f in findings:
        if not isinstance(f, dict):
            return foreign
        fields = (f.get("client"), f.get("scope"), f.get("name"), f.get("fingerprint"),
                  f.get("config"))
        project = f.get("project")
        if not all(isinstance(x, str) for x in fields) or not (project is None
                                                                 or isinstance(project, str)):
            return foreign
        key = approval_key(fields[0], fields[1], project, fields[2], fields[3], fields[4])
        every.add(key)
        (repoint if f.get("action") == "re-point" else left).add(key)
    return repoint - left, every, None


class Change(object):
    """One approved re-point, as the write needs it."""

    def __init__(self, finding, ctx):
        self.reg = finding.reg
        self.fingerprint = finding.fingerprint
        server = SERVERS[self.reg.name]
        self.entry = server.entry
        self.module = server.module
        self.command = os.path.join(ctx.home, ".local", "bin", server.entry)
        # The pinned interpreter form is the only one whose args change: to [] (#179 item 2).
        self.interp = self.reg.args == ["-m", server.module]


def done(change):
    reg = change.reg
    text = OK_LINE.format(name=reg.name, where=reg.where(), entry=change.entry,
                          settings=plural(len(reg.env), "setting"))
    if reg.client == CLAUDE_CODE:
        text += OK_CLAUDE_CODE
    return True, text, None


def refused(change, reason, order=TODO_LEFT, todo=None):
    label = change.reg.label()
    return False, f"{label}: {reason}", (order, todo or f"{label}: {reason}")


class Todos(object):
    """The closing to-dos: CSA_TODO_FILE when the installer set one, else `info` lines."""

    def __init__(self):
        self.items = []

    def add(self, order, title):
        item = (order, clean(title))
        if item not in self.items:
            self.items.append(item)

    def flush(self, environ):
        items = sorted(self.items, key=lambda it: it[0])  # stable: within an order, as found
        path = environ.get("CSA_TODO_FILE")
        if path and items:
            try:
                # The gate scripts' record, `<order>\t<title>\t-\t-`, so the installer's list
                # de-duplicates "Restart Claude Desktop" with theirs.
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write("".join(f"{order}\t{title}\t-\t-\n" for order, title in items))
                return
            except OSError:
                pass
        for _, title in items:
            emit("info", title)


# ── Writing a config: the same steps for every client ───────────────────────────────────────

class Locked(Exception):
    def __init__(self, lock):
        Exception.__init__(self)
        self.lock = lock


def dir_identity(path):
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return st.st_dev, st.st_ino, st.st_mtime_ns


class ClaudeLock(object):
    """Claude Code's own lock on its config (M1): mkdir `<config>.lock`, wait a bounded time
    for one that is held, never break it. What was created is recorded, so `check` can tell
    the write it is still this run's and held briefly, and the release removes only this run's
    lock: held past Claude Code's stale limit, the lock may have been taken over by then."""

    def __init__(self, path):
        self.lock = path + ".lock"
        self.mine = None
        self.taken = None

    def __enter__(self):
        deadline = time.monotonic() + CLAUDE_LOCK_WAIT
        while True:
            try:
                os.mkdir(self.lock, 0o700)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise Locked(self.lock)
                time.sleep(LOCK_POLL)
        self.taken = time.time()
        self.mine = dir_identity(self.lock)
        return self

    def ours(self):
        return self.mine is not None and dir_identity(self.lock) == self.mine

    def check(self):
        """None while the write may go on; else why it must stop."""
        if time.time() - self.taken > LOCK_HOLD_MAX:
            return R_LOCK_SLOW.format(secs=LOCK_HOLD_MAX)
        if not self.ours():
            return R_LOCK_LOST
        return None

    def __exit__(self, *exc):
        if self.ours():
            try:
                os.rmdir(self.lock)
            except OSError:
                pass
        return False


class NoLock(object):
    """The clients that take no lock on their config."""

    def __enter__(self):
        return self

    def check(self):
        return None

    def __exit__(self, *exc):
        return False


def identity(st):
    """What must not move between the read and the replace. The whole mode, not just the type:
    a chmod since the read changes no mtime, and the replace would put the old mode back."""
    return st.st_dev, st.st_ino, st.st_mtime_ns, st.st_size, st.st_mode


def moved(path, before):
    """Has the file at `path` changed since `before` was taken? A vanished file has."""
    try:
        return identity(os.lstat(path)) != identity(before)
    except OSError:
        return True


def prune_backups(path, keep=BACKUPS_KEPT):
    """`path`'s own backups, newest `keep` kept. csa-claude-connectors.py's prune, line for line
    in what it matches: the literal `.bak-` and exactly fourteen digits, sorted by name (the
    stamp is fixed-width), so no other tool's backup is ever touched."""
    d = os.path.dirname(path) or "."
    prefix = os.path.basename(path) + ".bak-"
    try:
        names = os.listdir(d)
    except OSError:
        return
    mine = sorted((n for n in names if n.startswith(prefix) and BACKUP_RE.search(n)),
                  reverse=True)
    for name in mine[keep:]:
        unlink_quietly(os.path.join(d, name))


def backup_stamp():
    """The %Y%m%d%H%M%S stamp csa-claude-connectors.py also uses, local time (A13)."""
    return time.strftime("%Y%m%d%H%M%S")


def make_backup(path, stamp, mode):
    """`<path>.bak-<stamp>`, a copy2 of the file, at its mode and never looser. The name is
    claimed with O_EXCL first, so nothing already there, a link included, is written through."""
    backup = f"{path}.bak-{stamp}"
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                 0o600)
    os.close(fd)
    try:
        shutil.copy2(path, backup)
        if stat.S_IMODE(os.lstat(backup).st_mode) & ~mode:
            raise OSError(0, "its backup came out more permissive than the file")
    except BaseException:
        unlink_quietly(backup)
        raise
    return backup


def write_temp(path, data, mode):
    """mkstemp beside `path`, set to `mode` before a byte is written, then the bytes, fsynced."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=TMP_PREFIX)
    try:
        with os.fdopen(fd, "wb") as fh:
            os.fchmod(fh.fileno(), mode)
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        unlink_quietly(tmp)
        raise
    return tmp


def abandon(*paths):
    for p in paths:
        unlink_quietly(p)
    return "changed", None


def other_names(st):
    """A hard-linked config has another name; os.replace would give this one a new file and
    leave the other holding the old, silently cut off."""
    return st.st_nlink > 1


def replace_file(path, data, before, stamp, verify, lock):
    """Steps 4-10 of the plan's edit_json, for any config: (status, detail). The status is
    "ok", "restored" or "unrestored" (detail: the backup), "changed", or "refused" (detail: why).

    `before` is the lstat taken before the file was read. No backup exists until the file is
    known unchanged since then (step 5), and one made is removed again if the file moves before
    the replace (step 7), or the lock is no longer safely held (`lock.check`): an abandoned
    write leaves no backup and prunes nothing. Only a replace that reads back as intended
    prunes (A13)."""
    mode = stat.S_IMODE(before.st_mode) & 0o777
    tmp = write_temp(path, data, mode)                     # 4
    backup = None
    try:
        hook("written", path)
        if moved(path, before):                            # 5
            return abandon(tmp)
        backup = make_backup(path, stamp, mode)            # 6
        hook("backed-up", path)
        if moved(path, before):                            # 7
            return abandon(tmp, backup)
        why = lock.check()
        if why:
            unlink_quietly(tmp)
            unlink_quietly(backup)
            return "refused", why
        os.replace(tmp, path)                              # 8
        tmp = None
    except BaseException:
        if tmp is not None:
            unlink_quietly(tmp)
            if backup is not None:
                unlink_quietly(backup)
        raise
    hook("replaced", path)
    if not verify():                                       # 9
        return restore(path, backup, mode), backup
    prune_backups(path)                                    # 10
    return "ok", backup


def restore(path, backup, mode):
    """Put the backup's bytes back, atomically and at the file's mode. The backup is kept."""
    tmp = None
    try:
        with open(backup, "rb") as fh:
            saved = fh.read()
        tmp = write_temp(path, saved, mode)
        os.replace(tmp, path)
    except OSError:
        if tmp is not None:
            unlink_quietly(tmp)
        return "unrestored"
    return "restored"


def outcome(status, change, detail):
    if status == "ok":
        return done(change)
    if status == "restored":
        return refused(change, R_RESTORED)
    if status == "unrestored":
        return refused(change, R_UNRESTORED.format(backup=tilde(detail)))
    if status == "refused":
        return refused(change, detail)
    return refused(change, R_CHANGED)


def sweep_temps(directory, since):
    """Remove this tool's own temp files in `directory` that are older than this run: a run
    killed between its mkstemp and its replace leaves one, holding the config's secrets. Only
    regular files, owned by this user, named exactly as mkstemp names them here (TMP_NAME), and
    last changed before `since`. Never anything else. Returns how many were removed."""
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    uid = os.getuid() if hasattr(os, "getuid") else None
    removed = 0
    for name in names:
        if not TMP_NAME.match(name):
            continue
        p = os.path.join(directory, name)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if (stat.S_ISREG(st.st_mode) and (uid is None or st.st_uid == uid)
                and st.st_mtime < since):
            try:
                os.unlink(p)
                removed += 1
            except OSError:
                pass
    return removed


def same(a, b, ordered=True):
    """Equal and of the same JSON types, objects with their keys in the same order when
    `ordered`: 1 == 1.0 == True in Python, and not in a client's JSON."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if (list(a) != list(b)) if ordered else (set(a) != set(b)):
            return False
        return all(same(a[k], b[k], ordered) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y, ordered) for x, y in zip(a, b))
    return a == b


# ── JSON configs: Claude Code, Claude Desktop, Gemini ────────────────────────────────────────

LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def json_indent(text):
    """The indent of the file's first indented line (default 2), tabs kept as tabs."""
    m = re.search(r"^([ \t]+)\S", text, re.M)
    if not m:
        return 2
    return m.group(1) if "\t" in m.group(1) else len(m.group(1))


def dump_json(data, like):
    """`data`, laid out as `like` was as far as json.dumps can: its indent, its trailing newline
    or none, its line endings, key order, non-ASCII raw. A lone surrogate is written as the
    escape JSON.stringify writes; NaN and the infinities, which no JSON client reads, raise."""
    text = json.dumps(data, indent=json_indent(like), ensure_ascii=False, allow_nan=False)
    text = LONE_SURROGATE.sub(lambda m: "\\u%04x" % ord(m.group()), text)
    if like.endswith("\n"):
        text += "\n"
    if "\r\n" in like:
        text = text.replace("\n", "\r\n")
    return text.encode("utf-8")


def entry_holder(data, reg):
    """The object that holds `reg`'s entry in a parsed config, or ShapeError."""
    try:
        if reg.client == CLAUDE_CODE and reg.scope == "local":
            holder = data["projects"][reg.project]["mcpServers"]
        else:
            holder = data["mcpServers"]
    except (KeyError, TypeError, IndexError):
        raise ShapeError(reg.name)
    if not isinstance(holder, dict) or not isinstance(holder.get(reg.name), dict):
        raise ShapeError(reg.name)
    return holder


def repointed(entry, command, args):
    """The entry with `command`, and `args` when given, replaced; every other key, `env`
    included, the same object in the same place."""
    new = {}
    for key, value in entry.items():
        if key == "command":
            new[key] = command
        elif key == "args" and args is not None:
            new[key] = args
        else:
            new[key] = value
    return new


def only_command_changed(old, new, change):
    if list(old) != list(new):
        return False
    return all(same(old[k], new[k]) for k in old
               if k != "command" and not (k == "args" and change.interp))


def edit_json(client, path, changes, ctx, stamp):
    """Re-point every approved change in one JSON config: one read, one backup and one write
    per file, however many of its entries change."""
    hook("edit", path)
    if linked_config(path):  # A10, again: it may have become a link since the audit
        why = R_LINK.format(path=tilde(os.path.realpath(path)))
        return [(c, refused(c, why)) for c in changes]
    try:
        with (ClaudeLock(path) if client == CLAUDE_CODE else NoLock()) as lock:
            return edit_json_held(client, path, changes, stamp, lock)
    except Locked as e:
        todo = (TODO_RESTART, T_LOCKED + T_LOCKED_STALE.format(lock=tilde(e.lock)))
        return [(c, refused(c, R_LOCKED.format(secs=CLAUDE_LOCK_WAIT), *todo)) for c in changes]


def edit_json_held(client, path, changes, stamp, lock):
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        return [(c, refused(c, R_CHANGED)) for c in changes]
    if other_names(before):
        return [(c, refused(c, R_HARD_LINK)) for c in changes]
    with open(path, "rb") as fh:
        raw = fh.read()
    hook("read", path)
    try:
        text = raw.decode("utf-8")
        data, why = (None, "bom") if text.startswith(chr(0xFEFF)) else parse_json(text, "it")
    except UnicodeDecodeError:
        data, why = None, "not UTF-8"
    if why:
        return [(c, refused(c, R_CHANGED)) for c in changes]
    new_data = copy.deepcopy(data)
    results, kept = [], []
    for c in changes:
        try:
            holder = entry_holder(data, c.reg)
            reg = json_entry(client, c.reg.scope, c.reg.project, c.reg.name, holder[c.reg.name],
                             path)
        except ShapeError:
            results.append((c, refused(c, R_CHANGED)))
            continue
        if reg.transport != "stdio" or reg.fingerprint() != c.fingerprint:
            results.append((c, refused(c, R_CHANGED)))
            continue
        old = holder[c.reg.name]
        new = repointed(old, c.command, [] if c.interp else None)
        if not only_command_changed(old, new, c):
            results.append((c, refused(c, R_NOT_CONFINED)))
            continue
        entry_holder(new_data, c.reg)[c.reg.name] = new
        kept.append((c, new))
    if not kept:
        return results
    # In memory, before the write: put the old entries back, and it is the document read.
    check = copy.deepcopy(new_data)
    for c, _ in kept:
        entry_holder(check, c.reg)[c.reg.name] = entry_holder(data, c.reg)[c.reg.name]
    try:
        if not same(check, data):
            raise ValueError()
        out = dump_json(new_data, text)
    except ValueError:
        return results + [(c, refused(c, R_UNWRITABLE_VALUE)) for c, _ in kept]

    def verify():
        try:
            with open(path, "rb") as fh:
                got, bad = parse_json(fh.read().decode("utf-8"), "it")
            return not bad and all(same(entry_holder(got, c.reg)[c.reg.name], new)
                                   for c, new in kept)
        except (OSError, ValueError, ShapeError, RecursionError):
            return False

    status, detail = replace_file(path, out, before, stamp, verify, lock)
    return results + [(c, outcome(status, c, detail)) for c, _ in kept]


# ── Codex: a line-local edit of config.toml, read back through `codex mcp get --json` ─────────

TOML_STR = r""""(?:[^"\\]|\\.)*"|'[^']*'"""
TOML_COMMAND = re.compile(r"^(\s*command\s*=\s*)(" + TOML_STR + r")(\s*(?:#.*)?)$")
TOML_ARGS = re.compile(r"^(\s*args\s*=\s*)\[\s*(" + TOML_STR + r")\s*,\s*(" + TOML_STR
                       + r")\s*,?\s*\](\s*(?:#.*)?)$")
TOML_KEY = "^\\s*(?:{k}|\"{k}\"|'{k}')\\s*="
TOML_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", "e": "\x1b", '"': '"',
                "\\": "\\"}


def toml_string(token):
    """The value of a one-line TOML string token, or None when it is not one this reads."""
    if token.startswith("'"):
        return token[1:-1]
    body, out, i = token[1:-1], [], 0
    while i < len(body):
        if body[i] != "\\":
            out.append(body[i])
            i += 1
            continue
        code = body[i + 1:i + 2]
        if code in TOML_ESCAPES:
            out.append(TOML_ESCAPES[code])
            i += 2
        elif code in ("u", "U"):
            width = 4 if code == "u" else 8
            digits = body[i + 2:i + 2 + width]
            if not re.match("^[0-9A-Fa-f]{%d}$" % width, digits) or int(digits, 16) > 0x10FFFF:
                return None
            out.append(chr(int(digits, 16)))
            i += 2 + width
        else:
            return None
    return "".join(out)


def toml_basic(value):
    """`value` as a TOML basic string."""
    out = []
    for ch in value:
        if ch in ('"', "\\"):
            out.append("\\" + ch)
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\u%04X" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def codex_line_edits(lines, change):
    """{line index: new line} for the change, or None when the table is not laid out as this
    can edit safely: `[mcp_servers.<name>]` (or `."<name>"`) exactly once; inside it, until the
    next header, exactly one `command = "<old>"` line, and for the interpreter form exactly one
    one-line `args = ["-m", "<module>"]`; and no multi-line string delimiter anywhere up to the
    end of the table. Lines are matched one at a time, and a multi-line string can hold a line
    that looks like the header or the command: one ABOVE the header could be the "header" this
    found while the real table is spelled `[mcp_servers.'<name>']` (review of d39f719)."""
    name = re.escape(change.reg.name)
    header = re.compile(r'^\s*\[\s*mcp_servers\s*\.\s*(?:%s|"%s")\s*\]\s*(?:#.*)?$' % (name, name))
    body = [ln[:-1] if ln.endswith("\r") else ln for ln in lines]
    heads = [i for i, ln in enumerate(body) if header.match(ln)]
    if len(heads) != 1:
        return None
    if any('"""' in ln or "'''" in ln for ln in body[:heads[0]]):
        return None
    start = heads[0] + 1
    end = next((i for i in range(start, len(body)) if body[i].lstrip().startswith("[")),
               len(body))
    region = range(start, end)
    if any('"""' in body[i] or "'''" in body[i] for i in region):
        return None
    edits = {}
    found = [i for i in region if re.match(TOML_KEY.format(k="command"), body[i])]
    m = TOML_COMMAND.match(body[found[0]]) if len(found) == 1 else None
    if not m or toml_string(m.group(2)) != change.reg.command:
        return None
    edits[found[0]] = m.group(1) + toml_basic(change.command) + m.group(3)
    if change.interp:
        found = [i for i in region if re.match(TOML_KEY.format(k="args"), body[i])]
        m = TOML_ARGS.match(body[found[0]]) if len(found) == 1 else None
        if not m or [toml_string(m.group(2)), toml_string(m.group(3))] != ["-m", change.module]:
            return None
        edits[found[0]] = m.group(1) + "[]" + m.group(4)
    return {i: new + lines[i][len(body[i]):] for i, new in edits.items()}


def codex_get(name, ctx):
    """`codex mcp get <name> --json`, from a fresh empty directory (A11): the entry, or None."""
    exe = which("codex", ctx.path)
    if not exe:
        return None
    try:
        rc, out, _ = run_bounded([exe, "mcp", "get", name, "--json"], CLIENT_TIMEOUT,
                                 ctx.environ, capture=True)
        data, why = parse_json(out.decode("utf-8"), "its output")
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        return None
    if rc != 0 or why:
        return None
    if isinstance(data, list) and len(data) == 1:
        data = data[0]
    if isinstance(data, dict) and list(data) == [name] and isinstance(data[name], dict):
        data = data[name]
    return data if isinstance(data, dict) else None


def codex_expected(got, change):
    """What `codex mcp get` must show after the edit: what it showed before, with the command
    (and, for the interpreter form, the args) replaced, and nothing else."""
    want = copy.deepcopy(got)
    fields = want["transport"] if isinstance(want.get("transport"), dict) else want
    fields["command"] = change.command
    if change.interp:
        fields["args"] = []
    return want


def edit_codex(path, changes, ctx, stamp):
    hook("edit", path)
    if linked_config(path):  # A10
        why = R_LINK.format(path=tilde(os.path.realpath(path)))
        return [(c, refused(c, why)) for c in changes]
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        return [(c, refused(c, R_CHANGED)) for c in changes]
    if other_names(before):
        return [(c, refused(c, R_HARD_LINK)) for c in changes]
    with open(path, "rb") as fh:
        raw = fh.read()
    hook("read", path)
    try:
        lines = raw.decode("utf-8").split("\n")
    except UnicodeDecodeError:
        return [(c, refused(c, R_CODEX_LAYOUT)) for c in changes]
    results, kept = [], []
    for c in changes:
        got = codex_get(c.reg.name, ctx)
        try:
            reg = codex_entry(c.reg.name, got, path) if got is not None else None
        except ShapeError:
            reg = None
        if reg is None:
            results.append((c, refused(c, R_CODEX_UNREAD)))
            continue
        if reg.fingerprint() != c.fingerprint:
            results.append((c, refused(c, R_CHANGED)))
            continue
        edits = codex_line_edits(lines, c)
        if edits is None:
            results.append((c, refused(c, R_CODEX_LAYOUT)))
            continue
        for i, line in edits.items():
            lines[i] = line
        kept.append((c, codex_expected(got, c)))
    if not kept:
        return results

    def verify():
        # Unordered: Codex may list a server's env in any order from one call to the next.
        return all(same(codex_get(c.reg.name, ctx), want, ordered=False) for c, want in kept)

    status, detail = replace_file(path, "\n".join(lines).encode("utf-8"), before, stamp, verify,
                                  NoLock())
    return results + [(c, outcome(status, c, detail)) for c, _ in kept]


# ── apply ────────────────────────────────────────────────────────────────────────────────────

STOP_SIGNALS = ("SIGTERM", "SIGHUP")


@contextlib.contextmanager
def exits_on_signals():
    """While apply runs, SIGTERM and SIGHUP raise SystemExit instead of ending the process
    where it stands, so every clean-up on the way out runs: the temp file holding a config's
    secrets is removed, an unused backup with it, and Claude Code's lock is released (review of
    d39f719: both were left). A signal between two statements can still leave a temp file
    behind, which the next apply sweeps (sweep_temps)."""
    def stop(signum, frame):
        raise SystemExit(128 + signum)

    saved = {}
    for name in STOP_SIGNALS:
        sig = getattr(signal, name, None)
        # One the caller ignores (`nohup` ignores SIGHUP) stays ignored.
        if sig is None or signal.getsignal(sig) == signal.SIG_IGN:
            continue
        try:
            saved[sig] = signal.signal(sig, stop)
        except (ValueError, OSError):  # not the main thread, or not this platform's
            pass
    try:
        yield
    finally:
        for sig, old in saved.items():
            signal.signal(sig, old if old is not None else signal.SIG_DFL)


def apply(args):
    """Re-audit; re-point each finding the agreed plan showed as a re-point, unchanged since
    (A4), whose standard binary is there; report everything else, and leave the to-dos."""
    started = time.time()
    ctx = Context(os.environ, args.system_applications)
    clients, findings = audit(ctx)
    for line in ctx.logs:
        emit("log", line)
    swept = []
    for client in CLIENTS:
        config = ctx.configs.get(client)
        directory = os.path.dirname(config) if config else None
        if directory and directory not in swept and not linked_config(config):
            swept.append(directory)
            n = sweep_temps(directory, started)
            if n:
                emit("info", f"removed {n} temporary {'copy' if n == 1 else 'copies'} of a "
                             f"config, left in {tilde(directory)} by a run stopped mid-write")
    if args.approved is None:
        # By hand: re-plan, show it, and act on it, as csa-claude-connectors.py --apply does.
        for row in render(clients, findings):
            emit("row", row)
        repoint = {key_of(f) for f in findings if f.action == "re-point"}
        every = {key_of(f) for f in findings}
        plan_why = None
    else:
        repoint, every, plan_why = load_approved(args.approved)
        if plan_why:
            emit("warn", f"the plan you agreed to ({tilde(args.approved)}) could not be read: "
                         f"{plan_why}; nothing is changed this run")
            repoint, every = set(), set()
    for client, status in clients:
        if status != "ok" and any(k[0] == client for k in repoint):
            emit("warn", f"{client}: {status}; nothing was changed there — run again")

    todos = Todos()
    groups = collections.OrderedDict()
    for f in findings:
        key = key_of(f)
        if f.action != "re-point":
            if f.todo:
                todos.add(TODO_RESTART if f.todo == T_QUIT_DESKTOP else TODO_LEFT, f.todo)
                if key in repoint and f.row:  # agreed to as a re-point, and now left
                    emit("warn", f.row)
            continue
        change = Change(f, ctx)
        if plan_why:
            result = refused(change, R_NO_PLAN)
        elif key not in repoint:
            result = refused(change, R_NOT_PLANNED if key in every else R_UNAPPROVED)
        elif standard_dead(change.command, SERVERS[f.reg.name], ctx):
            # Never launched: only its Python is probed, as the audit does.
            result = refused(change, R_NO_STANDARD + "; left as it is",
                             todo=T_NO_STANDARD.format(label=f.reg.label()))
        else:
            groups.setdefault((f.reg.client, f.reg.config), []).append(change)
            continue
        emit("warn", result[1])
        todos.add(*result[2])

    stamp = backup_stamp()
    restart = []
    for (client, path), changes in groups.items():
        # D4, asked again just before the write: Desktop may have started since the audit,
        # while this run waited on a lock, a client or a probe.
        running = (desktop_running(ctx, fresh=True)
                   if client == DESKTOP and not WRITE_DESKTOP_WHILE_RUNNING else False)
        if running is not False:
            row = ROW_DESKTOP_RUNNING if running else ROW_DESKTOP_UNKNOWN
            for c in changes:
                emit("warn", row.format(name=c.reg.name))
            todos.add(TODO_RESTART, T_QUIT_DESKTOP)
            continue
        try:
            if client == CODEX:
                results = edit_codex(path, changes, ctx, stamp)
            else:
                results = edit_json(client, path, changes, ctx, stamp)
        except Exception as e:  # this file only: the others are still repaired
            why = e.strerror if isinstance(e, OSError) and e.strerror else describe_error(e)
            results = [(c, refused(c, R_UNWRITTEN.format(why=why))) for c in changes]
        for c, (ok, text, todo) in results:
            emit("ok" if ok else "warn", text)
            if todo:
                todos.add(*todo)
            if ok and client not in restart:
                restart.append(client)
    for client in restart:
        todos.add(TODO_RESTART, T_RESTART.format(client=client))
    todos.flush(ctx.environ)
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
    a = sub.add_parser("apply", help="re-point each dead registration the agreed plan showed, "
                                     "changing only its command")
    a.add_argument("--approved", metavar="FILE",
                   help="the plan file agreed to (plan --out); without it, re-plan and apply")
    a.add_argument("--system-applications", default="/Applications", help=argparse.SUPPRESS)
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        # argparse has said why. Nothing was created, and whatever is at --out is not touched:
        # this run made it no more than any other file (review of e62c775).
        return 0 if e.code in (0, None) else 2
    if args.command == "apply":
        try:
            with exits_on_signals():
                return apply(args)
        except SystemExit:
            say("stopped by a signal, with what was reported done")
            raise
        except OutputLost:
            say("the results could not be printed; stopped, with what was reported done")
            return 2
        except Exception as e:
            say(f"internal error ({describe_error(e)}); stopped, with what was reported done")
            return 2
    if args.command != "plan":
        ap.print_usage(sys.stderr)
        return 2
    created = []
    try:
        return plan(args, created)
    except BaseException as e:
        # "Nothing was written" holds for --out too: the plan file THIS run created is removed,
        # so it cannot pass for a plan (A4). A file that was there before is never touched.
        discard(args.out, created[-1] if created else None)
        if not isinstance(e, Exception):
            raise
        say(f"internal error ({describe_error(e)}); nothing was written")
        return 2


if __name__ == "__main__":
    sys.exit(main())
