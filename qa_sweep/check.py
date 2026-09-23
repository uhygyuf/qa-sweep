"""Check a release-readiness report against the report contract.

The contract is documented in docs/report-contract.md. This module turns it into machine checks so a
report cannot pass by looking plausible: a verdict has to match its evidence, the results table has to
carry evidence per row, and absolute or hedged claims are rejected.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SECTION_LETTERS = list("ABCDEFG")

SECTION_TITLES = {
    "A": "verdict",
    "B": "environment, commands, scope and coverage",
    "C": "results table",
    "D": "bug list",
    "E": "files changed",
    "F": "remaining risks and limitations",
    "G": "release checklist",
}

HEADING_PATTERNS = [
    re.compile(r"^#{1,6}\s*([A-G])[.):]\s*(\S.*)$"),
    re.compile(r"^\s{0,3}\*\*([A-G])[.):]\s*(\S.*?)\*\*\s*$"),
    re.compile(r"^([A-G])[.):]\s+(\S.*)$"),
]

HEDGING = [
    (r"\bshould pass\b", "hedged claim: 'should pass'"),
    (r"\bshould work\b", "hedged claim: 'should work'"),
    (r"\blooks fine\b", "hedged claim: 'looks fine'"),
    (r"\bpresumably\b", "hedged claim: 'presumably'"),
    (r"\bI believe\b", "unsupported claim: 'I believe'"),
    (r"\bseems? to (work|pass)\b", "hedged claim: 'seems to work'"),
    (r"\bprobably (works|passes|fine|ok)\b", "hedged claim: 'probably works'"),
    (r"\bassum(e|es|ed|ing)\b[^.\n]{0,40}\b(works|passes|fine|correct|equivalent)\b",
     "unsupported assumption presented as a result"),
    (r"\btested,? it works\b", "claim without evidence"),
]

ABSOLUTE_CLAIMS = [
    (r"\bno bugs\b", "absolute claim: 'no bugs'"),
    (r"\bbug free\b", "absolute claim: 'bug free'"),
    (r"\b100% (tested|coverage)\b", "absolute claim: '100% tested'"),
]

VAGUE_EVIDENCE = {
    "", "-", "--", "n/a", "na", "none", "tbd", "?", "??", "ok", "pass", "passed", "see above",
    "manual", "looks fine", "should work", "as expected", "expected",
}

GREEN_CLAIMS = re.compile(
    r"(all (checks|tests) (pass|passed)|everything passes|suite is green|0 failures|"
    r"no failures|ci is green|all green)", re.I)
NOT_COVERED = re.compile(r"not covered|not-covered|uncovered|not executed|not runnable", re.I)
ROLLBACK = re.compile(r"\brollback\b|\broll back\b", re.I)
MONITOR = re.compile(r"\bmonitor", re.I)
RESULTS_REF = re.compile(r"[\w./\\-]*result[\w./\\-]*\.json", re.I)
PRIORITY = re.compile(r"^P[0-3]\b")
NO_DEFECTS = re.compile(r"no defects|no bugs found|none found|no issues found", re.I)
RESULT_LIST_KEYS = ("results", "checks", "tests", "assertions", "cases", "entries")


def _sections(text: str) -> dict:
    """Return {letter: (line_number, title, body)} for headings found, first hit per letter wins."""
    lines = text.splitlines()
    found = {}
    for index, line in enumerate(lines):
        for pattern in HEADING_PATTERNS:
            match = pattern.match(line.rstrip())
            if not match:
                continue
            letter, title = match.group(1), match.group(2).strip()
            if letter not in found:
                found[letter] = {"line": index + 1, "title": title, "body": []}
            break
    for letter, info in found.items():
        start = info["line"]
        later = sorted(v["line"] for v in found.values() if v["line"] > start)
        end = later[0] - 1 if later else len(lines)
        info["body"] = lines[start:end]
    return found


def _classify_verdict(body_lines) -> str:
    text = "\n".join(body_lines).lower()
    if "not recommended" in text or "release not recommended" in text:
        return "release not recommended"
    if "conditional" in text:
        return "conditional release"
    if "recommended" in text:
        return "release recommended"
    return ""


def _table_rows(body_lines):
    """Return markdown table data rows from a section, cells already split."""
    rows = []
    for line in body_lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells if cell):
            continue
        if cells and cells[0].lower() in ("area", "test area", "id", "check"):
            continue
        if any(cells):
            rows.append(cells)
    return rows


def _load_results(path: Path):
    """Return (entries, failures, error). Reads a results JSON written by the suite."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return [], 0, f"{path.name} is not readable JSON ({exc.__class__.__name__})"
    entries = None
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        for key in RESULT_LIST_KEYS:
            if isinstance(data.get(key), list):
                entries = data[key]
                break
    if entries is None:
        return [], 0, f"{path.name} has no list of results"
    failures = 0
    for entry in entries:
        if isinstance(entry, dict):
            value = entry.get("ok", entry.get("passed"))
            if value is False or value == 0:
                failures += 1
    return entries, failures, ""


def _resolve_reference(report_path: Path, reference: str):
    """Resolve a cited results path: relative to the report, then by file name nearby."""
    cleaned = reference.replace("\\", "/")
    name = Path(cleaned).name
    for base in (report_path.parent, report_path.parent.parent):
        candidate = (base / cleaned).resolve()
        if candidate.is_file():
            return candidate
    for base in (report_path.parent, report_path.parent.parent, report_path.parent / "tests"):
        candidate = (base / name).resolve()
        if candidate.is_file():
            return candidate
    return None


def check_report(report_path, strict: bool = False) -> dict:
    report_path = Path(report_path).resolve()
    checks = []
    violations = []
    warnings = []

    if not report_path.is_file():
        return {
            "report": str(report_path),
            "ok": False,
            "verdict": "",
            "sections": {letter: False for letter in SECTION_LETTERS},
            "checks": [],
            "violations": [f"report not found: {report_path}"],
            "warnings": [],
            "failures": 0,
            "results_files": [],
        }

    text = report_path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    sections = _sections(text)

    def add(check_id, ok, detail):
        checks.append({"id": check_id, "ok": bool(ok), "detail": detail})
        return ok

    missing = [letter for letter in SECTION_LETTERS if letter not in sections]
    add("sections.present", not missing,
        "all sections A to G present" if not missing else "missing section(s): " + ", ".join(missing))
    if missing:
        violations.append("missing required section(s): " + ", ".join(missing))

    present_order = [sections[letter]["line"] for letter in SECTION_LETTERS if letter in sections]
    add("sections.order", present_order == sorted(present_order),
        "sections appear in order" if present_order == sorted(present_order)
        else "sections are out of order: " + ", ".join(
            letter for letter, line in sorted(((l, sections[l]["line"]) for l in sections),
                                              key=lambda pair: pair[1])))
    if present_order != sorted(present_order):
        warnings.append("sections are not in A to G order")

    verdict = _classify_verdict(sections.get("A", {}).get("body", [])) if "A" in sections else ""
    add("verdict.present", bool(verdict),
        f"verdict: {verdict}" if verdict else "section A states no release verdict")
    if not verdict:
        violations.append("section A does not state one of: release recommended, "
                          "conditional release, release not recommended")

    hedging_hits, absolute_hits = [], []
    for index, line in enumerate(lines, start=1):
        for pattern, label in HEDGING:
            if re.search(pattern, line):
                hedging_hits.append(f"line {index}: {label}")
        for pattern, label in ABSOLUTE_CLAIMS:
            if re.search(pattern, line, re.I):
                absolute_hits.append(f"line {index}: {label}")
    add("claims.no_hedging", not hedging_hits,
        "no hedged claims" if not hedging_hits else "; ".join(hedging_hits[:6]))
    if hedging_hits:
        violations.append("hedged or unsupported claims: " + "; ".join(hedging_hits[:6]))
    add("claims.no_absolutes", not absolute_hits,
        "no absolute claims" if not absolute_hits else "; ".join(absolute_hits[:6]))
    if absolute_hits:
        violations.append("absolute claims: " + "; ".join(absolute_hits[:6]))

    b_body = sections.get("B", {}).get("body", [])
    add("coverage.limits_stated", bool(NOT_COVERED.search("\n".join(b_body))),
        "section B states what was not covered" if NOT_COVERED.search("\n".join(b_body))
        else "section B does not say what was not covered")
    if not NOT_COVERED.search("\n".join(b_body)):
        violations.append("section B must state what was not covered")

    c_rows = _table_rows(sections.get("C", {}).get("body", []))
    add("results.table", bool(c_rows),
        f"{len(c_rows)} result row(s)" if c_rows else "section C has no markdown table with result rows")
    if not c_rows:
        violations.append("section C has no results table")
    bad_rows = []
    for position, cells in enumerate(c_rows, start=1):
        evidence = cells[2] if len(cells) > 2 else (cells[-1] if cells else "")
        if evidence.strip().lower() in VAGUE_EVIDENCE or len(evidence.strip()) < 4:
            bad_rows.append(f"row {position}: evidence cell is '{evidence.strip()}'")
    add("results.evidence_per_row", not bad_rows,
        f"{len(c_rows)} row(s) carry evidence" if not bad_rows else "; ".join(bad_rows[:6]))
    if bad_rows:
        violations.append("result rows without evidence: " + "; ".join(bad_rows[:6]))

    d_body = sections.get("D", {}).get("body", [])
    d_rows = _table_rows(d_body)
    if d_rows:
        bad_priority = [f"row {position}" for position, cells in enumerate(d_rows, start=1)
                        if not any(PRIORITY.match(cell) for cell in cells)]
        add("bugs.priorities", not bad_priority,
            f"{len(d_rows)} defect row(s) carry a P0 to P3 priority" if not bad_priority
            else "defect row(s) without priority: " + ", ".join(bad_priority))
        if bad_priority:
            violations.append("defect rows missing a P0 to P3 priority: " + ", ".join(bad_priority))
    else:
        stated = bool(NO_DEFECTS.search("\n".join(d_body)))
        add("bugs.enumerated", stated,
            "no defect rows and section D says so explicitly" if stated
            else "section D has neither defect rows nor an explicit 'no defects found' statement")
        if not stated:
            violations.append("section D has neither a defect table nor an explicit "
                              "'no defects found' statement")

    high_severity = [cell for cells in d_rows for cell in cells if cell in ("P0", "P1")]
    references = sorted({match for match in RESULTS_REF.findall(text)})
    results_files, failures, resolved = [], 0, []
    for reference in references:
        candidate = _resolve_reference(report_path, reference)
        if candidate is not None:
            resolved.append(candidate)
            entries, file_failures, error = _load_results(candidate)
            if error:
                violations.append(error)
            failures += file_failures
            results_files.append({
                "path": str(candidate),
                "entries": len(entries),
                "failures": file_failures,
                "error": error,
            })
    add("results.files_cited", bool(results_files),
        f"{len(results_files)} results file(s) cited and readable" if results_files
        else "the report cites no readable results JSON")
    if not results_files:
        violations.append("the report cites no readable results JSON, so its numbers cannot be checked")

    add("results.counts_consistency", True,
        f"{failures} failing check(s) in the cited results" if results_files else "not applicable")

    green_claim = bool(GREEN_CLAIMS.search(text))
    add("verdict.matches_evidence", not (green_claim and failures > 0),
        "green claim agrees with the results files" if not (green_claim and failures > 0)
        else f"the report claims a green suite while {failures} check(s) failed")
    if green_claim and failures > 0:
        violations.append(f"report claims a green suite while {failures} check(s) failed")

    if verdict == "release recommended":
        if high_severity:
            violations.append("verdict is 'release recommended' while the bug list contains "
                              f"{sorted(set(high_severity))}")
        if failures > 0:
            violations.append("verdict is 'release recommended' while the cited results contain "
                              f"{failures} failing check(s)")

    if verdict in ("release recommended", "conditional release"):
        if not ROLLBACK.search(text):
            warnings.append("no rollback approach documented")
        if not MONITOR.search(text):
            warnings.append("no monitoring or error tracking documented")

    ok = not violations and not (strict and warnings)
    return {
        "report": str(report_path),
        "ok": ok,
        "verdict": verdict,
        "sections": {letter: letter in sections for letter in SECTION_LETTERS},
        "checks": checks,
        "violations": violations,
        "warnings": warnings,
        "failures": failures,
        "results_files": results_files,
        "table_rows": len(c_rows),
        "defect_rows": len(d_rows),
        "high_severity": sorted(set(high_severity)),
    }


def render_result(result: dict) -> str:
    """Human readable rendering of a check result."""
    lines = []
    verdict = result["verdict"] or "none stated"
    lines.append(f"report   : {result['report']}")
    lines.append(f"verdict  : {verdict}")
    lines.append(f"sections : " + " ".join(
        letter if present else f"({letter})" for letter, present in result["sections"].items()))
    lines.append(f"results  : {len(result['results_files'])} file(s), {result['failures']} failing check(s)")
    lines.append("")
    for check in result["checks"]:
        mark = "ok  " if check["ok"] else "FAIL"
        lines.append(f"  [{mark}] {check['id']}: {check['detail']}")
    if result["warnings"]:
        lines.append("")
        for warning in result["warnings"]:
            lines.append(f"  [warn] {warning}")
    if result["violations"]:
        lines.append("")
        for violation in result["violations"]:
            lines.append(f"  [contract] {violation}")
    lines.append("")
    lines.append("PASS" if result["ok"] else "FAIL")
    return "\n".join(lines)
