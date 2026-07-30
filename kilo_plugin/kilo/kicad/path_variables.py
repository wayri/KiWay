"""KiCad and project path-variable collection."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any, Mapping

from .project import Project, read_project_json


def collect_path_variables(
    project: Project,
    *,
    environment: Mapping[str, str] | None = None,
    version_major: int = 10,
) -> dict[str, str]:
    """Collect explicit environment, project, and installed KiCad path variables."""

    variables = dict(environment or os.environ)
    variables["KIPRJMOD"] = str(project.root)
    variables.update(_global_kicad_variables(version_major))
    project_data = read_project_json(project)
    env_node = project_data.get("environment", {})
    if isinstance(env_node, dict):
        project_vars: Any = env_node.get("vars", {})
        if isinstance(project_vars, dict):
            variables.update(
                {str(key): str(value) for key, value in project_vars.items() if value is not None}
            )

    if platform.system() == "Windows":
        program_files = Path(variables.get("ProgramFiles", r"C:\Program Files"))
        install = program_files / "KiCad" / f"{version_major}.0" / "share" / "kicad"
        if install.exists():
            variables.setdefault(f"KICAD{version_major}_FOOTPRINT_DIR", str(install / "footprints"))
            variables.setdefault(f"KICAD{version_major}_3DMODEL_DIR", str(install / "3dmodels"))
            variables.setdefault(f"KICAD{version_major}_SYMBOL_DIR", str(install / "symbols"))
            # KiCad retains compatibility with older official-library variables.
            for legacy_major in range(6, version_major):
                variables.setdefault(
                    f"KICAD{legacy_major}_FOOTPRINT_DIR", str(install / "footprints")
                )
                variables.setdefault(
                    f"KICAD{legacy_major}_3DMODEL_DIR", str(install / "3dmodels")
                )
                variables.setdefault(
                    f"KICAD{legacy_major}_SYMBOL_DIR", str(install / "symbols")
                )
        documents = Path(variables.get("USERPROFILE", str(Path.home()))) / "Documents"
        variables.setdefault(
            f"KICAD{version_major}_3RD_PARTY",
            str(documents / "KiCad" / f"{version_major}.0" / "3rdparty"),
        )
        for legacy_major in range(6, version_major):
            variables.setdefault(
                f"KICAD{legacy_major}_3RD_PARTY",
                str(documents / "KiCad" / f"{legacy_major}.0" / "3rdparty"),
            )
    return variables


def _global_kicad_variables(version_major: int) -> dict[str, str]:
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        config = (
            Path(appdata) / "kicad" / f"{version_major}.0" / "kicad_common.json"
            if appdata
            else None
        )
    elif platform.system() == "Darwin":
        config = (
            Path.home()
            / "Library"
            / "Preferences"
            / "kicad"
            / f"{version_major}.0"
            / "kicad_common.json"
        )
    else:
        config = (
            Path.home()
            / ".config"
            / "kicad"
            / f"{version_major}.0"
            / "kicad_common.json"
        )
    if config is None or not config.exists():
        return {}
    try:
        data = json.loads(config.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    environment_node = data.get("environment", {}) if isinstance(data, dict) else {}
    values = environment_node.get("vars", {}) if isinstance(environment_node, dict) else {}
    return (
        {str(key): str(value) for key, value in values.items() if value is not None}
        if isinstance(values, dict)
        else {}
    )
