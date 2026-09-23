# Report contract

The report a sweep produces is the deliverable, so its shape is machine checked. `qa-sweep check
TEST_REPORT.md` reads the report and the results JSON it cites, and fails when the two disagree.

Exit codes: 0 when the report passes, 1 when a rule is broken, 2 when the report cannot be read.

## Required sections

The headings are matched with or without a markdown level marker, so all of these work:

- `## A. Verdict`
- `**A. Verdict**`
- `A. Verdict`

Letters A to G have to appear, in order, with this content:

| Letter | Section | What it has to contain |
|---|---|---|
| A | Verdict | exactly one of: release recommended, conditional release, release not recommended |
| B | Environment, commands, scope, coverage | the commands run, and an explicit statement of what was not covered |
| C | Results table | a markdown table, one row per area, with a non-empty evidence cell |
| D | Bug list | a table whose rows carry a P0 to P3 priority, or the explicit statement "no defects found" |
| E | Files changed | the files touched and why |
| F | Remaining risks and limitations | what is still unknown, and the rollback and monitoring story |
| G | Release checklist | the gate list with its state |

## Rules the checker enforces

1. Every section is present and in order.
2. The verdict is stated, and it is one of the three allowed answers. A negative verdict is a valid
   answer and is not penalised.
3. No hedged or unsupported claim anywhere in the report: "should pass", "should work", "looks fine",
   "presumably", "I believe", "seems to work", "probably works", and an assumption phrased as a result.
4. No absolute claim: "no bugs", "bug free", "100% tested".
5. Section B says what was not covered.
6. Every result row carries evidence: something other than "n/a", "manual", "looks fine", "tbd", or a
   cell shorter than four characters.
7. Every defect row carries a P0, P1, P2 or P3 priority. A section D with no table has to say "no
   defects found" explicitly, so an empty list cannot be mistaken for a clean result.
8. The report cites at least one results JSON, that file exists and parses, and its list of checks is
   the one the report counts. A report that claims a green suite while the results contain failing
   checks is a violation.
9. A "release recommended" verdict next to an open P0 or P1, or next to a failing check, is a
   violation. That is the release gate of the prompt, enforced.

## Warnings, and `--strict`

Two items are warnings by default and failures under `--strict`:

- a release or conditional verdict with no rollback approach documented
- a release or conditional verdict with no monitoring or error tracking documented

They are warnings because a project can legitimately document them elsewhere; `--strict` is what a
release pipeline should run.

## What the checker cannot see

It reads text and JSON. It cannot tell whether a quoted command output is real, whether a test that was
run actually tested anything, or whether the sweep covered the riskiest module. Those stay the
reviewer's job; the contract only removes the claims that are provably contradicted by the artefacts
beside them.
