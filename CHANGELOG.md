# Changelog

## 1.0.0

First release.

- `qa-sweep detect` reports the stack, the exact gate commands and the risk modules of a project, each
  with the file that produced it.
- `qa-sweep install` writes the sweep prompt, a quick audit variant, the detection result, a suite
  scaffold and adapter files for Claude Code, Cursor and AGENTS.md style agents. It is idempotent and
  never replaces an existing file without `--force`.
- `qa-sweep check` validates a report against the contract: required sections in order, a stated and
  allowed verdict, evidence per result row, priorities per defect row, a stated coverage limit, a cited
  results JSON, and a verdict that agrees with the failing checks inside it.
- `qa-sweep selftest` runs the 61 check suite that tests this tool.
- Continuous integration on Linux and Windows across Python 3.9 and 3.12.
