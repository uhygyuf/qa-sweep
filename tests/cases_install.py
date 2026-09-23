"""Installer checks: what lands on disk, what is left alone, and that the scaffold actually runs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import support
from qa_sweep import install as install_module

AREA = "installer"
EXPECTED_FILES = [
    ".qa-sweep/prompt.md",
    ".qa-sweep/quick-audit.md",
    ".qa-sweep/stack.json",
    ".claude/commands/qa-sweep.md",
    ".cursor/rules/qa-sweep.mdc",
    "AGENTS.md",
    "tests/qa_lib.py",
    "tests/qa_suite.py",
]


def _tree(root: Path):
    return sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())


def run(check):
    with support.temp_project() as project:
        support.node_project(project)
        report = install_module.install(project)
        written = {str(Path(path).relative_to(project).as_posix()) for path in report["written"]}
        check("install.writes_expected_files", AREA, "every adapter and scaffold file is written",
              all(name in written for name in EXPECTED_FILES),
              f"written: {sorted(written)}")
        prompt = (project / ".qa-sweep" / "prompt.md").read_text(encoding="utf-8")
        check("install.prompt_has_no_placeholders", AREA, "no template placeholder survives rendering",
              "{{" not in prompt and "}}" not in prompt,
              "found: " + ", ".join(sorted({part.split("}}")[0] + "}}" for part in prompt.split("{{")[1:]})))
        check("install.prompt_has_gate_commands", AREA, "the detected test command is quoted in the prompt",
              "npm run test" in prompt, "expected 'npm run test' from package.json scripts.test")
        check("install.prompt_names_project", AREA, "the prompt names the project it was written for",
              "demo-api" in prompt, "expected the package.json name in the project facts block")
        check("install.prompt_carries_risks", AREA, "the prompt carries the risky modules with evidence",
              "authentication or session code" in prompt, "expected the auth risk line")

        stack = json.loads((project / ".qa-sweep" / "stack.json").read_text(encoding="utf-8"))
        check("install.stack_json_valid", AREA, "the detection result is stored next to the prompt",
              stack["stacks"] == ["node"] and stack["gates"], f"stacks: {stack['stacks']}")

        before = (project / ".qa-sweep" / "prompt.md").read_bytes()
        second = install_module.install(project)
        after = (project / ".qa-sweep" / "prompt.md").read_bytes()
        check("install.idempotent", AREA, "a second install writes nothing new and changes nothing",
              second["written"] == [] and second["unchanged"] and before == after,
              f"written: {second['written']}, unchanged: {len(second['unchanged'])} file(s)")

        agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        check("install.agents_block_once", AREA, "the AGENTS.md block is not duplicated by a second install",
              agents.count(install_module.AGENT_MARK_START) == 1,
              f"marker count: {agents.count(install_module.AGENT_MARK_START)}")

        suite = project / "tests" / "qa_suite.py"
        run_result = subprocess.run([sys.executable, str(suite)], cwd=str(project),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        results_path = project / "tests" / "qa-results.json"
        payload = {}
        if results_path.is_file():
            payload = json.loads(results_path.read_text(encoding="utf-8"))
        check("install.scaffold_runs", AREA, "the scaffolded suite runs and exits 0",
              run_result.returncode == 0, f"exit {run_result.returncode}: "
              + run_result.stdout.decode("utf-8", errors="replace").strip()[-300:])
        check("install.scaffold_writes_results", AREA, "the scaffolded suite writes its results file",
              results_path.is_file() and payload.get("totals", {}).get("checks", 0) >= 4,
              f"totals: {payload.get('totals')}")
        check("install.scaffold_marks_skips", AREA,
              "placeholders are recorded as skipped, never as passing checks",
              payload.get("totals", {}).get("skipped", 0) >= 1
              and all(entry["ok"] is not None for entry in payload.get("results", [])
                      if not entry.get("skipped")),
              f"skipped: {payload.get('totals', {}).get('skipped')}")

    with support.temp_project() as project:
        support.node_project(project)
        support.write(project, "tests/qa_suite.py", "# the project's own suite\n")
        report = install_module.install(project)
        kept = (project / "tests" / "qa_suite.py").read_text(encoding="utf-8")
        check("install.preserves_existing_suite", AREA,
              "an existing suite is left byte for byte alone without --force",
              kept == "# the project's own suite\n"
              and any("qa_suite.py" in path for path in report["skipped"]),
              f"content: {kept!r}, skipped: {report['skipped']}")
        forced = install_module.install(project, force=True)
        replaced = (project / "tests" / "qa_suite.py").read_text(encoding="utf-8")
        check("install.force_replaces", AREA, "--force replaces the file it would otherwise keep",
              "qa-sweep" in replaced and any("qa_suite.py" in path for path in forced["written"]),
              f"first line: {replaced.splitlines()[0]!r}")

    with support.temp_project() as project:
        support.python_project(project)
        before = _tree(project)
        report = install_module.install(project, dry_run=True)
        check("install.dry_run_writes_nothing", AREA, "--dry-run reports work but touches no file",
              _tree(project) == before and report["written"] and report["dry_run"],
              f"files after: {len(_tree(project))}, reported: {len(report['written'])}")

    with support.temp_project() as project:
        support.empty_project(project)
        report = install_module.install(project)
        prompt = (project / ".qa-sweep" / "prompt.md").read_text(encoding="utf-8")
        check("install.unknown_stack_is_honest", AREA,
              "an unrecognised project still gets a prompt that says no gate was detected",
              "No gate commands were detected" in prompt and report["stacks"] == [],
              f"stacks: {report['stacks']}")

    with support.temp_project() as project:
        missing = project / "does-not-exist"
        raised = ""
        try:
            install_module.install(missing)
        except FileNotFoundError as exc:
            raised = exc.__class__.__name__
        check("install.refuses_missing_target", AREA, "a target that does not exist is refused",
              raised == "FileNotFoundError", f"raised: {raised or 'nothing'}")
