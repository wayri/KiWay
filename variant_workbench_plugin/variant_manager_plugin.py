#!/usr/bin/env python3
"""KiCad IPC launcher for Design Variant Workbench.

The IPC action only discovers the active KiCad project, then starts the actual
Workbench as a detached process.  Detaching is deliberate: Default/variant
writes require KiCad to release the project files, and the Workbench must stay
open while the user closes KiCad before pressing Apply.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Optional, Tuple


def _root_from_project_file(project_file: Path) -> Optional[Path]:
    project_file = project_file.expanduser().resolve()
    same_stem = project_file.with_suffix('.kicad_sch')
    if same_stem.exists():
        return same_stem
    try:
        data = json.loads(project_file.read_text(encoding='utf-8'))
    except Exception:
        return None
    schematic = data.get('schematic', {}) if isinstance(data, dict) else {}
    top = schematic.get('top_level_sheets', []) if isinstance(schematic, dict) else []
    if isinstance(top, list):
        for entry in top:
            if not isinstance(entry, dict):
                continue
            filename = entry.get('filename')
            if not isinstance(filename, str) or not filename.strip():
                continue
            raw = filename.replace('${KIPRJMOD}', str(project_file.parent))
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = project_file.parent / candidate
            if candidate.exists():
                return candidate.resolve()
    return None


def detect_active_root() -> Tuple[Optional[str], str]:
    try:
        from kipy import KiCad
        client = KiCad(client_name='KiWay Design Variant Workbench')
        try:
            board = client.get_board()
            if board is None:
                return None, 'Plugin opened, but PCB Editor has no active board. Choose a .kicad_sch manually.'
            project = board.get_project()
            if project is None:
                return None, 'The active board is not associated with a KiCad project. Choose a .kicad_sch manually.'
            raw_path = Path(project.path)
            candidates = []
            if raw_path.suffix.lower() == '.kicad_pro':
                candidates.append(raw_path)
            elif raw_path.is_dir():
                candidates.append(raw_path / (project.name + '.kicad_pro'))
            else:
                candidates.append(raw_path)
                candidates.append(raw_path.with_suffix('.kicad_pro'))
            for pro in candidates:
                if pro.exists() and pro.suffix.lower() == '.kicad_pro':
                    root = _root_from_project_file(pro)
                    if root:
                        return str(root), f'✓ Active KiCad project detected through IPC: {pro.name}'
                    return None, f'Active project detected ({pro.name}), but its top-level schematic could not be resolved automatically.'
            return None, f'Active project reported by KiCad, but the project file path could not be resolved: {project.path}'
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as e:
        return None, f'IPC auto-detection was unavailable ({e}). Choose a .kicad_sch manually; all Workbench features still work.'


def launch_detached(initial: Optional[str], note: str) -> None:
    script = Path(__file__).resolve().with_name('kicad_variant_manager.py')
    cmd = [sys.executable, str(script), '--plugin-mode', '--launch-note', note]
    if initial:
        cmd.insert(2, initial)
    kwargs = dict(cwd=str(script.parent), stdin=subprocess.DEVNULL,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  close_fds=True)
    if os.name == 'nt':
        flags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) | getattr(subprocess, 'DETACHED_PROCESS', 0)
        kwargs['creationflags'] = flags
    else:
        kwargs['start_new_session'] = True
    subprocess.Popen(cmd, **kwargs)


def main() -> int:
    initial, note = detect_active_root()
    launch_detached(initial, note)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
