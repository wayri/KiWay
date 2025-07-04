# plugin_dialog.py (Non-Modal Version)

import wx
import pcbnew
import csv
from io import StringIO
import random

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
        super(PluginDialog, self).__init__(parent, title="KiCad Pin Extractor", size=(750, 600))
        print("DEBUG: PluginDialog __init__ called.")
        
        self.board = pcbnew.GetBoard() 
        self.all_board_footprints = self.board.GetFootprints() # Pre-fetch all footprints once

        self.current_display_footprints = [] # This list will hold footprints currently in ListCtrl

        self.InitUI()
        
        self._update_footprint_list_display(initial_selected_footprints)

        self.Centre()
        
        # --- CRITICAL CHANGE: Use Show() instead of ShowModal() ---
        self.Show() 
        
        # --- Bind the window close event to ensure proper destruction ---
        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def InitUI(self):
        panel = wx.Panel(self)
        main_vbox = wx.BoxSizer(wx.VERTICAL) 

        # Top section: List of selected components and Refresh button
        top_hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        list_panel = wx.Panel(panel)
        list_vbox = wx.BoxSizer(wx.VERTICAL)

        selected_label = wx.StaticText(list_panel, label="Selected Components:")
        list_vbox.Add(selected_label, 0, wx.ALL | wx.EXPAND, 5)

        self.footprint_list_ctrl = wx.ListCtrl(list_panel, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL)
        self.footprint_list_ctrl.InsertColumn(0, "Reference")
        self.footprint_list_ctrl.SetColumnWidth(0, 200)
        self.footprint_list_ctrl.Bind(wx.EVT_LIST_ITEM_SELECTED, self.OnListItemSelected)
        
        list_vbox.Add(self.footprint_list_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        
        # Refresh Selection button
        refresh_button = wx.Button(list_panel, label="Refresh Selection from PCB")
        refresh_button.Bind(wx.EVT_BUTTON, self.OnRefreshSelection)
        list_vbox.Add(refresh_button, 0, wx.ALL | wx.ALIGN_CENTER_HORIZONTAL, 5)

        list_panel.SetSizer(list_vbox)
        top_hbox.Add(list_panel, 1, wx.EXPAND | wx.ALL, 5)

        # Right section: Detailed properties of selected list item
        details_panel = wx.Panel(panel)
        details_vbox = wx.BoxSizer(wx.VERTICAL)
        
        details_label = wx.StaticText(details_panel, label="Selected Component Details:")
        details_vbox.Add(details_label, 0, wx.ALL | wx.EXPAND, 5)

        self.details_text_ctrl = wx.TextCtrl(details_panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        details_vbox.Add(self.details_text_ctrl, 1, wx.ALL | wx.EXPAND, 5)

        details_panel.SetSizer(details_vbox)
        top_hbox.Add(details_panel, 1, wx.EXPAND | wx.ALL, 5)

        main_vbox.Add(top_hbox, 2, wx.EXPAND | wx.ALL, 5) # Make top section take 2 parts of vertical space

        # --- Options Checkboxes Section ---
        options_panel = wx.StaticBoxSizer(wx.StaticBox(panel, label="Options"), wx.VERTICAL)
        
        self.highlight_nets_markdown_checkbox = wx.CheckBox(panel, label="Highlight Same Nets in Markdown Output")
        options_panel.Add(self.highlight_nets_markdown_checkbox, 0, wx.ALL, 5)

        self.sort_by_reference_checkbox = wx.CheckBox(panel, label="Sort Components by Reference (A-Z)")
        options_panel.Add(self.sort_by_reference_checkbox, 0, wx.ALL, 5)

        main_vbox.Add(options_panel, 0, wx.ALL | wx.EXPAND, 5)

        # --- Action Buttons Section ---
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        export_selected_button = wx.Button(panel, label="Export Selected")
        export_selected_button.Bind(wx.EVT_BUTTON, self.OnExportSelected)
        button_sizer.Add(export_selected_button, 0, wx.ALL, 5)

        export_js_button = wx.Button(panel, label="Export 'J's")
        export_js_button.Bind(wx.EVT_BUTTON, self.OnExportJs)
        button_sizer.Add(export_js_button, 0, wx.ALL, 5)
        
        cancel_button = wx.Button(panel, label="Close") # Renamed button for clarity
        cancel_button.Bind(wx.EVT_BUTTON, self.OnCancel)
        button_sizer.Add(cancel_button, 0, wx.ALL, 5)

        main_vbox.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        panel.SetSizer(main_vbox)
        main_vbox.Fit(self)

    def OnClose(self, event):
        """
        Event handler for the window close event (e.g., clicking the 'X' button).
        Ensures the dialog is properly destroyed.
        """
        print("DEBUG: Dialog OnClose event fired. Destroying dialog.")
        self.Destroy() # Destroy the dialog object

    def _update_footprint_list_display(self, footprints_list):
        """
        Clears and repopulates the ListCtrl with the given list of footprints.
        Also updates self.current_display_footprints.
        """
        self.footprint_list_ctrl.ClearAll()
        self.footprint_list_ctrl.InsertColumn(0, "Reference")
        self.footprint_list_ctrl.SetColumnWidth(0, 200)

        self.current_display_footprints = footprints_list 
        
        for i, fp in enumerate(self.current_display_footprints):
            self.footprint_list_ctrl.InsertItem(i, fp.GetReference())
        
        self.details_text_ctrl.SetValue("") # Clear details when list updates

    def OnRefreshSelection(self, event):
        """
        Event handler for the 'Refresh Selection from PCB' button.
        Gets the current selection from the KiCad PCB editor and updates the dialog's list.
        """
        print("DEBUG: OnRefreshSelection method called.")
        new_selected_footprints = [f for f in self.board.GetFootprints() if f.IsSelected()]
        self._update_footprint_list_display(new_selected_footprints)
        wx.MessageBox(f"Refreshed selection. Found {len(new_selected_footprints)} selected components.", "Selection Refreshed", wx.OK | wx.ICON_INFORMATION)

    def OnListItemSelected(self, event):
        """
        Event handler for when an item in the ListCtrl is selected.
        Displays detailed properties of the selected footprint in the details text area.
        """
        selected_index = event.GetIndex()
        if selected_index == wx.NOT_FOUND: # Should not happen if item is selected, but good check
            self.details_text_ctrl.SetValue("")
            return

        selected_fp = self.current_display_footprints[selected_index]
        print(f"DEBUG: List item selected: {selected_fp.GetReference()}")

        # Extract properties for display
        footprint_ref = selected_fp.GetReference()
        footprint_value = selected_fp.GetValue()
        footprint_id = selected_fp.GetFPID()
        footprint_full_name = str(footprint_id)
        footprint_description = selected_fp.GetLibDescription()
        footprint_layer = selected_fp.GetLayerName()
        footprint_pos = selected_fp.GetPosition()
        footprint_rot = selected_fp.GetOrientation()

        details_text = f"""
Reference: {footprint_ref}
Value: {footprint_value}
Footprint Name: {footprint_full_name}
Description: {footprint_description if footprint_description and footprint_description != "No description" else "N/A"}
Layer: {footprint_layer}
Position (X, Y): ({footprint_pos.x / 1000000.0:.2f}mm, {footprint_pos.y / 1000000.0:.2f}mm)
Rotation: {footprint_rot.AsDegrees():.1f}°
"""
        self.details_text_ctrl.SetValue(details_text.strip())


    def OnExportSelected(self, event):
        """
        Event handler for the 'Export Selected' button.
        Processes only the components currently displayed in the list.
        """
        print("DEBUG: OnExportSelected method called.")

        components_to_process = list(self.current_display_footprints) # Use the currently displayed list

        if self.sort_by_reference_checkbox.IsChecked():
            print("DEBUG: Sorting components by reference (for selected).")
            components_to_process.sort(key=lambda f: f.GetReference())
        else:
            print("DEBUG: Processing selected components in original selection order.")

        if not components_to_process:
            print("DEBUG: No selected footprints to process for export.")
            wx.MessageBox("No components are currently selected in the list to export.", "No Data", wx.OK | wx.ICON_INFORMATION)
            return

        self._perform_export(components_to_process, "selected_data.md", "selected_data.csv")
        # --- IMPORTANT: Do NOT close dialog here. User can continue interacting. ---
        # self.EndModal(wx.ID_OK) # REMOVED

    def OnExportJs(self, event):
        """
        Event handler for the 'Export 'J's' button.
        Filters all board footprints for those starting with 'J' and exports them.
        """
        print("DEBUG: OnExportJs method called.")

        js_footprints = [f for f in self.all_board_footprints if f.GetReference().startswith("J")]

        if self.sort_by_reference_checkbox.IsChecked():
            print("DEBUG: Sorting 'J' components by reference.")
            js_footprints.sort(key=lambda f: f.GetReference())
        else:
            print("DEBUG: Processing 'J' components in board order.")

        if not js_footprints:
            print("DEBUG: No 'J' components found on the board.")
            wx.MessageBox("No components starting with 'J' were found on the board.", "No 'J' Components", wx.OK | wx.INFORMATION)
            return
        
        self._perform_export(js_footprints, "js_components.md", "js_components.csv")
        # --- IMPORTANT: Do NOT close dialog here. User can continue interacting. ---
        # self.EndModal(wx.ID_OK) # REMOVED

    def OnCancel(self, event):
        """
        Event handler for the 'Close' button (formerly 'Cancel').
        Closes the dialog.
        """
        print("DEBUG: Close button clicked. Closing dialog.")
        self.Close() # This will trigger the OnClose event handler

    def _perform_export(self, footprints_list, default_md_name, default_csv_name):
        """
        Helper method to consolidate the common export logic (extraction, generation, saving).
        """
        extracted_data_by_footprint = self.extract_data(footprints_list)
        print(f"DEBUG: _perform_export: extract_data completed. Found {len(extracted_data_by_footprint)} components.")

        if not extracted_data_by_footprint:
            wx.MessageBox("No pins found in the filtered components to export.", "No Pin Data", wx.OK | wx.ICON_INFORMATION)
            print("DEBUG: _perform_export: No pins found after extraction.")
            return

        apply_markdown_highlight = self.highlight_nets_markdown_checkbox.IsChecked()
        print(f"DEBUG: _perform_export: Markdown highlighting requested: {apply_markdown_highlight}")

        markdown_content = self.generate_markdown(extracted_data_by_footprint, apply_markdown_highlight)
        csv_content = self.generate_csv(extracted_data_by_footprint)

        self.save_file_dialog(markdown_content, "Markdown Files (*.md)|*.md", "Save Pin Data (Markdown)", default_md_name)
        self.save_file_dialog(csv_content, "CSV Files (*.csv)|*.csv", "Save Pin Data (CSV)", default_csv_name)
        print("DEBUG: _perform_export: Export complete.")

    # --- Data Extraction and Generation Methods (Unchanged) ---
    def extract_data(self, footprints_to_process):
        extracted_data_by_footprint = {}
        for footprint in footprints_to_process: 
            footprint_ref = footprint.GetReference()
            footprint_value = footprint.GetValue()
            
            footprint_id = footprint.GetFPID()
            footprint_full_name = str(footprint_id) 
            
            footprint_description = footprint.GetLibDescription() 
            
            footprint_layer = footprint.GetLayerName()
            footprint_pos = footprint.GetPosition()
            footprint_rot = footprint.GetOrientation()

            general_properties = {
                "Reference": footprint_ref,
                "Value": footprint_value,
                "Footprint Name": footprint_full_name,
                "Description": footprint_description if footprint_description and footprint_description != "No description" else "N/A",
                "Layer": footprint_layer,
                "Position (X, Y)": f"({footprint_pos.x / 1000000.0:.2f}mm, {footprint_pos.y / 1000000.0:.2f}mm)",
                "Rotation": f"{footprint_rot.AsDegrees():.1f}°" 
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

    def generate_markdown(self, data_by_footprint, apply_highlight=False):
        markdown = "# Extracted Component Pin Data\n\n"
        
        html_color_palette = [
            "#FF0000", "#008000", "#0000FF", "#FFA500", "#800080", "#00FFFF", "#FFC0CB", "#00FF7F", "#8B4513",
            "#A52A2A", "#6A5ACD", "#D2691E", "#4682B4", "#BDB76B", "#FFD700"
        ]
        net_colors_map = {} 
        color_index = 0

        sorted_refs = sorted(data_by_footprint.keys(), key=lambda k: data_by_footprint[k]['general_properties']['Reference'])

        for ref in sorted_refs:
            component_data = data_by_footprint[ref]
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            markdown += f"## Component: {ref}\n\n"
            
            markdown += "### General Properties\n\n"
            markdown += "| Property | Value |\n"
            markdown += "|:---------|:------|\n"
            for prop_name, prop_value in general_props.items():
                markdown += f"| {prop_name} | {prop_value} |\n"
            markdown += "\n"

            if pin_data:
                markdown += "### Pin Details\n\n"
                markdown += "| Pad Name/Number | Net Name |\n"
                markdown += "|:----------------|:---------|\n"
                for pin_row in pin_data:
                    net_name = pin_row['Net Name']
                    
                    if apply_highlight and net_name != "":
                        if net_name not in net_colors_map:
                            net_colors_map[net_name] = html_color_palette[color_index % len(html_color_palette)]
                            color_index += 1
                        
                        display_net_name = f'<span style="color: {net_colors_map[net_name]};">{net_name}</span>'
                    else:
                        display_net_name = net_name
                        
                    markdown += f"| {pin_row['Pad Name/Number']} | {display_net_name} |\n"
                markdown += "\n"
            else:
                markdown += "No pins found for this component.\n\n"
        
        return markdown


    def generate_csv(self, data_by_footprint):
        output = StringIO()
        
        fixed_general_headers = ["Reference", "Value", "Footprint Name", "Description", "Layer", "Position (X, Y)", "Rotation"]
        pin_headers = ["Pad Name/Number", "Net Name"]
        
        fieldnames = fixed_general_headers + pin_headers
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()

        sorted_refs = sorted(data_by_footprint.keys(), key=lambda k: data_by_footprint[k]['general_properties']['Reference'])

        for ref in sorted_refs:
            component_data = data_by_footprint[ref]
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            base_row = {header: general_props.get(header, "") for header in fixed_general_headers}

            if not pin_data:
                writer.writerow(base_row)
            else:
                for pin_row in pin_data:
                    combined_row = base_row.copy()
                    combined_row.update(pin_row)
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