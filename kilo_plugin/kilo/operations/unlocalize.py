"""Conflict-aware link-only and byte-for-byte full-file restoration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kilo.errors import ConflictError, KiloError
from kilo.identity import existing_control_paths
from kilo.kicad.footprint import footprint_from_text, replace_model_paths
from kilo.kicad.lib_tables import LibraryTable
from kilo.kicad.pcb import read_board, replace_library_links
from kilo.kicad.project import Project
from kilo.kicad.schematic import read_schematic, replace_footprints
from kilo.transactions.manager import execute_transaction
from kilo.transactions.manifest import read_manifest
from kilo.util.hashing import sha256_file
from kilo.util.paths import kiprjmod_path


@dataclass(frozen=True)
class RestoreSettings:
    transaction_id: str | None = None
    restore_mode: str = "links-only"
    force: bool = False
    selected_symbol_uuids: frozenset[str] | None = None
    selected_sheets: frozenset[str] | None = None


@dataclass
class RestorePlan:
    project: Project
    source_manifest: dict[str, Any]
    settings: RestoreSettings
    outputs: dict[Path, bytes]
    expected_hashes: dict[Path, str | None]
    actions: list[str]
    warnings: list[str]

    def summary(self) -> dict[str, Any]:
        return {
            "project": self.project.name,
            "source_transaction": self.source_manifest["transaction_id"],
            "restore_mode": self.settings.restore_mode,
            "actions": self.actions,
            "warnings": self.warnings,
            "files_to_write": [
                path.relative_to(self.project.root).as_posix() for path in self.outputs
            ],
        }


def list_restore_points(project: Project) -> list[dict[str, Any]]:
    """List readable completed localization transactions newest first."""

    output: list[dict[str, Any]] = []
    for control in existing_control_paths(project.root):
        for path in (control / "backups").glob("*/transaction.json"):
            try:
                manifest = read_manifest(path)
            except (OSError, ValueError):
                continue
            if (
                manifest.get("operation") == "localize-project"
                and manifest.get("status") == "completed"
            ):
                output.append(manifest)
    return sorted(output, key=lambda item: item["transaction_id"], reverse=True)


def build_restore_plan(project: Project, settings: RestoreSettings | None = None) -> RestorePlan:
    """Build a non-destructive restore plan against current file hashes."""

    settings = settings or RestoreSettings()
    points = list_restore_points(project)
    manifest = next(
        (
            item
            for item in points
            if settings.transaction_id is None
            or item["transaction_id"] == settings.transaction_id
        ),
        None,
    )
    if manifest is None:
        raise KiloError("no matching completed localization restore point")
    if settings.restore_mode == "original-files":
        return _plan_full_restore(project, manifest, settings)
    if settings.restore_mode != "links-only":
        raise KiloError(f"unsupported restore mode: {settings.restore_mode}")
    return _plan_links_restore(project, manifest, settings)


def execute_restore(plan: RestorePlan) -> dict[str, Any]:
    """Execute a restore as a new reversible transaction."""

    return execute_transaction(
        project_root=plan.project.root,
        operation="unlocalize-project",
        outputs=plan.outputs,
        expected_hashes=plan.expected_hashes,
        metadata={
            "project": {"name": plan.project.name, "root": "."},
            "settings": {
                "restore_mode": plan.settings.restore_mode,
                "source_transaction": plan.source_manifest["transaction_id"],
            },
            "warnings": plan.warnings,
            "state": {"last_restore_source": plan.source_manifest["transaction_id"]},
        },
    )


def _plan_full_restore(
    project: Project, manifest: dict[str, Any], settings: RestoreSettings
) -> RestorePlan:
    transaction_root = _find_transaction_root(project, manifest["transaction_id"])
    outputs: dict[Path, bytes] = {}
    expected: dict[Path, str | None] = {}
    actions: list[str] = []
    warnings: list[str] = []
    for file_info in manifest.get("files", []):
        backup_path = file_info.get("backup_path")
        if not backup_path:
            continue
        destination = project.root / file_info["path"]
        backup = transaction_root / backup_path
        if not backup.exists():
            raise KiloError(f"restore backup is missing: {backup}")
        current = sha256_file(destination) if destination.exists() else None
        localized = file_info.get("after_sha256")
        if current != localized and not settings.force:
            raise ConflictError(
                f"{file_info['path']} changed after localization "
                f"(localized {localized}, current {current}); use links-only or explicit force"
            )
        if current != localized:
            warnings.append(
                f"full-file restore will overwrite later changes in {file_info['path']}"
            )
        outputs[destination] = backup.read_bytes()
        expected[destination] = current
        actions.append(f"Restore original file {file_info['path']}")
    return RestorePlan(project, manifest, settings, outputs, expected, actions, warnings)


def _find_transaction_root(project: Project, transaction_id: str) -> Path:
    for control in existing_control_paths(project.root):
        transaction_root = control / "backups" / transaction_id
        if (transaction_root / "transaction.json").is_file():
            return transaction_root
    raise KiloError(f"restore transaction directory is missing: {transaction_id}")


def _plan_links_restore(
    project: Project, manifest: dict[str, Any], settings: RestoreSettings
) -> RestorePlan:
    outputs: dict[Path, bytes] = {}
    expected: dict[Path, str | None] = {}
    actions: list[str] = []
    warnings: list[str] = []
    by_schematic: dict[Path, list[dict[str, Any]]] = {}
    for mapping in manifest.get("footprint_mappings", []):
        if (
            settings.selected_symbol_uuids
            and mapping["symbol_uuid"] not in settings.selected_symbol_uuids
        ):
            continue
        if settings.selected_sheets and mapping["sheet_path"] not in settings.selected_sheets:
            continue
        path = project.root / mapping["schematic"]
        by_schematic.setdefault(path, []).append(mapping)

    for path, mappings in by_schematic.items():
        schematic = read_schematic(path, mappings[0]["sheet_path"])
        schematic_replacements: dict[tuple[str, str], str] = {}
        current_by_uuid = {symbol.uuid: symbol for symbol in schematic.symbols}
        for mapping in mappings:
            symbol = current_by_uuid.get(mapping["symbol_uuid"])
            if symbol is None:
                warnings.append(f"{path.name}: symbol {mapping['symbol_uuid']} no longer exists")
                continue
            if symbol.footprint != mapping["localized"] and not settings.force:
                warnings.append(
                    f"{path.name}:{symbol.reference}: footprint changed after localization; skipped"
                )
                continue
            schematic_replacements[(symbol.sheet_path, symbol.uuid)] = mapping["original"]
        rendered, schematic_changes = replace_footprints(schematic, schematic_replacements)
        if schematic_changes:
            outputs[path] = rendered.encode("utf-8")
            expected[path] = sha256_file(path)
            actions.append(
                f"Restore {len(schematic_changes)} schematic footprint link(s) in {path.name}"
            )

    pcb_mappings = manifest.get("pcb_mappings", [])
    if project.board and project.board.exists() and pcb_mappings:
        board = read_board(project.board)
        board_by_uuid = {footprint.uuid: footprint for footprint in board.footprints}
        board_replacements: dict[str, str] = {}
        for mapping in pcb_mappings:
            footprint = board_by_uuid.get(mapping["footprint_uuid"])
            if footprint is None:
                warnings.append(
                    f"{project.board.name}: footprint {mapping['footprint_uuid']} no longer exists"
                )
                continue
            if footprint.library_id != mapping["localized"] and not settings.force:
                warnings.append(
                    f"{project.board.name}:{footprint.reference}: library link changed; skipped"
                )
                continue
            board_replacements[footprint.uuid] = mapping["original"]
        rendered, board_changes = replace_library_links(board, board_replacements)
        if board_changes:
            outputs[project.board] = rendered.encode("utf-8")
            expected[project.board] = sha256_file(project.board)
            actions.append(f"Restore {len(board_changes)} board footprint link(s)")

    partial = settings.selected_symbol_uuids is not None or settings.selected_sheets is not None
    _plan_model_path_restore(
        project,
        manifest,
        settings,
        outputs,
        expected,
        actions,
        warnings,
        set() if partial else None,
    )
    table_changes = manifest.get("library_table_changes", {})
    for nickname in table_changes.get("added", []):
        marker = f'"{nickname}:'
        relevant_files = {
            project.root / mapping["schematic"]
            for mapping in manifest.get("footprint_mappings", [])
        }
        if project.board:
            relevant_files.add(project.board)
        still_referenced = False
        for relevant in relevant_files:
            data = outputs.get(relevant)
            text = (
                data.decode("utf-8")
                if data is not None
                else (
                    relevant.read_text(encoding="utf-8-sig")
                    if relevant.exists()
                    else ""
                )
            )
            if marker in text:
                still_referenced = True
                break
        if still_referenced:
            warnings.append(
                f"kept {nickname} in fp-lib-table because localized references remain"
            )
            continue
        if not project.fp_lib_table.exists():
            warnings.append("project fp-lib-table is missing; local entry could not be removed")
            continue
        table = LibraryTable.read(project.fp_lib_table)
        local_folder = manifest.get("settings", {}).get("local_folder", "local-libraries")
        expected_uri = kiprjmod_path(
            Path(local_folder) / "footprints" / f"{nickname}.pretty"
        )
        try:
            rendered, removed = table.without_entry_text(nickname, expected_uri=expected_uri)
        except ConflictError as exc:
            warnings.append(str(exc))
            continue
        if removed:
            outputs[project.fp_lib_table] = rendered.encode("utf-8")
            expected[project.fp_lib_table] = sha256_file(project.fp_lib_table)
            actions.append(f"Remove {nickname} from project fp-lib-table")
    return RestorePlan(project, manifest, settings, outputs, expected, actions, warnings)


def _plan_model_path_restore(
    project: Project,
    manifest: dict[str, Any],
    settings: RestoreSettings,
    outputs: dict[Path, bytes],
    expected: dict[Path, str | None],
    actions: list[str],
    warnings: list[str],
    selected_footprints: set[str] | None,
) -> None:
    local_folder = manifest.get("settings", {}).get("local_folder", "local-libraries")
    nickname = manifest.get("settings", {}).get("footprint_library")
    if not nickname:
        return
    library = project.root / local_folder / "footprints" / f"{nickname}.pretty"
    by_footprint: dict[str, list[dict[str, Any]]] = {}
    for mapping in manifest.get("model_mappings", []):
        by_footprint.setdefault(mapping["footprint"], []).append(mapping)
    for name, mappings in by_footprint.items():
        if selected_footprints is not None and name not in selected_footprints:
            continue
        path = library / f"{name}.kicad_mod"
        if not path.exists():
            warnings.append(f"localized footprint {path} is missing; model links not restored")
            continue
        footprint = footprint_from_text(path.read_text(encoding="utf-8-sig"), path)
        replacements: dict[str, str] = {}
        current_paths = {model.path for model in footprint.models}
        for mapping in mappings:
            if mapping["localized_path"] in current_paths:
                replacements[mapping["localized_path"]] = mapping["original_path"]
            elif not settings.force:
                warnings.append(f"{path.name}: model path changed after localization; skipped")
        rendered, changed = replace_model_paths(footprint, replacements)
        if changed:
            outputs[path] = rendered.encode("utf-8")
            expected[path] = sha256_file(path)
            actions.append(f"Restore {len(changed)} model link(s) in {path.name}")
