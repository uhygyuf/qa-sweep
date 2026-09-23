"""Report contract checks: a plausible report must fail the contract, a complete one must pass."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import support
from qa_sweep.check import check_report

AREA = "report contract"
ROOT = Path(__file__).resolve().parents[1]


def _violations(result) -> str:
    return " | ".join(result["violations"])[:600]


def _cli(project: Path, *arguments):
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, "-m", "qa_sweep", *arguments], cwd=str(project),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environment,
                          timeout=120)


def run(check):
    with support.temp_project() as project:
        support.copy_fixture_project(project)
        good = check_report(project / "TEST_REPORT.md")
        check("check.good_report_passes", AREA, "a complete report passes the contract",
              good["ok"], _violations(good))
        check("check.good_report_passes_strict", AREA, "the same report passes with --strict",
              check_report(project / "TEST_REPORT.md", strict=True)["ok"],
              "warnings must be empty, a documented rollback and monitoring are required")
        check("check.verdict_parsed", AREA, "the verdict is read from section A",
              good["verdict"] == "conditional release", f"verdict: {good['verdict']!r}")
        check("check.results_counted", AREA, "failures are counted from the cited results file",
              good["failures"] == 1, f"failures: {good['failures']}")

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "## D. Bug list", "## Defect list")
        result = check_report(project / "TEST_REPORT.md")
        check("check.missing_section_fails", AREA, "a missing section D is a violation",
              not result["ok"] and any("section" in item and "D" in item for item in result["violations"]),
              _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "## B. Environment",
                             "The login flow should pass on the first try.\n\n## B. Environment")
        result = check_report(project / "TEST_REPORT.md")
        check("check.hedging_fails", AREA, "a hedged claim is rejected with its line number",
              not result["ok"] and "should pass" in _violations(result) and "line " in _violations(result),
              _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "| pass | `npm test` exit 0, 34 passed |", "| pass | n/a |")
        result = check_report(project / "TEST_REPORT.md")
        check("check.vague_evidence_fails", AREA, "a result row without evidence is a violation",
              not result["ok"] and "without evidence" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "| P3 |", "| minor |")
        result = check_report(project / "TEST_REPORT.md")
        check("check.missing_priority_fails", AREA, "a defect row without a P0 to P3 priority is a violation",
              not result["ok"] and "priority" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "**Conditional release.**", "**Release recommended.**")
        result = check_report(project / "TEST_REPORT.md")
        check("check.release_with_p1_fails", AREA,
              "a release verdict next to an open P1 or a failing check is a violation",
              not result["ok"] and "release recommended" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "Not covered:", "Left out:")
        result = check_report(project / "TEST_REPORT.md")
        check("check.coverage_limits_required", AREA,
              "a report that does not say what was not covered is a violation",
              not result["ok"] and "not covered" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "the message reads \"invalid\"", "there are no bugs left here")
        result = check_report(project / "TEST_REPORT.md")
        check("check.absolute_claim_fails", AREA, "an absolute claim such as 'no bugs' is a violation",
              not result["ok"] and "absolute" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        (project / "tests" / "qa-results.json").write_text("{ not json", encoding="utf-8")
        result = check_report(project / "TEST_REPORT.md")
        check("check.broken_results_json_fails", AREA, "an unreadable results file is a violation",
              not result["ok"] and "not readable JSON" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        (project / "tests" / "qa-results.json").unlink()
        result = check_report(project / "TEST_REPORT.md")
        check("check.missing_results_file_fails", AREA,
              "citing a results file that does not exist is a violation",
              not result["ok"] and "readable results JSON" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.replace_section_body(project, "D", "Defects exist and are tracked in the issue tracker.")
        result = check_report(project / "TEST_REPORT.md")
        check("check.empty_bug_list_fails", AREA,
              "a bug list with neither rows nor a 'no defects found' statement is a violation",
              not result["ok"] and "neither" in _violations(result), _violations(result))

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        support.patch_report(project, "**Conditional release.**", "**Release not recommended.**")
        result = check_report(project / "TEST_REPORT.md", strict=True)
        check("check.negative_verdict_accepted", AREA,
              "a 'release not recommended' verdict is a valid answer, not a violation",
              result["ok"] and result["verdict"] == "release not recommended",
              f"ok={result['ok']} verdict={result['verdict']!r} {_violations(result)}")

    with support.temp_project() as project:
        support.copy_fixture_project(project)
        passing = _cli(project, "check", "TEST_REPORT.md")
        stdout = passing.stdout.decode("utf-8", errors="replace")
        check("check.cli_exit_zero_on_pass", AREA, "the command line exits 0 for a report that passes",
              passing.returncode == 0 and "PASS" in stdout,
              f"exit {passing.returncode}: {stdout.strip().splitlines()[-1] if stdout.strip() else ''}")
        support.patch_report(project, "**Conditional release.**", "**Release recommended.**")
        failing = _cli(project, "check", "TEST_REPORT.md", "--json")
        payload = failing.stdout.decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(payload)
        except ValueError:
            parsed = None
        check("check.cli_exit_one_on_fail", AREA,
              "the command line exits 1 and prints JSON when the contract fails",
              failing.returncode == 1 and parsed is not None and parsed["ok"] is False,
              f"exit {failing.returncode}, json parsed: {parsed is not None}")
