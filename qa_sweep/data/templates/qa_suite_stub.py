"""Release-readiness suite for this project.

Scaffolded by qa-sweep. The checks here are starters: keep the areas, replace the placeholders with
checks that can fail for a real reason, and add the ones your project actually needs.

Run it with the test command detected for this project, or directly:

    python tests/qa_suite.py

Exit code equals the number of failing checks. Results land in tests/qa-results.json, which the report
cites as evidence.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from qa_lib import Suite, run_command  # noqa: E402

SUITE = Suite("release-readiness", HERE / "qa-results.json")


# Area 1, structure and wiring: the project can be understood and started by someone else.
readme = ROOT / "README.md"
SUITE.check(
    "structure.readme",
    "structure",
    "a README states what the project does and how to run it",
    readme.is_file() and len(readme.read_text(encoding="utf-8", errors="replace")) > 200,
    f"README.md at {readme} with {readme.stat().st_size if readme.is_file() else 0} bytes",
)

manifest = [name for name in ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml",
                              "build.gradle", "composer.json", "Gemfile")
            if (ROOT / name).is_file()]
SUITE.check(
    "structure.manifest",
    "structure",
    "a dependency manifest exists, so the build is reproducible",
    bool(manifest),
    f"found: {', '.join(manifest) if manifest else 'none'}",
)


# Area 2, secrets: nothing credential shaped is committed.
LEAK_NAMES = (".env", "id_rsa", "id_ed25519", "credentials.json", "secrets.yaml", "secrets.yml")
found_leaks = [name for name in LEAK_NAMES if (ROOT / name).is_file()]
SUITE.check(
    "secrets.none_committed",
    "secrets",
    "no obvious credential file is committed in the tree",
    not found_leaks,
    f"found: {', '.join(found_leaks)}" if found_leaks else "no credential file names at the root",
)


# Area 3, the test command itself: replace with a real gate for this project.
gate = run_command([sys.executable, "-c", "print('replace me with the project build or lint command')"],
                   cwd=ROOT, shell=False, timeout=60)
SUITE.check(
    "gates.placeholder",
    "release gates",
    "the project test or lint command runs and exits zero",
    gate["code"] == 0,
    f"exit {gate['code']} in {gate['seconds']:.2f}s: {gate['output'].strip()[:200]}",
)


# Area 4, a check that needs something you do not have yet: it is reported, never counted as a pass.
SUITE.skip(
    "journey.placeholder",
    "critical journey",
    "the primary user journey completes end to end",
    "no journey defined yet: name the journey, then drive it here against a test copy",
)


# Area 5, boundaries: absent, empty and oversized values on the primary input. Reported as skipped
# until it is written, because a placeholder that passes would certify behaviour nobody tested.
SUITE.skip(
    "boundary.placeholder",
    "boundaries",
    "an absent required value is rejected with a clear message rather than a crash",
    "not written yet: send an empty value to the primary input and assert the response",
)

sys.exit(SUITE.finish())
