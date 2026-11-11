#!/usr/bin/env python3
"""The CSA Python pin is declared in six scripts, and until now only two of them declared it.

`CSA_PYTHON_PREFERRED` (`$CsaPythonPreferred` on Windows) says which interpreter a fresh
machine gets, and is handed to the private gate repo's setup scripts so their
`uv tool install --python` lands the server on it. Only the two `*-ai-tools` scripts defined
it. `macos-update.sh` and `macos-plugins.sh` passed `"${CSA_PYTHON_PREFERRED:-}"` (empty) and
`windows-update.ps1` / `windows-plugins.ps1` assigned `$CsaPythonPreferred`, a variable they
never defined, so a person who ran `-update` or `-plugins` got whatever the gate script's own
fallback was. Nothing failed; the interpreter was simply guessed.

This pins:
  * all six scripts declare the preferred Python exactly once, and all six agree;
  * the floor (`CSA_PYTHON_MIN` / `$CsaPythonMin`) agrees across platforms;
  * every `CSA_DOC_PY_DEPS=(...)` copy in `scripts/*.sh` is identical (an array, not a function,
    so `tools/check-duplication.py` does not cover it);
  * no script installs onnxruntime or markitdown: neither appears in a deps array, nor on a code
    line that runs an `install`. onnxruntime's official macOS and Linux builds (>= 1.29) send
    Microsoft telemetry by default; markitdown pulls it in through magika, and pymupdf 2.x
    requires it outright, which is why pymupdf is pinned below 2. A comment may name them; the
    real resolution is checked by `tools/check-doc-deps-resolve.py`, which needs uv and the
    network.

What it cannot check: that 3.14 is the right number. That is a decision (the constants are
pinned below), not something a script can derive.

    python3 tests/test_python_pins.py
    python3 tests/test_python_pins.py --self-test
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

WANT = "3.14"

SH = ["scripts/macos-ai-tools.sh", "scripts/macos-plugins.sh", "scripts/macos-update.sh"]
PS1 = ["scripts/windows-ai-tools.ps1", "scripts/windows-plugins.ps1", "scripts/windows-update.ps1"]
SIX = SH + PS1

# An assignment, not a mention: anchored at line start so `$env:CSA_PYTHON_PREFERRED = ...`,
# `CSA_NESTED=1 CSA_PYTHON_PREFERRED="${...}"` and comments do not count.
PREFERRED_RE = {
    "sh": re.compile(r'^CSA_PYTHON_PREFERRED="([^"]*)"', re.M),
    "ps1": re.compile(r"^\$CsaPythonPreferred\s*=\s*'([^']*)'", re.M),
}
MIN_RE = {
    "sh": re.compile(r'^CSA_PYTHON_MIN="([^"]*)"', re.M),
    "ps1": re.compile(r"^\$CsaPythonMin\s*=\s*'([^']*)'", re.M),
}
# Tolerates indentation and a `local` / `readonly` / `declare -a` prefix, so a copy moved
# inside a function is still found rather than silently ignored. Group 1 is the array's name.
DEPS_RE = re.compile(
    r"^[ \t]*(?:(?:local|readonly|declare(?:\s+-[a-zA-Z]+)*)\s+)?"
    r"(CSA_DOC_PY_DEPS)=\(([^)]*)\)", re.M)

# Never installed by any script, for the reason in the module docstring. `install` as a whole
# word, so `uninstall` (the to-do that removes onnxruntime from an old venv) is not an install.
FORBIDDEN = ("onnxruntime", "markitdown", "magika")
FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")\b", re.I)
INSTALL_RE = re.compile(r"\binstall\b")
ALL_SCRIPTS = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "scripts").iterdir()
                     if p.suffix in (".sh", ".ps1"))


def kind(name: str) -> str:
    return "ps1" if name.endswith(".ps1") else "sh"


def load() -> dict[str, str]:
    return {n: (ROOT / n).read_text(encoding="utf-8") for n in dict.fromkeys(SIX + ALL_SCRIPTS)}


def six(texts: dict[str, str]) -> dict[str, str]:
    return {n: texts[n] for n in SIX}


def preferred_problems(texts: dict[str, str]) -> list[str]:
    """One message per script that does not declare exactly one preferred Python equal to WANT."""
    out = []
    for name, text in texts.items():
        found = PREFERRED_RE[kind(name)].findall(text)
        if len(found) != 1:
            out.append(f"{name}: {len(found)} declarations of the preferred Python, expected 1")
        elif found[0] != WANT:
            out.append(f"{name}: preferred Python is {found[0]!r}, expected {WANT!r}")
    return out


def min_problems(texts: dict[str, str]) -> list[str]:
    """The floor must be declared and agree across the platforms that declare it."""
    seen = {}
    for name, text in texts.items():
        found = MIN_RE[kind(name)].findall(text)
        if found:
            seen[name] = found[0]
    out = []
    for label, group in (("macOS", SH), ("Windows", PS1)):
        if not any(n in seen for n in group):
            out.append(f"{group[0]}: no {label} script declares the minimum Python")
    if len(set(seen.values())) > 1:
        out.append(f"the minimum Python differs between scripts: {seen}")
    for name, value in seen.items():
        if value != WANT:
            out.append(f"{name}: minimum Python is {value!r}, expected {WANT!r}")
    return out


def deps_problems(texts: dict[str, str]) -> list[str]:
    """Every copy of the deps array must be identical. Vacuous with one copy, by design."""
    flat: list[tuple[str, list[str]]] = []
    for name, text in texts.items():
        for m in DEPS_RE.finditer(text):
            flat.append((name, m.group(2).split()))
    out = []
    if flat:
        ref_name, ref = flat[0]
        for name, c in flat[1:]:
            if c != ref:
                out.append(f"{name}: CSA_DOC_PY_DEPS is {c}, but {ref_name} has {ref}")
    return out


def code_lines(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line that is not a full-line comment, in bash or PowerShell."""
    return [(i, l) for i, l in enumerate(text.splitlines(), 1) if not l.lstrip().startswith("#")]


def forbidden_problems(texts: dict[str, str]) -> list[str]:
    """No deps array and no code line that runs an `install` names onnxruntime, markitdown or
    magika. A comment explaining why they are absent is fine."""
    out = []
    for name, text in texts.items():
        for m in DEPS_RE.finditer(text):
            if FORBIDDEN_RE.search(m.group(2)):
                out.append(f"{name}: CSA_DOC_PY_DEPS names {FORBIDDEN_RE.search(m.group(2)).group(1)}")
        for i, line in code_lines(text):
            if INSTALL_RE.search(line) and FORBIDDEN_RE.search(line):
                out.append(f"{name}:{i}: an install names {FORBIDDEN_RE.search(line).group(1)}: "
                           f"{line.strip()[:120]}")
    return out


def run_checks(texts: dict[str, str]) -> list[str]:
    return (preferred_problems(six(texts)) + min_problems(six(texts)) + deps_problems(texts)
            + forbidden_problems(texts))


def self_test() -> int:
    """Break the rules on purpose and prove each break is reported, by file."""
    texts = load()
    if run_checks(texts):
        print("self-test cannot start: the real scripts already fail")
        return 1
    ok = True

    def expect(label: str, problems: list[str], names: list[str]) -> None:
        nonlocal ok
        missing = [n for n in names if not any(p.startswith(n) for p in problems)]
        good = bool(problems) and not missing
        print(f"  {'ok  ' if good else 'FAIL'}  {label}" + ("" if good else f" - unreported: {missing or 'anything'}"))
        ok = ok and good

    def expect_none(label: str, problems: list[str]) -> None:
        nonlocal ok
        good = not problems
        print(f"  {'ok  ' if good else 'FAIL'}  {label}" + ("" if good else f" - reported: {problems}"))
        ok = ok and good

    mutated = dict(texts)
    mutated[SH[0]] = PREFERRED_RE["sh"].sub('CSA_PYTHON_PREFERRED="3.15"', mutated[SH[0]])
    mutated[PS1[1]] = PREFERRED_RE["ps1"].sub("# removed", mutated[PS1[1]])
    expect("a 3.15 copy and a deleted copy are both reported, by file",
           preferred_problems(six(mutated)), [SH[0], PS1[1]])

    mutated = dict(texts)
    mutated[PS1[0]] = MIN_RE["ps1"].sub("$CsaPythonMin = '3.13'", mutated[PS1[0]])
    expect("a floor that differs across platforms is reported",
           min_problems(six(mutated)), [PS1[0]])

    mutated = dict(texts)
    mutated[SH[0]] = MIN_RE["sh"].sub("# removed", mutated[SH[0]])
    expect("a platform with no floor declared is reported",
           min_problems(six(mutated)), [SH[0]])

    mutated = dict(texts)
    real = DEPS_RE.search(mutated[SH[0]]).group(0)
    mutated[SH[1]] = mutated[SH[1]] + "\n" + real.replace("pymupdf", "pymupdf2") + "\n"
    expect("two CSA_DOC_PY_DEPS copies that differ are reported",
           deps_problems(mutated), [SH[1]])

    mutated = dict(texts)
    mutated[SH[2]] = mutated[SH[2]].replace(real, real.replace(",<2", ""))
    expect("a copy that drops the pymupdf<2 pin is reported (it differs from the others)",
           deps_problems(mutated), [SH[2]])

    mutated = dict(texts)
    for n in (SH[0], SH[2]):
        mutated[n] = mutated[n].replace(real, real.replace(")", ' "markitdown[all]>=0.1.9")'))
    expect("markitdown put back into both deps arrays (they still agree) is reported",
           forbidden_problems(mutated), [SH[0], SH[2]])

    mutated = dict(texts)
    mutated[PS1[0]] = mutated[PS1[0]] + "\n    & $py -m pip install --quiet onnxruntime\n"
    mutated[SH[1]] = mutated[SH[1]] + '\n  uv pip install --python "$vpy" magika\n'
    expect("an install line naming onnxruntime (.ps1) or magika (.sh) is reported",
           forbidden_problems(mutated), [PS1[0], SH[1]])

    mutated = dict(texts)
    mutated[SH[1]] = (mutated[SH[1]] + "\n# markitdown is not installed: it pulls onnxruntime\n"
                      '  echo "uv pip uninstall --python x onnxruntime"\n')
    expect_none("a comment naming onnxruntime, and an UNinstall of it, are not reported",
                forbidden_problems(mutated))

    mutated = dict(texts)
    mutated[SH[2]] = mutated[SH[2]] + "\nf() {\n    local CSA_DOC_PY_DEPS=(pyyaml other)\n}\n"
    ref = DEPS_RE.search(mutated[SH[0]]).group(0)
    mutated[SH[1]] = mutated[SH[1]] + "\nf() {\n    " + ref + "\n}\n"
    expect("an indented or local copy with different contents is found and reported",
           deps_problems(mutated), [SH[2]])

    print("self-test " + ("passed" if ok else "FAILED"))
    return 0 if ok else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    print("CSA Python pins\n")
    texts = load()
    failures = []
    for label, fn, scope in [
        (f"all six scripts declare the preferred Python exactly once, as {WANT}", preferred_problems,
         six(texts)),
        ("the minimum Python agrees across platforms", min_problems, six(texts)),
        ("every CSA_DOC_PY_DEPS copy is identical", deps_problems, texts),
        ("no script installs onnxruntime, markitdown or magika (deps arrays and install lines, "
         f"{len(ALL_SCRIPTS)} scripts)", forbidden_problems, texts),
    ]:
        problems = fn(scope)
        print(f"  {'ok  ' if not problems else 'FAIL'}  {label}")
        for p in problems:
            print(f"        {p}")
        failures += problems
    print()
    if failures:
        print(f"FAILED: {len(failures)} problem(s)")
        return 1
    n = sum(len(DEPS_RE.findall(t)) for t in texts.values())
    print(f"all checks passed - six scripts, {n} document-deps array copy(ies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
