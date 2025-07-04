import pcbnew
import os
import wx
import csv
from io import StringIO

class ExtractPinsPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Extract Component Pins (Simplified)"
        self.category = "Utilities"
        self.description = "Extracts pin names and associated net names from selected footprints, with cleaner tables and basic properties."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')

    def Run(self):
        board = pcbnew.GetBoard()
        selected_footprints = [f for f in board.GetFootprints() if f.IsSelected()]

        if not selected_footprints:
            wx.MessageBox("Please select at least one footprint.", "No Footprints Selected", wx.OK | wx.ICON_INFORMATION)
            return

        # Sort footprints by reference designator for consistent output
        selected_footprints.sort(key=lambda f: f.GetReference())

        extracted_data_by_footprint = {}

        for footprint in selected_footprints:
            footprint_ref = footprint.GetReference()
            footprint_value = footprint.GetValue() # Value is usually available and comes from symbol

            # Get the full footprint name (e.g., "Library:FootprintName")
            footprint_id = footprint.GetFPID()
            library_nickname = footprint_id.GetLibraryNickname()
            footprint_name_in_lib = footprint_id.GetFootprintName()
            footprint_full_name = f"{library_nickname}:{footprint_name_in_lib}"
            
            # Get other basic properties from pcbnew.FOOTPRINT object
            footprint_description = footprint.GetDescription()
            footprint_layer = footprint.GetLayerName()
            footprint_pos = footprint.GetPosition()
            footprint_rot = footprint.GetOrientation() # Returns in tenths of a degree (e.g., 900 for 90 degrees)

            # Collect general properties that are directly accessible
            general_properties = {
                "Reference": footprint_ref,
                "Value": footprint_value,
                "Footprint Name": footprint_full_name,
                "Description": footprint_description if footprint_description and footprint_description != "No description" else "N/A",
                "Layer": footprint_layer,
                "Position (X, Y)": f"({footprint_pos.x / 1000000.0:.2f}mm, {footprint_pos.y / 1000000.0:.2f}mm)", # Convert to mm
                "Rotation": f"{footprint_rot / 10.0:.1f}°" # Convert from tenths of a degree to degrees
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

        if not extracted_data_by_footprint:
            wx.MessageBox("No pins found in the selected footprints.", "No Pin Data", wx.OK | wx.ICON_INFORMATION)
            return

        # Generate Markdown content
        markdown_content = self.generate_markdown(extracted_data_by_footprint)

        # Generate CSV content
        csv_content = self.generate_csv(extracted_data_by_footprint)

        # Prompt user to save Markdown file
        self.save_file_dialog(markdown_content, "Markdown Files (*.md)|*.md", "Save Pin Data (Markdown)", "pin_data.md")

        # Prompt user to save CSV file
        self.save_file_dialog(csv_content, "CSV Files (*.csv)|*.csv", "Save Pin Data (CSV)", "pin_data.csv")

    def generate_markdown(self, data_by_footprint):
        markdown = "# Extracted Component Pin Data\n\n"
        
        for ref, component_data in data_by_footprint.items():
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            markdown += f"## Component: {ref}\n\n"
            
            # General Properties Table/List
            markdown += "### General Properties\n\n"
            markdown += "| Property | Value |\n"
            markdown += "|:---------|:------|\n"
            for prop_name, prop_value in general_props.items(): # Iterate directly, no need to sort here
                markdown += f"| {prop_name} | {prop_value} |\n"
            markdown += "\n" # Add a newline to separate from next table

            # Pin Table
            if pin_data:
                markdown += "### Pin Details\n\n"
                markdown += "| Pad Name/Number | Net Name |\n"
                markdown += "|:----------------|:---------|\n"
                for pin_row in pin_data:
                    markdown += f"| {pin_row['Pad Name/Number']} | {pin_row['Net Name']} |\n"
                markdown += "\n" # Add a newline to separate tables
            else:
                markdown += "No pins found for this component.\n\n"
        
        return markdown

    def generate_csv(self, data_by_footprint):
        output = StringIO()
        
        # Define a fixed set of general headers for CSV, in a desired order
        # This makes the CSV header more predictable.
        fixed_general_headers = ["Reference", "Value", "Footprint Name", "Description", "Layer", "Position (X, Y)", "Rotation"]
        pin_headers = ["Pad Name/Number", "Net Name"]
        
        fieldnames = fixed_general_headers + pin_headers
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()

        for ref, component_data in data_by_footprint.items():
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            base_row = {}
            for header in fixed_general_headers:
                base_row[header] = general_props.get(header, "") # Use .get() for safety if a prop is missing

            if not pin_data: # Handle components with no pins (unlikely, but robust)
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

# This line should be in your __init__.py file in the plugin folder,
# not in this main plugin file for proper package loading.
# (Confirm it's only in __init__.py as:
# from .extract_pins_plugin import ExtractPinsPlugin
# ExtractPinsPlugin().register()