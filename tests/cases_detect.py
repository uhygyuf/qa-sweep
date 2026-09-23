"""Detection checks: the gates and risks printed for a project must match the files on disk."""

from __future__ import annotations

import json

import support
from qa_sweep import detect as detect_module

AREA = "detection"


def _gates(info):
    return {gate["name"]: gate["command"] for gate in info["gates"]}


def run(check):
    with support.temp_project() as project:
        support.node_project(project)
        info = detect_module.detect(project)
        gates = _gates(info)
        check("detect.node_stacks", AREA, "a node project is reported as a node project",
              info["stacks"] == ["node"], f"stacks: {info['stacks']}")
        check("detect.node_install_uses_lockfile", AREA, "a lockfile selects npm ci",
              gates.get("install") == "npm ci", f"install: {gates.get('install')!r}")
        check("detect.node_scripts", AREA, "package.json scripts become the build and test gates",
              gates.get("build") == "npm run build" and gates.get("test") == "npm run test",
              f"build: {gates.get('build')!r}, test: {gates.get('test')!r}")
        check("detect.node_no_typescript_gate", AREA, "no tsconfig means no type check gate",
              "type check" not in gates, f"gates: {sorted(gates)}")

    with support.temp_project() as project:
        support.node_project(project, typescript=True, package_manager="pnpm")
        gates = _gates(detect_module.detect(project))
        check("detect.pnpm_lockfile", AREA, "a pnpm lockfile selects pnpm with a frozen install",
              gates.get("install") == "pnpm install --frozen-lockfile", f"install: {gates.get('install')!r}")
        check("detect.typescript_typecheck", AREA, "tsconfig.json adds a type check gate",
              gates.get("type check") == "pnpm exec tsc --noEmit", f"type check: {gates.get('type check')!r}")

    with support.temp_project() as project:
        support.write_json(project, "package.json", {"name": "x", "scripts": {}})
        gates = _gates(detect_module.detect(project))
        check("detect.no_lockfile", AREA, "a project without a lockfile gets npm install",
              gates.get("install") == "npm install", f"install: {gates.get('install')!r}")

    with support.temp_project() as project:
        support.python_project(project)
        info = detect_module.detect(project)
        gates = _gates(info)
        check("detect.python_stack", AREA, "a pyproject project is reported as python",
              info["stacks"] == ["python"], f"stacks: {info['stacks']}")
        check("detect.python_pytest", AREA, "pytest is the test gate when it is configured",
              gates.get("test") == "python -m pytest -q", f"test: {gates.get('test')!r}")
        check("detect.python_ruff_mypy", AREA, "declared ruff and mypy become lint and type check gates",
              gates.get("lint") == "python -m ruff check ." and gates.get("type check") == "python -m mypy .",
              f"lint: {gates.get('lint')!r}, type check: {gates.get('type check')!r}")

    with support.temp_project() as project:
        support.write(project, "requirements.txt", "flask\nrequests\n")
        support.write(project, "test_app.py", "def test_ok():\n    assert True\n")
        gates = _gates(detect_module.detect(project))
        check("detect.python_without_pytest", AREA,
              "a python project with tests but no pytest falls back to unittest discovery",
              gates.get("test") == "python -m unittest discover -s tests -v", f"test: {gates.get('test')!r}")

    with support.temp_project() as project:
        support.dotnet_project(project)
        gates = _gates(detect_module.detect(project))
        check("detect.dotnet_gates", AREA, "a solution file yields the dotnet gates",
              gates.get("build") == "dotnet build -c Release"
              and gates.get("format check") == "dotnet format --verify-no-changes",
              f"gates: {sorted(gates)}")

    with support.temp_project() as project:
        support.go_project(project)
        gates = _gates(detect_module.detect(project))
        check("detect.go_gates", AREA, "go.mod yields build, vet and test gates",
              gates.get("test") == "go test ./..." and gates.get("vet") == "go vet ./...",
              f"gates: {sorted(gates)}")

    with support.temp_project() as project:
        support.rust_project(project)
        gates = _gates(detect_module.detect(project))
        check("detect.rust_gates", AREA, "Cargo.toml yields build, test and fmt gates",
              gates.get("test") == "cargo test" and gates.get("format check") == "cargo fmt --check",
              f"gates: {sorted(gates)}")

    with support.temp_project() as project:
        support.static_project(project)
        info = detect_module.detect(project)
        check("detect.static_site", AREA, "an html only project is reported as a static site with a note",
              info["stacks"] == ["static"] and any("static site" in note for note in info["notes"]),
              f"stacks: {info['stacks']}, notes: {info['notes']}")

    with support.temp_project() as project:
        support.empty_project(project)
        info = detect_module.detect(project)
        check("detect.empty_project_is_honest", AREA,
              "an unrecognised directory reports no stack instead of inventing gates",
              info["stacks"] == [] and info["gates"] == [] and info["notes"],
              f"stacks: {info['stacks']}, gates: {info['gates']}, notes: {info['notes']}")

    with support.temp_project() as project:
        support.node_project(project, secrets=True)
        info = detect_module.detect(project)
        ids = {risk["id"] for risk in info["risks"]}
        expected = {"auth", "database", "file_upload", "secrets"}
        check("detect.risks_from_tree", AREA, "auth, database, upload and secret risks are found in the tree",
              expected <= ids, f"risks: {sorted(ids)}")
        check("detect.risks_have_evidence", AREA, "every risk carries the file that produced it",
              all(risk["evidence"] for risk in info["risks"]),
              "; ".join(f"{risk['id']}: {risk['evidence']}" for risk in info["risks"]))
        check("detect.risks_frontend_absent", AREA, "a backend only project reports no frontend risk",
              "frontend" not in ids, f"risks: {sorted(ids)}")

    with support.temp_project() as project:
        support.node_project(project)
        payload = json.loads(detect_module.detect_json(project))
        check("detect.json_output", AREA, "the JSON output parses and carries the same stacks",
              payload["stacks"] == ["node"] and "gates" in payload, f"keys: {sorted(payload)}")
