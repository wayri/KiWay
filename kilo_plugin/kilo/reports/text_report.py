"""Concise human-readable reports."""

from __future__ import annotations

from typing import Any


def render_scan(data: dict[str, Any]) -> str:
    counts = data["summary"]
    lines = [
        f"Project: {data['project']}",
        f"KiCad version: {data.get('kicad_version') or 'not detected'}",
        "",
        f"Symbols with footprints: {counts['symbols_with_footprints']}",
        f"Resolved footprints: {counts['resolved_footprints']}",
        f"Missing footprints: {counts['missing_footprints']}",
        f"Unique footprints: {counts['unique_footprints']}",
        f"3D model references: {counts['model_references']}",
        f"Resolved 3D models: {counts['resolved_models']}",
        f"Missing 3D models: {counts['missing_models']}",
    ]
    if data.get("warnings"):
        lines.extend(["", "Warnings:", *[f"- {item}" for item in data["warnings"]]])
    if data.get("conflicts"):
        lines.extend(["", "Conflicts:", *[f"- {item}" for item in data["conflicts"]]])
    return "\n".join(lines) + "\n"


def render_plan(data: dict[str, Any]) -> str:
    counts = data["dependency_counts"]
    lines = [
        f"Project: {data['project']}",
        f"KiCad version: {data.get('kicad_version') or 'not detected'}",
        "",
        f"Footprints found: {counts['symbols_with_footprints']}",
        f"Unique footprints: {counts['unique_footprints']}",
        f"3D model references: {counts['model_references']}",
        f"Unique 3D models: {counts['unique_models']}",
        "",
        "Actions:",
        *[f"- {item}" for item in data["actions"]],
    ]
    if data.get("warnings"):
        lines.extend(["", "Warnings:", *[f"- {item}" for item in data["warnings"]]])
    return "\n".join(lines) + "\n"
