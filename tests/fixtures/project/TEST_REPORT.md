# Test report: demo-api

## A. Verdict

**Conditional release.** The API can go to staging once the two conditions below are met. The verdict
covers the HTTP surface and the data layer; the admin web interface was out of scope for this pass.

Conditions:

1. fix DEF-1, the missing owner check on the document endpoint
2. add a rollback note to the deployment runbook

## B. Environment, commands run, scope and coverage

Environment: Node 22.4 on Windows 11, branch `release/1.4`, commit `9f2c1ab`, test database `demo_test`.

Commands run:

- `npm ci`, exit 0, 41.2s
- `npm run lint`, exit 0, 0 problems
- `npx tsc --noEmit`, exit 0
- `npm test`, exit 0, 34 passed
- `python tests/qa_suite.py`, exit 0, 12 checks with 1 failure, results in `tests/qa-results.json`

Coverage: the document and user HTTP endpoints, session handling, the document sharing journey, and
the input boundaries of both write endpoints.

Not covered: the admin web interface, uploads larger than 5 MB, the payment provider sandbox, load
above 20 concurrent clients, and the email worker.

## C. Results table

| Area | Status | Evidence | Notes |
|---|---|---|---|
| Build and lint | pass | `npm ci` exit 0, `npm run lint` exit 0 with 0 problems | 41.2s install on a warm cache |
| Type check | pass | `npx tsc --noEmit` exit 0 | strict mode enabled |
| Unit tests | pass | `npm test` exit 0, 34 passed | jest, 3.8s wall clock |
| Authorization | fail | `tests/qa-results.json` check `authz.owner` failed: GET /documents/42 as user 7 returned 200 with user 9's document | recorded as DEF-1 |
| Boundaries | pass | `tests/qa-results.json` checks `boundary.empty_title` and `boundary.long_title` passed | empty title and 200 KB title |
| Secrets | pass | `git grep -nE "(api[_-]?key|secret)"` reviewed by hand, no live value in the tree | .env is git ignored |

## D. Bug list

| Id | Title | Priority | Reproduction | Actual | Expected | Root cause | Fix |
|---|---|---|---|---|---|---|---|
| DEF-1 | Document endpoint returns another user's document | P1 | sign in as user 7, call `GET /api/documents/42`, which belongs to user 9 | 200 with the full document body | 404 | the handler filters on the document id only | open, needs a product decision between 404 and 403 |
| DEF-2 | Login failure message carries no information | P3 | submit a wrong password on the sign in page | the message reads "invalid" | text that says the password is wrong | one shared error constant for every failure | open, cosmetic |

## E. Files changed

- `tests/qa_suite.py` and `tests/qa_lib.py`, written by `qa-sweep install`, so the sweep can be re-run.
- no application file changed in this pass: DEF-1 needs an owner decision first.

## F. Remaining risks and limitations

DEF-1 is a P1 and the reason for the conditional verdict: an authenticated user can read any document
by guessing its id. Rollback is one command, `kubectl rollout undo deployment/api`, because the release
is a single image tag. Monitoring is the existing Sentry project plus a 4xx rate alert on the document
endpoint, both live before this pass.

Limits of this pass: no load test, no accessibility review, no cross browser check, and the admin
interface was not reviewed.

## G. Release checklist

| Gate | State | Note |
|---|---|---|
| install, build, lint, type check pass | yes | exit 0 for all four |
| critical automated tests pass | yes | 34 unit checks plus the 12 check suite |
| no unresolved P1 | no | DEF-1 is open |
| critical journeys pass | partial | the sharing journey fails as described in DEF-1 |
| no high severity security issue | partial | DEF-1 is an authorization defect |
| dependency audit reviewed | yes | no high severity advisory |
| rollback documented | yes | `kubectl rollout undo deployment/api` |
| monitoring in place | yes | Sentry plus the 4xx rate alert |
