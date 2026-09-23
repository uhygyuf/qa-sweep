"""Check harness for a release-readiness suite. Standard library only, no network.

Every check records an id, an area, a description, an ok flag, a detail string and its duration. The
suite writes JSON so a reviewer can re-run it and compare, and its exit code counts the failures.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

MAX_DETAIL = 2000


def run_command(command, cwd=None, timeout=120, shell=None):
    """Run a command and return code, stdout+stderr and duration in seconds."""
    if isinstance(command, str) and shell is None:
        shell = True
    started = time.time()
    try:
        completed = subprocess.run(
            command, cwd=str(cwd) if cwd else None, shell=shell, timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        output = completed.stdout.decode("utf-8", errors="replace")
        return {"code": completed.returncode, "output": output, "seconds": time.time() - started}
    except subprocess.TimeoutExpired:
        return {"code": None, "output": f"timeout after {timeout}s", "seconds": time.time() - started}
    except OSError as exc:
        return {"code": None, "output": f"could not run: {exc}", "seconds": time.time() - started}


class Suite:
    """Collect checks, print them, write the results file, return the exit code."""

    def __init__(self, name, results_path, verbose=True):
        self.name = name
        self.results_path = Path(results_path)
        self.verbose = verbose
        self.entries = []
        self.started = time.time()

    def _record(self, entry):
        entry["ms"] = round((time.time() - self.started) * 1000, 1)
        self.entries.append(entry)
        if self.verbose:
            if entry.get("skipped"):
                mark = "SKIP"
            else:
                mark = "ok  " if entry["ok"] else "FAIL"
            print(f"[{mark}] {entry['area']:24} {entry['id']}: {entry['description']}")
            if entry["detail"] and (not entry["ok"] or entry.get("skipped")):
                print(f"       {entry['detail'][:400]}")
        return entry

    def check(self, check_id, area, description, ok, detail=""):
        return self._record({
            "id": check_id, "area": area, "description": description,
            "ok": bool(ok), "detail": str(detail)[:MAX_DETAIL], "skipped": False,
        })

    def skip(self, check_id, area, description, reason):
        """A check that could not run. It is reported, never counted as a pass."""
        return self._record({
            "id": check_id, "area": area, "description": description,
            "ok": None, "detail": str(reason)[:MAX_DETAIL], "skipped": True,
        })

    def finish(self):
        failures = [entry for entry in self.entries if entry["ok"] is False]
        skipped = [entry for entry in self.entries if entry.get("skipped")]
        passed = len(self.entries) - len(failures) - len(skipped)
        payload = {
            "suite": self.name,
            "generated_by": "tests/qa_lib.py",
            "seconds": round(time.time() - self.started, 2),
            "totals": {"checks": len(self.entries), "passed": passed,
                       "failed": len(failures), "skipped": len(skipped)},
            "results": self.entries,
        }
        self.results_path.parent.mkdir(parents=True, exist_ok=True)
        self.results_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print("")
        print(f"{len(self.entries)} checks: {passed} passed, {len(failures)} failed, "
              f"{len(skipped)} skipped in {payload['seconds']}s")
        print(f"results written to {self.results_path}")
        if failures:
            print("")
            print("failing checks:")
            for entry in failures:
                print(f"  {entry['id']}: {entry['description']} ({entry['detail'][:200]})")
        return min(len(failures), 125)


def load_results(path):
    """Read a results file back. Useful when a check asserts on a previous run."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    print(__doc__)
    print("Import this module from your suite, for example: from qa_lib import Suite, run_command")
    sys.exit(0)
