#!/usr/bin/env python3
"""ShellCheck over scripts/*.sh at the one version CI runs, or say plainly that another one ran.

Why (#186): until this file, tools/check-all.sh ran whatever shellcheck was installed and printed
"clean", while CI's `bash` job ran the one Ubuntu 24.04 packages. On 2026-11-10 those were 0.11.0
(Homebrew) and 0.9.0, and they disagreed twice on one branch. 0.9.0 reported SC2120 on two
functions in scripts/macos-ai-tools.sh at 0bde1fd that 0.11.0 does not, and 0.9.0 rejects a
comment line starting `# shellcheck` that is not a valid directive, which 0.11.0 accepts. Local
said clean and CI failed, and nothing in "clean" said which shellcheck had produced it. #132 had
the same shape: `main` stayed red for six commits behind a green local check.

The fix is one pin, in this file, which both of them run: .github/workflows/lint.yml runs this
file instead of apt's shellcheck, and so does tools/check-all.sh. The version, the flags and the
file list therefore exist once.

Which shellcheck runs, in order:

  1. The pinned release binary, cached outside the repo, because check-all.sh asserts that the run
     does not change the working tree. It is used only if its --version is the pin.
  2. Otherwise the pinned release archive for this platform, downloaded from GitHub and refused
     unless its sha256 is the one pinned in ASSETS. A mismatch is a failure, never a fallback.
  3. Otherwise (offline, or no pinned build for this platform) the shellcheck on PATH, and the
     result says that it was used:
       - the pinned version: its result counts, since the same version gives the same findings;
       - another version, with findings: exit 1, naming both versions;
       - another version, clean: exit 77, "clean under X, but CI pins Y" (ADR-006). Clean under
         one version is not clean under another; that is #186;
       - no shellcheck at all: exit 77.
     CSA_REQUIRE_PINNED_SHELLCHECK=1, which lint.yml sets, makes step 3 a failure, so CI always
     runs the pin.

Why 0.11.0 and not 0.9.0, the version CI ran until now. 0.11.0 is the current release
(2025-08-04). It is the only one of the two with an Apple-silicon macOS build (0.9.0 would need
Rosetta on an M-series Mac) and with a sha256 that GitHub publishes for every asset (0.9.0's
assets have none). It is also what Homebrew installs, so a Mac's PATH fallback usually agrees too.
It was measured on 2026-11-12 and reports nothing in scripts/*.sh.

To move the pin, change VERSION and every sha256 in ASSETS. GitHub publishes the digests:

    gh api repos/koalaman/shellcheck/releases/tags/vX.Y.Z --jq '.assets[] | .name + " " + .digest'

Then run ./tools/check-all.sh, and fix or justify every new finding in the same PR.

--self-test breaks the rule on purpose. It first runs offline, with stand-in shellchecks:

  - another version that finds nothing must exit 77 and name both versions (the #186 case), never 0;
  - an archive whose sha256 is not the pin must be refused, without falling back;
  - a stale cached binary must not be used.

Then it uses the real pinned binary, and exits 77 if that cannot be had. A fixture with a
deliberate SC2120 must be reported, and the fixture's SC2119 (info) must not. That shows the
check can fail and that CI's flags reach it.

    python3 tools/check-shellcheck.py
    python3 tools/check-shellcheck.py --self-test
"""
from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import io
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION = "0.11.0"
RELEASES = f"https://github.com/koalaman/shellcheck/releases/download/v{VERSION}/"
# CI's flags, kept here and nowhere else. SC1091: sourced files are not present at lint time.
# SC2016: a single-quoted '$...' inside a heredoc sent to python is intentional.
ARGS = ["--severity=warning", "--exclude=SC1091,SC2016"]
GLOB = "scripts/*.sh"
_T = f"shellcheck-v{VERSION}"
# (os, cpu) -> (release asset, its sha256 as GitHub publishes it, the binary inside it).
ASSETS = {
    ("darwin", "arm64"): (f"{_T}.darwin.aarch64.tar.gz",
                          "339b930feb1ea764467013cc1f72d09cd6b869ebf1013296ba9055ab2ffbd26f",
                          f"{_T}/shellcheck"),
    ("darwin", "x86_64"): (f"{_T}.darwin.x86_64.tar.gz",
                           "c2c15e08df0e8fbc374c335b230a7ee958c313fa5714817a59aa59f1aa594f51",
                           f"{_T}/shellcheck"),
    ("linux", "x86_64"): (f"{_T}.linux.x86_64.tar.gz",
                          "b7af85e41cc99489dcc21d66c6d5f3685138f06d34651e6d34b42ec6d54fe6f6",
                          f"{_T}/shellcheck"),
    ("linux", "arm64"): (f"{_T}.linux.aarch64.tar.gz",
                         "68a8133197a50beb8803f8d42f9908d1af1c5540d4bb05fdfca8c1fa47decefc",
                         f"{_T}/shellcheck"),
    ("windows", "x86_64"): (f"{_T}.zip",
                            "8a4e35ab0b331c85d73567b12f2a444df187f483e5079ceffa6bda1faa2e740e",
                            "shellcheck.exe"),
}
REQUIRE_ENV = "CSA_REQUIRE_PINNED_SHELLCHECK"
SKIP = 77


class Refused(Exception):
    """What arrived is not what was pinned. This is never a reason to fall back."""


def platform_key() -> tuple[str, str]:
    cpu = platform.machine().lower()
    cpu = {"amd64": "x86_64", "aarch64": "arm64"}.get(cpu, cpu)
    return platform.system().lower(), cpu


def cache_root() -> pathlib.Path:
    """Outside the repo: check-all.sh fails a run that changes the working tree (#72)."""
    home = pathlib.Path.home()
    system = platform.system()
    if system == "Darwin":
        base = home / "Library" / "Caches"
    elif system == "Windows":
        base = pathlib.Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
    else:
        base = pathlib.Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache")
    return base / "csa-desktopsetup" / "shellcheck"


def version_of(cmd: list[str]) -> str | None:
    """What the binary says it is: `version: 0.11.0` in its --version output."""
    try:
        p = subprocess.run([*cmd, "--version"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"^version:\s*(\S+)", p.stdout, re.M)
    return m.group(1) if p.returncode == 0 and m else None


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: pathlib.Path) -> None:
    """urllib first; then curl, if urllib cannot (a Python with no CA certificates, say)."""
    try:
        with urllib.request.urlopen(url, timeout=120) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        return
    except (OSError, ValueError) as e:   # URLError and timeouts are OSErrors
        first = e
    curl = shutil.which("curl")
    if not curl or not url.startswith("https://"):
        raise OSError(f"cannot download {url}: {first}")
    try:
        p = subprocess.run([curl, "-fsSL", "--retry", "2", "--max-time", "300", "-o", str(dest),
                            url], capture_output=True, text=True, timeout=330)
    except subprocess.TimeoutExpired:
        raise OSError(f"cannot download {url}: {first}; curl timed out") from None
    if p.returncode != 0:
        raise OSError(f"cannot download {url}: {first}; curl: {p.stderr.strip() or p.returncode}")


def copy_member(archive: pathlib.Path, member: str, out: pathlib.Path) -> None:
    """Copy one named file out of the archive, to a path chosen here. Nothing else is extracted,
    so no path inside the archive decides where anything is written."""
    try:
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as z, z.open(member) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            return
        with tarfile.open(archive) as t:
            src = t.extractfile(member)
            if src is None:
                raise Refused(f"{archive.name}: {member} is not a regular file")
            with src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
    except (KeyError, tarfile.TarError, zipfile.BadZipFile) as e:
        raise Refused(f"{archive.name}: no usable {member} ({e})") from None


def fetch_pinned(cache: pathlib.Path, asset: str, sha: str, member: str,
                 base: str = RELEASES, prefix: tuple[str, ...] = ()) -> list[str]:
    """The pinned binary as a command. It comes from the cache if it still reports VERSION;
    otherwise it is downloaded, checked against `sha`, and cached. Raises OSError when it cannot
    be had, and Refused when what arrived is not what was pinned. `prefix` lets the self-test run a
    stand-in through the Python running this file."""
    binary = cache / f"v{VERSION}-{sha[:12]}" / pathlib.PurePosixPath(member).name
    cmd = [*prefix, str(binary)]
    if binary.is_file():
        if version_of(cmd) == VERSION:
            return cmd
        binary.unlink()                   # stale or damaged: fetch it again
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache) as td:
        archive = pathlib.Path(td) / asset
        download(base + asset, archive)
        got = sha256_of(archive)
        if got != sha:
            raise Refused(f"{asset} has sha256 {got}, but the pin is {sha}. Refusing to run it.")
        out = pathlib.Path(td) / binary.name
        copy_member(archive, member, out)
        out.chmod(0o755)
        reported = version_of([*prefix, str(out)])
        if reported != VERSION:
            raise Refused(f"{asset} matches its sha256, but its shellcheck reports "
                          f"{reported or 'no version'}, not {VERSION}")
        binary.parent.mkdir(parents=True, exist_ok=True)
        os.replace(out, binary)
    return cmd


def path_shellcheck() -> list[str] | None:
    found = shutil.which("shellcheck")
    return [found] if found else None


def lint(root: pathlib.Path, cmd: list[str], files: list[str]) -> int:
    try:
        p = subprocess.run([*cmd, *ARGS, *files], cwd=root, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                           errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        print(f"    {cmd[-1]} did not finish in 15 minutes")
        return 1
    print(p.stdout, end="")
    return p.returncode


def fallback(root: pathlib.Path, files: list[str], why: str, require: bool, which) -> int:
    if require:
        print(f"    FAILED: {REQUIRE_ENV} is set, and the pinned shellcheck {VERSION} could not "
              f"be had: {why}")
        return 1
    cmd = which()
    if not cmd:
        print(f"    SKIP: shellcheck did not run. The pinned {VERSION} could not be had ({why}), "
              f"and there is no shellcheck on PATH.")
        return SKIP
    v = version_of(cmd)
    label = v or "an unknown version"
    print(f"    the pinned shellcheck {VERSION} could not be had ({why});")
    print(f"    running {cmd[-1]} instead, which is shellcheck {label}")
    rc = lint(root, cmd, files)
    if rc:
        note = "" if v == VERSION else f". CI pins {VERSION}, which may not report the same"
        print(f"    FAILED: shellcheck {label} reported the above{note}")
        return 1
    if v == VERSION:
        print(f"    clean: shellcheck {v} from PATH, the version CI pins (not the "
              f"checksum-verified release binary)")
        return 0
    print(f"    SKIP: clean under shellcheck {label}, but CI pins {VERSION}. Clean here does not "
          f"mean clean in CI (#186).")
    return SKIP


def run_check(root: pathlib.Path, cache: pathlib.Path, require: bool,
              which=path_shellcheck, fetch=fetch_pinned, key: tuple[str, str] | None = None) -> int:
    files = sorted(p.relative_to(root).as_posix() for p in root.glob(GLOB))
    if not files:
        print(f"    FAILED: no {GLOB} under {root}; a clean result over nothing proves nothing")
        return 1
    key = key or platform_key()
    try:
        if key not in ASSETS:
            raise OSError(f"there is no pinned shellcheck build for {'/'.join(key)}")
        cmd = fetch(cache, *ASSETS[key])
    except Refused as e:
        print(f"    FAILED: {e}")
        return 1
    except OSError as e:
        return fallback(root, files, str(e), require, which)
    print(f"    shellcheck {VERSION}, the pinned release binary: {cmd[-1]}")
    print(f"    {' '.join(ARGS)} {GLOB} ({len(files)} files)")
    if lint(root, cmd, files):
        print(f"    FAILED: shellcheck {VERSION}, the version CI pins, reported the above")
        return 1
    print(f"    clean: shellcheck {VERSION}, the version CI pins")
    return 0


# ── self-test ─────────────────────────────────────────────────────────────────────────────────
# greet reads $1 and is never passed one: SC2120, a warning, which CI's flags must report. The
# bare call is SC2119, an info, which --severity=warning must hide.
FIXTURE = '#!/usr/bin/env bash\ngreet() { echo "hello ${1}"; }\ngreet\n'


def _stand_in(path: pathlib.Path, version: str, rc: int) -> pathlib.Path:
    """A Python file that answers --version like shellcheck and exits `rc` on a lint."""
    path.write_text(
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('ShellCheck - shell script analysis tool')\n"
        f"    print('version: {version}')\n"
        "    sys.exit(0)\n"
        f"if {rc}:\n"
        "    print('SC2120 (warning): a stand-in finding')\n"
        f"sys.exit({rc})\n", encoding="utf-8")
    return path


def _archive(where: pathlib.Path, asset: str, member: str, content: pathlib.Path) -> str:
    """Build a release-shaped archive; return its sha256."""
    path = where / asset
    if asset.endswith(".zip"):
        with zipfile.ZipFile(path, "w") as z:
            z.write(content, member)
    else:
        with tarfile.open(path, "w:gz") as t:
            t.add(content, member)
    return sha256_of(path)


def _quiet(fn, *args, **kwargs) -> tuple[object, str]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            result = fn(*args, **kwargs)
        except Exception as e:            # the case decides whether an exception is right
            result = e
    return result, buf.getvalue()


def _offline(*_args, **_kwargs):
    raise OSError("offline, in the self-test")


def _never(*_args, **_kwargs):
    raise AssertionError("must not be consulted")


def hermetic_cases(td: pathlib.Path) -> list[tuple[str, bool, str]]:
    root = td / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "a.sh").write_text("#!/usr/bin/env bash\ntrue\n", encoding="utf-8")
    other = "0.0.1-selftest"
    py = (sys.executable,)
    stand_in = lambda name, v, rc: [*py, str(_stand_in(td / name, v, rc))]   # noqa: E731
    # Any pinned platform: these cases are about the logic, not about the machine running them.
    check = functools.partial(run_check, key=next(iter(ASSETS)))
    cases: list[tuple[str, bool, str]] = []

    def case(name: str, ok: bool, out: str) -> None:
        cases.append((name, ok, out.strip()[-600:]))

    # The #186 defect: another version, clean. Exit 0 here is the bug.
    rc, out = _quiet(check, root, td / "c1", False, lambda: stand_in("old.py", other, 0),
                     _offline)
    case("another version, clean -> 77 naming both, never 0",
         rc == SKIP and other in out and VERSION in out, out)

    rc, out = _quiet(check, root, td / "c2", False, lambda: stand_in("oldf.py", other, 1),
                     _offline)
    case("another version, findings -> 1 naming both", rc == 1 and other in out and VERSION in out,
         out)

    rc, out = _quiet(check, root, td / "c3", False, lambda: stand_in("same.py", VERSION, 0),
                     _offline)
    case("the pinned version from PATH, clean -> 0, saying so",
         rc == 0 and "from PATH" in out, out)

    rc, out = _quiet(check, root, td / "c4", False, lambda: None, _offline)
    case("no shellcheck anywhere -> 77", rc == SKIP, out)

    rc, out = _quiet(check, root, td / "c5", True, lambda: stand_in("same2.py", VERSION, 0),
                     _offline)
    case(f"{REQUIRE_ENV} and no pinned binary -> 1, even with {VERSION} on PATH",
         rc == 1 and REQUIRE_ENV in out, out)

    empty = td / "empty"
    empty.mkdir()
    rc, out = _quiet(check, empty, td / "c6", False, lambda: stand_in("e.py", VERSION, 0),
                     _offline)
    case("no scripts at all -> 1, not a clean result about nothing", rc == 1, out)

    # The download path, on real archives served from a file:// URL. The "binary" is a stand-in
    # run through this Python, so the same cases run on macOS, Linux and Windows.
    served = td / "served"
    served.mkdir()
    good = _stand_in(td / "good.py", VERSION, 0)
    for asset, member in ((f"{_T}.selftest.tar.gz", f"{_T}/shellcheck"),
                          (f"{_T}.selftest.zip", "shellcheck.exe")):
        sha = _archive(served, asset, member, good)
        base = served.as_uri() + "/"
        cache = td / f"cache-{asset}"
        fetch = functools.partial(fetch_pinned, base=base, prefix=py)

        got, out = _quiet(fetch, cache, asset, "0" * 64, member)
        leftovers = [p for p in cache.rglob("*") if p.is_file()] if cache.exists() else []
        case(f"{asset}: a sha256 that is not the pin -> refused, nothing cached",
             isinstance(got, Refused) and not leftovers, str(got))

        rc, out = _quiet(check, root, cache, False, _never,
                         lambda c, *a: fetch(c, asset, "0" * 64, member))
        case(f"{asset}: a refused archive fails the run and never falls back to PATH",
             rc == 1 and "Refusing" in out, out)

        got, out = _quiet(fetch, cache, asset, sha, member)
        case(f"{asset}: the pinned sha256 -> extracted and cached",
             isinstance(got, list) and pathlib.Path(got[-1]).is_file(), str(got))

        got2, out = _quiet(fetch_pinned, cache, asset, sha, member,
                           base=(td / "nowhere").as_uri() + "/", prefix=py)
        case(f"{asset}: a cached pinned binary is used without downloading", got2 == got,
             str(got2))

        if isinstance(got, list):
            _stand_in(pathlib.Path(got[-1]), other, 0)           # the cache goes stale
            got3, out = _quiet(fetch, cache, asset, sha, member)
            case(f"{asset}: a cached binary reporting another version is replaced",
                 got3 == got and version_of(got3) == VERSION, str(got3))

    bad = [k for k, (asset, sha, _m) in ASSETS.items()
           if not asset.startswith(_T) or not re.fullmatch(r"[0-9a-f]{64}", sha)]
    case("every pinned asset is this version's and has a sha256", not bad, str(bad))
    return cases


def live_case(require: bool) -> tuple[int, str]:
    """The real pinned binary must report the fixture's SC2120 and hide its SC2119."""
    key = platform_key()
    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        (root / "scripts").mkdir()
        (root / "scripts" / "fixture.sh").write_text(FIXTURE, encoding="utf-8")
        rc, out = _quiet(run_check, root, cache_root(), require, lambda: None)
    if "pinned release binary" not in out:
        why = out.strip() or f"no pinned build for {'/'.join(key)}"
        if require or "FAILED" in out:
            return 1, f"FAILED: the pinned binary could not be run:\n{why}"
        return SKIP, f"SKIP: the live case could not run; the pinned binary could not be had:\n{why}"
    ok = rc == 1 and "SC2120" in out and "SC2119" not in out
    return (0 if ok else 1), out.rstrip()


def self_test(require: bool) -> int:
    with tempfile.TemporaryDirectory() as td:
        cases = hermetic_cases(pathlib.Path(td))
    failed = [c for c in cases if not c[1]]
    for name, ok, out in cases:
        print(f"    {'ok  ' if ok else 'FAIL'}  {name}")
        if not ok:
            print("          " + out.replace("\n", "\n          "))
    rc, detail = live_case(require)
    name = (f"the pinned shellcheck {VERSION} reports the fixture's SC2120 and hides its SC2119 "
            f"(CI's flags reach it, and the check can fail)")
    print(f"    {'ok  ' if rc == 0 else 'SKIP' if rc == SKIP else 'FAIL'}  {name}")
    if rc:
        print("          " + detail.replace("\n", "\n          "))
    if failed or rc == 1:
        print("self-test FAILED")
        return 1
    if rc == SKIP:
        print(f"self-test: {len(cases)} offline cases passed; the live case did not run")
        return SKIP
    print(f"self-test passed: {len(cases)} offline cases and the live case")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    require = bool(os.environ.get(REQUIRE_ENV))
    if a.self_test:
        return self_test(require)
    return run_check(ROOT, cache_root(), require)


if __name__ == "__main__":
    sys.exit(main())
