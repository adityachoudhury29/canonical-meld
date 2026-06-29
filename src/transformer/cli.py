"""Thin CLI surface.

    transformer run --manifest samples/manifest.json [--config configs/x.json] [--out out.json]
    transformer run --csv a.csv --ats b.json --resume r.txt --notes n.txt --github-fixture g.json
    transformer detect --input some_file.json

Engine, correctness and explainability are the point; this is intentionally minimal.
"""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, load_config
from .pipeline import dumps, load_manifest, run
from .sources import detect


def _sources_from_flags(args) -> list[dict]:
    sources: list[dict] = []
    if args.csv:
        sources.append({"type": "recruiter_csv", "path": args.csv})
    if args.ats:
        sources.append({"type": "ats_json", "path": args.ats})
    if args.resume:
        sources.append({"type": "resume", "path": args.resume})
    if args.notes:
        sources.append({"type": "recruiter_notes", "path": args.notes})
    if args.github_fixture or args.github_url:
        sources.append({
            "type": "github",
            "url": args.github_url,
            "fixture": args.github_fixture,
            "live": bool(args.github_live),
        })
    return sources


def _cmd_run(args) -> int:
    try:
        if args.manifest:
            sources = load_manifest(args.manifest)
        else:
            sources = _sources_from_flags(args)
        if not sources:
            print("error: no sources (use --manifest or per-source flags)", file=sys.stderr)
            return 2
        config = load_config(args.config) if args.config else None
    except (ConfigError, FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    result = run(sources, config)

    if not args.quiet:
        for w in result.warnings:
            print(f"[warn] {w}", file=sys.stderr)
        for e in result.errors:
            print(f"[validation] {e}", file=sys.stderr)

    text = dumps(result.profiles, pretty=not args.compact)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        if not args.quiet:
            print(f"wrote {len(result.profiles)} profile(s) -> {args.out}", file=sys.stderr)
    else:
        print(text)

    return 1 if result.errors else 0


def _cmd_detect(args) -> int:
    spec = {"path": args.input} if "github.com" not in args.input else {"url": args.input}
    try:
        print(detect(spec))
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="transformer",
                                description="Merge multi-source records into one canonical candidate profile")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run the pipeline and emit canonical JSON")
    r.add_argument("--manifest", help="manifest JSON listing the sources")
    r.add_argument("--config", help="runtime output config JSON")
    r.add_argument("--out", help="write output JSON to this path (else stdout)")
    r.add_argument("--csv", help="recruiter CSV export")
    r.add_argument("--ats", help="ATS JSON blob")
    r.add_argument("--resume", help="resume .txt/.pdf")
    r.add_argument("--notes", help="recruiter notes .txt")
    r.add_argument("--github-url", help="GitHub profile URL")
    r.add_argument("--github-fixture", help="GitHub API fixture JSON (offline/deterministic)")
    r.add_argument("--github-live", action="store_true", help="allow live GitHub API fetch")
    r.add_argument("--compact", action="store_true", help="compact (non-indented) JSON")
    r.add_argument("--quiet", action="store_true", help="suppress warnings on stderr")
    r.set_defaults(func=_cmd_run)

    d = sub.add_parser("detect", help="print the detected source type for a file/URL")
    d.add_argument("--input", required=True, help="file path or URL")
    d.set_defaults(func=_cmd_detect)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
