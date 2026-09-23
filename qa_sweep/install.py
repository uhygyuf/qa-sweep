"""Install the sweep prompt and the suite scaffold into a target project."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import detect as detect_module

DATA = Path(__file__).resolve().parent / "data"
PROMPT_FILES = {"master": "prompts/release-readiness.md", "quick": "prompts/quick-audit.md"}
SUITE_FILES = [("qa_lib.py", "templates/qa_lib.py"), ("qa_suite.py", "templates/qa_suite_stub.py")]
AGENT_MARK_START = "<!-- qa-sweep:begin -->"
AGENT_MARK_END = "<!-- qa-sweep:end -->"
PLACEHOLDERS = {
    "{{PROJECT_NAME}}", "{{STACKS}}", "{{GATES}}", "{{RISKS}}", "{{SCOPE_NOTES}}",
    "{{SUITE_PATH}}", "{{RESULTS_PATH}}",
}


def read_data(relative: str) -> str:
    path = DATA / relative
    return path.read_text(encoding="utf-8")


def _gate_block(info: dict) -> str:
    if not info["gates"]:
        return ("No gate commands were detected. Write them by hand before running anything: the "
                "install, build, lint, type check and test command for this project.")
    lines = []
    for gate in info["gates"]:
        optional = " (optional, run it if the tool is installed)" if gate.get("optional") else ""
        lines.append(f"- {gate['name']}: `{gate['command']}`{optional}  [from {gate['why']}]")
    return "\n".join(lines)


def _risk_block(info: dict) -> str:
    if not info["risks"]:
        return ("No high risk module was inferred from the tree. Confirm this by reading the code: "
                "auth, permissions, payments, data writes and file handling are the usual places a "
                "sweep finds a release blocker.")
    lines = []
    for risk in info["risks"]:
        lines.append(f"- {risk['id']}: {risk['label']}. Evidence: {'; '.join(risk['evidence'])}")
    return "\n".join(lines)


def _note_block(info: dict) -> str:
    if not info["notes"]:
        return "- None recorded by the installer."
    return "\n".join(f"- {note}" for note in info["notes"])


def render_prompt(template: str, info: dict, suite_path: str, results_path: str) -> str:
    replacements = {
        "{{PROJECT_NAME}}": info["name"],
        "{{STACKS}}": ", ".join(info["stacks"]) if info["stacks"] else "not detected",
        "{{GATES}}": _gate_block(info),
        "{{RISKS}}": _risk_block(info),
        "{{SCOPE_NOTES}}": _note_block(info),
        "{{SUITE_PATH}}": suite_path,
        "{{RESULTS_PATH}}": results_path,
    }
    rendered = template
    for token, value in replacements.items():
        rendered = rendered.replace(token, value)
    return rendered


def _write(path: Path, content: str, force: bool, dry_run: bool, report: dict):
    if path.exists() and not force:
        existing = path.read_text(encoding="utf-8", errors="replace")
        if existing == content:
            report["unchanged"].append(str(path))
        else:
            report["skipped"].append(str(path) + " (exists, use --force to replace)")
        return
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    report["written"].append(str(path))


def _append_agents_block(path: Path, block: str, dry_run: bool, report: dict):
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    pattern = re.compile(re.escape(AGENT_MARK_START) + r".*?" + re.escape(AGENT_MARK_END) + r"\n?",
                         re.S)
    if pattern.search(existing):
        updated = pattern.sub(block + "\n", existing)
        action = "updated"
    else:
        separator = "" if not existing or existing.endswith("\n") else "\n"
        updated = existing + separator + block + "\n"
        action = "written"
    if updated == existing:
        report["unchanged"].append(str(path))
        return
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8", newline="\n")
    report.setdefault(action, []).append(str(path))


def _agents_block(info: dict, suite_path: str) -> str:
    return "\n".join([
        AGENT_MARK_START,
        "## Release-readiness QA sweep",
        "",
        "Before a release, run the QA sweep prompt in `.qa-sweep/prompt.md`: recon and report the",
        f"commands first, then run the project gates, then the suite in `{suite_path}`, and finish with",
        "`TEST_REPORT.md` in the A to G shape.",
        "",
        f"Check the report before trusting it: `qa-sweep check TEST_REPORT.md`.",
        AGENT_MARK_END,
    ])


def install(target, agents=("claude", "cursor", "agents"), with_suite=True, force=False,
            dry_run=False) -> dict:
    """Write the prompt pack and suite scaffold into target. Returns a report of paths touched."""
    target = Path(target).resolve()
    if not target.exists():
        raise FileNotFoundError(f"target does not exist: {target}")
    if not target.is_dir():
        raise NotADirectoryError(f"target is not a directory: {target}")

    info = detect_module.detect(target)
    suite_path = "tests/qa_suite.py"
    results_path = "tests/qa-results.json"
    report = {"target": str(target), "dry_run": bool(dry_run), "written": [], "unchanged": [],
              "skipped": [], "updated": [], "stacks": info["stacks"], "gates": len(info["gates"])}

    master = render_prompt(read_data(PROMPT_FILES["master"]), info, suite_path, results_path)
    quick = render_prompt(read_data(PROMPT_FILES["quick"]), info, suite_path, results_path)
    stack_json = json.dumps(info, indent=2, ensure_ascii=False) + "\n"

    _write(target / ".qa-sweep" / "prompt.md", master, force, dry_run, report)
    _write(target / ".qa-sweep" / "quick-audit.md", quick, force, dry_run, report)
    _write(target / ".qa-sweep" / "stack.json", stack_json, force, dry_run, report)

    if "claude" in agents:
        _write(target / ".claude" / "commands" / "qa-sweep.md",
               "---\ndescription: Run the release-readiness QA sweep and write TEST_REPORT.md\n---\n\n"
               + master, force, dry_run, report)
    if "cursor" in agents:
        _write(target / ".cursor" / "rules" / "qa-sweep.mdc",
               "---\ndescription: Release-readiness QA sweep\nalwaysApply: false\n---\n\n" + master,
               force, dry_run, report)
    if "agents" in agents:
        _append_agents_block(target / "AGENTS.md", _agents_block(info, suite_path), dry_run, report)

    if with_suite:
        tests_dir = "tests/" if (target / "tests").exists() else "tests/"
        for name, relative in SUITE_FILES:
            _write(target / tests_dir / name, read_data(relative), force, dry_run, report)

    report["written"].sort()
    report["skipped"].sort()
    report["unchanged"].sort()
    return report


def render_install(report: dict) -> str:
    lines = [f"target   : {report['target']}",
             f"stacks   : {', '.join(report['stacks']) if report['stacks'] else 'none detected'}",
             f"gates    : {report['gates']} command(s) written into the prompt"]
    if report["dry_run"]:
        lines.append("dry run  : nothing was written")
    for label, key in (("written", "written"), ("updated", "updated"), ("unchanged", "unchanged"),
                       ("skipped", "skipped")):
        if report.get(key):
            lines.append(f"{label}:")
            lines.extend(f"  {path}" for path in report[key])
    if report.get("skipped"):
        lines.append("")
        lines.append("Existing files were left alone. Re-run with --force to replace them.")
    lines.append("")
    lines.append("Next: open .qa-sweep/prompt.md in your coding agent, or run the suite directly with "
                 "the test command detected for this project.")
    return "\n".join(lines)
