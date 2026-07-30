"""Typed dependency-scan models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from kilo.kicad.pcb import BoardFile, BoardFootprint
from kilo.kicad.schematic import SchematicFile, SchematicSymbol


@dataclass
class ModelDependency:
    original_path: str
    resolved_path: Path | None
    status: str
    source_parent: Path
    source_sha256: str | None = None


@dataclass
class FootprintDependency:
    symbol: SchematicSymbol
    nickname: str
    name: str
    status: str
    source_kind: str | None
    source_path: Path | None
    source_text: str | None
    source_sha256: str | None
    board_footprint: BoardFootprint | None
    library_sha256: str | None = None
    board_sha256: str | None = None
    conflict: str | None = None
    models: list[ModelDependency] = field(default_factory=list)


@dataclass
class ScanResult:
    project_name: str
    project_root: Path
    kicad_version: str | None
    schematics: list[SchematicFile]
    board: BoardFile | None
    dependencies: list[FootprintDependency]
    warnings: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> list[FootprintDependency]:
        return [item for item in self.dependencies if item.status == "resolved"]

    @property
    def missing(self) -> list[FootprintDependency]:
        return [item for item in self.dependencies if item.status != "resolved"]

    def summary(self) -> dict[str, int]:
        unique_footprints = {
            item.source_sha256 for item in self.resolved if item.source_sha256 is not None
        }
        models = [model for item in self.resolved for model in item.models]
        unique_models = {
            model.source_sha256 for model in models if model.source_sha256 is not None
        }
        return {
            "symbols_with_footprints": len(self.dependencies),
            "resolved_footprints": len(self.resolved),
            "missing_footprints": len(self.missing),
            "unique_footprints": len(unique_footprints),
            "model_references": len(models),
            "resolved_models": sum(model.resolved_path is not None for model in models),
            "missing_models": sum(model.resolved_path is None for model in models),
            "unique_models": len(unique_models),
        }
