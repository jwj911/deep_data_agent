import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from data_agent.observability.report import (build_diagnostic_report,
                                             parse_json_lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a redacted diagnostic report from JSON logs.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="JSON Lines log file to read.",
    )
    parser.add_argument(
        "--request-id",
        help="Optional 32-character lowercase hexadecimal request ID.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional report path. Defaults to standard output.",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=200,
        help="Maximum number of non-folded timeline events.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        with args.input.open("r", encoding="utf-8", errors="replace") as file:
            events, invalid_line_count = parse_json_lines(file)
        report = build_diagnostic_report(
            events,
            request_id=args.request_id,
            invalid_line_count=invalid_line_count,
            max_events=args.max_events,
        )
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output is None:
            sys.stdout.write(rendered)
        else:
            args.output.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError):
        sys.stderr.write("Unable to export the diagnostic report.\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
