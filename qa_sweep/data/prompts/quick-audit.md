# Quick QA audit

A shorter pass for one change, one pull request, or a repository too small to justify a full sweep.
Timebox it to about thirty minutes and keep the same evidence rules: every claim carries a command and
its output, and anything you could not run is reported as not covered.

## Working rules

1. Test first, re-test after every fix.
2. Never claim a test ran that did not run.
3. No "should pass", no "looks fine", no "presumably".
4. Do not delete user data, reset environments or change production configuration.
5. Minimal changes only.

## Project facts already gathered

- Project: {{PROJECT_NAME}}
- Detected stacks: {{STACKS}}
- Gate commands detected by qa-sweep:
{{GATES}}
- Risk hints, each with the file that produced it:
{{RISKS}}
- Notes from detection:
{{SCOPE_NOTES}}

## The pass

1. Run the gates that exist (build, lint, type check, test) and record command, output excerpt and exit
   code. If the project has no test suite, say so and write the three highest value checks instead of
   a general suite.
2. Read the diff or the changed area and write down what it is supposed to do. If the change has no
   stated intent, ask before testing it.
3. Test the changed behaviour directly: the happy path, one absent required value, one oversized
   value, and one authorization boundary if the change touches data belonging to a user.
4. Check that nothing around the change broke: run the neighbouring tests, and the one journey that
   passes through this code.
5. Security pass, read only: no secret in the diff, no personal data in logs or error text, no input
   reaching a query, a shell or a template without validation.
6. Write the result in the same A to G shape as the full sweep, but shorter: verdict, commands run
   with evidence, what was not covered, defects with priority, and the single next action.

## Release gate

Recommend the change only when the gates pass, no P0 or P1 is open, the changed path has a test, and
the rollback is one command or one revert. Otherwise say what blocks it.
