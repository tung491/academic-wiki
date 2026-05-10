"""Cross-shell CLI shim for SKILL.md.

All subcommands are thin wrappers around academic_wiki_lib helpers; they exist
so wiki orchestration runs identically on bash, zsh, PowerShell, and cmd via
`python -m academic_wiki_lib.cli <subcommand> [args]`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _cmd_acquire(args: argparse.Namespace) -> int:
    from academic_wiki_lib.lockfile import LockHeld, acquire
    lock_path = Path(args.wiki_root) / ".lock"
    try:
        acquire(lock_path, op=args.op)
    except LockHeld as e:
        print(str(e), file=sys.stderr)
        return 1
    return 0


def _cmd_release(args: argparse.Namespace) -> int:
    from academic_wiki_lib.lockfile import release
    release(Path(args.wiki_root) / ".lock")
    return 0


def _cmd_source_sha(args: argparse.Namespace) -> int:
    from academic_wiki_lib.source_sha import file_sha256
    print(file_sha256(args.path))
    return 0


def _cmd_find_paper(args: argparse.Namespace) -> int:
    from academic_wiki_lib.paper_id import find_existing_paper_by_identifiers
    identifiers = {}
    if args.doi:
        identifiers["doi"] = args.doi
    if args.arxiv:
        identifiers["arxiv"] = args.arxiv
    if args.url:
        identifiers["url"] = args.url
    pid = find_existing_paper_by_identifiers(args.wiki_root, identifiers)
    print(json.dumps({"paper_id": pid}))
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="academic_wiki_lib.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("acquire", help="Acquire <wiki-root>/.lock for an operation")
    p.add_argument("wiki_root")
    p.add_argument("--op", required=True)
    p.set_defaults(func=_cmd_acquire)

    p = sub.add_parser("release", help="Release <wiki-root>/.lock")
    p.add_argument("wiki_root")
    p.set_defaults(func=_cmd_release)

    p = sub.add_parser("source-sha", help="Print SHA-256 of a file")
    p.add_argument("path")
    p.set_defaults(func=_cmd_source_sha)

    p = sub.add_parser("find-paper", help="Find an existing paper-id by identifier")
    p.add_argument("wiki_root")
    p.add_argument("--doi", default=None)
    p.add_argument("--arxiv", default=None)
    p.add_argument("--url", default=None)
    p.set_defaults(func=_cmd_find_paper)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
