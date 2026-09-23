"""Repository checks: the shipped prompts and templates stay free of personal data and stale numbers."""

from __future__ import annotations

import re
from pathlib import Path

from qa_sweep import install as install_module

AREA = "repository"
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "qa_sweep" / "data"
CASES = sorted((ROOT / "tests").glob("cases_*.py"))

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WINDOWS_HOME = re.compile(r"[A-Za-z]:\\\\?Users\\\\?[A-Za-z]")
POSIX_HOME = re.compile(r"/home/[A-Za-z]")
PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")


def run(check):
    text_files = sorted(DATA.rglob("*.md")) + sorted(DATA.rglob("*.py"))
    check("repo.data_files_present", AREA, "the prompt pack and templates ship with the package",
              len(text_files) >= 4, f"{len(text_files)} file(s) under qa_sweep/data")

    leaks = []
    scanned = list(text_files)
    previous_results = ROOT / "tests" / "selftest-results.json"
    if previous_results.is_file():
        scanned.append(previous_results)
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        for pattern, label in ((EMAIL, "email address"), (WINDOWS_HOME, "windows home path"),
                               (POSIX_HOME, "posix home path")):
            if pattern.search(text):
                leaks.append(f"{path.name}: {label}")
    check("repo.no_personal_data", AREA,
          "no email address or home path in the shipped prompts or the committed results",
          not leaks, "; ".join(leaks))

    unknown = []
    for path in DATA.rglob("*"):
        if path.suffix not in (".md", ".py"):
            continue
        for token in PLACEHOLDER.findall(path.read_text(encoding="utf-8")):
            if token not in install_module.PLACEHOLDERS:
                unknown.append(f"{path.name}: {token}")
    check("repo.placeholders_allowlisted", AREA,
          "every placeholder in the prompt pack is one the installer knows how to fill",
          not unknown, "; ".join(unknown))

    declared = set(install_module.PROMPT_FILES.values()) | {relative for _, relative in install_module.SUITE_FILES}
    missing = sorted(name for name in declared if not (DATA / name).is_file())
    check("repo.declared_files_exist", AREA, "every file the installer reads exists on disk",
          not missing, f"missing: {missing}")

    compile_errors = []
    for path in sorted(DATA.rglob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            compile_errors.append(f"{path.name}: {exc}")
    check("repo.templates_compile", AREA, "the shipped python templates are valid source",
          not compile_errors, "; ".join(compile_errors))

    calls = 0
    for path in CASES:
        calls += len(re.findall(r"^\s*(?:check|skip)\(", path.read_text(encoding="utf-8"), re.M))
    readme = (ROOT / "README.md")
    quoted = None
    if readme.is_file():
        match = re.search(r"Self-test checks: (\d+)", readme.read_text(encoding="utf-8"))
        quoted = int(match.group(1)) if match else None
    check("repo.readme_check_count_current", AREA,
          "the number of self-tests quoted in the README equals the number the suite runs",
          quoted == calls, f"README quotes {quoted}, the suite declares {calls} checks")

    doc = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    required = ["## What it does", "## Install", "## Usage", "## Limitations", "## License"]
    absent = [heading for heading in required if heading not in doc]
    check("repo.readme_sections", AREA, "the README keeps the sections a reader needs",
          not absent, f"missing: {absent}")

    contract = ROOT / "docs" / "report-contract.md"
    check("repo.contract_documented", AREA, "the report contract is documented next to the code",
          contract.is_file() and "A." in contract.read_text(encoding="utf-8"),
          f"{contract} exists: {contract.is_file()}")

    # Anything that only exists from Python 3.10 was a real defect once: the installer crashed on 3.9.
    modern = [
        (re.compile(r"write_text\([^\n]*,\s*newline="), "Path.write_text(newline=) needs 3.10"),
        (re.compile(r"zip\([^\n]*strict="), "zip(strict=) needs 3.10"),
        (re.compile(r"^\s*match\s+\w.*:\s*$", re.M), "a match statement needs 3.10"),
        (re.compile(r"\btomllib\b"), "tomllib needs 3.11"),
    ]
    sources = [path for path in sorted((ROOT / "qa_sweep").rglob("*.py")) if path.name != "cases_repo.py"]
    sources += [path for path in sorted((ROOT / "tests").rglob("*.py")) if path.name != "cases_repo.py"]
    sources += sorted(DATA.rglob("*.py"))
    offenders = []
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for pattern, label in modern:
            if pattern.search(text):
                offenders.append(f"{path.name}: {label}")
    check("repo.python39_compatible", AREA,
          "nothing in the package, the templates or the tests needs an API newer than Python 3.9",
          not offenders, "; ".join(offenders))
