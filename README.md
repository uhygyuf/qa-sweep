# qa-sweep

Install a release-readiness QA sweep prompt for a coding agent, and check the report that comes back
against an evidence contract.

A coding agent will happily write "tests pass, looks ready to ship". `qa-sweep` gives the agent a
prompt that forbids that answer, and then checks the report it produced: every required section, every
result row with evidence, every defect with a priority, and a verdict that matches the results file
next to it.

## What it does

- `qa-sweep detect` reads a project and prints the exact gate commands for its stack, plus the modules
  that carry release risk, each with the file that produced it.
- `qa-sweep install` writes a re-runnable prompt, a suite scaffold and the adapter files for Claude
  Code, Cursor and AGENTS.md based agents into the project.
- `qa-sweep check TEST_REPORT.md` validates the report against the contract and exits non-zero when a
  claim contradicts the artifacts beside it.
- `qa-sweep selftest` runs the suite that tests this tool.

No runtime dependencies. Python 3.9 or newer, standard library only.

## Why the checker exists

A prompt alone is advice. The failure mode of an AI run QA report is not that the findings are wrong,
it is that the evidence is missing while the tone stays confident. The checker removes the part of that
which is mechanically detectable:

- a verdict of "release recommended" next to an open P0 or P1, or next to failing checks in the cited
  results file
- a results table whose evidence cell says "n/a", "manual" or "looks fine"
- hedged or unsupported phrasing anywhere in the report
- a bug list that neither lists defects with priorities nor says "no defects found"
- a report that never states what was not covered

Anything richer than that stays the reviewer's job. The tool takes away the claims that are provably
contradicted by the artifacts, and nothing more.

## Install

From a clone, no installation is needed:

```bash
git clone https://github.com/uhygyuf/qa-sweep
cd qa-sweep
python -m qa_sweep detect .
```

Or install the console script:

```bash
python -m pip install .
qa-sweep version
```

## Usage

```bash
# what is this project, and which commands decide if it is releasable
qa-sweep detect .
qa-sweep detect . --json > stack.json

# put the prompt and the suite scaffold into a project (writes into the target, nothing else)
qa-sweep install ..\my-app
qa-sweep install ..\my-app --dry-run
qa-sweep install ..\my-app --agent claude --no-suite

# after the agent produced a report
qa-sweep check TEST_REPORT.md
qa-sweep check TEST_REPORT.md --json --strict
```

Real `detect` output for a Node project, verbatim apart from the machine specific root path:

```text
project  : demo-api
root     : /work/demo-api
stacks   : node
files    : 6 scanned
tests    : no test tree found
gates    :
  install            npm ci
                     from package.json
  build              npm run build
                     from package.json scripts.build
  lint               npm run lint
                     from package.json scripts.lint
  test               npm run test
                     from package.json scripts.test
  dependency audit   npm audit --audit-level=high (optional)
                     from package.json
risks    :
  auth               authentication or session code
                     declared in package.json: jsonwebtoken
                     file src/auth/login.js
  file_upload        file upload handling
                     declared in package.json: multer
                     file src/uploads/handler.js
  database           data store, migrations or ORM
                     file prisma/schema.prisma
```

Real `check` output for the sample report in this repository, verbatim apart from the root path:

```text
report   : tests/fixtures/project/TEST_REPORT.md
verdict  : conditional release
sections : A B C D E F G
results  : 1 file(s), 1 failing check(s)

  [ok  ] sections.present: all sections A to G present
  [ok  ] sections.order: sections appear in order
  [ok  ] verdict.present: verdict: conditional release
  [ok  ] claims.no_hedging: no hedged claims
  [ok  ] claims.no_absolutes: no absolute claims
  [ok  ] coverage.limits_stated: section B states what was not covered
  [ok  ] results.table: 6 result row(s)
  [ok  ] results.evidence_per_row: 6 row(s) carry evidence
  [ok  ] bugs.priorities: 2 defect row(s) carry a P0 to P3 priority
  [ok  ] results.files_cited: 1 results file(s) cited and readable
  [ok  ] results.counts_consistency: 1 failing check(s) in the cited results
  [ok  ] verdict.matches_evidence: green claim agrees with the results files

PASS
```

`install` writes these files into the target, and refuses to replace any of them unless `--force` is
given:

```text
.qa-sweep/prompt.md              the sweep prompt, with the project facts filled in
.qa-sweep/quick-audit.md         the thirty minute variant for one change
.qa-sweep/stack.json             the detection result, kept as evidence
.claude/commands/qa-sweep.md     Claude Code slash command
.cursor/rules/qa-sweep.mdc       Cursor rule
AGENTS.md                        a short block between two markers, appended once
tests/qa_lib.py                  the check harness
tests/qa_suite.py                the suite scaffold, which runs immediately
```

## The prompt

`qa_sweep/data/prompts/release-readiness.md` is the full sweep: recon and report the plan first, write
a re-runnable suite before running anything, run the existing gates, add tests by risk, triage suite
defect against project defect, fix and re-test at most five rounds, then security, performance and
accessibility passes, then the report. `quick-audit.md` is the same discipline for one change.

Both share the rules that make the report usable: test first and re-test after every fix, never claim a
test ran that did not run, evidence only, no destructive action, minimal changes, and state plainly
what was not covered.

The report shape is A to G: verdict, environment and coverage, results table, bug list, files changed,
remaining risks, release checklist. The machine checkable parts are documented in
[docs/report-contract.md](docs/report-contract.md).

## Evidence

Every claim below was produced by a command in this repository.

| Area | Command | Result |
|---|---|---|
| Self-tests | `python tests/run_tests.py` | 62 checks, 62 passed, 0 failed, 0 skipped |
| Detection | `python -m qa_sweep detect . --json` | prints the stack and gates of this repository |
| Installer | `python -m qa_sweep install tests/fixtures/project --dry-run` | lists the files it would write, writes none |
| Contract pass | `python -m qa_sweep check tests/fixtures/project/TEST_REPORT.md` | exit 0, PASS |
| Contract fail | the same report with "release recommended" and an open P1 | exit 1, names both violations |
| Python 3.9 | the continuous integration matrix | the suite passes on 3.9 and 3.12, Linux and Windows |

Self-test checks: 62

The suite is `tests/run_tests.py` with four case modules. Results land in `tests/selftest-results.json`,
which is committed so a reviewer can compare runs.

## Defects found and fixed

The suite found these while it was being written. The first two are defects in the tool, the last two
were defects in the tests themselves, listed because a suite that only ever certifies its own author is
worth less.

1. The Python detector chose `python -m pytest -q` for any project with a test tree, even when pytest
   was not declared as a dependency, so the printed gate would fail on a clean machine. Found by
   `detect.python_without_pytest`, fixed by requiring pytest in the manifest or its configuration.
2. The prompt identified the project by its directory name, so installing into a temporary directory
   produced "Project: qa-sweep-test-s2vo8f45". Found by `install.prompt_names_project`, fixed by
   reading the name from package.json, pyproject.toml or Cargo.toml first.
3. The fixture helper that blanks a report section replaced from the heading to the end of the file,
   because the pattern used a greedy match across lines. Found by `check.empty_bug_list_fails`, fixed
   by walking the heading lines instead of matching a region.
4. Path comparison in the installer tests failed on Windows, where a temporary directory appears as
   `LEOWAN~1` in one call and in long form in another. Found by the case module crashing, fixed by
   resolving the temporary directory once.
5. `install` used `Path.write_text(newline="\n")`, which only exists from Python 3.10, so the tool
   crashed for anyone on 3.9 while the local suite stayed green on 3.11. Found by the continuous
   integration matrix on 3.9, fixed by writing bytes directly, and closed with the
   `repo.python39_compatible` check so the class of defect cannot come back unnoticed.

## Limitations

- The checker reads text and JSON. It cannot tell whether a quoted command output is real, whether a
  test that ran asserted anything useful, or whether the sweep touched the riskiest module.
- The tool never runs the target project's gates itself. Detection is a suggestion; the agent runs the
  commands and the report carries the output.
- Detection covers Node, Python, .NET, Go, Rust, Java, PHP, Ruby, static sites and containers. A
  project with none of those markers gets a prompt that says no gate was found rather than a guess.
- Risk detection is name and dependency based. A module whose risk is only visible in the code will be
  missed, and the prompt tells the agent to correct the list from the repository.
- The suite scaffold is a starter: four areas with two placeholders recorded as skipped. It has to be
  replaced with checks that can fail for a real reason. A skipped check is never counted as a pass.
- The prompt does not cover mobile apps, embedded targets or model training pipelines.
- Adapters exist for Claude Code, Cursor and AGENTS.md style agents. Other agents need
  `.qa-sweep/prompt.md` pasted manually.

## Known hardening items

- The checker trusts the numbers inside the cited results JSON. A suite that writes `ok: true` without
  asserting anything will pass the contract.
- Section E is checked for presence only, not for whether the listed files were really the changed
  ones.
- There is no verification of quoted command output against a CI log.

## Development

```bash
python tests/run_tests.py          # the suite, exit code equals the number of failures
python -m qa_sweep selftest        # the same suite through the console script
python -m qa_sweep version
```

Layout:

```text
qa_sweep/            the package: cli, detect, install, check
qa_sweep/data/       the prompt pack and the templates that ship with the package
docs/                the report contract
tests/               the self-tests, the fixtures and their results
```

## License

MIT. See [LICENSE](LICENSE).
