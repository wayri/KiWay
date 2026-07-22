"""Extract test-point descriptors and export manufacturing documentation."""

from __future__ import annotations

import csv
import html
import os
import re
from typing import Any, Dict, Iterable, List, Sequence

import pcbnew
import wx

from .help_utils import open_help
from .selection_utils import footprint, select_items
from .guided_ui import add_workflow


TYPE_LABELS = {
    "TM": "Telemetry",
    "TC": "Telecommand",
    "TA": "Telemetry Analog",
    "TD": "Telemetry Digital",
    "CA": "Command Analog",
    "CD": "Command Digital",
}


def _fields(footprint: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    getter = getattr(footprint, "GetFields", None)
    if not callable(getter):
        return result
    try:
        for field in getter():
            result[str(field.GetName())] = str(field.GetText())
    except Exception:
        return result
    return result


def parse_net_descriptor(net_name: str, board_order: Sequence[str] = ()) -> Dict[str, str]:
    raw = str(net_name or "")
    upper = raw.upper()
    board_hits = []
    for board in board_order:
        board = str(board).strip().upper()
        if not board:
            continue
        for match in re.finditer(re.escape(board), upper):
            before = upper[match.start() - 1] if match.start() else ""
            after = upper[match.end()] if match.end() < len(upper) else ""
            if before.isalnum() or after.isalnum():
                continue
            board_hits.append((match.start(), match.end(), board))
    board_hits.sort(key=lambda item: (item[0], item[1]))
    spans = []
    for hit in board_hits:
        if not spans or hit[0] >= spans[-1][1]:
            spans.append(hit)
    boards = [item[2] for item in spans]
    markers = list(re.finditer(r"(?<![A-Z0-9])(TM|TC|TA|TD|CA|CD)(?![A-Z0-9])", upper))
    kind = markers[0].group(1) if markers else ""
    masked = list(upper)
    for start, end, _board in spans:
        for index in range(start, end):
            masked[index] = " "
    for marker_match in markers:
        for index in range(marker_match.start(), marker_match.end()):
            masked[index] = " "
    signal_tokens = [token for token in re.findall(r"[A-Z0-9]+", "".join(masked)) if token not in {"SIGNAL", "SIG", "NET"}]
    source = boards[0] if boards else ""
    destination = boards[1] if len(boards) > 1 else ""
    return {
        "Type": kind,
        "Type Description": TYPE_LABELS.get(kind, ""),
        "Source Board": source,
        "Destination Board": destination,
        "Signal": "_".join(signal_tokens),
    }


def extract_test_points(board: Any, descriptor_field: str = "TP_Descriptor", board_order: Sequence[str] = ()) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for footprint in board.GetFootprints():
        reference = str(footprint.GetReference())
        value = str(footprint.GetValue())
        if not (reference.upper().startswith("TP") or "TESTPOINT" in value.upper()):
            continue
        fields = _fields(footprint)
        descriptor = fields.get(descriptor_field, "")
        if not descriptor:
            descriptor = fields.get("Descriptor", fields.get("Function", fields.get("Description", "")))
        for pad in footprint.Pads():
            net = str(pad.GetNetname()) if hasattr(pad, "GetNetname") else ""
            parsed = parse_net_descriptor(net, board_order)
            rows.append({
                "TP Reference": reference,
                "Value": value,
                "Footprint": str(footprint.GetFPIDAsString()) if hasattr(footprint, "GetFPIDAsString") else "",
                "Pad": str(pad.GetNumber()),
                "Net Name": net,
                "Descriptor": descriptor,
                "Type": parsed["Type"],
                "Type Description": parsed["Type Description"],
                "Source Board": parsed["Source Board"],
                "Destination Board": parsed["Destination Board"],
                "Signal": parsed["Signal"],
                "Notes": fields.get("Notes", fields.get("Comment", "")),
            })
    return rows


class TestPointDescriptorPlugin(pcbnew.ActionPlugin):
    def defaults(self) -> None:
        self.name = "KiWay Test Point Descriptor Extractor"
        self.category = "Documentation"
        self.description = "Extract test-point nets, descriptors, and TM/TC metadata to engineering documents."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), "icon.png")
        self.version = "0.4.1"

    def Run(self) -> None:
        try:
            board = pcbnew.GetBoard()
            if board is None or not hasattr(board, "GetFootprints"):
                raise RuntimeError("Open a PCB in PCB Editor first.")
            TestPointFrame(None, board).Show()
        except Exception as exc:
            wx.MessageBox(str(exc), "KiWay Test Point Descriptor Extractor", wx.OK | wx.ICON_ERROR)


class TestPointFrame(wx.Frame):
    def __init__(self, parent: Any, board: Any) -> None:
        super().__init__(parent, title="KiWay Test Point Descriptor Extractor", size=(1120, 650))
        self.board = board
        self.rows: List[Dict[str, str]] = []
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)
        self.workflow = add_workflow(
            panel, root, "Test Point Descriptor Extractor",
            "Configure descriptor conventions, preview parsed records, then export reviewed documentation.",
            ("Configure", "Review preview", "Export"),
        )
        options = wx.FlexGridSizer(0, 2, 6, 8)
        self.field = wx.TextCtrl(panel, value="TP_Descriptor")
        self.boards = wx.TextCtrl(panel, value="DEMO_CTRL,DEMO_SENSOR,DEMO_POWER,DEMO_IO")
        options.Add(wx.StaticText(panel, label="Descriptor field:"), 0, wx.ALIGN_CENTER_VERTICAL)
        options.Add(self.field, 1, wx.EXPAND)
        options.Add(wx.StaticText(panel, label="Board order (comma separated):"), 0, wx.ALIGN_CENTER_VERTICAL)
        options.Add(self.boards, 1, wx.EXPAND)
        options.AddGrowableCol(1, 1)
        root.Add(options, 0, wx.EXPAND | wx.ALL, 8)
        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.select_test_point)
        columns = ("TP Reference", "Net Name", "Descriptor", "Type", "Source Board", "Destination Board", "Signal", "Notes")
        for index, label in enumerate(columns):
            self.list.InsertColumn(index, label, width=145 if index not in (2, 7) else 210)
        root.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in (("Extract Preview", self.extract), ("Export CSV", self.export_csv), ("Export Markdown", self.export_markdown), ("Export HTML", self.export_html)):
            button = wx.Button(panel, label=label)
            button.Bind(wx.EVT_BUTTON, handler)
            row.Add(button, 0, wx.ALL, 5)
        select = wx.Button(panel, label="Select on PCB")
        select.Bind(wx.EVT_BUTTON, self.select_test_point)
        row.Add(select, 0, wx.ALL, 5)
        help_btn = wx.Button(panel, label="Help")
        help_btn.Bind(wx.EVT_BUTTON, lambda _event: open_help(self))
        row.Add(help_btn, 0, wx.ALL, 5)
        root.Add(row, 0, wx.ALIGN_RIGHT | wx.ALL, 5)
        self.status = wx.StaticText(panel, label="Ready.")
        root.Add(self.status, 0, wx.EXPAND | wx.ALL, 6)
        panel.SetSizer(root)
        self.extract(None)
        self.Centre()

    def _refresh_list(self) -> None:
        self.list.DeleteAllItems()
        keys = ("TP Reference", "Net Name", "Descriptor", "Type", "Source Board", "Destination Board", "Signal", "Notes")
        for row in self.rows:
            index = self.list.InsertItem(self.list.GetItemCount(), row.get(keys[0], ""))
            for col, key in enumerate(keys[1:], 1):
                self.list.SetItem(index, col, row.get(key, ""))
        self.status.SetLabel(f"Extracted {len(self.rows)} test-point records.")
        self.workflow.set_step(1 if self.rows else 0, "Cross-select uncertain rows and verify parsed endpoints/types before export." if self.rows else "Check the descriptor field and TP naming, then Extract again.")

    def extract(self, _event: Any) -> None:
        board_order = [item.strip() for item in self.boards.GetValue().split(",") if item.strip()]
        self.rows = extract_test_points(self.board, self.field.GetValue().strip() or "TP_Descriptor", board_order)
        self._refresh_list()

    def select_test_point(self, event: Any) -> None:
        index = event.GetIndex() if hasattr(event, "GetIndex") else self.list.GetFirstSelected()
        if index < 0 or index >= len(self.rows):
            wx.MessageBox("Select a test-point row first.", "KiWay", wx.OK | wx.ICON_INFORMATION)
            return
        select_items(self.board, [footprint(self.board, self.rows[index].get("TP Reference", ""))])
        self.status.SetLabel(f"Selected {self.rows[index].get('TP Reference', '')} on the PCB.")
        self.workflow.set_step(2, "Continue reviewing records or export the approved document.")

    def _save_path(self, wildcard: str) -> str:
        with wx.FileDialog(self, "Export test-point documentation", wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return ""
            return dialog.GetPath()

    def export_csv(self, _event: Any) -> None:
        path = self._save_path("CSV files (*.csv)|*.csv")
        if not path: return
        keys = list(self.rows[0].keys()) if self.rows else ["TP Reference", "Net Name", "Descriptor"]
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys); writer.writeheader(); writer.writerows(self.rows)
        self.status.SetLabel(f"Wrote {path}")
        self.workflow.set_step(3, "Open the exported CSV and complete review/sign-off.")

    def _markdown(self) -> str:
        keys = list(self.rows[0].keys()) if self.rows else ["TP Reference", "Net Name", "Descriptor"]
        lines = ["# Test Point Descriptor Report", "", "| " + " | ".join(keys) + " |", "|" + "|".join(["---"] * len(keys)) + "|"]
        for row in self.rows:
            lines.append("| " + " | ".join(str(row.get(key, "")).replace("|", "\\|").replace("\n", " ") for key in keys) + " |")
        return "\n".join(lines) + "\n"

    def export_markdown(self, _event: Any) -> None:
        path = self._save_path("Markdown files (*.md)|*.md")
        if path:
            with open(path, "w", encoding="utf-8") as handle: handle.write(self._markdown())
            self.status.SetLabel(f"Wrote {path}")
            self.workflow.set_step(3, "Open the exported Markdown and complete review/sign-off.")

    def export_html(self, _event: Any) -> None:
        path = self._save_path("HTML files (*.html)|*.html")
        if not path: return
        keys = list(self.rows[0].keys()) if self.rows else ["TP Reference", "Net Name", "Descriptor"]
        table = "<table><thead><tr>" + "".join(f"<th>{html.escape(key)}</th>" for key in keys) + "</tr></thead><tbody>"
        for row in self.rows:
            table += "<tr>" + "".join(f"<td>{html.escape(str(row.get(key, '')))}</td>" for key in keys) + "</tr>"
        table += "</tbody></table>"
        document = "<!doctype html><html><head><meta charset='utf-8'><style>body{font-family:Arial;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3da;padding:6px;text-align:left}th{background:#edf2f7}</style></head><body><h1>Test Point Descriptor Report</h1>" + table + "</body></html>"
        with open(path, "w", encoding="utf-8") as handle: handle.write(document)
        self.status.SetLabel(f"Wrote {path}")
        self.workflow.set_step(3, "Open the exported HTML and complete review/sign-off.")
