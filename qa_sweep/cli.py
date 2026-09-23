"""Command line entry point: qa-sweep detect | install | check | selftest | version."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__
from . import check as check_module
from . import detect as detect_module
from . import install as install_module

AGENT_CHOICES = ["claude", "cursor", "agents", "all"]


def render_detect(info: dict) -> str:
    lines = [f"project  : {info['name']}",
             f"root     : {info['root']}",
             f"stacks   : {', '.join(info['stacks']) if info['stacks'] else 'none detected'}",
             f"files    : {info['file_count']} scanned",
             f"tests    : {'existing test tree found' if info['has_existing_tests'] else 'no test tree found'}",
             "gates    :"]
    if info["gates"]:
        for gate in info["gates"]:
            optional = " (optional)" if gate.get("optional") else ""
            lines.append(f"  {gate['name']:18} {gate['command']}{optional}")
            lines.append(f"  {'':18} from {gate['why']}")
    else:
        lines.append("  none detected, write the gate commands by hand")
    lines.append("risks    :")
    if info["risks"]:
        for risk in info["risks"]:
            lines.append(f"  {risk['id']:18} {risk['label']}")
            for evidence in risk["evidence"][:2]:
                lines.append(f"  {'':18} {evidence}")
    else:
        lines.append("  none inferred from the tree")
    if info["notes"]:
        lines.append("notes    :")
        for note in info["notes"]:
            lines.append(f"  {note}")
    return "\n".join(lines)


def cmd_detect(args) -> int:
    try:
        info = detect_module.detect(args.path)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(info, indent=2, ensure_ascii=False) if args.json else render_detect(info))
    return 0


def cmd_install(args) -> int:
    agents = args.agent or ["all"]
    if "all" in agents:
        agents = ["claude", "cursor", "agents"]
    seen = []
    for agent in agents:
        if agent not in seen:
            seen.append(agent)
    try:
        report = install_module.install(args.path, agents=tuple(seen), with_suite=not args.no_suite,
                                        force=args.force, dry_run=args.dry_run)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(install_module.render_install(report))
    return 0


def cmd_check(args) -> int:
    result = check_module.check_report(args.report, strict=args.strict)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(check_module.render_result(result))
    return 0 if result["ok"] else 1


def cmd_selftest(args) -> int:
    suite = Path(__file__).resolve().parents[1] / "tests" / "run_tests.py"
    if not suite.is_file():
        print("The bundled self-tests live in a source checkout: clone the repository and run "
              "python tests/run_tests.py", file=sys.stderr)
        return 2
    return subprocess.call([sys.executable, str(suite)])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qa-sweep",
        description="Install a release-readiness QA sweep prompt for a coding agent, and check the "
                    "report that comes back against an evidence contract.")
    subparsers = parser.add_subparsers(dest="command")

    detect_parser = subparsers.add_parser(
        "detect", help="print the stack, gate commands and risk hints for a project")
    detect_parser.add_argument("path", nargs="?", default=".")
    detect_parser.add_argument("--json", action="store_true", help="print machine readable output")
    detect_parser.set_defaults(func=cmd_detect)

    install_parser = subparsers.add_parser(
        "install", help="write the prompt pack and the suite scaffold into a project")
    install_parser.add_argument("path", nargs="?", default=".")
    install_parser.add_argument("--agent", action="append", choices=AGENT_CHOICES,
                                help="agent adapter to write, repeatable, default all")
    install_parser.add_argument("--no-suite", action="store_true",
                               help="skip the tests/qa_suite.py scaffold")
    install_parser.add_argument("--force", action="store_true",
                                help="replace files that already exist")
    install_parser.add_argument("--dry-run", action="store_true",
                                help="print what would be written, write nothing")
    install_parser.set_defaults(func=cmd_install)

    check_parser = subparsers.add_parser(
        "check", help="validate a report against the report contract")
    check_parser.add_argument("report", help="path to TEST_REPORT.md")
    check_parser.add_argument("--json", action="store_true", help="print machine readable output")
    check_parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    check_parser.set_defaults(func=cmd_check)

    selftest_parser = subparsers.add_parser("selftest", help="run the bundled self-tests")
    selftest_parser.set_defaults(func=cmd_selftest)

    subparsers.add_parser("version", help="print the version")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    if args.command == "version":
        print(f"qa-sweep {__version__}")
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
