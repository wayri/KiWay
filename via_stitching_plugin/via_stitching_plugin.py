"""Ground via stitching grid generator inside the board outline bounding box."""

from __future__ import annotations

import os
from typing import Any, List

import pcbnew
import wx


class ViaStitchingPlugin(pcbnew.ActionPlugin):
    def defaults(self) -> None:
        self.name = "KiWay Via Stitching"
        self.category = "Routing"
        self.description = "Generate a configurable ground-via stitching grid."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")
        self.version = "0.1.0"

    def Run(self) -> None:
        ViaFrame(None, pcbnew.GetBoard()).Show()


class ViaFrame(wx.Frame):
    def __init__(self, parent: Any, board: Any) -> None:
        super().__init__(parent, title="KiWay Via Stitching", size=(580, 360))
        self.board = board
        self._build_ui()
        self.Centre()

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(0, 2, 6, 8)
        self.spacing = wx.TextCtrl(panel, value="2.50")
        self.edge = wx.TextCtrl(panel, value="1.00")
        self.drill = wx.TextCtrl(panel, value="0.30")
        self.diameter = wx.TextCtrl(panel, value="0.60")
        for label, control in (("Grid spacing (mm):", self.spacing), ("Edge inset (mm):", self.edge), ("Drill (mm):", self.drill), ("Via diameter (mm):", self.diameter)):
            grid.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(control, 1, wx.EXPAND)
        grid.AddGrowableCol(1, 1)
        root.Add(grid, 0, wx.EXPAND | wx.ALL, 10)
        self.status = wx.StaticText(panel, label="Only unconnected vias are created; inspect against copper zones and keepouts.")
        root.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        row = wx.BoxSizer(wx.HORIZONTAL)
        for text, handler in (("Preview", self.preview), ("Generate", self.generate)):
            button = wx.Button(panel, label=text)
            button.Bind(wx.EVT_BUTTON, handler)
            row.Add(button, 0, wx.ALL, 5)
        root.Add(row, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        panel.SetSizer(root)

    def _plan(self) -> List[Any]:
        spacing = pcbnew.FromMM(float(self.spacing.GetValue()))
        inset = pcbnew.FromMM(float(self.edge.GetValue()))
        drill = pcbnew.FromMM(float(self.drill.GetValue()))
        diameter = pcbnew.FromMM(float(self.diameter.GetValue()))
        box = self.board.GetBoardEdgesBoundingBox()
        result = []
        x = box.GetLeft() + inset
        while x <= box.GetRight() - inset:
            y = box.GetTop() + inset
            while y <= box.GetBottom() - inset:
                via = pcbnew.PCB_VIA(self.board)
                via.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
                via.SetDrill(int(drill))
                via.SetWidth(int(diameter))
                via.SetNetCode(0)
                result.append(via)
                y += spacing
            x += spacing
        return result

    def preview(self, _event: Any) -> None:
        try: self.status.SetLabel(f"Ready to create {len(self._plan())} ground stitching vias.")
        except Exception as exc: self.status.SetLabel(str(exc))

    def generate(self, _event: Any) -> None:
        try:
            plan = self._plan()
            for via in plan: self.board.Add(via)
            if hasattr(pcbnew, "Refresh"): pcbnew.Refresh()
            self.status.SetLabel(f"Created {len(plan)} vias. Run DRC and review board-edge/keepout clearances.")
        except Exception as exc:
            wx.MessageBox(str(exc), "KiWay Via Stitching", wx.OK | wx.ICON_ERROR)

