# plugin_dialog.py (Layout Compacted & AttributeError Resolution Attempt)

import wx
import pcbnew
import csv
from io import StringIO
import random
import os
import webbrowser

# --- HELP_DOC string definition is confirmed removed from this file ---

class PluginDialog(wx.Dialog):
    """
    A non-modal wxPython dialog for the KiCad pin extraction plugin.
    Allows interaction with KiCad while the dialog is open.
    """

    def __init__(self, parent, initial_selected_footprints):
        """
        Initializes the dialog window.

        Args:
            parent: The parent wx.Window (can be None for a top-level dialog,
                    or pcbnew.GetBoard().GetParentWindow() for more strict parenting).
            initial_selected_footprints: A list of pcbnew.FOOTPRINT objects selected initially.
        """
        # --- ADJUSTED INITIAL SIZE FOR SMALLER/COMPACTER LAYOUT ---
        super(PluginDialog, self).__init__(parent, title="KiCad Pin Extractor", size=(750, 500)) # Smaller size
        print("DEBUG: PluginDialog __init__ called.")

        self.board = pcbnew.GetBoard()
        self.all_board_footprints = self.board.GetFootprints()

        self.current_display_footprints = []

        self.InitUI()

        self._update_footprint_list_display(initial_selected_footprints)

        self.Centre()
        self.Show()
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def InitUI(self):
        panel = wx.Panel(self)
        main_vbox = wx.BoxSizer(wx.VERTICAL)

        top_hbox = wx.BoxSizer(wx.HORIZONTAL)

        list_panel = wx.Panel(panel)
        list_vbox = wx.BoxSizer(wx.VERTICAL)

        list_vbox.Add(wx.StaticText(list_panel, label="Selected Components:"), 0, wx.ALL | wx.EXPAND, 2) # Reduced padding
        self.footprint_list_ctrl = wx.ListCtrl(list_panel, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL)
        self.footprint_list_ctrl.InsertColumn(0, "Reference")
        self.footprint_list_ctrl.SetColumnWidth(0, 100) # Reduced column width
        self.footprint_list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnListItemSelected)

        list_vbox.Add(self.footprint_list_ctrl, 1, wx.ALL | wx.EXPAND, 2) # Reduced padding

        refresh_button = wx.Button(list_panel, label="Refresh Selection from PCB")
        refresh_button.Bind(wx.EVT_BUTTON, self.OnRefreshSelection)
        list_vbox.Add(refresh_button, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 2) # Reduced padding
        list_panel.SetSizer(list_vbox)
        top_hbox.Add(list_panel, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding

        details_panel = wx.Panel(panel)
        details_vbox = wx.BoxSizer(wx.VERTICAL)
        details_vbox.Add(wx.StaticText(details_panel, label="Selected Component Details:"), 0, wx.ALL | wx.EXPAND, 2) # Reduced padding
        self.details_text_ctrl = wx.TextCtrl(details_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        details_vbox.Add(self.details_text_ctrl, 1, wx.ALL | wx.EXPAND, 2) # Reduced padding
        details_panel.SetSizer(details_vbox)
        top_hbox.Add(details_panel, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding
        main_vbox.Add(top_hbox, 2, wx.EXPAND | wx.ALL, 2) # Reduced padding

        middle_hbox = wx.BoxSizer(wx.HORIZONTAL)

        filters_panel = wx.StaticBoxSizer(wx.StaticBox(panel, label="Filters (Apply to 'J's & 'Connectors' Exports)"),
                                           wx.VERTICAL)
        grid_filters = wx.GridSizer(4, 2, 2, 2) # Reduced gaps

        grid_filters.Add(wx.StaticText(panel, label="Footprint Name Filter:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.fp_name_filter_ctrl = wx.TextCtrl(panel)
        grid_filters.Add(self.fp_name_filter_ctrl, 0, wx.EXPAND)

        grid_filters.Add(wx.StaticText(panel, label="Value Filter:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.value_filter_ctrl = wx.TextCtrl(panel)
        grid_filters.Add(self.value_filter_ctrl, 0, wx.EXPAND)

        grid_filters.Add(wx.StaticText(panel, label="Net Name Filter (any pin):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.net_name_filter_ctrl = wx.TextCtrl(panel)
        grid_filters.Add(self.net_name_filter_ctrl, 0, wx.EXPAND)

        grid_filters.Add(wx.StaticText(panel, label="Connector Type Filter (comma-sep):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.connector_type_filter_ctrl = wx.TextCtrl(panel)
        grid_filters.Add(self.connector_type_filter_ctrl, 0, wx.EXPAND)

        filters_panel.Add(grid_filters, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding
        middle_hbox.Add(filters_panel, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding

        options_panel = wx.StaticBoxSizer(wx.StaticBox(panel, label="Output Options"), wx.VERTICAL)

        self.highlight_nets_markdown_checkbox = wx.CheckBox(panel, label="Highlight Same Nets in Markdown Output")
        options_panel.Add(self.highlight_nets_markdown_checkbox, 0, wx.ALL, 2) # Reduced padding

        self.sort_by_reference_checkbox = wx.CheckBox(panel, label="Sort Components by Reference (A-Z)")
        options_panel.Add(self.sort_by_reference_checkbox, 0, wx.ALL, 2) # Reduced padding

        self.output_column_checkboxes = {}
        column_checkbox_data = {
            "General Properties": ["Reference", "Value", "Footprint Name", "Description", "Layer", "Position", "Rotation",
                                   "Connector Type"],
            "Pin Details": ["Pad Name/Number", "Net Name"]
        }

        options_panel.Add(wx.StaticText(panel, label="Select Output Columns:"), 0, wx.ALL, 2) # Reduced padding

        column_checkbox_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        for category, columns in column_checkbox_data.items():
            col_vbox = wx.BoxSizer(wx.VERTICAL)
            col_vbox.Add(wx.StaticText(panel, label=f"{category}"), 0, wx.ALL, 1) # Reduced padding
            for col_name in columns:
                cb = wx.CheckBox(panel, label=f"Include {col_name}")
                cb.SetValue(True)
                self.output_column_checkboxes[col_name] = cb
                col_vbox.Add(cb, 0, wx.ALL, 1) # Reduced padding
            column_checkbox_hbox.Add(col_vbox, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding

        options_panel.Add(column_checkbox_hbox, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding
        middle_hbox.Add(options_panel, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding
        main_vbox.Add(middle_hbox, 1, wx.EXPAND | wx.ALL, 2) # Reduced padding


        progress_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.status_text = wx.StaticText(panel, label="Ready.")
        progress_sizer.Add(self.status_text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2) # Reduced padding
        self.progress_bar = wx.Gauge(panel, range=100, size=(150, 15), style=wx.GA_HORIZONTAL) # Reduced progress bar width
        self.progress_bar.Hide()
        progress_sizer.Add(self.progress_bar, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 2) # Reduced padding
        main_vbox.Add(progress_sizer, 0, wx.EXPAND | wx.ALL, 2) # Reduced padding

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.export_selected_button = wx.Button(panel, label="Export Selected")
        self.export_selected_button.Bind(wx.EVT_BUTTON, self.OnExportSelected)
        self.export_selected_button.Enable(False)
        button_sizer.Add(self.export_selected_button, 0, wx.ALL, 2) # Reduced padding

        export_js_button = wx.Button(panel, label="Export 'J's")
        export_js_button.Bind(wx.EVT_BUTTON, self.OnExportJs)
        button_sizer.Add(export_js_button, 0, wx.ALL, 2) # Reduced padding

        export_connectors_by_type_button = wx.Button(panel, label="Export Connectors (by Type)")
        export_connectors_by_type_button.Bind(wx.EVT_BUTTON, self.OnExportConnectorsByType)
        button_sizer.Add(export_connectors_by_type_button, 0, wx.ALL, 2) # Reduced padding

        help_button = wx.Button(panel, label="Help")
        help_button.Bind(wx.EVT_BUTTON, self.OnHelp)
        button_sizer.Add(help_button, 0, wx.ALL, 2) # Reduced padding

        cancel_button = wx.Button(panel, label="Close")
        cancel_button.Bind(wx.EVT_BUTTON, self.OnCancel)
        button_sizer.Add(cancel_button, 0, wx.ALL, 2) # Reduced padding

        main_vbox.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 2) # Reduced padding

        panel.SetSizer(main_vbox)
        main_vbox.Fit(self)

    def OnHelp(self, event):
        print("DEBUG: Help button clicked. Opening HTML Help.")
        
        plugin_dir = os.path.dirname(__file__)
        help_file_path = os.path.join(plugin_dir, "help_doc.html")
        
        if os.path.exists(help_file_path):
            try:
                webbrowser.open_new_tab(f"file:///{help_file_path}")
                print(f"DEBUG: Opened help file: {help_file_path}")
            except Exception as e:
                wx.MessageBox(f"Could not open help file in browser.\nError: {e}", "Error Opening Help", wx.OK | wx.ICON_ERROR)
                print(f"ERROR: Failed to open help file: {e}")
        else:
            wx.MessageBox(f"Help file not found: {help_file_path}", "Help File Missing", wx.OK | wx.ICON_ERROR)
            print(f"ERROR: Help file not found: {help_file_path}")

    def OnClose(self, event):
        print("DEBUG: Main Dialog OnClose event fired. Destroying dialog.")
        self.Destroy()

    def _update_footprint_list_display(self, footprints_list):
        self.footprint_list_ctrl.ClearAll()
        self.footprint_list_ctrl.InsertColumn(0, "Reference")
        self.footprint_list_ctrl.SetColumnWidth(0, 100) # Keep consistent with InitUI
        self.current_display_footprints = footprints_list

        for i, fp in enumerate(self.current_display_footprints):
            self.footprint_list_ctrl.InsertItem(i, fp.GetReference())
        
        self.details_text_ctrl.SetValue("")

        self.export_selected_button.Enable(bool(footprints_list))


    def OnRefreshSelection(self, event):
        print("DEBUG: OnRefreshSelection method called.")
        new_selected_footprints = [f for f in self.board.GetFootprints() if f.IsSelected()]
        self._update_footprint_list_display(new_selected_footprints)
        wx.MessageBox(f"Refreshed selection. Found {len(new_selected_footprints)} selected components.",
                      "Selection Refreshed", wx.OK | wx.ICON_INFORMATION)

    def OnListItemSelected(self, event):
        selected_index = event.GetIndex()
        if selected_index == wx.NOT_FOUND:
            self.details_text_ctrl.SetValue("")
            return

        selected_fp = self.current_display_footprints[selected_index]
        print(f"DEBUG: List item selected: {selected_fp.GetReference()}")

        props = self._get_footprint_properties_for_display(selected_fp)

        details_text = ""
        for prop_name, prop_value in props.items():
            details_text += f"{prop_name}: {prop_value}\n"

        self.details_text_ctrl.SetValue(details_text.strip())

    def _get_footprint_property_safe(self, footprint, prop_name):
        """
        Safely retrieves the value of a property from a footprint,
        by iterating its fields. Returns None if property not found.
        """
        for field in footprint.GetFields():
            if field.GetName() == prop_name:
                return field.GetText()
        return None

    def _get_footprint_properties_for_display(self, fp):
        properties = {}
        properties["Reference"] = fp.GetReference()
        properties["Value"] = fp.GetValue()

        footprint_id = fp.GetFPID()
        properties["Footprint Name"] = str(footprint_id)

        description = fp.GetLibDescription()
        properties["Description"] = description if description and description != "No description" else "N/A"

        properties["Layer"] = fp.GetLayerName()
        pos = fp.GetPosition()
        properties["Position (X, Y)"] = f"({pos.x / 1000000.0:.2f}mm, {pos.y / 1000000.0:.2f}mm)"
        rot = fp.GetOrientation()
        properties["Rotation"] = f"{rot.AsDegrees():.1f}°"

        connector_type_val = self._get_footprint_property_safe(fp, "connector-type")
        if connector_type_val is not None:
            properties["Connector Type"] = connector_type_val.strip()
        else:
            properties["Connector Type"] = "N/A (No 'connector-type' property)"

        return properties


    def OnExportSelected(self, event):
        print("DEBUG: OnExportSelected method called.")
        initial_footprints = list(self.current_display_footprints)
        self._process_and_export(initial_footprints, "selected_data.md", "selected_data.csv", "selected components")

    def OnExportJs(self, event):
        print("DEBUG: OnExportJs method called.")
        initial_footprints = list(self.all_board_footprints)
        initial_footprints = [f for f in initial_footprints if
                              f.GetReference().startswith("J")]
        self._process_and_export(initial_footprints, "js_components.md", "js_components.csv", "'J' components")

    def OnExportConnectorsByType(self, event):
        print("DEBUG: OnExportConnectorsByType method called.")
        initial_footprints = list(self.all_board_footprints)

        connector_type_filter_raw = self.connector_type_filter_ctrl.GetValue().strip()
        connector_types_to_match = [t.strip().lower() for t in connector_type_filter_raw.split(',') if t.strip()]

        if not connector_types_to_match:
            wx.MessageBox("Please enter connector types (e.g., 'harness,backplane') in the filter field.",
                          "Filter Required", wx.OK | wx.ICON_INFORMATION)
            return

        filtered_footprints = []
        for fp in initial_footprints:
            fp_connector_type_val = self._get_footprint_property_safe(fp, "connector-type")
            if fp_connector_type_val is not None:
                if fp_connector_type_val.lower().strip() in connector_types_to_match:
                    filtered_footprints.append(fp)

        self._process_and_export(filtered_footprints, "connectors_by_type.md", "connectors_by_type.csv",
                                 "connectors by type")

    def OnCancel(self, event):
        print("DEBUG: Close button clicked. Closing dialog.")
        self.Close()

    def _process_and_export(self, initial_footprints_list, default_md_name, default_csv_name, export_type_desc):
        """
        Consolidates filtering, extraction, generation, and saving for all export types.
        """
        self.status_text.SetLabel(f"Applying filters for {export_type_desc}...")
        self.progress_bar.Show()
        self.progress_bar.SetValue(0)
        self.progress_bar.SetRange(100)
        wx.Yield()

        filtered_footprints = self._apply_text_filters(initial_footprints_list)

        self.status_text.SetLabel(f"Extracting data for {len(filtered_footprints)} components...")
        self.progress_bar.SetValue(25)
        wx.Yield()

        extracted_data_by_footprint = self.extract_data(filtered_footprints)
        print(f"DEBUG: _process_and_export: extract_data completed. Found {len(extracted_data_by_footprint)} components.")

        if not extracted_data_by_footprint:
            wx.MessageBox(f"No pins found in the {export_type_desc} after filtering to export.", "No Pin Data",
                          wx.OK | wx.ICON_INFORMATION)
            self.status_text.SetLabel("No data found.")
            self.progress_bar.Hide()
            return

        if self.sort_by_reference_checkbox.IsChecked():
            print("DEBUG: Sorting components by reference for output.")
            sorted_refs = sorted(extracted_data_by_footprint.keys(),
                                 key=lambda k: extracted_data_by_footprint[k]['general_properties']['Reference'])
            ordered_extracted_data = {ref: extracted_data_by_footprint[ref] for ref in sorted_refs}
            extracted_data_by_footprint = ordered_extracted_data
        else:
            print("DEBUG: Outputting components in processed order.")

        apply_markdown_highlight = self.highlight_nets_markdown_checkbox.IsChecked()
        selected_columns = self._get_selected_columns()

        self.status_text.SetLabel("Generating Markdown content...")
        self.progress_bar.SetValue(50)
        wx.Yield()
        markdown_content = self.generate_markdown(extracted_data_by_footprint, apply_markdown_highlight,
                                                  selected_columns)

        self.status_text.SetLabel("Generating CSV content...")
        self.progress_bar.SetValue(75)
        wx.Yield()
        
        csv_content = ""
        try:
            csv_content = self.generate_csv(extracted_data_by_footprint, selected_columns)
            print(f"DEBUG: CSV content generated. Length: {len(csv_content)} bytes.")
        except Exception as e:
            print(f"ERROR: Exception during CSV generation: {e}")
            import traceback
            traceback.print_exc()
            wx.MessageBox(f"An error occurred during CSV generation:\n{e}", "CSV Generation Error", wx.OK | wx.ICON_ERROR)
            self.status_text.SetLabel("Error during CSV generation.")
            self.progress_bar.Hide()
            return

        self.status_text.SetLabel("Showing save dialogs...")
        self.progress_bar.Hide()
        wx.Yield()

        self.save_file_dialog(markdown_content, "Markdown Files (*.md)|*.md", "Save Pin Data (Markdown)",
                              default_md_name)
        self.save_file_dialog(csv_content, "CSV Files (*.csv)|*.csv", "Save Pin Data (CSV)", default_csv_name)

        self.status_text.SetLabel("Done.")
        self.progress_bar.SetValue(100)
        self.progress_bar.Hide()
        print("DEBUG: _perform_export: Export complete.")

    def _apply_text_filters(self, footprints_list):
        """
        Applies Footprint Name, Value, and Net Name filters to a list of footprints.
        Returns a new filtered list.
        """
        filtered = list(footprints_list)

        fp_name_filter_text = self.fp_name_filter_ctrl.GetValue().strip().lower()
        value_filter_text = self.value_filter_ctrl.GetValue().strip().lower()
        net_name_filter_text = self.net_name_filter_ctrl.GetValue().strip().lower()

        if fp_name_filter_text:
            filtered = [fp for fp in filtered if str(fp.GetFPID()).lower().find(fp_name_filter_text) != -1]
            print(f"DEBUG: Applied FP Name filter '{fp_name_filter_text}'. Found {len(filtered)} FPs.")

        if value_filter_text:
            filtered = [fp for fp in filtered if fp.GetValue().lower().find(value_filter_text) != -1]
            print(f"DEBUG: Applied Value filter '{value_filter_text}'. Found {len(filtered)} FPs.")

        if net_name_filter_text:
            filtered_by_net = []
            for fp in filtered:
                for pad in fp.Pads():
                    net = pad.GetNet()
                    if net and net.GetNetname().lower().find(net_name_filter_text) != -1:
                        filtered_by_net.append(fp)
                        break
            filtered = filtered_by_net
            print(f"DEBUG: Applied Net Name filter '{net_name_filter_text}'. Found {len(filtered)} FPs.")

        return filtered

    def _get_selected_columns(self):
        """
        Returns a list of column names that are checked by the user for output.
        """
        selected_cols = []
        all_possible_columns = [
            "Reference", "Value", "Footprint Name", "Description", "Layer",
            "Position", "Rotation", "Connector Type",
            "Pad Name/Number", "Net Name"
        ]

        for col_name in all_possible_columns:
            cb = self.output_column_checkboxes.get(col_name)
            if cb and cb.IsChecked():
                selected_cols.append(col_name)
        return selected_cols

    def extract_data(self, footprints_to_process):
        extracted_data_by_footprint = {}
        total_footprints = len(footprints_to_process)
        for i, footprint in enumerate(footprints_to_process):
            if total_footprints > 0:
                self.progress_bar.SetValue(25 + int((i / total_footprints) * 25))
                wx.Yield()

            footprint_ref = footprint.GetReference()
            footprint_value = footprint.GetValue()

            footprint_id = footprint.GetFPID()
            footprint_full_name = str(footprint_id)

            footprint_description = footprint.GetLibDescription()

            footprint_layer = footprint.GetLayerName()
            footprint_pos = footprint.GetPosition()
            footprint_rot = footprint.GetOrientation()

            connector_type_val = self._get_footprint_property_safe(footprint, "connector-type")
            if connector_type_val is None:
                connector_type_val = ""

            general_properties = {
                "Reference": footprint_ref,
                "Value": footprint_value,
                "Footprint Name": footprint_full_name,
                "Description": footprint_description if footprint_description and footprint_description != "No description" else "N/A",
                "Layer": footprint_layer,
                "Position": f"({footprint_pos.x / 1000000.0:.2f}mm, {footprint_pos.y / 1000000.0:.2f}mm)",
                "Rotation": f"{footprint_rot.AsDegrees():.1f}°",
                "Connector Type": connector_type_val
            }

            pin_data = []
            for pad in footprint.Pads():
                pad_name = pad.GetPadName()
                net_name = ""
                net = pad.GetNet()
                if net:
                    net_name = net.GetNetname()
                pin_data.append({
                    "Pad Name/Number": pad_name,
                    "Net Name": net_name
                })

            extracted_data_by_footprint[footprint_ref] = {
                "general_properties": general_properties,
                "pin_data": pin_data
            }
        return extracted_data_by_footprint

    def generate_markdown(self, data_by_footprint, apply_highlight=False, selected_columns=None):
        markdown = "# Extracted Component Pin Data\n\n"

        if selected_columns is None:
            selected_columns = self._get_selected_columns()

        html_color_palette = [
            "#FF0000", "#008000", "#0000FF", "#FFA500", "#800080", "#00FFFF", "#FFC0CB", "#00FF7F", "#8B4513",
            "#A52A2A", "#6A5ACD", "#D2691E", "#4682B4", "#BDB76B", "#FFD700"
        ]
        net_colors_map = {}
        color_index = 0

        for ref, component_data in data_by_footprint.items():
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            markdown += f"## Component: {ref}\n\n"

            general_headers_to_include = [col for col in selected_columns if col in general_props]
            if general_headers_to_include:
                markdown += "### General Properties\n\n"
                markdown += "| " + " | ".join(general_headers_to_include) + " |\n"
                markdown += "|:" + "---------|:---------".join([""] * len(general_headers_to_include)) + "|\n"

                row_values = []
                for header in general_headers_to_include:
                    if header == "Position":
                        row_values.append(general_props.get("Position (X, Y)", "N/A"))
                    elif header == "Rotation":
                        row_values.append(general_props.get("Rotation", "N/A"))
                    else:
                        row_values.append(str(general_props.get(header, "N/A")))
                markdown += "| " + " | ".join(row_values) + " |\n"
                markdown += "\n"

            pin_headers_to_include = [col for col in selected_columns if col in ["Pad Name/Number", "Net Name"]]
            if pin_data and pin_headers_to_include:
                markdown += "### Pin Details\n\n"
                markdown += "| " + " | ".join(pin_headers_to_include) + " |\n"
                markdown += "|:" + "----------------|:---------".join([""] * len(pin_headers_to_include)) + "|\n"

                for pin_row in pin_data:
                    row_values = []
                    for header in pin_headers_to_include:
                        val = pin_row.get(header, "N/A")
                        if header == "Net Name" and apply_highlight and val != "N/A" and val != "":
                            if val not in net_colors_map:
                                net_colors_map[val] = html_color_palette[color_index % len(html_color_palette)]
                                color_index += 1

                            display_val = f'<span style="color: {net_colors_map[val]};">{val}</span>'
                        else:
                            display_val = val

                        row_values.append(display_val)
                    markdown += "| " + " | ".join(row_values) + " |\n"
                markdown += "\n"
            elif pin_data and not pin_headers_to_include:
                markdown += "Pin details available but no pin columns selected.\n\n"
            else:
                markdown += "No pins found for this component.\n\n"

        return markdown

    def generate_csv(self, data_by_footprint, selected_columns=None):
        output = StringIO()

        if selected_columns is None:
            selected_columns = self._get_selected_columns()

        csv_headers = []
        general_prop_cols_map = { # Map display name to internal storage key if different
            "Reference": "Reference", "Value": "Value", "Footprint Name": "Footprint Name",
            "Description": "Description", "Layer": "Layer",
            "Position": "Position (X, Y)", "Rotation": "Rotation",
            "Connector Type": "Connector Type"
        }
        pin_detail_cols_map = {
            "Pad Name/Number": "Pad Name/Number", "Net Name": "Net Name"
        }

        for col in selected_columns:
            if col in general_prop_cols_map:
                csv_headers.append(general_prop_cols_map[col])
            elif col in pin_detail_cols_map:
                csv_headers.append(pin_detail_cols_map[col])

        writer = csv.DictWriter(output, fieldnames=csv_headers, extrasaction='ignore')
        writer.writeheader()

        for ref, component_data in data_by_footprint.items():
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            base_row = {}
            for col_display_name, col_storage_name in general_prop_cols_map.items():
                if col_display_name in selected_columns:
                    base_row[col_storage_name] = general_props.get(col_storage_name, "")

            if not pin_data:
                if any(col_name in selected_columns for col_name in general_prop_cols_map.keys()):
                    writer.writerow(base_row)
            else:
                for pin_row in pin_data:
                    combined_row = base_row.copy()
                    for col_display_name, col_storage_name in pin_detail_cols_map.items():
                        if col_display_name in selected_columns:
                            combined_row[col_storage_name] = pin_row.get(col_storage_name, "")
                    writer.writerow(combined_row)

        return output.getvalue()

    def save_file_dialog(self, content, wildcard, title, default_filename):
        with wx.FileDialog(
                None,
                title,
                wildcard=wildcard,
                defaultFile=default_filename,
                style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT
        ) as file_dialog:
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return

            pathname = file_dialog.GetPath()
            try:
                with open(pathname, 'w', encoding='utf-8') as f:
                    f.write(content)
                wx.MessageBox(f"File saved successfully to:\n{pathname}", "Success", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                wx.MessageBox(f"Error saving file:\n{e}", "Error", wx.OK | wx.ICON_ERROR)