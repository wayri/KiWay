"""Project localization planning and execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kilo.dependencies.models import FootprintDependency, ScanResult
from kilo.dependencies.scanner import scan_project
from kilo.errors import ConflictError, KiloError
from kilo.kicad.embedded_files import add_embedded_files, make_embedded_file
from kilo.kicad.footprint import (
    footprint_from_text,
    pad_numbers,
    replace_model_paths,
)
from kilo.kicad.lib_tables import LibraryEntry, LibraryTable
from kilo.kicad.pcb import (
    board_invariants,
    board_invariants_from_text,
    replace_library_links,
)
from kilo.kicad.project import Project
from kilo.kicad.schematic import replace_footprints
from kilo.transactions.manager import execute_transaction
from kilo.util.hashing import sha256_bytes, sha256_file, sha256_text
from kilo.util.naming import collision_name, sanitize_name
from kilo.util.paths import kiprjmod_path


@dataclass(frozen=True)
class LocalizationSettings:
    """Settings persisted in project-local Kilo state."""

    local_folder: str = "local-libraries"
    library_name: str | None = None
    model_mode: str = "local-files"
    strict: bool = False


@dataclass
class LocalizationPlan:
    project: Project
    settings: LocalizationSettings
    scan: ScanResult
    library_name: str
    outputs: dict[Path, bytes]
    expected_hashes: dict[Path, str | None]
    source_hashes: dict[Path, str]
    footprint_mappings: list[dict[str, Any]]
    model_mappings: list[dict[str, Any]]
    actions: list[str]
    warnings: list[str] = field(default_factory=list)
    library_added: bool = False

    def summary(self) -> dict[str, Any]:
        return {
            "project": self.project.name,
            "root": str(self.project.root),
            "kicad_version": self.scan.kicad_version,
            "dependency_counts": self.scan.summary(),
            "library_name": self.library_name,
            "model_mode": self.settings.model_mode,
            "actions": self.actions,
            "warnings": self.warnings,
            "conflicts": self.scan.conflicts,
            "files_to_write": [
                path.relative_to(self.project.root).as_posix() for path in self.outputs
            ],
        }


def build_localization_plan(
    project: Project, settings: LocalizationSettings | None = None
) -> LocalizationPlan:
    """Rescan and construct every output in memory without writing the project."""

    settings = settings or LocalizationSettings()
    if settings.model_mode not in {"local-files", "embedded"}:
        raise KiloError(f"unsupported model mode: {settings.model_mode}")
    scan = scan_project(project)
    if settings.strict and scan.missing:
        missing = ", ".join(item.symbol.footprint for item in scan.missing)
        raise KiloError(f"strict localization aborted; unresolved footprints: {missing}")

    library_name = sanitize_name(settings.library_name or f"{project.name}_Local")
    local_root = project.root / settings.local_folder
    footprint_library = local_root / "footprints" / f"{library_name}.pretty"
    model_library = local_root / "3dmodels" / f"{library_name}.3dshapes"
    outputs: dict[Path, bytes] = {}
    expected_hashes: dict[Path, str | None] = {}
    source_hashes: dict[Path, str] = {}
    footprint_mappings: list[dict[str, Any]] = []
    model_mappings: list[dict[str, Any]] = []
    warnings = list(scan.warnings)
    actions: list[str] = []

    resolved_names = _assign_local_names(scan.resolved, footprint_library)
    model_names: dict[str, str] = {}
    generated_footprints: dict[tuple[str, str], str] = {}
    schematic_replacements: dict[Path, dict[tuple[str, str], str]] = {}
    board_replacements: dict[str, str] = {}

    for index, dependency in enumerate(scan.resolved):
        assert dependency.source_text is not None and dependency.source_sha256 is not None
        if dependency.source_path is not None and dependency.source_path.is_file():
            source_hashes[dependency.source_path] = sha256_file(dependency.source_path)
        local_name = resolved_names[index]
        source_key = (dependency.source_sha256, local_name)
        if source_key not in generated_footprints:
            footprint = footprint_from_text(dependency.source_text)
            path_replacements: dict[str, str] = {}
            embedded_payloads = []
            embedded_names: dict[str, str] = {}
            for model in dependency.models:
                if model.status == "embedded":
                    warnings.append(
                        f"{dependency.name}: existing embedded model {model.original_path!r} "
                        "was retained"
                    )
                    continue
                if model.resolved_path is None or model.source_sha256 is None:
                    if settings.strict:
                        raise KiloError(
                            f"strict localization aborted; model {model.original_path!r} missing"
                        )
                    continue
                source_hashes[model.resolved_path] = model.source_sha256
                if settings.model_mode == "embedded":
                    local_model_name = model.resolved_path.name
                    prior_hash = embedded_names.get(local_model_name.casefold())
                    if prior_hash and prior_hash != model.source_sha256:
                        local_model_name = (
                            f"{collision_name(model.resolved_path.stem, model.source_sha256)}"
                            f"{model.resolved_path.suffix.lower()}"
                        )
                    embedded_key = local_model_name.casefold()
                    if embedded_key not in embedded_names:
                        embedded_names[embedded_key] = model.source_sha256
                        embedded_payloads.append(
                            make_embedded_file(
                                local_model_name, model.resolved_path.read_bytes(), "model"
                            )
                        )
                    localized_path = f"kicad-embed://{local_model_name}"
                    actions.append(
                        f"Embed 3D model {model.resolved_path} in {local_name}.kicad_mod"
                    )
                else:
                    model_key = model.source_sha256
                    file_model_name = model_names.get(model_key)
                    if file_model_name is None:
                        file_model_name = _available_model_name(
                            model.resolved_path.name, model.source_sha256, model_library, outputs
                        )
                        model_names[model_key] = file_model_name
                        destination = model_library / file_model_name
                        data = model.resolved_path.read_bytes()
                        _queue_if_changed(outputs, expected_hashes, destination, data)
                        actions.append(
                            f"Copy 3D model {model.resolved_path} -> "
                            f"{destination.relative_to(project.root)}"
                        )
                    assert file_model_name is not None
                    destination = model_library / file_model_name
                    localized_path = kiprjmod_path(
                        destination.relative_to(project.root)
                    )
                path_replacements[model.original_path] = localized_path
                model_mappings.append(
                    {
                        "footprint": local_name,
                        "original_path": model.original_path,
                        "localized_path": localized_path,
                        "source_sha256": model.source_sha256,
                    }
                )
            localized_text, _ = replace_model_paths(footprint, path_replacements)
            if embedded_payloads:
                localized_text = add_embedded_files(localized_text, embedded_payloads)
            if pad_numbers(footprint_from_text(localized_text)) != pad_numbers(footprint):
                raise KiloError(f"localization changed pad numbering in {dependency.name}")
            target = footprint_library / f"{local_name}.kicad_mod"
            _queue_if_changed(
                outputs, expected_hashes, target, localized_text.encode("utf-8")
            )
            generated_footprints[source_key] = localized_text
            actions.append(
                f"Create localized footprint {target.relative_to(project.root)}"
            )

        localized_id = f"{library_name}:{local_name}"
        symbol = dependency.symbol
        schematic_replacements.setdefault(symbol.file, {})[
            (symbol.sheet_path, symbol.uuid)
        ] = localized_id
        if dependency.board_footprint is not None:
            board_replacements[dependency.board_footprint.uuid] = localized_id
        footprint_mappings.append(
            {
                "symbol_uuid": symbol.uuid,
                "sheet_path": symbol.sheet_path,
                "schematic": symbol.file.relative_to(project.root).as_posix(),
                "reference": symbol.reference,
                "original": symbol.footprint,
                "localized": localized_id,
                "original_name": dependency.name,
                "generated_name": local_name,
                "source": dependency.source_kind,
                "source_sha256": dependency.source_sha256,
                "localized_sha256": sha256_text(generated_footprints[source_key]),
            }
        )

    for schematic in scan.schematics:
        replacements = schematic_replacements.get(schematic.path, {})
        if not replacements:
            continue
        rendered, schematic_changes = replace_footprints(schematic, replacements)
        if schematic_changes:
            _queue_if_changed(
                outputs, expected_hashes, schematic.path, rendered.encode("utf-8")
            )
            actions.append(
                f"Rewrite {len(schematic_changes)} footprint assignment(s) in "
                f"{schematic.path.relative_to(project.root)}"
            )

    pcb_mappings: list[dict[str, str]] = []
    if scan.board is not None and board_replacements:
        rendered, board_changes = replace_library_links(scan.board, board_replacements)
        if board_changes:
            if board_invariants_from_text(rendered) != board_invariants(scan.board):
                raise KiloError("localization changed immutable board structure counts")
            _queue_if_changed(
                outputs, expected_hashes, scan.board.path, rendered.encode("utf-8")
            )
            actions.append(f"Update {len(board_changes)} board footprint library link(s)")
            pcb_mappings = [
                {
                    "footprint_uuid": footprint.uuid,
                    "reference": footprint.reference,
                    "original": footprint.library_id,
                    "localized": localized,
                }
                for footprint, localized in board_changes
            ]

    table = (
        LibraryTable.read(project.fp_lib_table)
        if project.fp_lib_table.exists()
        else LibraryTable.empty(project.fp_lib_table)
    )
    table_entry = LibraryEntry(
        name=library_name,
        type="KiCad",
        uri=kiprjmod_path(footprint_library.relative_to(project.root)),
        description="Localized footprints generated by Kilo — KiCad Localizer",
    )
    table_text, library_added = table.merged_text(table_entry)
    if library_added:
        _queue_if_changed(
            outputs, expected_hashes, project.fp_lib_table, table_text.encode("utf-8")
        )
        actions.append(f"Add {library_name} to project fp-lib-table")

    readme = local_root / "README.md"
    readme_data = (
        "# Project-local KiCad libraries\n\n"
        "Generated and managed by Kilo — KiCad Localizer. Paths use `${KIPRJMOD}`; "
        "do not add these libraries to the global table.\n"
    ).encode("utf-8")
    _queue_if_changed(outputs, expected_hashes, readme, readme_data)
    if readme in outputs:
        actions.append(f"Create {readme.relative_to(project.root)}")

    # Stash board mappings in a private metadata slot consumed during execution.
    plan = LocalizationPlan(
        project=project,
        settings=settings,
        scan=scan,
        library_name=library_name,
        outputs=outputs,
        expected_hashes=expected_hashes,
        source_hashes=source_hashes,
        footprint_mappings=footprint_mappings,
        model_mappings=model_mappings,
        actions=actions,
        warnings=warnings,
        library_added=library_added,
    )
    setattr(plan, "_pcb_mappings", pcb_mappings)
    return plan


def execute_localization(plan: LocalizationPlan) -> dict[str, Any]:
    """Execute a previously built plan after verifying every scanned file hash."""

    for path, expected in plan.source_hashes.items():
        current = sha256_file(path) if path.exists() else None
        if current != expected:
            raise KiloError(
                f"source dependency changed after scan: {path} "
                f"(expected {expected}, found {current})"
            )
    metadata: dict[str, Any] = {
        "project": {
            "name": plan.project.name,
            "root": ".",
            "kicad_version": plan.scan.kicad_version,
        },
        "settings": {
            "local_folder": plan.settings.local_folder,
            "footprint_library": plan.library_name,
            "model_mode": plan.settings.model_mode,
        },
        "footprint_mappings": plan.footprint_mappings,
        "pcb_mappings": getattr(plan, "_pcb_mappings", []),
        "model_mappings": plan.model_mappings,
        "library_table_changes": {
            "added": [plan.library_name] if plan.library_added else [],
            "removed": [],
            "modified": [],
        },
        "warnings": plan.warnings,
        "conflicts": plan.scan.conflicts,
        "state": {
            "local_folder": plan.settings.local_folder,
            "footprint_library": plan.library_name,
            "model_mode": plan.settings.model_mode,
        },
    }
    return execute_transaction(
        project_root=plan.project.root,
        operation="localize-project",
        outputs=plan.outputs,
        metadata=metadata,
        expected_hashes=plan.expected_hashes,
    )


def localize_project(
    project: Project,
    settings: LocalizationSettings | None = None,
    *,
    dry_run: bool = False,
) -> LocalizationPlan | dict[str, Any]:
    """Convenience API that always rescans immediately before planning."""

    plan = build_localization_plan(project, settings)
    return plan if dry_run else execute_localization(plan)


def _assign_local_names(
    dependencies: list[FootprintDependency], library: Path
) -> dict[int, str]:
    assignments: dict[int, str] = {}
    claimed: dict[str, str] = {}
    existing_hashes: dict[str, str] = {}
    if library.exists():
        for path in library.glob("*.kicad_mod"):
            existing_hashes[path.stem] = sha256_file(path)
    for index, dependency in enumerate(dependencies):
        assert dependency.source_sha256 is not None
        base = sanitize_name(dependency.name)
        candidate = base
        prior = claimed.get(candidate)
        existing = existing_hashes.get(candidate)
        if (prior and prior != dependency.source_sha256) or (
            existing and existing != dependency.source_sha256
        ):
            candidate = collision_name(base, dependency.source_sha256)
        while candidate in claimed and claimed[candidate] != dependency.source_sha256:
            candidate = collision_name(candidate, dependency.source_sha256)
        claimed[candidate] = dependency.source_sha256
        assignments[index] = candidate
    return assignments


def _available_model_name(
    name: str,
    digest: str,
    directory: Path,
    outputs: dict[Path, bytes],
) -> str:
    stem = sanitize_name(Path(name).stem)
    suffix = Path(name).suffix.lower()
    candidate = f"{stem}{suffix}"
    path = directory / candidate
    queued = outputs.get(path)
    if path.exists() and sha256_file(path) != digest:
        candidate = f"{collision_name(stem, digest)}{suffix}"
    elif queued is not None and sha256_bytes(queued) != digest:
        candidate = f"{collision_name(stem, digest)}{suffix}"
    return candidate


def _queue_if_changed(
    outputs: dict[Path, bytes],
    expected_hashes: dict[Path, str | None],
    path: Path,
    data: bytes,
) -> None:
    before = sha256_file(path) if path.exists() else None
    expected_hashes[path] = before
    if before != sha256_bytes(data):
        if path in outputs and outputs[path] != data:
            raise ConflictError(f"two different outputs target {path}")
        outputs[path] = data
