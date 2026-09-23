"""Detect the stack of a project directory and the exact gate commands for it.

Every gate carries the file that made the tool believe it exists, so a reviewer can falsify it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "dist", "build", "out",
    "target", "bin", "obj", ".next", ".nuxt", ".svelte-kit", ".cache", "__pycache__",
    "vendor", "coverage", ".idea", ".vs", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
MAX_FILES = 6000

# Dependency names that change the risk profile of a project, grouped by what they imply.
RISK_DEPS = {
    "auth": [
        "passport", "jsonwebtoken", "bcrypt", "bcryptjs", "next-auth", "lucia", "jose",
        "flask-login", "django-allauth", "python-jose", "authlib", "spring-security",
        "auth0", "clerk", "supabase", "firebase-admin", "msal",
    ],
    "database": [
        "prisma", "sequelize", "typeorm", "mongoose", "knex", "mysql", "mysql2", "pg",
        "sqlite3", "better-sqlite3", "sqlalchemy", "psycopg", "psycopg2", "django",
        "redis", "ioredis", "kafkajs", "amqplib",
    ],
    "file_upload": ["multer", "formidable", "busboy", "python-multipart", "werkzeug", "shrine"],
    "payments": ["stripe", "paypal", "braintree", "razorpay", "square"],
    "frontend": ["react", "react-dom", "vue", "svelte", "next", "nuxt", "angular", "solid-js"],
    "outbound_http": ["axios", "node-fetch", "got", "undici", "requests", "httpx", "aiohttp"],
    "template_render": ["ejs", "pug", "handlebars", "jinja2", "mustache", "nunjucks"],
    "deserialization": ["js-yaml", "yaml", "pickle", "node-serialize", "xml2js", "lxml"],
}

RISK_LABELS = {
    "auth": "authentication or session code",
    "database": "data store, migrations or ORM",
    "file_upload": "file upload handling",
    "payments": "payment provider integration",
    "frontend": "rendered user interface",
    "outbound_http": "outbound HTTP calls to third parties",
    "template_render": "server side template rendering",
    "deserialization": "parsing of structured input",
}

NAME_HINTS = [
    ("auth", re.compile(r"(^|[_-])(auth|login|session|signin|signup|password|token|jwt|oauth)", re.I)),
    ("database", re.compile(r"(^|[_-])(model|models|migration|migrations|schema|repository|dao)\b", re.I)),
    ("file_upload", re.compile(r"(^|[_-])(upload|uploads|attachment|file_?upload)", re.I)),
    ("payments", re.compile(r"(^|[_-])(payment|checkout|billing|invoice|order)", re.I)),
    ("multi_tenant", re.compile(r"(^|[_-])(tenant|workspace|organisation|organization|account_id)", re.I)),
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json(path: Path) -> dict:
    try:
        data = json.loads(read_text(path))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def walk_files(root: Path, limit: int = MAX_FILES):
    """Return files under root as paths relative to root, skipping vendor and cache trees."""
    found = []
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in SKIP_DIRS or entry.name.startswith(".git"):
                    continue
                stack.append(entry)
            else:
                found.append(entry.relative_to(root))
                if len(found) >= limit:
                    return found
    return found


def _dep(entry, name, source):
    return name if entry is None else entry


def collect_deps(root: Path, files) -> dict:
    """Map dependency name to the manifest that declares it."""
    deps = {}

    def add(names, source):
        for name in names:
            deps.setdefault(name.lower(), source)

    pkg = read_json(root / "package.json")
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        block = pkg.get(key)
        if isinstance(block, dict):
            add(list(block.keys()), "package.json")

    for name in ("requirements.txt", "requirements-dev.txt"):
        path = root / name
        if path.exists():
            add([re.split(r"[=<>!\[; ]", line.strip(), 1)[0]
                 for line in read_text(path).splitlines()
                 if line.strip() and not line.strip().startswith("#")], name)

    pyproject = read_text(root / "pyproject.toml")
    if pyproject:
        add(re.findall(r'^\s*"?([A-Za-z0-9_.\-]+)"?\s*[><=~!\[]', pyproject, re.M), "pyproject.toml")
        add(re.findall(r'"([A-Za-z0-9_.\-]+)\s*[><=~!]', pyproject), "pyproject.toml")

    composer = read_json(root / "composer.json")
    for key in ("require", "require-dev"):
        block = composer.get(key)
        if isinstance(block, dict):
            add(list(block.keys()), "composer.json")

    gemfile = read_text(root / "Gemfile")
    if gemfile:
        add(re.findall(r"^\s*gem\s+['\"]([^'\"]+)", gemfile, re.M), "Gemfile")

    cargo = read_text(root / "Cargo.toml")
    if cargo:
        add(re.findall(r"^\s*([A-Za-z0-9_\-]+)\s*=", cargo, re.M), "Cargo.toml")

    gomod = read_text(root / "go.mod")
    if gomod:
        add(re.findall(r"^\s*([a-z0-9.\-]+\.[a-z]{2,}/[^\s]+)\s", gomod, re.M), "go.mod")

    return deps


def _node_gates(root: Path, files, gates, notes):
    pkg_path = root / "package.json"
    if not pkg_path.exists():
        return False
    pkg = read_json(pkg_path)
    scripts = pkg.get("scripts") if isinstance(pkg.get("scripts"), dict) else {}

    if (root / "pnpm-lock.yaml").exists():
        pm, runner, install = "pnpm", "pnpm", "pnpm install --frozen-lockfile"
    elif (root / "yarn.lock").exists():
        pm, runner, install = "yarn", "yarn", "yarn install --immutable"
    elif (root / "bun.lockb").exists() or (root / "bun.lock").exists():
        pm, runner, install = "bun", "bun run", "bun install --frozen-lockfile"
    else:
        pm, runner = "npm", "npm run"
        install = "npm ci" if (root / "package-lock.json").exists() else "npm install"
    gates.append({"name": "install", "command": install, "why": "package.json"})

    for script, label in (("build", "build"), ("lint", "lint"), ("typecheck", "type check"),
                          ("type-check", "type check"), ("format:check", "format check"),
                          ("test", "test"), ("test:unit", "unit test"),
                          ("test:e2e", "end to end test")):
        if script in scripts:
            gates.append({"name": label, "command": f"{runner} {script}",
                          "why": f"package.json scripts.{script}"})

    if (root / "tsconfig.json").exists() and not any(g["name"] == "type check" for g in gates):
        command = "npx tsc --noEmit" if pm == "npm" else f"{pm} exec tsc --noEmit"
        gates.append({"name": "type check", "command": command, "why": "tsconfig.json"})

    if "test" not in scripts:
        notes.append("package.json has no test script: the suite has to be created before it can run.")
    gates.append({"name": "dependency audit",
                  "command": "npm audit --audit-level=high" if pm == "npm" else f"{pm} audit --audit-level=high",
                  "why": "package.json", "optional": True})
    return True


def _python_gates(root: Path, files, gates, notes):
    markers = [n for n in ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
                           "Pipfile", "tox.ini") if (root / n).exists()]
    has_tests = (root / "tests").is_dir() or (root / "test").is_dir() or any(
        f.name.startswith("test_") and f.suffix == ".py" for f in files)
    if not markers and not has_tests:
        return False
    source = markers[0] if markers else "tests/"

    pyproject = read_text(root / "pyproject.toml")
    deps = collect_deps(root, files)
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists():
        gates.append({"name": "install", "command": "pip install -e .", "why": source})
    elif (root / "requirements.txt").exists():
        gates.append({"name": "install", "command": "pip install -r requirements.txt", "why": source})

    if "pytest" in deps or (root / "pytest.ini").exists() or "tool.pytest" in pyproject:
        gates.append({"name": "test", "command": "python -m pytest -q", "why": "pytest configuration or tests/"})
    elif has_tests:
        gates.append({"name": "test", "command": "python -m unittest discover -s tests -v",
                      "why": "tests directory"})
    else:
        notes.append("no test tree found: the suite has to be written before anything can be re-run.")
    if "ruff" in deps or "[tool.ruff" in pyproject:
        gates.append({"name": "lint", "command": "python -m ruff check .", "why": "ruff in " + source})
    if "mypy" in deps or "[tool.mypy" in pyproject:
        gates.append({"name": "type check", "command": "python -m mypy .", "why": "mypy in " + source})
    if "black" in deps or "[tool.black" in pyproject:
        gates.append({"name": "format check", "command": "python -m black --check .", "why": "black in " + source})
    gates.append({"name": "dependency audit", "command": "python -m pip_audit",
                  "why": "installed packages", "optional": True})
    return True


def _dotnet_gates(root: Path, files, gates, notes):
    solutions = [f for f in files if f.suffix in (".sln", ".slnx")]
    projects = [f for f in files if f.suffix == ".csproj"]
    if not solutions and not projects:
        return False
    target = solutions[0].name if solutions else ""
    gates.append({"name": "build", "command": "dotnet build -c Release",
                  "why": target or projects[0].name})
    gates.append({"name": "test", "command": "dotnet test --no-build -c Release",
                  "why": "solution or project files"})
    gates.append({"name": "format check", "command": "dotnet format --verify-no-changes",
                  "why": target or projects[0].name})
    gates.append({"name": "dependency audit",
                  "command": "dotnet list package --vulnerable --include-transitive",
                  "why": target or projects[0].name, "optional": True})
    if not any(f.suffix == ".cs" and "test" in f.name.lower() for f in files):
        notes.append("no test project file name contains 'test': confirm whether a test project exists.")
    return True


def _go_gates(root: Path, files, gates, notes):
    if not (root / "go.mod").exists():
        return False
    gates.append({"name": "build", "command": "go build ./...", "why": "go.mod"})
    gates.append({"name": "vet", "command": "go vet ./...", "why": "go.mod"})
    gates.append({"name": "test", "command": "go test ./...", "why": "go.mod"})
    gates.append({"name": "dependency audit", "command": "govulncheck ./...",
                  "why": "go.mod", "optional": True})
    return True


def _rust_gates(root: Path, files, gates, notes):
    if not (root / "Cargo.toml").exists():
        return False
    gates.append({"name": "build", "command": "cargo build --release", "why": "Cargo.toml"})
    gates.append({"name": "test", "command": "cargo test", "why": "Cargo.toml"})
    gates.append({"name": "format check", "command": "cargo fmt --check", "why": "Cargo.toml"})
    gates.append({"name": "lint", "command": "cargo clippy --all-targets -- -D warnings",
                  "why": "Cargo.toml", "optional": True})
    return True


def _java_gates(root: Path, files, gates, notes):
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        wrapper = "./gradlew" if (root / "gradlew").exists() else "gradle"
        gates.append({"name": "build", "command": f"{wrapper} build", "why": "build.gradle"})
        gates.append({"name": "test", "command": f"{wrapper} test", "why": "build.gradle"})
        gates.append({"name": "dependency audit", "command": f"{wrapper} dependencyCheckAnalyze",
                      "why": "build.gradle", "optional": True})
        return True
    if (root / "pom.xml").exists():
        gates.append({"name": "build", "command": "mvn -B -DskipTests package", "why": "pom.xml"})
        gates.append({"name": "test", "command": "mvn -B test", "why": "pom.xml"})
        gates.append({"name": "dependency audit", "command": "mvn -B org.owasp:dependency-check-maven:check",
                      "why": "pom.xml", "optional": True})
        return True
    return False


def _php_gates(root: Path, files, gates, notes):
    composer = root / "composer.json"
    if not composer.exists():
        return False
    data = read_json(composer)
    scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
    gates.append({"name": "install", "command": "composer install --no-interaction", "why": "composer.json"})
    gates.append({"name": "validate", "command": "composer validate --strict", "why": "composer.json"})
    if "test" in scripts:
        gates.append({"name": "test", "command": "composer test", "why": "composer.json scripts.test"})
    if "lint" in scripts:
        gates.append({"name": "lint", "command": "composer lint", "why": "composer.json scripts.lint"})
    return True


def _ruby_gates(root: Path, files, gates, notes):
    if not (root / "Gemfile").exists():
        return False
    gates.append({"name": "install", "command": "bundle install", "why": "Gemfile"})
    if (root / "spec").is_dir():
        gates.append({"name": "test", "command": "bundle exec rspec", "why": "spec directory"})
    else:
        gates.append({"name": "test", "command": "bundle exec rake test", "why": "Rakefile"})
    gates.append({"name": "dependency audit", "command": "bundle exec bundle-audit check --update",
                  "why": "Gemfile", "optional": True})
    return True


def _static_gates(root: Path, files, gates, notes):
    html = [f for f in files if f.suffix in (".html", ".htm")]
    if not html:
        return False
    gates.append({"name": "page inventory", "command": "python -m http.server 8000",
                  "why": html[0].name, "optional": True})
    notes.append("static site: no build step, so the checks that matter are link targets, "
                 "asset paths and the accessibility of each page.")
    return True


def _container_gates(root: Path, files, gates, notes):
    if (root / "Dockerfile").exists():
        name = root.name.lower().replace(" ", "-") or "app"
        gates.append({"name": "container build", "command": f"docker build -t {name}:qa .",
                      "why": "Dockerfile", "optional": True})
    if (root / "docker-compose.yml").exists() or (root / "compose.yaml").exists():
        gates.append({"name": "compose config", "command": "docker compose config -q",
                      "why": "docker-compose.yml or compose.yaml", "optional": True})
    return bool((root / "Dockerfile").exists())


DETECTORS = [
    ("node", _node_gates),
    ("python", _python_gates),
    ("dotnet", _dotnet_gates),
    ("go", _go_gates),
    ("rust", _rust_gates),
    ("java", _java_gates),
    ("php", _php_gates),
    ("ruby", _ruby_gates),
    ("static", _static_gates),
]


def detect_risks(root: Path, files, deps) -> list:
    risks = []
    evidence = {}

    for group, names in RISK_DEPS.items():
        hits = sorted(name for name in names if name in deps)
        if hits:
            evidence.setdefault(group, []).append(
                "declared in " + sorted({deps[n] for n in hits})[0] + ": " + ", ".join(hits[:4]))

    for rel in files:
        for group, pattern in NAME_HINTS:
            if pattern.search(rel.stem) or (rel.parent.name and pattern.search(rel.parent.name)):
                bucket = evidence.setdefault(group, [])
                if len(bucket) < 3 and ("file " + rel.as_posix()) not in bucket:
                    bucket.append("file " + rel.as_posix())

    if (root / ".env").exists():
        evidence.setdefault("secrets", []).append(".env present in the tree")
    for rel in files:
        if rel.suffix in (".pem", ".key", ".p12") or rel.name in ("id_rsa", "id_ed25519"):
            evidence.setdefault("secrets", []).append("file " + rel.as_posix())

    if (root / "Dockerfile").exists() or (root / "docker-compose.yml").exists():
        evidence.setdefault("container", []).append("Dockerfile or compose file present")

    if (root / ".github" / "workflows").is_dir():
        evidence.setdefault("ci", []).append(".github/workflows present")

    for group in ("auth", "database", "file_upload", "payments", "frontend", "outbound_http",
                  "template_render", "deserialization", "multi_tenant", "secrets", "container", "ci"):
        if group in evidence:
            risks.append({
                "id": group,
                "label": RISK_LABELS.get(group, group.replace("_", " ") + " present"),
                "evidence": sorted(set(evidence[group]))[:4],
            })
    order = ["auth", "multi_tenant", "payments", "file_upload", "database", "secrets",
             "template_render", "deserialization", "outbound_http", "frontend", "container", "ci"]
    risks.sort(key=lambda r: order.index(r["id"]) if r["id"] in order else 99)
    return risks


def _manifest_name(root: Path) -> str:
    """The project's own name from its manifest, so a prompt does not say 'temp-ab12cd34'."""
    package = read_json(root / "package.json")
    name = package.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    for manifest in ("pyproject.toml", "Cargo.toml"):
        match = re.search(r'^\s*name\s*=\s*"([^"]+)"', read_text(root / manifest), re.M)
        if match:
            return match.group(1)
    return ""


def detect(root) -> dict:
    """Inspect a directory and return stacks, gate commands, risks and notes."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    files = walk_files(root)
    deps = collect_deps(root, files)
    stacks, gates, notes = [], [], []

    for name, detector in DETECTORS:
        before = len(gates)
        try:
            matched = detector(root, files, gates, notes)
        except (OSError, ValueError):
            matched = False
        if matched:
            stacks.append(name)
        del before

    if _container_gates(root, files, gates, notes) and "container" not in stacks:
        stacks.append("container")

    if not stacks:
        notes.append("no stack markers found: point the tool at a project root, or write the gates by hand.")

    audit = [g for g in gates if g["name"] == "dependency audit"]
    for extra in audit[1:]:
        gates.remove(extra)

    return {
        "root": str(root),
        "name": _manifest_name(root) or root.name,
        "directory": root.name,
        "stacks": stacks,
        "gates": gates,
        "risks": detect_risks(root, files, deps),
        "notes": notes,
        "file_count": len(files),
        "has_existing_tests": bool((root / "tests").is_dir() or (root / "test").is_dir()
                                   or any(f.suffix in (".spec.ts", ".test.ts", ".spec.js", ".test.js")
                                          for f in files)),
    }


def detect_json(root) -> str:
    return json.dumps(detect(root), indent=2, ensure_ascii=False)
