from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .merge import merge_batches
from .models import PageBatch
from .normalize import normalize_batch
from .pdf import inspect_pdf, propose_split_plans, split_pdf
from .report import write_validation_report
from .validate import validate_document


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reg2md",
        description="Source-grounded regulation PDF to Markdown utilities",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_command = commands.add_parser("inspect")
    inspect_command.add_argument("pdf")

    plan_command = commands.add_parser("plan")
    plan_command.add_argument("pdf")
    plan_command.add_argument("--reliable-pages", type=int, default=60)
    plan_command.add_argument("--overlap", type=int, default=1)

    split_command = commands.add_parser("split")
    split_command.add_argument("pdf")
    split_command.add_argument("plan_json")
    split_command.add_argument("output_dir")

    normalize_command = commands.add_parser("normalize")
    normalize_command.add_argument("markdown")
    normalize_command.add_argument("content_list")
    normalize_command.add_argument("official_start_page", type=int)
    normalize_command.add_argument("output")

    merge_command = commands.add_parser("merge")
    merge_command.add_argument("batch_specs_json")
    merge_command.add_argument("expected_page_count", type=int)
    merge_command.add_argument("output")

    validate_command = commands.add_parser("validate")
    validate_command.add_argument("markdown")
    validate_command.add_argument("source_pdf")
    validate_command.add_argument("report")
    validate_command.add_argument("--findings")
    validate_command.add_argument("--audit-manifest")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "inspect":
        _print(inspect_pdf(args.pdf).model_dump(mode="json"))
    elif args.command == "plan":
        info = inspect_pdf(args.pdf)
        plans = propose_split_plans(
            info,
            reliable_pages=args.reliable_pages,
            overlap=args.overlap,
        )
        _print([plan.model_dump(mode="json") for plan in plans])
    elif args.command == "split":
        payload = _load_json(args.plan_json)
        plan = payload[0] if isinstance(payload, list) else payload
        batches = [PageBatch.model_validate(item) for item in plan["batches"]]
        _print(
            [
                batch.model_dump(mode="json")
                for batch in split_pdf(args.pdf, batches, args.output_dir)
            ]
        )
    elif args.command == "normalize":
        _print(
            normalize_batch(
                args.markdown,
                args.content_list,
                args.official_start_page,
                args.output,
            )
        )
    elif args.command == "merge":
        _print(
            merge_batches(
                _load_json(args.batch_specs_json),
                args.output,
                args.expected_page_count,
            )
        )
    elif args.command == "validate":
        result = validate_document(
            args.markdown,
            args.source_pdf,
            args.findings,
            args.audit_manifest,
        )
        report_path = write_validation_report(result, args.report, args.findings)
        _print(
            {
                "status": result.status,
                "report_path": report_path,
                "release_allowed": result.status == "passed",
            }
        )


if __name__ == "__main__":
    main()
