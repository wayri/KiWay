"""Explicit dry-run-first project dependency repair."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kilo.kicad.project import Project
from kilo.transactions.manager import execute_transaction

from .localize import LocalizationPlan, LocalizationSettings, build_localization_plan


@dataclass
class RepairPlan:
    """A repair is an incremental localization plan with separate history semantics."""

    localization: LocalizationPlan

    def summary(self) -> dict[str, Any]:
        data = self.localization.summary()
        data["operation"] = "repair-project"
        return data


def build_repair_plan(
    project: Project, settings: LocalizationSettings | None = None
) -> RepairPlan:
    """Plan recovery from board geometry and reconstruction of local dependencies."""

    return RepairPlan(build_localization_plan(project, settings))


def execute_repair(plan: RepairPlan) -> dict[str, Any]:
    """Execute only the actions displayed by :func:`build_repair_plan`."""

    local = plan.localization
    return execute_transaction(
        project_root=local.project.root,
        operation="repair-project",
        outputs=local.outputs,
        expected_hashes=local.expected_hashes,
        metadata={
            "project": {
                "name": local.project.name,
                "root": ".",
                "kicad_version": local.scan.kicad_version,
            },
            "settings": {
                "local_folder": local.settings.local_folder,
                "footprint_library": local.library_name,
                "model_mode": local.settings.model_mode,
            },
            "footprint_mappings": local.footprint_mappings,
            "model_mappings": local.model_mappings,
            "warnings": local.warnings,
            "conflicts": local.scan.conflicts,
            "state": {
                "local_folder": local.settings.local_folder,
                "footprint_library": local.library_name,
                "model_mode": local.settings.model_mode,
            },
        },
    )
