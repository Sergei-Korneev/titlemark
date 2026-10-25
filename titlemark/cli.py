"""Command line interface for titlemark."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __author__, __version__
from .ai import DEFAULT_MODEL as DEFAULT_AI_MODEL, DEFAULT_URL as DEFAULT_AI_URL
from .extractors import supported_extensions
from .naming import DEFAULT_TEMPLATE, TEMPLATE_FIELDS, validate_template
from .renamer import apply_plans, plan_many, write_csv_report

_STATUS_MARK = {
    "ok": "*",
    "same": "=",
    "no-title": "?",
    "unsupported": "-",
    "error": "!",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="titlemark",
        description=(
            "Reads a document, detects its title and author, and renames the "
            "file into something a human would recognise "
            "(default pattern: \"Author - Title [year].ext\"). "
            "By default it runs in dry-run mode: nothing is renamed, only a "
            "plan is printed. "
            f"Supported formats: {', '.join(supported_extensions())}."
        ),
        epilog=(
            "Examples:\n"
            "  titlemark book.pdf                   # what would the file become\n"
            "  titlemark --apply book.pdf           # rename it\n"
            "  titlemark --apply -r ~/Downloads     # whole folder, recursively\n"
            "  titlemark --report plan.csv -r .     # save the plan as CSV\n"
            "  titlemark --title-from-text book.pdf # title = whole page text\n"
            "  titlemark --ai book.pdf              # vision LLM reads the cover\n"
            '  titlemark --naming-template "{title}-{year}" book.pdf\n'
            "\n"
            f"Author:  {__author__}\n"
            f"Version: {__version__} (see also: titlemark --version)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__} — {__author__}")
    parser.add_argument("paths", nargs="+", type=Path,
                        help="file(s) or folder(s) with documents")
    parser.add_argument("-a", "--apply", action="store_true",
                        help="actually rename (without this flag only a plan "
                             "is printed)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="walk folders recursively")
    parser.add_argument("-n", "--naming-template", metavar="PATTERN",
                        default=None,
                        help=f"name pattern with placeholders "
                             f"{', '.join('{%s}' % t for t in TEMPLATE_FIELDS)}; "
                             f"the extension is appended automatically "
                             f"(default: \"{DEFAULT_TEMPLATE}\")")
    ocr_group = parser.add_mutually_exclusive_group()
    ocr_group.add_argument("--no-ocr", action="store_true",
                           help="never OCR scanned pages")
    ocr_group.add_argument("--force-ocr", action="store_true",
                           help="always OCR the leading pages and use that "
                                "text instead of the built-in text layer "
                                "(for PDFs with a broken encoding)")
    parser.add_argument("--ocr-pages", type=int, default=2, metavar="N",
                        help="how many leading pages to OCR (default: 2)")

    ai_group = parser.add_argument_group(
        "AI (vision LLM over the cover; enabled only by --ai)")
    ai_group.add_argument("--ai", action="store_true",
                          help="ask a vision LLM to read the document cover; "
                               "its answer outranks the heuristics "
                               "(OpenAI-compatible API: cloud or local Ollama)")
    ai_group.add_argument("--ai-url", metavar="URL",
                          default=os.environ.get("TITLEMARK_AI_URL", DEFAULT_AI_URL),
                          help=f"API endpoint (default: {DEFAULT_AI_URL}; "
                               "for Ollama: http://localhost:11434/v1; "
                               "env TITLEMARK_AI_URL)")
    ai_group.add_argument("--ai-model", metavar="MODEL",
                          default=os.environ.get("TITLEMARK_AI_MODEL", DEFAULT_AI_MODEL),
                          help=f"model name (default: {DEFAULT_AI_MODEL}; "
                               "for Ollama: moondream, llava; "
                               "env TITLEMARK_AI_MODEL)")
    ai_group.add_argument("--ai-key", metavar="KEY",
                          default=os.environ.get("TITLEMARK_AI_KEY", ""),
                          help="API key (env TITLEMARK_AI_KEY); "
                               "not needed for local Ollama")
    ai_group.add_argument("--ai-timeout", type=int, default=60, metavar="SEC",
                          help="AI request timeout in seconds (default: 60)")
    parser.add_argument("--no-year", action="store_true",
                        help="do not append the year to file names")
    parser.add_argument("--title-from-text", action="store_true",
                        help="build the title from the WHOLE page text without "
                             "special characters (title fragments are joined "
                             "into one), instead of picking candidate lines")
    parser.add_argument("--title-pages", type=int, default=1, metavar="N",
                        help="how many leading pages to take for "
                             "--title-from-text (default: 1)")
    parser.add_argument("--report", type=Path, metavar="CSV",
                        help="save the plan as a CSV report")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show title candidates, warnings and text snippets")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="print only the summary")
    return parser


def _short(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _print_plan(plans, verbose: bool = False) -> None:
    for plan in plans:
        mark = _STATUS_MARK.get(plan.status, "?")
        if plan.status == "ok" and plan.new_name:
            info = plan.info
            src = info.title_source.value if info else "?"
            print(f"{mark} {plan.path.name}")
            print(f"  -> {_short(plan.new_name, 150)}  [{src}]")
        elif plan.status == "same":
            print(f"{mark} {plan.path.name}  (name already fits)")
        else:
            print(f"{mark} {plan.path.name}  ({plan.detail or plan.status})")

        if verbose and plan.info and plan.status == "ok":
            info = plan.info
            if info.author:
                print(f"     author: {info.author} [{info.author_source.value}]")
            if info.year:
                print(f"     year:   {info.year}")
            for cand, score in info.title_candidates[:3]:
                print(f"     candidate ({score}): {_short(cand, 90)}")
            for warn in info.warnings:
                print(f"     ! {warn}")
            if info.text_snippet:
                snippet = _short(info.text_snippet.replace("\n", " ⏎ "), 160)
                print(f"     text: {snippet}")


def _print_summary(plans) -> None:
    counts: dict[str, int] = {}
    for plan in plans:
        counts[plan.status] = counts.get(plan.status, 0) + 1
    print()
    print(f"Total files: {len(plans)}")
    for status in ("ok", "same", "no-title", "unsupported", "error"):
        if counts.get(status):
            print(f"  {status:<12}: {counts[status]}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.naming_template:
        problem = validate_template(args.naming_template)
        if problem:
            print(f"bad --naming-template: {problem}", file=sys.stderr)
            return 2

    missing = [p for p in args.paths if not p.exists()]
    if missing:
        for path in missing:
            print(f"path not found: {path}", file=sys.stderr)
        return 2

    ai_config = None
    if args.ai:
        from .ai import AiConfig

        if not args.ai_key and not ("localhost" in args.ai_url
                                    or "127.0.0.1" in args.ai_url):
            print("a cloud API key is required: --ai-key or TITLEMARK_AI_KEY "
                  "(local Ollama needs no key)", file=sys.stderr)
            return 2
        ai_config = AiConfig(url=args.ai_url, model=args.ai_model,
                             api_key=args.ai_key, timeout=args.ai_timeout)

    plans = plan_many(
        args.paths,
        recursive=args.recursive,
        use_ocr=not args.no_ocr,
        ocr_pages=args.ocr_pages,
        include_year=not args.no_year,
        force_ocr=args.force_ocr,
        ai=ai_config,
        title_from_text=args.title_pages if args.title_from_text else 0,
        naming_template=args.naming_template,
    )

    if not plans:
        print("No supported files found.", file=sys.stderr)
        return 1

    if not args.quiet:
        mode = "RENAMING" if args.apply else "PLAN (dry-run, no files changed)"
        print(f"=== {mode} ===")
        _print_plan(plans, verbose=args.verbose)

    if args.apply:
        renamed = apply_plans(plans)
        print(f"Renamed: {len(renamed)}")
    else:
        to_rename = sum(1 for p in plans if p.status == "ok")
        print(f"Will rename: {to_rename} (run with --apply)")

    if args.report:
        write_csv_report(plans, args.report)
        print(f"Report saved: {args.report}")

    _print_summary(plans)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
