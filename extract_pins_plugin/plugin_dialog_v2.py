# plugin_dialog_v2.py 
"""
KiWay Extract Pins Plugin - Enhanced Dialog v2.0

@author - Wayri (Yawar)
@version - 2.0.0
@date - 2025

Enhanced GUI with:
- Signal flow analysis
- IC signal chart generation
- SVG diagram export
- Power net grouping
- Improved filtering

THIS PLUGIN IS PROVIDED AS IS WITHOUT ANY GUARANTEE OR WARRANTY.
"""

import wx
import pcbnew
import csv
from io import StringIO
import os
import webbrowser
import re

# Import core modules
try:
    from .core.data_extractor import DataExtractor
    from .core.signal_flow import SignalFlowAnalyzer
    from .core.formatters import get_formatter, MarkdownFormatter, CSVFormatter
    from .core.diagram_generator import SVGDiagramGenerator
except ImportError:
    # Fallback for direct execution
    from core.data_extractor import DataExtractor
    from core.signal_flow import SignalFlowAnalyzer
    from core.formatters import get_formatter, MarkdownFormatter, CSVFormatter
    from core.diagram_generator import SVGDiagramGenerator


class PluginDialogV2(wx.Dialog):
    """
    Enhanced wxPython dialog for the KiCad pin extraction plugin v2.0.
    Includes signal flow analysis and diagram generation.
    """

    def __init__(self, parent, initial_selected_footprints):
        super(PluginDialogV2, self).__init__(
            parent, 
            title="KiWay Pin Extractor v2.0", 
            size=(900, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )
        
        self.board = pcbnew.GetBoard()
        self.extractor = DataExtractor(self.board)
        self.analyzer = SignalFlowAnalyzer(self.extractor)
        self.diagram_gen = SVGDiagramGenerator()
        
        self.current_display_footprints = []
        self.all_refs = sorted([fp.GetReference() for fp in self.extractor.footprints], 
                               key=DataExtractor.natural_sort_key)
        self.all_ics = [r for r in self.all_refs if r.startswith('U')]
        
        # Auto-refresh timer for detecting new selections
        self.auto_refresh_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnAutoRefreshTimer, self.auto_refresh_timer)
        self.last_known_selection = set()  # Track what we've already added
        
        self.InitUI()
        self._update_footprint_list_display(initial_selected_footprints)
        
        # Initialize last known selection with initial footprints
        self.last_known_selection = {fp.GetReference() for fp in initial_selected_footprints}
        
        self.Centre()
        self.Show()
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def InitUI(self):
        """Initialize the user interface with notebook tabs."""
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Create notebook for tabs
        self.notebook = wx.Notebook(panel)
        
        # Tab 1: Extract Pins (original functionality)
        self.extract_panel = self._create_extract_tab()
        self.notebook.AddPage(self.extract_panel, "Extract Pins")
        
        # Tab 2: Signal Flow
        self.signal_flow_panel = self._create_signal_flow_tab()
        self.notebook.AddPage(self.signal_flow_panel, "Signal Flow")
        
        # Tab 3: IC Signal Chart
        self.ic_chart_panel = self._create_ic_chart_tab()
        self.notebook.AddPage(self.ic_chart_panel, "IC Signal Chart")
        
        # Tab 4: Diagrams
        self.diagram_panel = self._create_diagram_tab()
        self.notebook.AddPage(self.diagram_panel, "Diagrams")
        
        main_sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 5)
        
        # Status bar
        status_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.status_text = wx.StaticText(panel, label="Ready.")
        status_sizer.Add(self.status_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.progress_bar = wx.Gauge(panel, range=100, size=(200, 20))
        self.progress_bar.Hide()
        status_sizer.Add(self.progress_bar, 0, wx.ALL, 5)
        
        main_sizer.Add(status_sizer, 0, wx.EXPAND | wx.ALL, 2)
        
        # Bottom buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        help_btn = wx.Button(panel, label="Help")
        help_btn.Bind(wx.EVT_BUTTON, self.OnHelp)
        button_sizer.Add(help_btn, 0, wx.ALL, 5)
        
        button_sizer.AddStretchSpacer()
        
        close_btn = wx.Button(panel, label="Close")
        close_btn.Bind(wx.EVT_BUTTON, self.OnClose)
        button_sizer.Add(close_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        panel.SetSizer(main_sizer)

    def _create_extract_tab(self):
        """Create the Extract Pins tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Top section: Component selection
        top_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Left: Component list
        left_panel = wx.StaticBoxSizer(wx.StaticBox(panel, label="Selected Components"), wx.VERTICAL)
        
        self.footprint_list_ctrl = wx.ListCtrl(panel, size=(200, 150), 
                                                style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.footprint_list_ctrl.InsertColumn(0, "Reference", width=80)
        self.footprint_list_ctrl.InsertColumn(1, "Value", width=100)
        self.footprint_list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnListItemSelected)
        left_panel.Add(self.footprint_list_ctrl, 1, wx.EXPAND | wx.ALL, 2)
        
        # Auto-refresh checkbox
        auto_refresh_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.auto_refresh_cb = wx.CheckBox(panel, label="Auto-Refresh")
        self.auto_refresh_cb.SetToolTip("Automatically add components as you click them on the PCB")
        self.auto_refresh_cb.Bind(wx.EVT_CHECKBOX, self.OnAutoRefreshToggle)
        auto_refresh_sizer.Add(self.auto_refresh_cb, 0, wx.ALL, 2)
        
        self.auto_status = wx.StaticText(panel, label="")
        self.auto_status.SetForegroundColour(wx.Colour(0, 150, 0))
        auto_refresh_sizer.Add(self.auto_status, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        
        left_panel.Add(auto_refresh_sizer, 0, wx.EXPAND | wx.ALL, 2)
        
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.multi_select_cb = wx.CheckBox(panel, label="Multi-select")
        self.multi_select_cb.SetToolTip("Add to existing selection on manual refresh")
        btn_sizer.Add(self.multi_select_cb, 0, wx.ALL, 2)
        
        refresh_btn = wx.Button(panel, label="Refresh", size=(70, -1))
        refresh_btn.Bind(wx.EVT_BUTTON, self.OnRefreshSelection)
        refresh_btn.SetToolTip("Manually refresh from PCB selection")
        btn_sizer.Add(refresh_btn, 0, wx.ALL, 2)
        
        remove_btn = wx.Button(panel, label="Remove", size=(70, -1))
        remove_btn.Bind(wx.EVT_BUTTON, self.OnRemoveSelectedFromList)
        btn_sizer.Add(remove_btn, 0, wx.ALL, 2)
        
        clear_btn = wx.Button(panel, label="Clear", size=(50, -1))
        clear_btn.Bind(wx.EVT_BUTTON, self.OnClearList)
        clear_btn.SetToolTip("Clear the component list")
        btn_sizer.Add(clear_btn, 0, wx.ALL, 2)
        
        left_panel.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 2)
        top_sizer.Add(left_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        # Right: Details
        right_panel = wx.StaticBoxSizer(wx.StaticBox(panel, label="Component Details"), wx.VERTICAL)
        self.details_text = wx.TextCtrl(panel, size=(250, 150), 
                                         style=wx.TE_MULTILINE | wx.TE_READONLY)
        right_panel.Add(self.details_text, 1, wx.EXPAND | wx.ALL, 2)
        top_sizer.Add(right_panel, 1, wx.EXPAND | wx.ALL, 5)
        
        sizer.Add(top_sizer, 1, wx.EXPAND)
        
        # Middle: Filters
        filter_sizer = wx.StaticBoxSizer(wx.StaticBox(panel, label="Filters (Wildcards: * ?)"), wx.HORIZONTAL)
        
        filter_sizer.Add(wx.StaticText(panel, label="Reference:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        self.ref_filter = wx.TextCtrl(panel, size=(80, -1))
        self.ref_filter.SetValue("J*")
        filter_sizer.Add(self.ref_filter, 0, wx.ALL, 2)
        
        filter_sizer.Add(wx.StaticText(panel, label="Net:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        self.net_filter_ctrl = wx.ComboBox(panel, size=(100, -1), 
                                           choices=sorted(self.extractor.all_nets)[:50])
        filter_sizer.Add(self.net_filter_ctrl, 0, wx.ALL, 2)
        
        filter_sizer.Add(wx.StaticText(panel, label="Value:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2)
        self.value_filter_ctrl = wx.ComboBox(panel, size=(80, -1),
                                              choices=sorted(set(fp.GetValue() for fp in self.extractor.footprints)))
        filter_sizer.Add(self.value_filter_ctrl, 0, wx.ALL, 2)
        
        sizer.Add(filter_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Options
        options_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.ignore_unconnected_cb = wx.CheckBox(panel, label="Ignore Unconnected")
        options_sizer.Add(self.ignore_unconnected_cb, 0, wx.ALL, 5)
        
        self.ignore_power_cb = wx.CheckBox(panel, label="Ignore Power Nets")
        options_sizer.Add(self.ignore_power_cb, 0, wx.ALL, 5)
        
        self.sort_by_type_cb = wx.CheckBox(panel, label="Sort by Net Type")
        options_sizer.Add(self.sort_by_type_cb, 0, wx.ALL, 5)
        
        self.highlight_nets_cb = wx.CheckBox(panel, label="Highlight Nets (MD)")
        options_sizer.Add(self.highlight_nets_cb, 0, wx.ALL, 5)
        
        sizer.Add(options_sizer, 0, wx.EXPAND | wx.ALL, 2)
        
        # Export buttons
        export_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.export_selected_btn = wx.Button(panel, label="Export Selected")
        self.export_selected_btn.Bind(wx.EVT_BUTTON, self.OnExportSelected)
        self.export_selected_btn.Enable(False)
        export_sizer.Add(self.export_selected_btn, 0, wx.ALL, 5)
        
        export_j_btn = wx.Button(panel, label="Export J*")
        export_j_btn.Bind(wx.EVT_BUTTON, self.OnExportJs)
        export_sizer.Add(export_j_btn, 0, wx.ALL, 5)
        
        export_pattern_btn = wx.Button(panel, label="Export by Pattern")
        export_pattern_btn.Bind(wx.EVT_BUTTON, self.OnExportByPattern)
        export_sizer.Add(export_pattern_btn, 0, wx.ALL, 5)
        
        export_nets_btn = wx.Button(panel, label="Unique Nets")
        export_nets_btn.Bind(wx.EVT_BUTTON, self.OnExtractUniqueNets)
        export_sizer.Add(export_nets_btn, 0, wx.ALL, 5)
        
        sizer.Add(export_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        
        panel.SetSizer(sizer)
        return panel

    def _create_signal_flow_tab(self):
        """Create the Signal Flow tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Source/Destination selection
        sel_sizer = wx.FlexGridSizer(2, 4, 5, 10)
        sel_sizer.AddGrowableCol(1)
        sel_sizer.AddGrowableCol(3)
        
        sel_sizer.Add(wx.StaticText(panel, label="Source:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.source_pattern = wx.TextCtrl(panel, value="J*")
        self.source_pattern.SetToolTip("Source components (wildcards: * ?)")
        sel_sizer.Add(self.source_pattern, 1, wx.EXPAND)
        
        sel_sizer.Add(wx.StaticText(panel, label="Destination:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.dest_pattern = wx.TextCtrl(panel, value="U*")
        self.dest_pattern.SetToolTip("Destination components (wildcards: * ?)")
        sel_sizer.Add(self.dest_pattern, 1, wx.EXPAND)
        
        sizer.Add(sel_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # Options
        opt_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.sf_include_intermediates = wx.CheckBox(panel, label="Include Intermediates")
        opt_sizer.Add(self.sf_include_intermediates, 0, wx.ALL, 5)
        
        self.sf_include_power = wx.CheckBox(panel, label="Include Power Nets")
        opt_sizer.Add(self.sf_include_power, 0, wx.ALL, 5)
        
        sizer.Add(opt_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Preview area
        preview_sizer = wx.StaticBoxSizer(wx.StaticBox(panel, label="Preview"), wx.VERTICAL)
        self.sf_preview = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
                                       size=(-1, 200))
        self.sf_preview.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        preview_sizer.Add(self.sf_preview, 1, wx.EXPAND | wx.ALL, 2)
        sizer.Add(preview_sizer, 1, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        preview_btn = wx.Button(panel, label="Preview")
        preview_btn.Bind(wx.EVT_BUTTON, self.OnSignalFlowPreview)
        btn_sizer.Add(preview_btn, 0, wx.ALL, 5)
        
        export_csv_btn = wx.Button(panel, label="Export CSV")
        export_csv_btn.Bind(wx.EVT_BUTTON, lambda e: self.OnSignalFlowExport('csv'))
        btn_sizer.Add(export_csv_btn, 0, wx.ALL, 5)
        
        export_md_btn = wx.Button(panel, label="Export Markdown")
        export_md_btn.Bind(wx.EVT_BUTTON, lambda e: self.OnSignalFlowExport('md'))
        btn_sizer.Add(export_md_btn, 0, wx.ALL, 5)
        
        export_svg_btn = wx.Button(panel, label="Export SVG Diagram")
        export_svg_btn.Bind(wx.EVT_BUTTON, lambda e: self.OnSignalFlowExport('svg'))
        btn_sizer.Add(export_svg_btn, 0, wx.ALL, 5)
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        
        panel.SetSizer(sizer)
        return panel

    def _create_ic_chart_tab(self):
        """Create the IC Signal Chart tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # IC selection
        sel_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sel_sizer.Add(wx.StaticText(panel, label="Select IC:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        self.ic_combo = wx.ComboBox(panel, choices=self.all_ics, style=wx.CB_DROPDOWN)
        if self.all_ics:
            self.ic_combo.SetValue(self.all_ics[0])
        sel_sizer.Add(self.ic_combo, 1, wx.ALL, 5)
        
        self.ic_include_power = wx.CheckBox(panel, label="Include Power Nets")
        sel_sizer.Add(self.ic_include_power, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        
        sizer.Add(sel_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Preview
        preview_sizer = wx.StaticBoxSizer(wx.StaticBox(panel, label="IC Pin Connections"), wx.VERTICAL)
        self.ic_preview = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL,
                                       size=(-1, 250))
        self.ic_preview.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        preview_sizer.Add(self.ic_preview, 1, wx.EXPAND | wx.ALL, 2)
        sizer.Add(preview_sizer, 1, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        preview_btn = wx.Button(panel, label="Preview")
        preview_btn.Bind(wx.EVT_BUTTON, self.OnICChartPreview)
        btn_sizer.Add(preview_btn, 0, wx.ALL, 5)
        
        export_csv_btn = wx.Button(panel, label="Export CSV")
        export_csv_btn.Bind(wx.EVT_BUTTON, lambda e: self.OnICChartExport('csv'))
        btn_sizer.Add(export_csv_btn, 0, wx.ALL, 5)
        
        export_md_btn = wx.Button(panel, label="Export Markdown")
        export_md_btn.Bind(wx.EVT_BUTTON, lambda e: self.OnICChartExport('md'))
        btn_sizer.Add(export_md_btn, 0, wx.ALL, 5)
        
        export_svg_btn = wx.Button(panel, label="Export SVG Chart")
        export_svg_btn.Bind(wx.EVT_BUTTON, lambda e: self.OnICChartExport('svg'))
        btn_sizer.Add(export_svg_btn, 0, wx.ALL, 5)
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 5)
        
        panel.SetSizer(sizer)
        return panel

    def _create_diagram_tab(self):
        """Create the Diagrams tab."""
        panel = wx.Panel(self.notebook)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        info = wx.StaticText(panel, label="Generate self-contained SVG block diagrams.\nNo external dependencies required.")
        sizer.Add(info, 0, wx.ALL, 10)
        
        # Component selection
        sel_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sel_sizer.Add(wx.StaticText(panel, label="Components:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5)
        self.diagram_refs = wx.TextCtrl(panel, value="U1,U2,J1")
        self.diagram_refs.SetToolTip("Comma-separated references or wildcards (e.g., U*, J1,J2)")
        sel_sizer.Add(self.diagram_refs, 1, wx.ALL, 5)
        sizer.Add(sel_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Options
        opt_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.diag_ignore_power = wx.CheckBox(panel, label="Exclude Power Nets")
        opt_sizer.Add(self.diag_ignore_power, 0, wx.ALL, 5)
        
        self.diag_dark_mode = wx.CheckBox(panel, label="Dark Mode")
        self.diag_dark_mode.SetValue(True)
        opt_sizer.Add(self.diag_dark_mode, 0, wx.ALL, 5)
        
        sizer.Add(opt_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Generate buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        gen_block_btn = wx.Button(panel, label="Generate Component Blocks")
        gen_block_btn.Bind(wx.EVT_BUTTON, self.OnGenerateBlockDiagram)
        btn_sizer.Add(gen_block_btn, 0, wx.ALL, 5)
        
        gen_flow_btn = wx.Button(panel, label="Generate Flow Diagram")
        gen_flow_btn.Bind(wx.EVT_BUTTON, self.OnGenerateFlowDiagram)
        btn_sizer.Add(gen_flow_btn, 0, wx.ALL, 5)
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        panel.SetSizer(sizer)
        return panel

    # ==================== Event Handlers ====================
    
    def OnClose(self, event):
        # Stop timer before closing
        if self.auto_refresh_timer.IsRunning():
            self.auto_refresh_timer.Stop()
        self.Destroy()

    def OnHelp(self, event):
        plugin_dir = os.path.dirname(__file__)
        help_file = os.path.join(plugin_dir, "help_doc.html")
        if os.path.exists(help_file):
            webbrowser.open_new_tab(f"file:///{help_file}")
        else:
            wx.MessageBox("Help file not found.", "Error", wx.OK | wx.ICON_ERROR)

    def OnAutoRefreshToggle(self, event):
        """Toggle auto-refresh timer on/off."""
        if self.auto_refresh_cb.IsChecked():
            # Start timer - check every 500ms
            self.auto_refresh_timer.Start(500)
            self.auto_status.SetLabel("(Active)")
            self.status_text.SetLabel("Auto-refresh enabled. Click components on PCB to add them.")
        else:
            self.auto_refresh_timer.Stop()
            self.auto_status.SetLabel("")
            self.status_text.SetLabel("Auto-refresh disabled.")

    def OnAutoRefreshTimer(self, event):
        """Timer callback - check for newly selected components."""
        try:
            # Get currently selected footprints from PCB
            currently_selected = {fp.GetReference(): fp 
                                  for fp in self.board.GetFootprints() if fp.IsSelected()}
            
            # Find new selections (not already in our list)
            existing_refs = {fp.GetReference() for fp in self.current_display_footprints}
            new_refs = set(currently_selected.keys()) - existing_refs
            
            if new_refs:
                # Add new components to list
                new_footprints = [currently_selected[ref] for ref in new_refs]
                all_footprints = list(self.current_display_footprints) + new_footprints
                
                # Sort and update
                all_footprints.sort(key=lambda fp: DataExtractor.natural_sort_key(fp.GetReference()))
                self._update_footprint_list_display(all_footprints)
                
                # Update status
                added_str = ", ".join(sorted(new_refs, key=DataExtractor.natural_sort_key))
                self.status_text.SetLabel(f"Added: {added_str}")
                
        except Exception as e:
            # Silently handle errors during auto-refresh
            pass

    def OnClearList(self, event):
        """Clear the component list."""
        self.current_display_footprints = []
        self._update_footprint_list_display([])
        self.last_known_selection = set()
        self.status_text.SetLabel("List cleared.")

    def _update_footprint_list_display(self, footprints_list):
        self.footprint_list_ctrl.DeleteAllItems()
        self.current_display_footprints = list(footprints_list)
        
        for i, fp in enumerate(self.current_display_footprints):
            self.footprint_list_ctrl.InsertItem(i, fp.GetReference())
            self.footprint_list_ctrl.SetItem(i, 1, fp.GetValue())
        
        self.details_text.SetValue("")
        self.export_selected_btn.Enable(bool(footprints_list))

    def OnRefreshSelection(self, event):
        newly_selected = [f for f in self.board.GetFootprints() if f.IsSelected()]
        
        if self.multi_select_cb.IsChecked():
            existing = {fp.GetReference(): fp for fp in self.current_display_footprints}
            for fp in newly_selected:
                existing[fp.GetReference()] = fp
            merged = sorted(existing.values(), key=lambda f: DataExtractor.natural_sort_key(f.GetReference()))
            self._update_footprint_list_display(merged)
        else:
            self._update_footprint_list_display(newly_selected)
        
        self.status_text.SetLabel(f"Found {len(self.current_display_footprints)} components.")

    def OnListItemSelected(self, event):
        idx = event.GetIndex()
        if idx < 0 or idx >= len(self.current_display_footprints):
            return
        
        fp = self.current_display_footprints[idx]
        pos = fp.GetPosition()
        rot = fp.GetOrientation()
        
        details = f"Reference: {fp.GetReference()}\n"
        details += f"Value: {fp.GetValue()}\n"
        details += f"Footprint: {fp.GetFPID()}\n"
        details += f"Layer: {fp.GetLayerName()}\n"
        details += f"Position: ({pos.x/1e6:.2f}mm, {pos.y/1e6:.2f}mm)\n"
        details += f"Rotation: {rot.AsDegrees():.1f}°\n"
        
        conn_type = self.extractor.get_footprint_property(fp, "connector-type")
        if conn_type:
            details += f"Connector Type: {conn_type}\n"
        
        details += f"\nPins: {len(list(fp.Pads()))}"
        
        self.details_text.SetValue(details)

    def OnRemoveSelectedFromList(self, event):
        idx = self.footprint_list_ctrl.GetFirstSelected()
        if idx != wx.NOT_FOUND and idx < len(self.current_display_footprints):
            del self.current_display_footprints[idx]
            self._update_footprint_list_display(self.current_display_footprints)

    def _get_footprints_by_pattern(self, pattern: str):
        """Get footprints matching pattern(s)."""
        patterns = [p.strip() for p in pattern.split(',') if p.strip()]
        result = []
        for p in patterns:
            result.extend(self.extractor.get_footprints_by_reference_pattern(p))
        # Remove duplicates
        seen = set()
        unique = []
        for fp in result:
            ref = fp.GetReference()
            if ref not in seen:
                seen.add(ref)
                unique.append(fp)
        return unique

    def OnExportSelected(self, event):
        if not self.current_display_footprints:
            wx.MessageBox("No components selected.", "Info", wx.OK)
            return
        self._export_footprints(self.current_display_footprints, "selected")

    def OnExportJs(self, event):
        footprints = self._get_footprints_by_pattern("J*")
        if not footprints:
            wx.MessageBox("No 'J*' components found.", "Info", wx.OK)
            return
        self._export_footprints(footprints, "connectors")

    def OnExportByPattern(self, event):
        pattern = self.ref_filter.GetValue().strip()
        if not pattern:
            wx.MessageBox("Enter a reference pattern.", "Info", wx.OK)
            return
        
        footprints = self._get_footprints_by_pattern(pattern)
        if not footprints:
            wx.MessageBox(f"No components matching '{pattern}'.", "Info", wx.OK)
            return
        self._export_footprints(footprints, pattern.replace('*', '').replace('?', ''))

    def _export_footprints(self, footprints, name_prefix):
        """Export footprint data to CSV and Markdown."""
        self.status_text.SetLabel("Extracting data...")
        self.progress_bar.Show()
        self.progress_bar.SetValue(25)
        wx.Yield()
        
        data = self.extractor.extract_footprint_data(
            footprints,
            ignore_unconnected=self.ignore_unconnected_cb.IsChecked(),
            ignore_power_nets=self.ignore_power_cb.IsChecked(),
            value_filter=self.value_filter_ctrl.GetValue().strip() or None,
            net_filter=self.net_filter_ctrl.GetValue().strip() or None,
            sort_pins_by_net_type=self.sort_by_type_cb.IsChecked()
        )
        
        if not data:
            wx.MessageBox("No data found after filtering.", "Info", wx.OK)
            self.progress_bar.Hide()
            return
        
        self.progress_bar.SetValue(50)
        wx.Yield()
        
        # Generate CSV
        csv_formatter = CSVFormatter()
        csv_content = csv_formatter.format_component_data(data)
        
        self.progress_bar.SetValue(75)
        wx.Yield()
        
        # Generate Markdown
        md_formatter = MarkdownFormatter(highlight_nets=self.highlight_nets_cb.IsChecked())
        md_content = md_formatter.format_component_data(data)
        
        self.progress_bar.Hide()
        
        # Save files
        self._save_file(csv_content, "CSV", f"{name_prefix}_pins.csv")
        self._save_file(md_content, "Markdown", f"{name_prefix}_pins.md")
        
        self.status_text.SetLabel("Export complete.")

    def OnExtractUniqueNets(self, event):
        pattern = self.ref_filter.GetValue().strip() or "J*"
        footprints = self._get_footprints_by_pattern(pattern)
        
        if not footprints:
            wx.MessageBox(f"No components matching '{pattern}'.", "Info", wx.OK)
            return
        
        nets = self.extractor.extract_unique_nets(
            footprints,
            ignore_power_nets=self.ignore_power_cb.IsChecked(),
            net_filter=self.net_filter_ctrl.GetValue().strip() or None,
            sort_by_type=self.sort_by_type_cb.IsChecked()
        )
        
        if not nets:
            wx.MessageBox("No nets found.", "Info", wx.OK)
            return
        
        csv_content = "Net Name\n" + "\n".join(nets)
        self._save_file(csv_content, "CSV", "unique_nets.csv")

    # Signal Flow handlers
    def OnSignalFlowPreview(self, event):
        src_pattern = self.source_pattern.GetValue().strip()
        dst_pattern = self.dest_pattern.GetValue().strip()
        
        if not src_pattern or not dst_pattern:
            wx.MessageBox("Enter source and destination patterns.", "Info", wx.OK)
            return
        
        sources = [fp.GetReference() for fp in self._get_footprints_by_pattern(src_pattern)]
        dests = [fp.GetReference() for fp in self._get_footprints_by_pattern(dst_pattern)]
        
        if not sources or not dests:
            wx.MessageBox("No matching components found.", "Info", wx.OK)
            return
        
        data = self.analyzer.generate_source_destination_table(
            sources, dests, 
            include_intermediates=self.sf_include_intermediates.IsChecked()
        )
        
        if not data:
            self.sf_preview.SetValue("No connections found between source and destination.")
            return
        
        # Format preview
        lines = [f"Found {len(data)} connection(s)\n"]
        lines.append(f"{'Source':<10} {'Pin':<6} {'Net':<25} {'Dest':<10} {'Pin':<6}")
        lines.append("-" * 60)
        for entry in data[:50]:  # Limit preview
            lines.append(f"{entry['Source Reference']:<10} {entry['Source Pin']:<6} {entry['Net Name']:<25} {entry['Destination Reference']:<10} {entry['Destination Pin']:<6}")
        
        if len(data) > 50:
            lines.append(f"\n... and {len(data) - 50} more")
        
        self.sf_preview.SetValue("\n".join(lines))

    def OnSignalFlowExport(self, format_type):
        src_pattern = self.source_pattern.GetValue().strip()
        dst_pattern = self.dest_pattern.GetValue().strip()
        
        sources = [fp.GetReference() for fp in self._get_footprints_by_pattern(src_pattern)]
        dests = [fp.GetReference() for fp in self._get_footprints_by_pattern(dst_pattern)]
        
        data = self.analyzer.generate_source_destination_table(
            sources, dests,
            include_intermediates=self.sf_include_intermediates.IsChecked()
        )
        
        if not data:
            wx.MessageBox("No data to export.", "Info", wx.OK)
            return
        
        if format_type == 'svg':
            content = self.diagram_gen.generate_signal_flow_diagram(
                data, title=f"Signal Flow: {src_pattern} → {dst_pattern}"
            )
            self._save_file(content, "SVG", "signal_flow.svg")
        else:
            formatter = get_formatter(format_type)
            content = formatter.format_signal_flow(data)
            ext = 'md' if format_type == 'md' else format_type
            self._save_file(content, format_type.upper(), f"signal_flow.{ext}")

    # IC Chart handlers
    def OnICChartPreview(self, event):
        ic_ref = self.ic_combo.GetValue().strip()
        if not ic_ref:
            wx.MessageBox("Select an IC.", "Info", wx.OK)
            return
        
        data = self.analyzer.generate_ic_signal_chart(
            ic_ref,
            include_power_nets=self.ic_include_power.IsChecked()
        )
        
        if not data:
            self.ic_preview.SetValue(f"No data found for {ic_ref}")
            return
        
        lines = [f"IC: {ic_ref} - {len(data)} connection(s)\n"]
        lines.append(f"{'Pin':<6} {'Net':<25} {'Dest':<10} {'Dest Pin':<8} {'Type':<8}")
        lines.append("-" * 60)
        
        for entry in data:
            pwr = "PWR" if entry['Is Power Net'] == 'Yes' else "SIG"
            lines.append(f"{entry['IC Pin']:<6} {entry['Net Name']:<25} {entry['Destination Reference']:<10} {entry['Destination Pin']:<8} {pwr:<8}")
        
        self.ic_preview.SetValue("\n".join(lines))

    def OnICChartExport(self, format_type):
        ic_ref = self.ic_combo.GetValue().strip()
        if not ic_ref:
            return
        
        data = self.analyzer.generate_ic_signal_chart(
            ic_ref,
            include_power_nets=self.ic_include_power.IsChecked()
        )
        
        if not data:
            wx.MessageBox("No data to export.", "Info", wx.OK)
            return
        
        if format_type == 'svg':
            ic_fp = self.extractor.get_footprint_by_reference(ic_ref)
            ic_value = ic_fp.GetValue() if ic_fp else ""
            content = self.diagram_gen.generate_ic_signal_chart(
                ic_ref, ic_value, data
            )
            self._save_file(content, "SVG", f"{ic_ref}_chart.svg")
        else:
            formatter = get_formatter(format_type)
            content = formatter.format_signal_flow(data)
            ext = 'md' if format_type == 'md' else format_type
            self._save_file(content, format_type.upper(), f"{ic_ref}_chart.{ext}")

    # Diagram handlers
    def OnGenerateBlockDiagram(self, event):
        refs_str = self.diagram_refs.GetValue().strip()
        if not refs_str:
            return
        
        footprints = self._get_footprints_by_pattern(refs_str)
        if not footprints:
            wx.MessageBox("No matching components.", "Info", wx.OK)
            return
        
        # Generate block for first component (for simplicity)
        fp = footprints[0]
        data = self.extractor.extract_footprint_data(
            [fp], sort_pins_by_net_type=True
        )
        
        if fp.GetReference() in data:
            comp_data = data[fp.GetReference()]
            content = self.diagram_gen.generate_component_block(
                fp.GetReference(),
                fp.GetValue(),
                comp_data['pins']
            )
            self._save_file(content, "SVG", f"{fp.GetReference()}_block.svg")

    def OnGenerateFlowDiagram(self, event):
        refs_str = self.diagram_refs.GetValue().strip()
        if not refs_str:
            wx.MessageBox("Enter component references.", "Info", wx.OK)
            return
        
        footprints = self._get_footprints_by_pattern(refs_str)
        if not footprints:
            wx.MessageBox("No matching components found.", "Info", wx.OK)
            return
        
        refs = [fp.GetReference() for fp in footprints]
        
        # For flow diagram, find all connections FROM these components TO any other component
        self.status_text.SetLabel("Generating flow diagram...")
        wx.Yield()
        
        # Use the first component(s) as sources and find their destinations
        # If only 1 component, show all its connections
        # If multiple, show connections between them
        
        if len(refs) == 1:
            # Single component: show all connections from/to it
            data = self.analyzer.generate_ic_signal_chart(
                refs[0],
                include_power_nets=not self.diag_ignore_power.IsChecked()
            )
            if not data:
                wx.MessageBox(f"No connections found for {refs[0]}.", "Info", wx.OK)
                return
            
            # Convert IC chart format to signal flow format
            flow_data = []
            for entry in data:
                flow_data.append({
                    'Source Reference': refs[0],
                    'Source Pin': entry.get('IC Pin', ''),
                    'Net Name': entry.get('Net Name', ''),
                    'Destination Reference': entry.get('Destination Reference', ''),
                    'Destination Pin': entry.get('Destination Pin', '')
                })
            
            content = self.diagram_gen.generate_signal_flow_diagram(
                flow_data, 
                title=f"Connections: {refs[0]}"
            )
        else:
            # Multiple components: show connections between all of them
            # Use all as both sources and destinations to catch all inter-connections
            data = self.analyzer.generate_source_destination_table(refs, refs)
            
            if not data:
                # Try finding connections from these to any other component
                all_other_refs = [r for r in self.all_refs if r not in refs]
                data = self.analyzer.generate_source_destination_table(refs, all_other_refs[:20])
            
            if not data:
                wx.MessageBox("No connections found between specified components.", "Info", wx.OK)
                return
            
            content = self.diagram_gen.generate_signal_flow_diagram(
                data, 
                title=f"Signal Flow: {', '.join(refs[:3])}{'...' if len(refs) > 3 else ''}"
            )
        
        self._save_file(content, "SVG", "flow_diagram.svg")
        self.status_text.SetLabel("Diagram generated.")

    def _save_file(self, content, format_name, default_name):
        """Show save dialog and write file."""
        wildcard = f"{format_name} files (*.{default_name.split('.')[-1]})|*.{default_name.split('.')[-1]}"
        
        with wx.FileDialog(
            self, f"Save {format_name}",
            wildcard=wildcard,
            defaultFile=default_name,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as dlg:
            if dlg.ShowModal() == wx.ID_CANCEL:
                return
            
            path = dlg.GetPath()
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
                wx.MessageBox(f"Saved: {path}", "Success", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR)
