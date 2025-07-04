import wx
import pcbnew
import csv
from io import StringIO
import random # Still useful for generating diverse colors for Markdown HTML

class PluginDialog(wx.Dialog):
    """
    A custom wxPython dialog for the KiCad pin extraction plugin.
    It provides a user interface to:
    - Display currently selected components.
    - Offer options like sorting components and highlighting same nets in Markdown output.
    - Trigger data extraction and file saving.
    """
    def __init__(self, parent, selected_footprints):
        """
        Initializes the dialog window.
        
        Args:
            parent: The parent wx.Window (typically None for a top-level dialog).
            selected_footprints: A list of pcbnew.FOOTPRINT objects currently selected.
        """
        super(PluginDialog, self).__init__(parent, title="KiCad Pin Extractor", size=(600, 500))
        
        print("DEBUG: PluginDialog __init__ called.") # DEBUG PRINT
        
        self.selected_footprints = selected_footprints
        self.board = pcbnew.GetBoard() # Reference to the board (not used for PCB highlighting anymore)
        
        # No more need for original_pad_colors or net_colors for PCB highlighting
        # self.original_pad_colors = {} 
        # self.net_colors = {} 

        self.InitUI()
        self.Centre()
        self.ShowModal()
        self.Destroy()
        
        print("DEBUG: PluginDialog closed.") # DEBUG PRINT

    def InitUI(self):
        """
        Configures the layout and widgets of the dialog's user interface.
        """
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # --- Selected Components Section ---
        selected_label = wx.StaticText(panel, label="Selected Components:")
        vbox.Add(selected_label, 0, wx.ALL | wx.EXPAND, 5)

        self.footprint_list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL)
        self.footprint_list_ctrl.InsertColumn(0, "Reference")
        self.footprint_list_ctrl.SetColumnWidth(0, 200)
        
        for i, fp in enumerate(self.selected_footprints):
            self.footprint_list_ctrl.InsertItem(i, fp.GetReference())
        
        vbox.Add(self.footprint_list_ctrl, 1, wx.ALL | wx.EXPAND, 5)

        # --- Options Checkboxes Section ---
        options_panel = wx.StaticBoxSizer(wx.StaticBox(panel, label="Options"), wx.VERTICAL)
        
        # --- NEW CHECKBOX FOR MARKDOWN HIGHLIGHTING ---
        self.highlight_nets_markdown_checkbox = wx.CheckBox(panel, label="Highlight Same Nets in Markdown Output")
        options_panel.Add(self.highlight_nets_markdown_checkbox, 0, wx.ALL, 5)
        # No bind needed, its state is read on "Export & Run"

        # --- CHECKBOX FOR SORTING ---
        self.sort_by_reference_checkbox = wx.CheckBox(panel, label="Sort Components by Reference (A-Z)")
        options_panel.Add(self.sort_by_reference_checkbox, 0, wx.ALL, 5)

        vbox.Add(options_panel, 0, wx.ALL | wx.EXPAND, 5)

        # --- Action Buttons Section ---
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        export_button = wx.Button(panel, label="Export & Run")
        cancel_button = wx.Button(panel, label="Cancel")

        export_button.Bind(wx.EVT_BUTTON, self.OnExportRun)
        cancel_button.Bind(wx.EVT_BUTTON, self.OnCancel)

        button_sizer.Add(export_button, 0, wx.ALL, 5)
        button_sizer.Add(cancel_button, 0, wx.ALL, 5)
        vbox.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        panel.SetSizer(vbox)
        vbox.Fit(self)

    # --- REMOVED: OnHighlightNets, apply_net_highlight, reset_net_colors ---
    # These methods are no longer needed as highlighting is for Markdown, not PCB view.

    def OnExportRun(self, event):
        """
        Event handler for the 'Export & Run' button.
        Performs data extraction, generates files, and prompts for saving.
        """
        print("DEBUG: OnExportRun method called.") # DEBUG PRINT

        # --- CONDITIONAL SORTING LOGIC ---
        components_to_process = list(self.selected_footprints) # Create a copy to allow sorting
        if self.sort_by_reference_checkbox.IsChecked():
            print("DEBUG: Sorting components by reference.") # DEBUG PRINT
            components_to_process.sort(key=lambda f: f.GetReference())
        else:
            print("DEBUG: Processing components in original selection order.") # DEBUG PRINT


        # Basic check: ensure there are footprints to process
        if not components_to_process:
            print("DEBUG: No footprints in components_to_process when OnExportRun called.") # DEBUG PRINT
            wx.MessageBox("Internal error: No selected footprints found for extraction.", "Plugin Error", wx.OK | wx.ICON_ERROR)
            return

        # Extract data (pass the potentially sorted list)
        extracted_data_by_footprint = self.extract_data(components_to_process)
        print(f"DEBUG: extract_data completed. Found {len(extracted_data_by_footprint)} components.") # DEBUG PRINT

        if not extracted_data_by_footprint:
            wx.MessageBox("No pins found in the selected footprints to export.", "No Pin Data", wx.OK | wx.ICON_INFORMATION)
            print("DEBUG: No pins found after extraction.") # DEBUG PRINT
            return

        # Check if Markdown highlighting is requested
        apply_markdown_highlight = self.highlight_nets_markdown_checkbox.IsChecked()
        print(f"DEBUG: Markdown highlighting requested: {apply_markdown_highlight}") # DEBUG PRINT

        # Generate content for Markdown and CSV files
        print("DEBUG: Generating Markdown content.") # DEBUG PRINT
        markdown_content = self.generate_markdown(extracted_data_by_footprint, apply_markdown_highlight) # Pass the flag
        print("DEBUG: Generating CSV content.") # DEBUG PRINT
        csv_content = self.generate_csv(extracted_data_by_footprint)

        # Prompt user to save Markdown file
        print("DEBUG: Showing Markdown save dialog.") # DEBUG PRINT
        self.save_file_dialog(markdown_content, "Markdown Files (*.md)|*.md", "Save Pin Data (Markdown)", "pin_data.md")

        # Prompt user to save CSV file
        print("DEBUG: Showing CSV save dialog.") # DEBUG PRINT
        self.save_file_dialog(csv_content, "CSV Files (*.csv)|*.csv", "Save Pin Data (CSV)", "pin_data.csv")
        
        # No PCB reset needed for Markdown highlighting
        # pcbnew.Refresh() # Removed
        
        print("DEBUG: Export & Run finished. Closing dialog.") # DEBUG PRINT
        self.EndModal(wx.ID_OK)

    def OnCancel(self, event):
        """
        Event handler for the 'Cancel' button.
        Closes the dialog without exporting.
        """
        # No PCB reset needed for Markdown highlighting
        # pcbnew.Refresh() # Removed
        self.EndModal(wx.ID_CANCEL)

    # --- Data Extraction and Generation Methods ---

    def extract_data(self, footprints_to_process):
        """
        Extracts relevant properties and pin details from the provided list of footprints.
        Returns a dictionary organized by footprint reference designator.
        """
        extracted_data_by_footprint = {}
        for footprint in footprints_to_process: 
            footprint_ref = footprint.GetReference()
            footprint_value = footprint.GetValue()
            
            footprint_id = footprint.GetFPID()
            footprint_full_name = str(footprint_id) 
            
            footprint_description = footprint.GetLibDescription() # Corrected: Get description from the footprint's library definition
            
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

    def generate_markdown(self, data_by_footprint, apply_highlight=False): # ADD apply_highlight FLAG
        """
        Generates a Markdown formatted string from the extracted data.
        Each component gets its own section with a general properties table and a pin details table.
        Optionally applies color highlighting to net names using HTML in Markdown.
        """
        markdown = "# Extracted Component Pin Data\n\n"
        
        # Define a palette of HTML-friendly colors for highlighting nets
        # These are standard web colors, more can be added
        html_color_palette = [
            "#FF0000", "#008000", "#0000FF", "#FFA500", "#800080", "#00FFFF", "#FFC0CB", "#00FF7F", "#8B4513",
            "#A52A2A", "#6A5ACD", "#D2691E", "#4682B4", "#BDB76B", "#FFD700"
        ]
        net_colors_map = {} # To store assigned colors for nets
        color_index = 0

        # Sort components in the markdown output by reference key for consistent display
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
                    
                    # Apply highlighting if requested
                    if apply_highlight and net_name != "": # Don't highlight empty net names
                        if net_name not in net_colors_map:
                            net_colors_map[net_name] = html_color_palette[color_index % len(html_color_palette)]
                            color_index += 1
                        
                        # Wrap net name in HTML span tag for color
                        display_net_name = f'<span style="color: {net_colors_map[net_name]};">{net_name}</span>'
                    else:
                        display_net_name = net_name # No highlighting
                        
                    markdown += f"| {pin_row['Pad Name/Number']} | {display_net_name} |\n"
                markdown += "\n"
            else:
                markdown += "No pins found for this component.\n\n"
        
        return markdown


    def generate_csv(self, data_by_footprint):
        """
        Generates a CSV formatted string from the extracted data.
        The CSV is flattened, meaning each row represents a single pin,
        and general component properties are repeated for each pin of that component.
        """
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
        """
        Opens a standard file dialog, prompting the user to select a location
        and filename to save the provided content.
        """
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