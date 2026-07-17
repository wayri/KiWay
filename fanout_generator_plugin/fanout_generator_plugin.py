"""Conservative radial fanout generator for selected/all SMD pads."""

from __future__ import annotations

import math
import os
from typing import Any, List, Tuple

import pcbnew
import wx


def _coord(value: Any) -> float:
    return float(value) / 1_000_000.0 if hasattr(value, "__float__") else float(value)


class FanoutGeneratorPlugin(pcbnew.ActionPlugin):
    def defaults(self) -> None:
        self.name = "KiWay Fanout Generator"
        self.category = "Routing"
        self.description = "Generate conservative radial fanout tracks from SMD pads."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")
        self.version = "0.1.0"

    def Run(self) -> None:
        FanoutFrame(None, pcbnew.GetBoard()).Show()


class FanoutFrame(wx.Frame):
    def __init__(self, parent: Any, board: Any) -> None:
        super().__init__(parent, title="KiWay Fanout Generator", size=(620, 420))
        self.board = board
        self._build_ui()
        self.Centre()

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(0, 2, 6, 8)
        self.ref = wx.TextCtrl(panel, value="")
        self.width = wx.TextCtrl(panel, value="0.20")
        self.length = wx.TextCtrl(panel, value="1.50")
        self.clearance = wx.TextCtrl(panel, value="0.30")
        for label, control in (("Footprint reference (blank = all):", self.ref), ("Track width (mm):", self.width), ("Fanout length (mm):", self.length), ("Pad clearance (mm):", self.clearance)):
            grid.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)
        grid.AddGrowableCol(1, 1)
        root.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        self.status = wx.StaticText(panel, label="Select a footprint reference or leave blank for all SMD footprints.")
        root.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        row = wx.BoxSizer(wx.HORIZONTAL)
        for text, handler in (("Preview", self.preview), ("Generate", self.generate)):
            button = wx.Button(panel, label=text)
            button.Bind(wx.EVT_BUTTON, handler)
            row.Add(button, 0, wx.ALL, 5)
        root.Add(row, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        panel.SetSizer(root)

    def _plan(self) -> List[Tuple[Any, Any, Any]]:
        try:
            width = pcbnew.FromMM(float(self.width.GetValue()))
            length = pcbnew.FromMM(float(self.length.GetValue()))
        except (TypeError, ValueError):
            raise ValueError("Width and length must be numeric millimetre values.")
        wanted = self.ref.GetValue().strip().upper()
        result = []
        for fp in self.board.GetFootprints():
            if wanted and fp.GetReference().upper() != wanted:
                continue
            for pad in fp.Pads():
                if pad.GetAttribute() not in (getattr(pcbnew, "PAD_ATTRIB_SMD", 0), 0):
                    continue
                pos = pad.GetPosition()
                angle = math.atan2(_coord(pos.y) - _coord(fp.GetPosition().y), _coord(pos.x) - _coord(fp.GetPosition().x))
                end = pcbnew.VECTOR2I(pos.x + int(math.cos(angle) * length), pos.y + int(math.sin(angle) * length))
                result.append((pad, end, width))
        return result

    def preview(self, _event: Any) -> None:
        try:
            self.status.SetLabel(f"Ready to generate {len(self._plan())} fanout tracks.")
        except Exception as exc:
            self.status.SetLabel(str(exc))

    def generate(self, _event: Any) -> None:
        try:
            plan = self._plan()
            for pad, end, width in plan:
                track = pcbnew.PCB_TRACK(self.board)
                track.SetStart(pad.GetPosition())
                track.SetEnd(end)
                track.SetWidth(width)
                track.SetLayer(pad.GetLayer())
                track.SetNetCode(pad.GetNetCode())
                self.board.Add(track)
            if hasattr(pcbnew, "Refresh"): pcbnew.Refresh()
            self.status.SetLabel(f"Generated {len(plan)} fanout tracks. Review clearance and routing before fabrication.")
        except Exception as exc:
            wx.MessageBox(str(exc), "KiWay Fanout Generator", wx.OK | wx.ICON_ERROR)

