"""qa-sweep self-tests.

Standard library only, no network, no writes outside temporary directories. Every check fabricates the
condition it asserts on, in both directions: the state the tool must fix, and the healthy state it
must leave alone.

    python tests/run_tests.py

Exit code equals the number of failing checks, so CI fails on the first defect.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
for entry in (str(ROOT), str(HERE)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

RESULTS = []
STARTED = time.time()

# Paths from this machine are replaced before the results file is written, so the committed evidence
# is portable and carries no user name. The replacement runs on the finished JSON text, which means a
# path that was already escaped by repr() is caught too.
WINDOWS_PATH = re.compile(r"[A-Za-z]:(?:[\\/]+[^\\/\s\"']+)+")
POSIX_PATH = re.compile(r"/(?:home|Users|tmp|var|private|mnt|opt|usr)/[^\s\"',)]*")


def _windows_token(match) -> str:
    lowered = match.group(0).lower()
    if "users" in lowered:
        return "<home>"
    if "temp" in lowered or "tmp" in lowered:
        return "<tmp>"
    return "<path>"


def scrub(text: str) -> str:
    return POSIX_PATH.sub("<path>", WINDOWS_PATH.sub(_windows_token, text))


def check(check_id, area, description, ok, detail=""):
    entry = {
        "id": check_id,
        "area": area,
        "description": description,
        "ok": bool(ok),
        "detail": str(detail)[:2000],
        "skipped": False,
        "ms": round((time.time() - STARTED) * 1000, 1),
    }
    RESULTS.append(entry)
    print(f"[{'ok  ' if entry['ok'] else 'FAIL'}] {area:16} {check_id}: {description}")
    if not entry["ok"]:
        print(f"       {entry['detail'][:500]}")
    return entry


def skip(check_id, area, description, reason):
    entry = {
        "id": check_id,
        "area": area,
        "description": description,
        "ok": None,
        "detail": str(reason)[:2000],
        "skipped": True,
        "ms": round((time.time() - STARTED) * 1000, 1),
    }
    RESULTS.append(entry)
    print(f"[SKIP] {area:16} {check_id}: {description}")
    return entry


def load_cases():
    modules = []
    for path in sorted(HERE.glob("cases_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append((path.stem, module))
    return modules


def main() -> int:
    print(f"qa-sweep self-tests, python {sys.version.split()[0]}")
    print("")
    crashed = []
    for name, module in load_cases():
        area = getattr(module, "AREA", name)
        try:
            module.run(check)
        except Exception as exc:  # a case module that crashes must fail loudly, not silently
            crashed.append(f"{name}: {exc.__class__.__name__}: {exc}")
            check(f"{name}.module_ran", area, f"the {name} case module runs to completion", False,
                  f"{exc.__class__.__name__}: {exc}")
        print("")

    failures = [entry for entry in RESULTS if entry["ok"] is False]
    skipped = [entry for entry in RESULTS if entry.get("skipped")]
    passed = len(RESULTS) - len(failures) - len(skipped)
    payload = {
        "suite": "qa-sweep self-tests",
        "generated_by": "tests/run_tests.py",
        "seconds": round(time.time() - STARTED, 2),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "totals": {"checks": len(RESULTS), "passed": passed, "failed": len(failures),
                   "skipped": len(skipped)},
        "results": RESULTS,
    }
    results_path = HERE / "selftest-results.json"
    results_path.write_text(scrub(json.dumps(payload, indent=2)), encoding="utf-8")

    print(f"{len(RESULTS)} checks: {passed} passed, {len(failures)} failed, {len(skipped)} skipped "
          f"in {payload['seconds']}s")
    print(f"results written to {results_path}")
    if failures:
        print("")
        print("failing checks:")
        for entry in failures:
            print(f"  {entry['id']}: {entry['description']}")
            print(f"    {entry['detail'][:300]}")
    if crashed:
        print("")
        print("case modules that crashed:")
        for line in crashed:
            print(f"  {line}")
    return min(len(failures), 125)


if __name__ == "__main__":
    sys.exit(main())
