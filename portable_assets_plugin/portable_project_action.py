#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import wx

from portable_assets.app import PortableAssetsFrame
from portable_assets.core.engine import ProjectContext


def project_from_ipc():
    try:
        from kipy import KiCad
        kicad = KiCad()
        board = kicad.get_board()
        project_dir = Path(board.document.project.path)
        board_name = Path(board.document.board_filename)
        board_path = board_name if board_name.is_absolute() else project_dir / board_name
        return ProjectContext.discover(project_dir, board_path)
    except Exception:
        return None


def choose_project():
    dlg = wx.DirDialog(None, "Choose a KiCad project directory", style=wx.DD_DIR_MUST_EXIST)
    try:
        if dlg.ShowModal() == wx.ID_OK:
            return ProjectContext.discover(dlg.GetPath())
    finally:
        dlg.Destroy()
    return None


def main():
    parser = argparse.ArgumentParser(description="KiCad Portable Assets")
    parser.add_argument("--project", help="Path to a KiCad project directory, .kicad_pro, or .kicad_pcb")
    args = parser.parse_args()

    app = wx.App(False)
    ctx = ProjectContext.discover(args.project) if args.project else project_from_ipc()
    if ctx is None:
        ctx = choose_project()
    if ctx is None:
        return 1
    frame = PortableAssetsFrame(ctx)
    frame.Show()
    app.MainLoop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
