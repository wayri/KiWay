"""Install verified Kilo or legacy payloads into a project-local library."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kilo.errors import ConflictError, KiloError
from kilo.identity import CONTROL_DIRECTORIES
from kilo.kicad.embedded_files import add_embedded_files, make_embedded_file
from kilo.kicad.footprint import footprint_from_text, replace_model_paths
from kilo.kicad.lib_tables import LibraryEntry, LibraryTable
from kilo.kicad.project import Project
from kilo.kicad.schematic import read_schematic, replace_footprints
from kilo.transactions.manager import execute_transaction
from kilo.util.hashing import sha256_bytes, sha256_file
from kilo.util.naming import collision_name, sanitize_name
from kilo.util.paths import kiprjmod_path

from .package_block import read_package


@dataclass(frozen=True)
class InstallSettings:
    nickname: str | None = None
    local_folder: str = "local-libraries"
    model_mode: str = "local-files"
    collision: str = "cancel"
    strict: bool = False


@dataclass
class InstallPlan:
    project: Project
    settings: InstallSettings
    package_manifest: dict[str, Any]
    nickname: str
    outputs: dict[Path, bytes]
    expected_hashes: dict[Path, str | None]
    source_hashes: dict[Path, str]
    actions: list[str]
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "project": self.project.name,
            "package_id": self.package_manifest["package_id"],
            "package_version": self.package_manifest["version"],
            "nickname": self.nickname,
            "model_mode": self.settings.model_mode,
            "actions": self.actions,
            "warnings": self.warnings,
            "files_to_write": [
                path.relative_to(self.project.root).as_posix() for path in self.outputs
            ],
        }


def build_install_plan(
    block_path: Path, project: Project, settings: InstallSettings | None = None
) -> InstallPlan:
    """Verify and plan extraction, relinking, and project-local registration."""

    settings = settings or InstallSettings()
    if settings.model_mode not in {"local-files", "embedded"}:
        raise KiloError(f"unsupported model mode: {settings.model_mode}")
    block, manifest, embedded = read_package(block_path)
    base_nickname = sanitize_name(settings.nickname or f"DB_{manifest['name']}")
    nickname = _choose_nickname(project, base_nickname, settings.collision)
    local_root = project.root / settings.local_folder
    footprint_library = local_root / "footprints" / f"{nickname}.pretty"
    model_library = local_root / "3dmodels" / f"{nickname}.3dshapes"
    block_library = local_root / "design-blocks" / f"{nickname}.kicad_blocks"
    license_directory = local_root / "licenses" / nickname
    installed_block = block_library / f"{sanitize_name(block.name)}.kicad_block"
    outputs: dict[Path, bytes] = {}
    expected: dict[Path, str | None] = {}
    source_hashes = {
        path: sha256_file(path)
        for path in block.root.rglob("*")
        if path.is_file()
    }
    actions: list[str] = []
    warnings: list[str] = list(manifest.get("warnings", []))

    for license_entry in manifest.get("licenses", []):
        destination = license_directory / sanitize_name(license_entry["name"])
        _queue(
            outputs,
            expected,
            destination,
            embedded[license_entry["embedded_file"]],
            settings.collision,
        )
        actions.append(f"Install attribution file {destination.name}")

    models_by_key = {entry["key"]: entry for entry in manifest.get("models", [])}
    installed_model_names: dict[str, str] = {}
    claimed_model_names: dict[str, str] = {}
    for model_entry in manifest.get("models", []):
        filename = sanitize_name(model_entry["filename"])
        key = filename.casefold()
        prior = claimed_model_names.get(key)
        if prior and prior != model_entry["sha256"]:
            source_path = Path(filename)
            filename = (
                f"{collision_name(source_path.stem, model_entry['sha256'])}"
                f"{source_path.suffix.lower()}"
            )
            key = filename.casefold()
        claimed_model_names[key] = model_entry["sha256"]
        installed_model_names[model_entry["key"]] = filename
    footprint_names: dict[str, str] = {}
    for footprint_entry in manifest.get("footprints", []):
        name = sanitize_name(footprint_entry["name"])
        footprint_names[footprint_entry["key"]] = name
        payload = embedded[footprint_entry["embedded_file"]].decode("utf-8")
        footprint = footprint_from_text(payload)
        footprint.document.replace_atom(footprint.document.root.atoms[1], name, quoted=True)
        renamed_text = footprint.document.render()
        footprint = footprint_from_text(renamed_text)
        path_replacements: dict[str, str] = {}
        embedded_models = []
        for model_key in footprint_entry.get("models", []):
            model_entry = models_by_key.get(model_key)
            if model_entry is None:
                if settings.strict:
                    raise KiloError(
                        f"footprint {name} refers to missing model key {model_key}"
                    )
                warnings.append(f"footprint {name} refers to missing model key {model_key}")
                continue
            model_data = embedded[model_entry["embedded_file"]]
            original_paths = model_entry.get("original_paths", [model_entry["original_path"]])
            if settings.model_mode == "embedded":
                filename = installed_model_names[model_key]
                localized_path = f"kicad-embed://{filename}"
                embedded_models.append(make_embedded_file(filename, model_data, "model"))
            else:
                filename = installed_model_names[model_key]
                destination = model_library / filename
                _queue(outputs, expected, destination, model_data, settings.collision)
                localized_path = kiprjmod_path(destination.relative_to(project.root))
            for original_path in original_paths:
                path_replacements[original_path] = localized_path
        localized_text, _ = replace_model_paths(footprint, path_replacements)
        if embedded_models:
            localized_text = add_embedded_files(localized_text, embedded_models)
        destination = footprint_library / f"{name}.kicad_mod"
        _queue(outputs, expected, destination, localized_text.encode("utf-8"), settings.collision)
        actions.append(f"Install footprint {nickname}:{name}")

    # Install a self-contained copy of the selected design block and rewrite its symbols.
    by_schematic: dict[str, list[dict[str, Any]]] = {}
    for mapping in manifest.get("symbol_mappings", []):
        by_schematic.setdefault(mapping["schematic"], []).append(mapping)
    for source in block.root.rglob("*"):
        if not source.is_file() or any(part in CONTROL_DIRECTORIES for part in source.parts):
            continue
        relative = source.relative_to(block.root)
        if relative.as_posix() in by_schematic:
            continue
        destination = installed_block / relative
        _queue(outputs, expected, destination, source.read_bytes(), settings.collision)
    for relative_text, mappings in by_schematic.items():
        source = block.root / relative_text
        schematic = read_schematic(source, mappings[0].get("sheet_path", "/"))
        replacements = {
            (mapping.get("sheet_path", "/"), mapping["symbol_uuid"]): (
                f"{nickname}:{footprint_names[mapping['footprint_key']]}"
            )
            for mapping in mappings
        }
        rendered, changed = replace_footprints(schematic, replacements)
        if changed:
            destination = installed_block / relative_text
            _queue(
                outputs,
                expected,
                destination,
                rendered.encode("utf-8"),
                settings.collision,
            )
            actions.append(f"Rewrite {len(changed)} symbol assignment(s) in installed block")

    fp_table = (
        LibraryTable.read(project.fp_lib_table)
        if project.fp_lib_table.exists()
        else LibraryTable.empty(project.fp_lib_table)
    )
    fp_text, fp_added = fp_table.merged_text(
        LibraryEntry(
            nickname,
            "KiCad",
            kiprjmod_path(footprint_library.relative_to(project.root)),
            description=f"Kilo package {manifest['package_id']} {manifest['version']}",
        )
    )
    if fp_added:
        _queue(
            outputs,
            expected,
            project.fp_lib_table,
            fp_text.encode("utf-8"),
            "upgrade",
        )
        actions.append(f"Add {nickname} to project fp-lib-table")

    design_table_path = project.root / "design-block-lib-table"
    design_table = (
        LibraryTable.read(design_table_path, expected_root="design_block_lib_table")
        if design_table_path.exists()
        else LibraryTable.empty(design_table_path, root_head="design_block_lib_table")
    )
    design_nickname = f"{nickname}_Blocks"
    design_text, design_added = design_table.merged_text(
        LibraryEntry(
            design_nickname,
            "KiCad",
            kiprjmod_path(block_library.relative_to(project.root)),
            description=f"Installed Kilo package {manifest['name']}",
        )
    )
    if design_added:
        _queue(
            outputs,
            expected,
            design_table_path,
            design_text.encode("utf-8"),
            "upgrade",
        )
        actions.append(f"Register design-block library {design_nickname}")
    return InstallPlan(
        project, settings, manifest, nickname, outputs, expected, source_hashes, actions, warnings
    )


def execute_install(plan: InstallPlan) -> dict[str, Any]:
    """Execute an installation as one project transaction."""

    for path, expected in plan.source_hashes.items():
        current = sha256_file(path) if path.exists() else None
        if current != expected:
            raise KiloError(f"package source changed after scan: {path}")
    return execute_transaction(
        project_root=plan.project.root,
        operation="install-block",
        outputs=plan.outputs,
        expected_hashes=plan.expected_hashes,
        metadata={
            "project": {"name": plan.project.name, "root": "."},
            "package": {
                "package_id": plan.package_manifest["package_id"],
                "name": plan.package_manifest["name"],
                "version": plan.package_manifest["version"],
                "nickname": plan.nickname,
            },
            "settings": {
                "local_folder": plan.settings.local_folder,
                "model_mode": plan.settings.model_mode,
            },
            "warnings": plan.warnings,
            "state": {
                "local_folder": plan.settings.local_folder,
                "installed_package": plan.package_manifest["package_id"],
            },
        },
    )


def _choose_nickname(project: Project, base: str, collision: str) -> str:
    table = (
        LibraryTable.read(project.fp_lib_table)
        if project.fp_lib_table.exists()
        else LibraryTable.empty(project.fp_lib_table)
    )
    if table.find(base) is None:
        return base
    if collision == "side-by-side":
        version = 2
        while table.find(f"{base}_v{version}") is not None:
            version += 1
        return f"{base}_v{version}"
    if collision in {"reuse", "upgrade"}:
        return base
    raise ConflictError(
        f"footprint library nickname {base!r} already exists; choose reuse, upgrade, "
        "or side-by-side explicitly"
    )


def _queue(
    outputs: dict[Path, bytes],
    expected: dict[Path, str | None],
    path: Path,
    data: bytes,
    collision: str,
) -> None:
    queued = outputs.get(path)
    if queued is not None:
        if queued != data:
            raise ConflictError(f"two different package payloads target {path}")
        return
    before = sha256_file(path) if path.exists() else None
    after = sha256_bytes(data)
    expected[path] = before
    if before == after:
        return
    if before is not None and collision not in {"upgrade"}:
        raise ConflictError(f"refusing to overwrite different installed content: {path}")
    outputs[path] = data
