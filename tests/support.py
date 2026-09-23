"""Shared fixtures for the qa-sweep self-tests.

Every project used by a test is fabricated on disk in a temporary directory, so the tool meets the
real thing: real manifests, real file trees, real JSON written to disk.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"


@contextmanager
def temp_project():
    """A real directory on disk, removed at the end of the block."""
    directory = Path(tempfile.mkdtemp(prefix="qa-sweep-test-")).resolve()
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def write(root: Path, relative: str, text: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    return path


def write_json(root: Path, relative: str, data) -> Path:
    return write(root, relative, json.dumps(data, indent=2))


def node_project(root: Path, typescript: bool = False, package_manager: str = "npm",
                 secrets: bool = False) -> Path:
    scripts = {"build": "tsc -p .", "test": "jest", "lint": "eslint ."}
    write_json(root, "package.json", {
        "name": "demo-api",
        "version": "1.0.0",
        "scripts": scripts,
        "dependencies": {"express": "^4.19.0", "jsonwebtoken": "^9.0.0", "multer": "^1.4.5"},
        "devDependencies": {"jest": "^29.7.0", "eslint": "^9.0.0"},
    })
    if package_manager == "npm":
        write_json(root, "package-lock.json", {"lockfileVersion": 3})
    elif package_manager == "pnpm":
        write(root, "pnpm-lock.yaml", "lockfileVersion: '9.0'\n")
    elif package_manager == "yarn":
        write(root, "yarn.lock", "# yarn lockfile v1\n")
    if typescript:
        write_json(root, "tsconfig.json", {"compilerOptions": {"strict": True}})
    write(root, "src/auth/login.js", "module.exports = function login() {};\n")
    write(root, "src/uploads/handler.js", "module.exports = function upload() {};\n")
    write(root, "prisma/schema.prisma", "model User { id Int @id }\n")
    if secrets:
        write(root, ".env", "DATABASE_URL=postgres://localhost/demo\n")
    write(root, "README.md", "\n".join([
        "# demo-api",
        "",
        "A small HTTP API used by the qa-sweep self-tests. It stores documents and users, and it needs",
        "a PostgreSQL database.",
        "",
        "## Run",
        "",
        "1. copy `.env.example` to `.env` and fill in the connection string",
        "2. `npm ci`",
        "3. `npm run build`",
        "4. `npm run test`",
        "5. `npm start`, the API answers on port 3000",
        "",
        "## Endpoints",
        "",
        "- `POST /api/documents` creates a document",
        "- `GET /api/documents/:id` reads one document",
        "- `POST /api/session` signs a user in",
        "",
    ]) + "\n")
    return root


def python_project(root: Path) -> Path:
    write(root, "pyproject.toml", "\n".join([
        "[project]",
        'name = "demo-pkg"',
        'version = "0.1.0"',
        'dependencies = ["requests>=2.31", "sqlalchemy>=2.0"]',
        "",
        "[tool.pytest.ini_options]",
        'testpaths = ["tests"]',
        "",
        "[tool.ruff]",
        "line-length = 100",
        "",
        "[tool.mypy]",
        "strict = true",
    ]) + "\n")
    write(root, "src/app/models.py", "class User:\n    pass\n")
    write(root, "tests/test_app.py", "def test_ok():\n    assert True\n")
    write(root, "README.md", "# demo-pkg\n")
    return root


def dotnet_project(root: Path) -> Path:
    write(root, "Demo.sln", "Microsoft Visual Studio Solution File\n")
    write(root, "src/Demo/Demo.csproj", "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n")
    write(root, "src/Demo/Program.cs", "class Program { static void Main() {} }\n")
    write(root, "README.md", "# demo dotnet\n")
    return root


def go_project(root: Path) -> Path:
    write(root, "go.mod", "module example.com/demo\n\ngo 1.22\n")
    write(root, "main.go", "package main\n\nfunc main() {}\n")
    return root


def rust_project(root: Path) -> Path:
    write(root, "Cargo.toml", "[package]\nname = \"demo\"\nversion = \"0.1.0\"\n")
    write(root, "src/main.rs", "fn main() {}\n")
    return root


def static_project(root: Path) -> Path:
    write(root, "index.html", "<!doctype html><html><body><h1>demo</h1></body></html>\n")
    write(root, "about.html", "<!doctype html><html><body><h1>about</h1></body></html>\n")
    return root


def empty_project(root: Path) -> Path:
    write(root, "notes.txt", "nothing to detect here\n")
    return root


def copy_fixture_project(destination: Path) -> Path:
    """Copy the sample report tree into destination, so a test can mutate it."""
    source = FIXTURES / "project"
    shutil.copytree(source, destination, dirs_exist_ok=True)
    return destination


def patch_report(project: Path, old: str, new: str, relative: str = "TEST_REPORT.md") -> Path:
    path = project / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"fixture report does not contain the text to replace: {old!r}")
    path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
    return path


def replace_section_body(project: Path, letter: str, new_body: str, relative: str = "TEST_REPORT.md"):
    """Replace the body of one report section, keeping its heading."""
    path = project / relative
    lines = path.read_text(encoding="utf-8").splitlines()
    heading = re.compile(r"^#{1,6}\s*" + letter + r"[.):]")
    any_heading = re.compile(r"^#{1,6}\s*[A-Z][.):]")
    start = next((index for index, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise AssertionError(f"fixture report has no section {letter}")
    end = next((index for index in range(start + 1, len(lines)) if any_heading.match(lines[index])),
               len(lines))
    updated = lines[:start + 1] + ["", new_body, ""] + lines[end:]
    path.write_bytes(("\n".join(updated) + "\n").encode("utf-8"))
    return path


def read_results(project: Path, relative: str = "tests/qa-results.json") -> dict:
    return json.loads((project / relative).read_text(encoding="utf-8"))
