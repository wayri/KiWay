"""Read-only project validation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kilo.dependencies.scanner import scan_project
from kilo.identity import VALIDATION_SCHEMA, existing_control_paths
from kilo.kicad.footprint import read_footprint
from kilo.kicad.lib_tables import LibraryTable
from kilo.kicad.path_variables import collect_path_variables
from kilo.kicad.project import Project
from kilo.transactions.manifest import read_manifest
from kilo.util.paths import resolve_existing_path


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass
class ValidationResult:
    project: str
    root: str
    kicad_version: str | None
    summary: dict[str, int]
    issues: list[ValidationIssue]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": VALIDATION_SCHEMA,
            "project": self.project,
            "root": self.root,
            "kicad_version": self.kicad_version,
            "valid": self.valid,
            "summary": self.summary,
            "issues": [asdict(issue) for issue in self.issues],
        }


def validate_project(project: Project) -> ValidationResult:
    """Validate resolution, local tables, models, and Kilo metadata."""

    scan = scan_project(project)
    issues: list[ValidationIssue] = []
    for dependency in scan.missing:
        issues.append(
            ValidationIssue(
                "error",
                "footprint-unresolved",
                f"{dependency.symbol.reference or dependency.symbol.uuid}: "
                f"{dependency.symbol.footprint!r} does not resolve",
                str(dependency.symbol.file),
            )
        )
    for dependency in scan.resolved:
        for model in dependency.models:
            if model.status == "missing":
                issues.append(
                    ValidationIssue(
                        "warning",
                        "model-unresolved",
                        f"{dependency.symbol.reference or dependency.symbol.uuid}: "
                        f"{model.original_path!r} does not resolve",
                        str(dependency.source_path) if dependency.source_path else None,
                    )
                )
    issues.extend(_validate_table(project))
    issues.extend(_validate_manifests(project))
    issues.extend(_validate_installed_packages(project))
    return ValidationResult(
        project=project.name,
        root=str(project.root),
        kicad_version=scan.kicad_version,
        summary=scan.summary(),
        issues=issues,
    )


def _validate_table(project: Project) -> list[ValidationIssue]:
    if not project.fp_lib_table.exists():
        return []
    variables = collect_path_variables(project)
    table = LibraryTable.read(project.fp_lib_table)
    issues: list[ValidationIssue] = []
    names: dict[str, str] = {}
    for entry in table.entries:
        if entry.name in names and names[entry.name] != entry.uri:
            issues.append(
                ValidationIssue(
                    "error",
                    "duplicate-nickname",
                    f"{entry.name!r} maps to conflicting paths",
                    str(project.fp_lib_table),
                )
            )
        names[entry.name] = entry.uri
        if entry.disabled or entry.type.casefold() == "table":
            continue
        resolved = resolve_existing_path(
            entry.uri,
            variables,
            project_root=project.root,
            source_parent=project.root,
        )
        if resolved is None:
            issues.append(
                ValidationIssue(
                    "error",
                    "library-path-missing",
                    f"library {entry.name!r} path {entry.uri!r} does not exist",
                    str(project.fp_lib_table),
                )
            )
        elif resolved.is_dir():
            for footprint in resolved.glob("*.kicad_mod"):
                try:
                    read_footprint(footprint)
                except Exception as exc:
                    issues.append(
                        ValidationIssue(
                            "error",
                            "footprint-invalid",
                            f"{footprint.name}: {exc}",
                            str(footprint),
                        )
                    )
    return issues


def _validate_manifests(project: Project) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for control in existing_control_paths(project.root):
        for path in (control / "backups").glob("*/transaction.json"):
            try:
                read_manifest(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                issues.append(
                    ValidationIssue(
                        "error",
                        "transaction-invalid",
                        str(exc),
                        str(path),
                    )
                )
    return issues


def _validate_installed_packages(project: Project) -> list[ValidationIssue]:
    from kilo.operations.package_block import read_package

    root = project.root / "local-libraries" / "design-blocks"
    if not root.exists():
        return []
    issues: list[ValidationIssue] = []
    for block in root.rglob("*.kicad_block"):
        try:
            read_package(block)
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    "error",
                    "package-invalid",
                    str(exc),
                    str(block),
                )
            )
    return issues
