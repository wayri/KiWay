"""Functional wxPython application for Kilo workflows."""

from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable

from kilo.dependencies.scanner import scan_project
from kilo.identity import CONTROL_DIRECTORY, PRODUCT_TITLE
from kilo.kicad.project import detect_kicad_version, discover_project
from kilo.operations.install_block import (
    InstallSettings,
    build_install_plan,
    execute_install,
)
from kilo.operations.localize import build_localization_plan, execute_localization
from kilo.operations.package_block import (
    PackageSettings,
    build_package_plan,
    execute_package,
)
from kilo.operations.repair import build_repair_plan, execute_repair
from kilo.operations.unlocalize import (
    RestoreSettings,
    build_restore_plan,
    execute_restore,
    list_restore_points,
)
from kilo.operations.validate import validate_project
from kilo.plugin.project_detection import current_project_path
from kilo.reports.html_report import render_validation_html
from kilo.version import __version__

try:
    import wx  # type: ignore[import-not-found,import-untyped]
except ImportError as exc:  # pragma: no cover - depends on KiCad runtime
    raise RuntimeError("wxPython is required; launch with KiCad's bundled Python") from exc


class OperationPanel(wx.Panel):  # type: ignore[misc]
    """Common controls and cancellable worker dispatch."""

    def __init__(self, parent: wx.Window, title: str) -> None:
        super().__init__(parent)
        self.title = title
        self.cancelled = threading.Event()
        self.worker: threading.Thread | None = None
        self.last_report: Path | None = None
        self.path = wx.TextCtrl(self, value=str(current_project_path() or Path.cwd()))
        self.output = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL
        )
        self.status = wx.StaticText(
            self, label=f"KiCad version: {detect_kicad_version() or 'not detected'}"
        )
        browse = wx.Button(self, label="Browse…")
        browse.Bind(wx.EVT_BUTTON, self._browse)
        self.buttons = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in (
            ("Scan", self.on_scan),
            ("Dry Run", self.on_dry_run),
            ("Execute", self.on_execute),
            ("Cancel", self.on_cancel),
            ("Open Report", self.on_open_report),
            ("Export Log", self.on_export_log),
        ):
            button = wx.Button(self, label=label)
            button.Bind(wx.EVT_BUTTON, handler)
            self.buttons.Add(button, 0, wx.RIGHT, 6)
        top = wx.BoxSizer(wx.VERTICAL)
        top.Add(wx.StaticText(self, label=title), 0, wx.ALL, 8)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Path:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row.Add(self.path, 1, wx.RIGHT, 6)
        row.Add(browse, 0)
        top.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        top.Add(self.status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        top.Add(self.buttons, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        top.Add(self.output, 1, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(top)

    def _browse(self, _event: wx.CommandEvent) -> None:
        with wx.DirDialog(self, f"Select path for {self.title}") as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.path.SetValue(dialog.GetPath())

    def run(self, operation: Callable[[], Any]) -> None:
        if self.worker and self.worker.is_alive():
            self.append("An operation is already running.")
            return
        self.cancelled.clear()
        self.append("Working…")

        def target() -> None:
            try:
                result = operation()
                if self.cancelled.is_set():
                    wx.CallAfter(self.append, "Cancelled before the write phase.")
                else:
                    wx.CallAfter(self.append, json.dumps(_jsonable(result), indent=2))
            except Exception as exc:
                wx.CallAfter(self.append, f"Error: {exc}")

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def append(self, text: str) -> None:
        self.output.AppendText(text.rstrip() + "\n")

    def on_scan(self, _event: wx.CommandEvent) -> None:
        self.run(lambda: scan_project(discover_project(Path(self.path.GetValue()))).summary())

    def on_dry_run(self, _event: wx.CommandEvent) -> None:
        self.append("Dry run is not configured for this tab.")

    def on_execute(self, _event: wx.CommandEvent) -> None:
        self.append("Execute is not configured for this tab.")

    def on_cancel(self, _event: wx.CommandEvent) -> None:
        self.cancelled.set()
        self.append("Cancellation requested; no new write phase will start.")

    def on_open_report(self, _event: wx.CommandEvent) -> None:
        if self.last_report and self.last_report.exists():
            webbrowser.open(self.last_report.as_uri())
        else:
            self.append("No report has been generated yet.")

    def on_export_log(self, _event: wx.CommandEvent) -> None:
        with wx.FileDialog(
            self,
            "Export log",
            wildcard="Text files (*.txt)|*.txt",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                Path(dialog.GetPath()).write_text(self.output.GetValue(), encoding="utf-8")


class LocalizePanel(OperationPanel):  # type: ignore[misc]
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, "Localize Project")

    def on_dry_run(self, _event: wx.CommandEvent) -> None:
        self.run(
            lambda: build_localization_plan(
                discover_project(Path(self.path.GetValue()))
            ).summary()
        )

    def on_execute(self, _event: wx.CommandEvent) -> None:
        if not _confirm_saved(self):
            return

        def operation() -> Any:
            plan = build_localization_plan(discover_project(Path(self.path.GetValue())))
            if self.cancelled.is_set():
                return {"cancelled": True}
            return execute_localization(plan)

        self.run(operation)


class PackagePanel(OperationPanel):  # type: ignore[misc]
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, "Design Block Packager")

    def on_scan(self, _event: wx.CommandEvent) -> None:
        self.on_dry_run(_event)

    def on_dry_run(self, _event: wx.CommandEvent) -> None:
        self.run(lambda: build_package_plan(Path(self.path.GetValue())).summary())

    def on_execute(self, _event: wx.CommandEvent) -> None:
        if _confirm_saved(self):
            def operation() -> Any:
                plan = build_package_plan(Path(self.path.GetValue()))
                if self.cancelled.is_set():
                    return {"cancelled": True}
                return execute_package(plan)

            self.run(operation)


class InstallPanel(OperationPanel):  # type: ignore[misc]
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, "Design Block Installer")
        self.block = wx.TextCtrl(self)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(
            wx.StaticText(self, label="Portable block:"),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            6,
        )
        row.Add(self.block, 1)
        self.GetSizer().Insert(2, row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

    def on_scan(self, _event: wx.CommandEvent) -> None:
        self.on_dry_run(_event)

    def _plan(self) -> Any:
        return build_install_plan(
            Path(self.block.GetValue()),
            discover_project(Path(self.path.GetValue())),
            InstallSettings(),
        )

    def on_dry_run(self, _event: wx.CommandEvent) -> None:
        self.run(lambda: self._plan().summary())

    def on_execute(self, _event: wx.CommandEvent) -> None:
        if _confirm_saved(self):
            def operation() -> Any:
                plan = self._plan()
                if self.cancelled.is_set():
                    return {"cancelled": True}
                return execute_install(plan)

            self.run(operation)


class ValidatePanel(OperationPanel):  # type: ignore[misc]
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, "Validate / Repair")

    def on_scan(self, _event: wx.CommandEvent) -> None:
        def operation() -> Any:
            result = validate_project(discover_project(Path(self.path.GetValue())))
            report = result.project + "-kilo-validation.html"
            self.last_report = Path(self.path.GetValue()).resolve() / report
            self.last_report.write_text(
                render_validation_html(result.to_dict()), encoding="utf-8"
            )
            return result.to_dict()

        self.run(operation)

    def on_dry_run(self, _event: wx.CommandEvent) -> None:
        self.run(
            lambda: build_repair_plan(
                discover_project(Path(self.path.GetValue()))
            ).summary()
        )

    def on_execute(self, _event: wx.CommandEvent) -> None:
        if _confirm_saved(self):
            def operation() -> Any:
                plan = build_repair_plan(discover_project(Path(self.path.GetValue())))
                if self.cancelled.is_set():
                    return {"cancelled": True}
                return execute_repair(plan)

            self.run(operation)


class HistoryPanel(OperationPanel):  # type: ignore[misc]
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, "History / Restore")
        restore = wx.Button(self, label="Restore")
        restore.Bind(wx.EVT_BUTTON, self.on_execute)
        self.buttons.Add(restore, 0, wx.RIGHT, 6)

    def on_scan(self, _event: wx.CommandEvent) -> None:
        self.run(lambda: list_restore_points(discover_project(Path(self.path.GetValue()))))

    def on_dry_run(self, _event: wx.CommandEvent) -> None:
        self.run(
            lambda: build_restore_plan(
                discover_project(Path(self.path.GetValue())), RestoreSettings()
            ).summary()
        )

    def on_execute(self, _event: wx.CommandEvent) -> None:
        if _confirm_saved(self):
            def operation() -> Any:
                plan = build_restore_plan(
                    discover_project(Path(self.path.GetValue())), RestoreSettings()
                )
                if self.cancelled.is_set():
                    return {"cancelled": True}
                return execute_restore(plan)

            self.run(operation)


class SettingsPanel(wx.Panel):  # type: ignore[misc]
    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(self, label="Default local folder"), 0, wx.ALL, 8)
        sizer.Add(wx.TextCtrl(self, value="local-libraries"), 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(
            wx.StaticText(
                self,
                label=(
                    f"Project selections are persisted in {CONTROL_DIRECTORY}/state.json "
                    "after a successful operation."
                ),
            ),
            0,
            wx.ALL,
            8,
        )
        self.SetSizer(sizer)


class HelpPanel(wx.Panel):  # type: ignore[misc]
    """Native, offline help sourced from the installed Kilo README."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent)
        help_path = Path(__file__).resolve().parents[1] / "README.md"
        try:
            help_text = help_path.read_text(encoding="utf-8")
        except OSError:
            help_text = (
                f"{PRODUCT_TITLE}\n\n"
                "The installed help file could not be read. Use `kilo --help` "
                "for command-line help."
            )
        content = wx.TextCtrl(
            self,
            value=help_text,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
        )
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(content, 1, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(sizer)


class MainFrame(wx.Frame):  # type: ignore[misc]
    def __init__(self) -> None:
        super().__init__(None, title=PRODUCT_TITLE, size=(980, 720))
        self.notebook = wx.Notebook(self)
        self.notebook.AddPage(PackagePanel(self.notebook), "Design Block Packager")
        self.notebook.AddPage(InstallPanel(self.notebook), "Design Block Installer")
        self.notebook.AddPage(LocalizePanel(self.notebook), "Localize Project")
        self.notebook.AddPage(ValidatePanel(self.notebook), "Validate / Repair")
        self.notebook.AddPage(HistoryPanel(self.notebook), "History / Restore")
        self.notebook.AddPage(SettingsPanel(self.notebook), "Settings")
        self.help_page = self.notebook.GetPageCount()
        self.notebook.AddPage(HelpPanel(self.notebook), "Help")

        menu_bar = wx.MenuBar()
        help_menu = wx.Menu()
        show_help = help_menu.Append(wx.ID_HELP, "&Kilo Help\tF1")
        about = help_menu.Append(wx.ID_ABOUT, "&About Kilo")
        menu_bar.Append(help_menu, "&Help")
        self.SetMenuBar(menu_bar)
        self.Bind(wx.EVT_MENU, self._show_help, show_help)
        self.Bind(wx.EVT_MENU, self._show_about, about)
        self.Centre()

    def _show_help(self, _event: wx.CommandEvent) -> None:
        self.notebook.SetSelection(self.help_page)

    def _show_about(self, _event: wx.CommandEvent) -> None:
        wx.MessageBox(
            f"{PRODUCT_TITLE}\nVersion {__version__}\n\n"
            "Portable project dependencies for KiCad 10.",
            f"About {PRODUCT_TITLE}",
            wx.OK | wx.ICON_INFORMATION,
            self,
        )


def launch() -> None:
    """Launch standalone or inside KiCad's existing wx event loop."""

    app = wx.App.Get() or wx.App(False)
    frame = MainFrame()
    frame.Show()
    if not wx.App.IsMainLoopRunning():
        app.MainLoop()


def _confirm_saved(parent: wx.Window) -> bool:
    message = (
        "Save the KiCad project before continuing. After dependency files or "
        "library tables change, close/reopen or reload affected KiCad editors."
    )
    return (
        wx.MessageBox(message, PRODUCT_TITLE, wx.OK | wx.CANCEL | wx.ICON_WARNING, parent)
        == wx.OK
    )


def _jsonable(value: Any) -> Any:
    if hasattr(value, "summary"):
        return value.summary()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value
