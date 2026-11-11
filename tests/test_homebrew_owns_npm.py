#!/usr/bin/env python3
"""npm updates only what npm installed; npm itself belongs to Homebrew's node@24 (#153).

Since #74 force-links the keg-only node@24, every file under
`/opt/homebrew/lib/node_modules/npm/` is a symlink into the read-only Cellar. That broke npm in
two ways, from one cause:

* **The installers' `npm update -g <pkg>`** failed with EACCES (exit -13, ~22 lines of red per
  tool) on every re-run, because npm's reify-finish rewrites `node_modules/npm/npmrc` through
  the symlink into the keg. The `|| npm install -g <pkg>` fallback did the actual work.
* **The updater's bare `npm update -g`** included npm itself, so it installed a registry npm
  over Homebrew's link farm - a copy `bin/npm` never runs. Nobody got a newer npm, and the
  installers stopped failing until the next `brew link` restored the symlinks.

The fix, whoever owns npm updates it: installers run `npm install -g <pkg>@latest`; the
updater lists outdated globals, leaves npm and corepack to `brew upgrade` when they are
Homebrew's own copy, and installs everything else `@latest` - npm and corepack included when
they are nvm's or in another prefix you can write to, as `npm update -g` did. The plan row is
built from the same decision, so it names what the step will run.

Two more things this pins, both found while writing it and both measured on npm 11.20:

* `npm outdated` exits 1 both when something is outdated and when it FAILED (an unreachable
  registry exits 1 with nothing on stdout). The issue's draft did `|| true` and so reported an
  offline machine as "already current". A failure here must say so.
* `npm outdated -g` lists a package `npm link` put there, and `npm install -g <pkg>@latest`
  replaces that link with the registry copy, where `npm update -g` left it alone. A link is
  someone's working copy, so it is skipped, and the plan says so.

And from review, four layouts for npm itself, each with its own outcome and plan wording:
Homebrew's link farm into its Cellar (left to `brew upgrade`); an nvm Node (updated, `install -g
npm@latest`); the registry copy an earlier `npm update -g` left in Homebrew's prefix (left
alone: Homebrew's bin/npm does not run it); and a prefix you cannot write to (left to its owner).

Every function under test is extracted from the shipping scripts, never copied, and `npm` is a
stub on a stub-first PATH (stub-only for the "no npm" case). Each assertion is also run against
the pre-#153 code, embedded below as controls, and must FAIL there (ADR-005), so this cannot
pass vacuously. `--rev <ref>` reads the scripts from a git revision instead: at 7b6d743, the
last main before the fix, it must report the defect.

    python3 tests/test_homebrew_owns_npm.py
    python3 tests/test_homebrew_owns_npm.py --rev 7b6d743      # expected: FAILED
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def _posix_bash() -> str:
    r"""Absolute path to a POSIX bash. Resolved once, absolutely, for two reasons.

    These tests replace PATH with a stub directory, so a bare "bash" could not be found there.
    And on Windows a bare "bash" is resolved by CreateProcess against the PARENT process's
    PATH, which finds C:\Windows\System32\bash.exe -- the WSL launcher, not a shell.
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

# Windows needs these to locate its own per-user directories (see test_survives_tool_failure.py).
_KEEP_NT = ("SystemRoot", "SystemDrive", "ComSpec", "PATHEXT",
            "LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP")


def base_env() -> dict[str, str]:
    if os.name != "nt":
        return {}
    return {k: os.environ[k] for k in _KEEP_NT if k in os.environ}


ROOT = pathlib.Path(__file__).resolve().parent.parent
REV: str | None = None


def read(name: str) -> str:
    if REV is None:
        return (ROOT / "scripts" / name).read_text(encoding="utf-8")
    r = subprocess.run(["git", "show", f"{REV}:scripts/{name}"], cwd=ROOT, capture_output=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"cannot read scripts/{name} at {REV}: {r.stderr.strip()}")
    return r.stdout


def extract(text: str, name: str) -> str:
    """A shell function exactly as the script defines it, or a stand-in that says it is missing.

    Missing is not an error here, because `--rev` at a commit before the fix has no
    npm_global_outdated: the stand-in fails loudly at run time and the checks report it.
    """
    m = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    if not m:
        return f'{name}() {{ echo "MISSING FUNCTION: {name}"; return 97; }}'
    return m.group(0)


# The stub npm. Records every call, one line each, and refuses an `outdated` that is not the
# parseable form update_npm reads - so drifting to the human table fails here, not in the field.
NPM_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$NPM_LOG"
case "$1" in
  outdated)
    case "$*" in *-g*--parseable*|*--parseable*-g*) ;; *) echo "stub: unexpected outdated form: $*" >&2; exit 99 ;; esac
    if [ -n "${NPM_OUTDATED_FILE:-}" ]; then /bin/cat "$NPM_OUTDATED_FILE"; fi
    exit "${NPM_OUTDATED_EXIT:-0}" ;;
  install) exit "${NPM_INSTALL_EXIT:-0}" ;;
esac
exit 0
"""

# `npm outdated -g --parseable` as npm 11 prints it (measured; fields are
# path:name@wanted:name@current:name@latest:dependent). npm and corepack outdated alongside two
# real globals, one of them scoped - the shape of the reporting machine in #153. The paths are
# deliberately ones that cannot exist, so who owns npm here never depends on the machine running
# the test (whose /opt/homebrew may well hold an npm): a prefix that is not there is not
# writable, so npm and corepack are "other" and never installed.
MIXED = """\
/nonexistent-csa-test/lib/node_modules/npm:npm@12.2.0:npm@11.19.0:npm@12.2.0:global
/nonexistent-csa-test/lib/node_modules/corepack:corepack@0.35.0:corepack@0.34.0:corepack@0.35.0:global
/nonexistent-csa-test/lib/node_modules/wrangler:wrangler@4.149.0:wrangler@4.62.0:wrangler@4.149.0:global
/nonexistent-csa-test/lib/node_modules/@openai/codex:@openai/codex@0.60.0:@openai/codex@0.50.0:@openai/codex@0.60.0:global
"""
ONLY_HOMEBREW = "".join(l + "\n" for l in MIXED.splitlines()[:2])
# The fixtures below name real paths in the test's temporary directory ({TMP}), laid out by the
# function passed as `layout`, because what update_npm does with npm, and what the plan may say
# about it, depend on what is there.
#
# A package `npm link` put there: npm outdated lists it, and `npm install -g is-odd@latest`
# would replace the link with the registry copy (measured on npm 11.20; `npm update -g` left it).
LINKED = "{TMP}/node_modules/is-odd:is-odd@3.0.1:is-odd@0.0.1:is-odd@3.0.1:global\n"
# npm and corepack in four layouts: Homebrew's link farm (left to brew upgrade), an nvm Node
# (updated), the registry npm an earlier `npm update -g` left in Homebrew's prefix (#153's
# symptom 2; left alone), and a prefix you cannot write to (left to its owner).
BREW_HELD = """\
{TMP}/homebrew/lib/node_modules/npm:npm@12.2.0:npm@11.19.0:npm@12.2.0:global
{TMP}/homebrew/lib/node_modules/corepack:corepack@0.35.0:corepack@0.34.0:corepack@0.35.0:global
"""
NVM_HELD = """\
{TMP}/.nvm/versions/node/v26.13.0/lib/node_modules/npm:npm@12.2.0:npm@11.20.0:npm@12.2.0:global
{TMP}/.nvm/versions/node/v26.13.0/lib/node_modules/corepack:corepack@0.35.0:corepack@0.34.0:corepack@0.35.0:global
"""
LEFTOVER_HELD = "{TMP}/homebrew/lib/node_modules/npm:npm@12.3.0:npm@12.2.0:npm@12.3.0:global\n"
READONLY_HELD = "{TMP}/sys/lib/node_modules/npm:npm@12.2.0:npm@10.9.0:npm@12.2.0:global\n"
CELLAR_NPM = "../Cellar/node@24/24.21.0_2/bin/npm"


def linked_layout(tmp: pathlib.Path) -> None:
    (tmp / "src").mkdir()
    (tmp / "node_modules").mkdir()
    os.symlink(tmp / "src", tmp / "node_modules" / "is-odd", target_is_directory=True)


def homebrew_layout(tmp: pathlib.Path) -> None:
    """Homebrew's link farm as #153 measured it: real directories, each file a relative link
    into the keg."""
    for pkg in ("npm", "corepack"):
        keg = tmp / "homebrew" / "Cellar" / "node@24" / "24.21.0_2" / "lib" / "node_modules" / pkg
        keg.mkdir(parents=True)
        (keg / "package.json").write_text("{}\n", encoding="utf-8")
        farm = tmp / "homebrew" / "lib" / "node_modules" / pkg
        farm.mkdir(parents=True)
        os.symlink(f"../../../Cellar/node@24/24.21.0_2/lib/node_modules/{pkg}/package.json",
                   farm / "package.json")


def nvm_layout(tmp: pathlib.Path) -> None:
    for pkg in ("npm", "corepack"):
        d = tmp / ".nvm" / "versions" / "node" / "v26.13.0" / "lib" / "node_modules" / pkg
        d.mkdir(parents=True)
        (d / "package.json").write_text("{}\n", encoding="utf-8")


def leftover_layout(tmp: pathlib.Path, *, bin_link: bool = True) -> None:
    """A registry npm (real files) in a Homebrew prefix, where Homebrew's links were. With
    bin_link, the prefix's bin/npm still points into the Cellar, as #153 measured."""
    (tmp / "homebrew" / "Cellar" / "node@24" / "24.21.0_2" / "bin").mkdir(parents=True)
    d = tmp / "homebrew" / "lib" / "node_modules" / "npm"
    d.mkdir(parents=True)
    (d / "package.json").write_text("{}\n", encoding="utf-8")
    if bin_link:
        (tmp / "homebrew" / "bin").mkdir()
        os.symlink(CELLAR_NPM, tmp / "homebrew" / "bin" / "npm")


def leftover_without_bin_link(tmp: pathlib.Path) -> None:
    leftover_layout(tmp, bin_link=False)


def readonly_layout(tmp: pathlib.Path) -> None:
    """npm in a prefix you cannot write to, like a root-owned Node."""
    d = tmp / "sys" / "lib" / "node_modules" / "npm"
    d.mkdir(parents=True)
    (d / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp / "sys" / "lib" / "node_modules").chmod(0o555)

HELPERS = 'info() { echo "INFO: $*"; }\nwarn() { echo "WARN: $*"; }\nsuccess() { echo "OK: $*"; }\n'


def run(funcs: list[str], body: str, *, outdated: str = "", outdated_exit: int = 0,
        install_exit: int = 0, with_npm: bool = True, tools: tuple[str, ...] = (),
        layout=None) -> dict:
    """Run `body` after the given function definitions. Returns output, status and npm calls."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        stub = tmp / "bin"
        stub.mkdir()
        if with_npm:
            (stub / "npm").write_text(NPM_STUB, encoding="utf-8")
        for tool in tools:      # a CLI that is "already installed", e.g. codex
            (stub / tool).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        for f in stub.iterdir():
            f.chmod(0o755)
        if layout is not None:
            layout(tmp)
        outdated = outdated.replace("{TMP}", str(tmp))
        (tmp / "outdated.txt").write_text(outdated, encoding="utf-8")
        log = tmp / "npm.log"
        log.write_text("", encoding="utf-8")
        script = ("#!/usr/bin/env bash\nset -euo pipefail\n" + HELPERS + "\n".join(funcs)
                  + "\n" + body + '\necho "SURVIVED"\n')
        h = tmp / "harness.sh"
        h.write_text(script, encoding="utf-8")
        # Stub-first, with /usr/bin:/bin for sed and tr (csa_npm, csa_debug_requested). With no
        # npm the PATH is the stub directory ALONE, so a real npm on the runner cannot answer.
        path = f"{stub}:/usr/bin:/bin" if with_npm else str(stub)
        env = {**base_env(), "PATH": path, "HOME": str(tmp), "NPM_LOG": str(log),
               "NPM_OUTDATED_FILE": str(tmp / "outdated.txt"),
               "NPM_OUTDATED_EXIT": str(outdated_exit), "NPM_INSTALL_EXIT": str(install_exit)}
        p = subprocess.run([BASH, str(h)], capture_output=True, text=True, env=env)
        calls = [c for c in log.read_text(encoding="utf-8").splitlines() if c]
        for d, _, _ in os.walk(tmp):       # readonly_layout: let the cleanup delete it
            os.chmod(d, 0o755)
        return {"out": p.stdout + p.stderr, "rc": p.returncode, "calls": calls}


def installs(r: dict) -> list[list[str]]:
    """The argument list of every `npm install` call."""
    return [c.split()[1:] for c in r["calls"] if c.split()[:1] == ["install"]]


def never_updates(r: dict) -> bool:
    return not any(c.split()[:1] == ["update"] for c in r["calls"])


def never_installs_homebrews(r: dict) -> bool:
    return not any(re.fullmatch(r"(npm|corepack)(@.*)?", a) for args in installs(r) for a in args)


# ── The update side (macos-update.sh) ────────────────────────────────────────────────────

def update_funcs(text: str, update_npm: str | None = None, owner_note: str | None = None,
                 decision: str | None = None) -> list[str]:
    names = ["has_command", "csa_debug_requested", "csa_npm", "npm_node_owned", "npm_owner",
             "npm_global_outdated", "npm_update_plan"]
    return ([extract(text, n) for n in names]
            + [decision or extract(text, "npm_update_decision")]
            + [owner_note or extract(text, "npm_owner_note")]
            + [update_npm or extract(text, "update_npm")])


# The plan's note as #190 first wrote it: every npm and corepack "Homebrew's", whatever was there.
# Untrue for the leftover copy in Homebrew's prefix, and for a prefix you cannot write to.
ALWAYS_HOMEBREW_NOTE = ('npm_owner_note() { echo "Homebrew\'s own copy; the Homebrew step '
                        'upgrades it"; }')

# The decision as #190 first made it: npm and corepack never updated, whoever owned them. An nvm
# user's npm then stopped updating at all - the regression the review ruled out.
NEVER_UPDATE_NPM = (
    'npm_update_decision() {\n'
    '  if npm_node_owned "$1"; then echo homebrew\n'
    '  elif [[ "$2" == linked ]]; then echo linked\n'
    '  else echo update; fi\n'
    '}')


def update_findings(funcs: list[str]) -> list[str]:
    """Every way update_npm (and its plan row) can be wrong. Empty means correct."""
    bad: list[str] = []

    r = run(funcs, "update_npm", outdated=MIXED, outdated_exit=1)
    if not (r["rc"] == 0 and "SURVIVED" in r["out"]):
        bad.append(f"mixed: update_npm did not complete (rc={r['rc']}): {r['out'][-300:]!r}")
    if not never_updates(r):
        bad.append(f"mixed: ran `npm update`: {r['calls']}")
    if not never_installs_homebrews(r):
        bad.append(f"mixed: installed npm or corepack itself: {installs(r)}")
    if installs(r) != [["-g", "wrangler@latest", "@openai/codex@latest"]]:
        bad.append("mixed: expected ONE `install -g wrangler@latest @openai/codex@latest` "
                   f"(scoped name kept whole), got {installs(r)}")

    r = run(funcs, "update_npm", outdated=ONLY_HOMEBREW, outdated_exit=1)
    if installs(r) or not never_updates(r):
        bad.append(f"only npm/corepack outdated: npm was asked to change something: {r['calls']}")
    if "already current" not in r["out"]:
        bad.append(f"only npm/corepack outdated: did not say 'already current': {r['out'][-200:]!r}")

    r = run(funcs, "update_npm", outdated="", outdated_exit=0)
    if installs(r) or not never_updates(r) or "already current" not in r["out"]:
        bad.append(f"nothing outdated: expected no change and 'already current': {r['calls']} "
                   f"{r['out'][-200:]!r}")

    # npm outdated failed: exit 1, nothing on stdout (an unreachable registry, measured).
    r = run(funcs, "update_npm", outdated="", outdated_exit=1)
    if installs(r) or not never_updates(r):
        bad.append(f"outdated failed: npm was asked to change something: {r['calls']}")
    if "already current" in r["out"] or "Could not list" not in r["out"]:
        bad.append("outdated failed: must warn 'Could not list', never claim 'already current': "
                   f"{r['out'][-200:]!r}")
    if not (r["rc"] == 0 and "SURVIVED" in r["out"]):
        bad.append(f"outdated failed: the caller did not survive (rc={r['rc']})")

    r = run(funcs, "update_npm", with_npm=False)
    if not (r["rc"] == 0 and "SURVIVED" in r["out"]) or r["calls"]:
        bad.append(f"no npm on PATH: expected a silent return 0 (rc={r['rc']}): {r['out'][-200:]!r}")

    r = run(funcs, "update_npm", outdated=MIXED, outdated_exit=1, install_exit=1)
    if not (r["rc"] == 0 and "SURVIVED" in r["out"]) or "WARN" not in r["out"]:
        bad.append(f"install failed: expected a warning and the caller to survive (rc={r['rc']})")

    # The plan row, built from the same functions: it must name what update_npm installs, and
    # name npm and corepack as not updated here rather than listing them as updates.
    r = run(funcs, "npm_update_plan", outdated=MIXED, outdated_exit=1)
    plan = r["out"]
    to_update = plan.split("not updated here")[0]
    for name in ("wrangler 4.62.0 -> 4.149.0", "@openai/codex 0.50.0 -> 0.60.0"):
        if name not in to_update:
            bad.append(f"plan: does not name {name!r} as an update: {plan!r}")
    if re.search(r"^\s*(npm|corepack) ", to_update, re.M):
        bad.append(f"plan: lists npm or corepack as something it will update: {plan!r}")
    for held in (r"npm 11\.19\.0 -> 12\.2\.0", r"corepack 0\.34\.0 -> 0\.35\.0"):
        if not re.search(r"^    not updated here: " + held + r" \(", plan, re.M):
            bad.append(f"plan: does not name {held!r} as not updated here: {plan!r}")
    if installs(r) or not never_updates(r):
        bad.append(f"plan: the preview changed something: {r['calls']}")

    r = run(funcs, "npm_update_plan", outdated="", outdated_exit=1)
    if "could not be checked" not in r["out"] or "up to date" in r["out"]:
        bad.append(f"plan, outdated failed: must say it could not check: {r['out']!r}")

    r = run(funcs, "npm_update_plan", outdated=ONLY_HOMEBREW, outdated_exit=1)
    if "all up to date" not in r["out"] or "not updated here: npm" not in r["out"]:
        bad.append(f"plan, only npm/corepack outdated: {r['out']!r}")

    r = run(funcs, "npm_update_plan", with_npm=False)
    if "npm not installed" not in r["out"]:
        bad.append(f"plan, no npm: {r['out']!r}")

    # The cases below need real paths without a colon, and a symlink: not on Windows, where the
    # parseable path is C:\... and a symlink needs a privilege.
    if LINKS_OK:
        # A linked package is someone's working copy: never replaced, and named as left alone.
        r = run(funcs, "update_npm", outdated=MIXED + LINKED, outdated_exit=1, layout=linked_layout)
        if any(a.startswith("is-odd") for args in installs(r) for a in args):
            bad.append(f"linked: replaced an npm-linked package with the registry copy: {installs(r)}")
        if installs(r) != [["-g", "wrangler@latest", "@openai/codex@latest"]]:
            bad.append(f"linked: the other packages were not updated as usual: {installs(r)}")
        r = run(funcs, "npm_update_plan", outdated=LINKED, outdated_exit=1, layout=linked_layout)
        if "all up to date" not in r["out"] or not re.search(r"not updated here: is-odd .*npm link", r["out"]):
            bad.append(f"plan, linked: must name is-odd as left alone, not as an update: {r['out']!r}")

        # Whoever owns npm updates it, and the plan says exactly what happens, per layout.
        # Homebrew's link farm: left to brew upgrade, and called Homebrew's.
        r = run(funcs, "update_npm", outdated=BREW_HELD, outdated_exit=1, layout=homebrew_layout)
        if installs(r) or not never_updates(r):
            bad.append(f"owner (homebrew): npm wrote into Homebrew's copy: {r['calls']}")
        r = run(funcs, "npm_update_plan", outdated=BREW_HELD, outdated_exit=1, layout=homebrew_layout)
        for held in (r"npm 11\.19\.0 -> 12\.2\.0", r"corepack 0\.34\.0 -> 0\.35\.0"):
            if not re.search(r"not updated here: " + held
                             + r" \(Homebrew's own copy; the Homebrew step upgrades it\)", r["out"]):
                bad.append(f"plan, owner (homebrew): {held!r} not named as Homebrew's: {r['out']!r}")

        # nvm's Node: npm's own to update, as `npm update -g` did - installed @latest, and listed
        # in the plan as an update.
        r = run(funcs, "update_npm", outdated=NVM_HELD, outdated_exit=1, layout=nvm_layout)
        if installs(r) != [["-g", "npm@latest", "corepack@latest"]] or not never_updates(r):
            bad.append(f"owner (nvm): expected `install -g npm@latest corepack@latest`, got {r['calls']}")
        r = run(funcs, "npm_update_plan", outdated=NVM_HELD, outdated_exit=1, layout=nvm_layout)
        to_update = r["out"].split("not updated here")[0]
        if ("npm 11.20.0 -> 12.2.0" not in to_update or "corepack 0.34.0 -> 0.35.0" not in to_update
                or "not updated here" in r["out"]):
            bad.append(f"plan, owner (nvm): must list npm and corepack as updates: {r['out']!r}")

        # The registry npm an earlier `npm update -g` left in Homebrew's prefix: left alone, and
        # the plan says why - naming what bin/npm runs only when bin/npm links into the Cellar.
        for label, layout, says in (
                ("leftover", leftover_layout,
                 r"at \S+/homebrew/lib/node_modules/npm, a copy in Homebrew's prefix that \S+/homebrew/bin/npm "
                 r"does not run - it runs Homebrew's Cellar copy \(#153\); left alone"),
                ("leftover, no bin link", leftover_without_bin_link,
                 r"at \S+/homebrew/lib/node_modules/npm, in Homebrew's prefix but not Homebrew's own copy "
                 r"\(#153\); left alone")):
            r = run(funcs, "update_npm", outdated=LEFTOVER_HELD, outdated_exit=1, layout=layout)
            if installs(r) or not never_updates(r):
                bad.append(f"owner ({label}): npm wrote into Homebrew's prefix: {r['calls']}")
            r = run(funcs, "npm_update_plan", outdated=LEFTOVER_HELD, outdated_exit=1, layout=layout)
            if "Homebrew step upgrades" in r["out"] or not re.search(says, r["out"]):
                bad.append(f"plan, owner ({label}): {r['out']!r}")

        # A prefix you cannot write to: left to its owner (as root everything is writable, so
        # this case cannot be built there).
        if not ROOT_USER:
            r = run(funcs, "update_npm", outdated=READONLY_HELD, outdated_exit=1, layout=readonly_layout)
            if installs(r) or not never_updates(r):
                bad.append(f"owner (read-only): npm tried to write where it cannot: {r['calls']}")
            r = run(funcs, "npm_update_plan", outdated=READONLY_HELD, outdated_exit=1, layout=readonly_layout)
            if ("Homebrew step upgrades" in r["out"]
                    or not re.search(r"at \S+/sys/lib/node_modules/npm, which you cannot write to; "
                                     r"left to whoever installed it", r["out"])):
                bad.append(f"plan, owner (read-only): {r['out']!r}")
    return bad


LINKS_OK = os.name != "nt"
ROOT_USER = hasattr(os, "geteuid") and os.geteuid() == 0


# ── The installers (macos-ai-tools.sh, macos-work-tools.sh) ─────────────────────────────────

INSTALLERS = [
    # (script, function, call, the CLI it installs, expected install args)
    ("macos-ai-tools.sh", "install_codex", 'codex_needs_migration=""\ninstall_codex',
     "codex", ["-g", "@openai/codex@latest"]),
    ("macos-ai-tools.sh", "install_gemini", 'gemini_needs_migration=""\ninstall_gemini',
     "gemini", ["-g", "@google/gemini-cli@latest"]),
    ("macos-work-tools.sh", "install_npm_package",
     'install_npm_package "Wrangler" "wrangler" "wrangler"', "wrangler", ["-g", "wrangler@latest"]),
]


def installer_funcs(text: str, func: str, override: str | None = None) -> list[str]:
    return [extract(text, n) for n in ("has_command", "csa_debug_requested", "csa_npm")] + \
        [override or extract(text, func)]


def installer_findings(funcs: list[str], call: str, cli: str, expected: list[str]) -> list[str]:
    bad: list[str] = []
    for present in (True, False):
        state = f"{cli} {'installed' if present else 'absent'}"
        r = run(funcs, call, tools=(cli,) if present else ())
        if not never_updates(r):
            bad.append(f"{state}: ran `npm update`: {r['calls']}")
        if installs(r) != [expected]:
            bad.append(f"{state}: expected exactly one `install {' '.join(expected)}`, "
                       f"got {r['calls']}")
        if not (r["rc"] == 0 and "SURVIVED" in r["out"]):
            bad.append(f"{state}: did not complete (rc={r['rc']}): {r['out'][-200:]!r}")
    return bad


# ── No script runs `npm update` at all ──────────────────────────────────────────────────────

NPM_UPDATE = re.compile(r"\b(csa_)?npm\s+update\b")


def static_findings(texts: dict[str, str]) -> list[str]:
    """A non-comment line in any shipping script that runs `npm update`, or names it - a plan row
    or a warning that says `npm update -g` is wording that is no longer true."""
    bad = []
    for name, text in texts.items():
        for n, line in enumerate(text.splitlines(), 1):
            code = line.strip()
            if code.startswith("#") or not NPM_UPDATE.search(code):
                continue
            bad.append(f"{name}:{n}: runs or names `npm update`: {code}")
    return bad


# ── Controls: the code before #153, which every check above must catch ─────────────────────

OLD_UPDATE_NPM = """update_npm() {
  if ! has_command npm; then return 0; fi

  info "Updating global npm packages"
  csa_npm update -g || warn "npm update -g failed; continuing"
}"""

# The issue's draft, as written: right about npm, but `|| true` turns a failed `npm outdated`
# into "already current" - the case this file adds.
DRAFT_UPDATE_NPM = """update_npm() {
  if ! has_command npm; then return 0; fi
  local outdated pkg
  local pkgs=()
  outdated="$(npm outdated -g --parseable 2>/dev/null)" || true
  while IFS=: read -r _ _ _ pkg _; do
    pkg="${pkg%@*}"
    case "$pkg" in ""|npm|corepack) continue ;; esac
    pkgs+=("${pkg}@latest")
  done <<<"$outdated"
  if [[ ${#pkgs[@]} -eq 0 ]]; then
    info "Global npm packages already current"
    return 0
  fi
  info "Updating global npm packages: ${pkgs[*]}"
  csa_npm install -g "${pkgs[@]}" || warn "npm install -g failed; continuing"
}"""

OLD_INSTALL_CODEX = """install_codex() {
  if ! has_command npm; then
    warn "npm not found; skipping Codex CLI"
    return 1
  fi
  if [[ -z "$codex_needs_migration" ]] && has_command codex; then
    info "Updating Codex CLI"
    csa_npm update -g @openai/codex || csa_npm install -g @openai/codex || warn "Failed to update Codex CLI"
  else
    info "Installing Codex CLI"
    csa_npm install -g @openai/codex || warn "Failed to install Codex CLI"
  fi
}"""


def main() -> int:
    global REV
    args = sys.argv[1:]
    if args[:1] == ["--rev"] and len(args) == 2:
        REV = args[1]
    elif args:
        raise SystemExit("usage: test_homebrew_owns_npm.py [--rev <git-rev>]")

    failures: list[str] = []

    def check(findings: list[str], label: str) -> None:
        print(f"    {'ok  ' if not findings else 'FAIL'}  {label}")
        for f in findings:
            print(f"          {f}")
        if findings:
            failures.append(label)

    def control(findings: list[str], label: str) -> None:
        """A control passes when the check DOES find something in deliberately broken code."""
        print(f"    {'ok  ' if findings else 'FAIL'}  control: {label}")
        if not findings:
            failures.append(f"control: {label} (the check cannot fail - it proves nothing)")

    where = f" at {REV}" if REV else ""
    update_text = read("macos-update.sh")
    print(f"\nmacos-update.sh{where} :: update_npm, npm_update_plan")
    findings = update_findings(update_funcs(update_text))
    check([f for f in findings if not f.startswith("plan")],
          "updates every outdated global @latest - npm and corepack only when npm owns them, "
          "npm-linked packages never - and says so when it cannot")
    check([f for f in findings if f.startswith("plan")],
          "the plan names exactly that, and says per layout what happens to npm/corepack")
    if not LINKS_OK:
        print("    skip  the npm-linked cases: no symlink, and a colon in every path, on Windows")

    for script, func, call, cli, expected in INSTALLERS:
        print(f"\n{script}{where} :: {func}")
        check(installer_findings(installer_funcs(read(script), func), call, cli, expected),
              f"`npm install -g {expected[-1]}` whether or not {cli} is installed, never `update -g`")

    print(f"\nscripts/*{where} (not windows-update.ps1, yet): no shipping script runs `npm update`")
    # Not windows-update.ps1, yet: its Update-Npm still runs a bare `npm update -g` until the
    # rewrite is measured on Windows (#184), where npm.cmd prefers a global copy of npm when one
    # exists. The draft PR that rewrites it adds the file to this list.
    names = ["macos-ai-tools.sh", "macos-update.sh", "macos-work-tools.sh", "macos-plugins.sh",
             "windows-ai-tools.ps1", "windows-work-tools.ps1", "windows-plugins.ps1"]
    check(static_findings({n: read(n) for n in names}), "no `npm update` / `csa_npm update`")

    if REV is None:
        print("\ncontrols (ADR-005): the same checks against the code before #153")
        control(update_findings(update_funcs(update_text, OLD_UPDATE_NPM)),
                "a bare `npm update -g` is caught")
        draft = update_findings(update_funcs(update_text, DRAFT_UPDATE_NPM))
        control([f for f in draft if f.startswith("outdated failed")],
                "the issue's draft, which calls a failed `npm outdated` 'already current', is caught")
        if LINKS_OK:
            control([f for f in draft if f.startswith("linked")],
                     "the issue's draft, which replaces an npm-linked package, is caught")
            always = update_findings(update_funcs(update_text, owner_note=ALWAYS_HOMEBREW_NOTE))
            control([f for f in always if f.startswith("plan, owner (leftover")],
                    "a plan that calls every skipped npm Homebrew's (the leftover copy) is caught")
            never = update_findings(update_funcs(update_text, decision=NEVER_UPDATE_NPM))
            control([f for f in never if f.startswith("owner (nvm)")],
                    "never updating npm, whoever owns it (an nvm user's npm frozen), is caught")
        control(installer_findings(installer_funcs(read("macos-ai-tools.sh"), "install_codex",
                                                   OLD_INSTALL_CODEX),
                                   'codex_needs_migration=""\ninstall_codex', "codex",
                                   ["-g", "@openai/codex@latest"]),
                "`npm update -g X || npm install -g X` is caught")
        control(static_findings({"synthetic.ps1":
                                 "        $null = Invoke-NativeNpm { npm update -g }\n"}),
                "the static scan sees `npm update` inside an Invoke-NativeNpm block")

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
