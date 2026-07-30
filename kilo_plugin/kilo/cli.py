"""Command-line interface for automation and testing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from kilo.dependencies.scanner import scan_project
from kilo.errors import KiloError
from kilo.identity import CLI_NAME, SCAN_SCHEMA
from kilo.kicad.project import discover_project
from kilo.operations.install_block import (
    InstallSettings,
    build_install_plan,
    execute_install,
)
from kilo.operations.localize import LocalizationSettings, localize_project
from kilo.operations.package_block import (
    PackageSettings,
    build_package_plan,
    execute_package,
)
from kilo.operations.repair import build_repair_plan, execute_repair
from kilo.operations.unlocalize import (
    RestoreSettings,
    build_restore_plan,
    execute_restore,
)
from kilo.operations.validate import validate_project
from kilo.reports.html_report import render_validation_html
from kilo.reports.json_report import render_json
from kilo.reports.text_report import render_plan, render_scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=CLI_NAME)
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan-project", help="scan project dependencies")
    scan.add_argument("project", type=Path)
    scan.add_argument("--json", action="store_true")

    localize = subparsers.add_parser(
        "localize-project", help="create a project-local footprint/model library"
    )
    localize.add_argument("project", type=Path)
    localize.add_argument("--library-name")
    localize.add_argument("--local-folder", default="local-libraries")
    localize.add_argument(
        "--model-mode", choices=["local-files", "embedded"], default="local-files"
    )
    _add_write_flags(localize)

    validate = subparsers.add_parser("validate-project", help="read-only validation")
    validate.add_argument("project", type=Path)
    validate.add_argument("--report", type=Path)
    validate.add_argument("--json", action="store_true")

    unlocalize = subparsers.add_parser(
        "unlocalize-project", help="restore links or original files from a transaction"
    )
    unlocalize.add_argument("project", type=Path)
    unlocalize.add_argument("--transaction")
    unlocalize.add_argument(
        "--restore-mode", choices=["links-only", "original-files"], default="links-only"
    )
    unlocalize.add_argument("--force", action="store_true")
    unlocalize.add_argument("--symbol-uuid", action="append", default=[])
    unlocalize.add_argument("--sheet", action="append", default=[])
    _add_write_flags(unlocalize)

    package = subparsers.add_parser("package-block", help="package a portable design block")
    package.add_argument("block", type=Path)
    package.add_argument("--output", type=Path)
    package.add_argument("--package-id")
    package.add_argument("--name")
    package.add_argument("--package-version", default="1.0.0")
    _add_write_flags(package)

    install = subparsers.add_parser("install-block", help="install a portable design block")
    install.add_argument("block", type=Path)
    install.add_argument("--project", required=True, type=Path)
    install.add_argument("--nickname")
    install.add_argument("--local-folder", default="local-libraries")
    install.add_argument("--model-mode", choices=["local-files", "embedded"], default="local-files")
    install.add_argument(
        "--collision",
        choices=["cancel", "reuse", "upgrade", "side-by-side"],
        default="cancel",
    )
    _add_write_flags(install)

    repair = subparsers.add_parser("repair-project", help="repair project dependencies")
    repair.add_argument("project", type=Path)
    _add_write_flags(repair)
    return parser


def _add_write_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--strict", action="store_true")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan-project":
            scan = scan_project(discover_project(args.project))
            data = {
                "schema": SCAN_SCHEMA,
                "project": scan.project_name,
                "root": str(scan.project_root),
                "kicad_version": scan.kicad_version,
                "summary": scan.summary(),
                "warnings": scan.warnings,
                "conflicts": scan.conflicts,
                "dependencies": [_dependency_dict(item) for item in scan.dependencies],
            }
            sys.stdout.write(render_json(data) if args.json else render_scan(data))
            return 2 if scan.missing else 0
        if args.command == "localize-project":
            project = discover_project(args.project)
            settings = LocalizationSettings(
                local_folder=args.local_folder,
                library_name=args.library_name,
                model_mode=args.model_mode,
                strict=args.strict,
            )
            localization_result = localize_project(project, settings, dry_run=args.dry_run)
            if args.dry_run:
                assert not isinstance(localization_result, dict)
                data = localization_result.summary()
                sys.stdout.write(render_json(data) if args.json else render_plan(data))
            else:
                assert isinstance(localization_result, dict)
                data = localization_result
                sys.stdout.write(
                    render_json(data)
                    if args.json
                    else f"Localization completed: {data['transaction_id']}\n"
                )
            return 0
        if args.command == "validate-project":
            validation_result = validate_project(discover_project(args.project))
            data = validation_result.to_dict()
            if args.report:
                report = args.report.resolve()
                report.parent.mkdir(parents=True, exist_ok=True)
                report.write_text(render_validation_html(data), encoding="utf-8")
            sys.stdout.write(
                render_json(data)
                if args.json
                else (
                    f"Project: {validation_result.project}\n"
                    f"Result: {'valid' if validation_result.valid else 'errors found'}\n"
                    f"Issues: {len(validation_result.issues)}\n"
                )
            )
            return 0 if validation_result.valid else 2
        if args.command == "unlocalize-project":
            restore_plan = build_restore_plan(
                discover_project(args.project),
                RestoreSettings(
                    transaction_id=args.transaction,
                    restore_mode=args.restore_mode,
                    force=args.force,
                    selected_symbol_uuids=(
                        frozenset(args.symbol_uuid) if args.symbol_uuid else None
                    ),
                    selected_sheets=frozenset(args.sheet) if args.sheet else None,
                ),
            )
            if args.dry_run:
                data = restore_plan.summary()
            else:
                data = execute_restore(restore_plan)
            sys.stdout.write(
                render_json(data)
                if args.json
                else (
                    "\n".join(f"- {action}" for action in restore_plan.actions) + "\n"
                    if args.dry_run
                    else f"Un-localization completed: {data['transaction_id']}\n"
                )
            )
            return 0
        if args.command == "package-block":
            package_plan = build_package_plan(
                args.block,
                PackageSettings(
                    output=args.output,
                    package_id=args.package_id,
                    package_name=args.name,
                    version=args.package_version,
                    strict=args.strict,
                ),
            )
            data = package_plan.summary() if args.dry_run else execute_package(package_plan)
            sys.stdout.write(
                render_json(data)
                if args.json
                else (
                    "\n".join(f"- {action}" for action in package_plan.actions) + "\n"
                    if args.dry_run
                    else f"Packaging completed: {data['transaction_id']}\n"
                )
            )
            return 0
        if args.command == "install-block":
            install_plan = build_install_plan(
                args.block,
                discover_project(args.project),
                InstallSettings(
                    nickname=args.nickname,
                    local_folder=args.local_folder,
                    model_mode=args.model_mode,
                    collision=args.collision,
                    strict=args.strict,
                ),
            )
            data = install_plan.summary() if args.dry_run else execute_install(install_plan)
            sys.stdout.write(
                render_json(data)
                if args.json
                else (
                    "\n".join(f"- {action}" for action in install_plan.actions) + "\n"
                    if args.dry_run
                    else f"Installation completed: {data['transaction_id']}\n"
                )
            )
            return 0
        if args.command == "repair-project":
            repair_plan = build_repair_plan(
                discover_project(args.project),
                LocalizationSettings(strict=args.strict),
            )
            data = repair_plan.summary() if args.dry_run else execute_repair(repair_plan)
            sys.stdout.write(
                render_json(data)
                if args.json
                else (
                    "\n".join(
                        f"- {action}"
                        for action in repair_plan.localization.actions
                    )
                    + "\n"
                    if args.dry_run
                    else f"Repair completed: {data['transaction_id']}\n"
                )
            )
            return 0
        raise AssertionError(f"unhandled command: {args.command}")
    except (KiloError, OSError, ValueError) as exc:
        if getattr(args, "json", False):
            sys.stdout.write(json.dumps({"error": str(exc)}, indent=2) + "\n")
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1


def _dependency_dict(item: Any) -> dict[str, Any]:
    return {
        "symbol_uuid": item.symbol.uuid,
        "reference": item.symbol.reference,
        "sheet_path": item.symbol.sheet_path,
        "original": item.symbol.footprint,
        "nickname": item.nickname,
        "name": item.name,
        "status": item.status,
        "source": item.source_kind,
        "source_path": str(item.source_path) if item.source_path else None,
        "source_sha256": item.source_sha256,
        "conflict": item.conflict,
        "models": [
            {
                "original_path": model.original_path,
                "resolved_path": str(model.resolved_path) if model.resolved_path else None,
                "status": model.status,
                "source_sha256": model.source_sha256,
            }
            for model in item.models
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
