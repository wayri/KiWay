# plugin_dialog.py
# Located in: your_kicad_plugin_directory/extract_pins_plugin/plugin_dialog.py

import wx
import pcbnew
import csv
from io import StringIO
import random # Used for generating random colors for highlighting

class PluginDialog(wx.Dialog):
    """
    A custom wxPython dialog for the KiCad pin extraction plugin.
    It provides a user interface to:
    - Display currently selected components.
    - Offer options like highlighting same nets.
    - Trigger data extraction and file saving.
    """
    def __init__(self, parent, selected_footprints):
        """
        Initializes the dialog window.
        
        Args:
            parent: The parent wx.Window (typically None for a top-level dialog).
            selected_footprints: A list of pcbnew.FOOTPRINT objects currently selected.
        """
        # Call the constructor of the base wx.Dialog class
        super(PluginDialog, self).__init__(parent, title="KiCad Pin Extractor", size=(600, 500))
        
        print("DEBUG: PluginDialog __init__ called.") # DEBUG PRINT
        
        # Store essential data that the dialog will operate on
        self.selected_footprints = selected_footprints
        self.board = pcbnew.GetBoard() # Get the current PCB board instance (same as from ActionPlugin)
        
        # Dictionaries to manage net highlighting state:
        # Stores original pad text colors to allow reverting them when highlighting is off or dialog closes.
        self.original_pad_colors = {} 
        # Stores the assigned highlight color for each unique net name.
        self.net_colors = {} 

        self.InitUI() # Call method to set up the visual layout of the dialog
        self.Centre() # Center the dialog window on the screen
        self.ShowModal() # Display the dialog and block execution until it is closed by the user
        self.Destroy() # Destroy the dialog object after it's closed to free up system resources
        
        print("DEBUG: PluginDialog closed.") # DEBUG PRINT

    def InitUI(self):
        """
        Configures the layout and widgets of the dialog's user interface.
        """
        panel = wx.Panel(self) # Create a panel to serve as the main drawing area for widgets
        vbox = wx.BoxSizer(wx.VERTICAL) # Use a vertical box sizer for top-level layout

        # --- Selected Components Section ---
        selected_label = wx.StaticText(panel, label="Selected Components:")
        vbox.Add(selected_label, 0, wx.ALL | wx.EXPAND, 5) # Add label with padding and horizontal expansion

        # wx.ListCtrl to show the reference designators of the selected footprints
        self.footprint_list_ctrl = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_NO_HEADER | wx.LC_SINGLE_SEL)
        self.footprint_list_ctrl.InsertColumn(0, "Reference") # Define a single column for references
        self.footprint_list_ctrl.SetColumnWidth(0, 200) # Set an appropriate width for the column
        
        # Populate the ListCtrl with the reference designator of each selected footprint
        for i, fp in enumerate(self.selected_footprints):
            self.footprint_list_ctrl.InsertItem(i, fp.GetReference())
        
        # Add the ListCtrl to the sizer, making it expand vertically to fill available space
        vbox.Add(self.footprint_list_ctrl, 1, wx.ALL | wx.EXPAND, 5)

        # --- Options Checkboxes Section ---
        # A static box to visually group the options
        options_panel = wx.StaticBoxSizer(wx.StaticBox(panel, label="Options"), wx.VERTICAL)
        
        # Checkbox for the "Highlight Same Nets" feature
        self.highlight_nets_checkbox = wx.CheckBox(panel, label="Highlight Same Nets")
        options_panel.Add(self.highlight_nets_checkbox, 0, wx.ALL, 5) # Add checkbox with padding
        
        # Bind the checkbox's state change event to the OnHighlightNets method
        self.highlight_nets_checkbox.Bind(wx.EVT_CHECKBOX, self.OnHighlightNets)

        vbox.Add(options_panel, 0, wx.ALL | wx.EXPAND, 5) # Add the options panel to the main sizer

        # --- Action Buttons Section ---
        button_sizer = wx.BoxSizer(wx.HORIZONTAL) # Horizontal sizer to arrange buttons
        export_button = wx.Button(panel, label="Export & Run")
        cancel_button = wx.Button(panel, label="Cancel")

        # Bind button click events to their respective handler methods
        export_button.Bind(wx.EVT_BUTTON, self.OnExportRun)
        cancel_button.Bind(wx.EVT_BUTTON, self.OnCancel)

        # Add buttons to their sizer
        button_sizer.Add(export_button, 0, wx.ALL, 5)
        button_sizer.Add(cancel_button, 0, wx.ALL, 5)
        
        # Add the button sizer to the main sizer, aligned to the right
        vbox.Add(button_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

        panel.SetSizer(vbox) # Assign the sizer to the panel
        vbox.Fit(self) # Automatically adjust the dialog's size to fit its contents

    def OnHighlightNets(self, event):
        """
        Event handler for the 'Highlight Same Nets' checkbox.
        Applies or removes net highlighting based on the checkbox's current state.
        """
        if self.highlight_nets_checkbox.IsChecked():
            self.apply_net_highlight()
        else:
            self.reset_net_colors()
        
        # Crucial: Force KiCad's PCB view to refresh to show the color changes
        self.board.UpdateBoundingBox() # Good practice to update bounding box if elements moved/changed
        pcbnew.Refresh() # This command redraws the PCB canvas

    def apply_net_highlight(self):
        """
        Applies a unique color to the text of pads that belong to the same net,
        for pads within the currently selected footprints.
        """
        # Define a palette of distinct wx.Colour objects (Red, Green, Blue components).
        # You can expand or modify this palette with more colors as needed.
        color_palette = [
            wx.Colour(255, 0, 0),    # Bright Red
            wx.Colour(0, 255, 0),    # Bright Green
            wx.Colour(0, 0, 255),    # Bright Blue
            wx.Colour(255, 255, 0),  # Yellow
            wx.Colour(0, 255, 255),  # Cyan
            wx.Colour(255, 0, 255),  # Magenta
            wx.Colour(255, 128, 0),  # Orange
            wx.Colour(128, 0, 255),  # Purple
            wx.Colour(0, 128, 128),  # Teal
            wx.Colour(128, 128, 0),  # Olive
            wx.Colour(128, 0, 0),    # Dark Red
            wx.Colour(0, 128, 0),    # Dark Green
            wx.Colour(0, 0, 128),    # Dark Blue
        ]
        
        # First, reset any previously applied highlights to ensure a clean state
        self.reset_net_colors() 
        self.net_colors = {} # Clear the net-to-color mapping for a fresh assignment
        color_index = 0 # Index to cycle through the color_palette

        # Iterate through all pads of the selected footprints
        for footprint in self.selected_footprints:
            for pad in footprint.Pads():
                net = pad.GetNet() # Get the net object associated with the pad
                if net: # Ensure the pad is connected to a net
                    net_name = net.GetNetname() # Get the name of the net
                    
                    # If this net name hasn't been assigned a color yet, pick one from the palette
                    if net_name not in self.net_colors:
                        self.net_colors[net_name] = color_palette[color_index % len(color_palette)]
                        color_index += 1 # Move to the next color for the next unique net
                    
                    # Store the pad's original text color before changing it.
                    # This is crucial for reverting the colors later.
                    # We use the pad object itself as the key in the dictionary.
                    if pad not in self.original_pad_colors:
                         self.original_pad_colors[pad] = pad.GetTextColour()
                    
                    # Apply the assigned net color to the pad's text
                    pad.SetTextColour(self.net_colors[net_name])
                    
                    # Note: Directly changing pad.SetColor() might affect the pad's fill color,
                    # which can sometimes obscure other elements. Setting text color is often
                    # a less intrusive way to provide visual highlighting. For full net highlighting
                    # (including tracks), KiCad's internal highlight tool (hotkey 'H') is more comprehensive.

    def reset_net_colors(self):
        """
        Resets the text color of all previously highlighted pads back to their original colors.
        """
        # Iterate through the stored original colors and apply them back to the pads
        for pad, original_color in self.original_pad_colors.items():
            pad.SetTextColour(original_color)
            # If you also modified pad.SetColor(), you would reset that here as well:
            # e.g., pad.SetColor(original_pad_fill_color)
        self.original_pad_colors.clear() # Clear the storage after resetting all colors

    def OnExportRun(self, event):
        """
        Event handler for the 'Export & Run' button.
        This method triggers the data extraction, generates the Markdown and CSV files,
        prompts the user to save them, and then closes the dialog.
        """
        print("DEBUG: OnExportRun method called.") # DEBUG PRINT

        # Basic check: ensure there are footprints to process
        if not self.selected_footprints:
            print("DEBUG: No footprints in self.selected_footprints when OnExportRun called.") # DEBUG PRINT
            wx.MessageBox("Internal error: No selected footprints found for extraction.", "Plugin Error", wx.OK | wx.ICON_ERROR)
            return

        # Extract data from selected footprints
        extracted_data_by_footprint = self.extract_data()
        print(f"DEBUG: extract_data completed. Found {len(extracted_data_by_footprint)} components.") # DEBUG PRINT

        if not extracted_data_by_footprint:
            wx.MessageBox("No pins found in the selected footprints to export.", "No Pin Data", wx.OK | wx.ICON_INFORMATION)
            print("DEBUG: No pins found after extraction.") # DEBUG PRINT
            return

        # Generate content for Markdown and CSV files
        print("DEBUG: Generating Markdown content.") # DEBUG PRINT
        markdown_content = self.generate_markdown(extracted_data_by_footprint)
        print("DEBUG: Generating CSV content.") # DEBUG PRINT
        csv_content = self.generate_csv(extracted_data_by_footprint)

        # Prompt user to save the Markdown file
        print("DEBUG: Showing Markdown save dialog.") # DEBUG PRINT
        self.save_file_dialog(markdown_content, "Markdown Files (*.md)|*.md", "Save Pin Data (Markdown)", "pin_data.md")

        # Prompt user to save the CSV file
        print("DEBUG: Showing CSV save dialog.") # DEBUG PRINT
        self.save_file_dialog(csv_content, "CSV Files (*.csv)|*.csv", "Save Pin Data (CSV)", "pin_data.csv")
        
        # Reset any applied highlights before closing the dialog
        self.reset_net_colors()
        pcbnew.Refresh() # Ensure the PCB view is updated one last time
        
        print("DEBUG: Export & Run finished. Closing dialog.") # DEBUG PRINT
        # Close the dialog with an OK result code
        self.EndModal(wx.ID_OK) 

    def OnCancel(self, event):
        """
        Event handler for the 'Cancel' button.
        Resets any applied highlights and closes the dialog without exporting files.
        """
        self.reset_net_colors() # Reset colors if the user cancels
        pcbnew.Refresh() # Ensure the PCB view is updated
        
        # Close the dialog with a Cancel result code
        self.EndModal(wx.ID_CANCEL) 

    # --- Data Extraction and Generation Methods (Copied from previous successful version) ---
    # These methods are now part of the PluginDialog class

    def extract_data(self):
        """
        Extracts relevant properties and pin details from the selected footprints.
        Returns a dictionary organized by footprint reference designator.
        """
        extracted_data_by_footprint = {}
        for footprint in self.selected_footprints:
            footprint_ref = footprint.GetReference() # e.g., "J1"
            footprint_value = footprint.GetValue()   # e.g., "CONN_01x02"
            
            # --- START CORRECTED LINES for getting footprint name ---
            # Get the LIB_ID object first
            footprint_id = footprint.GetFPID()
            
            # The most reliable way to get the "Library:FootprintName" string from LIB_ID
            footprint_full_name = str(footprint_id) 
            # --- END CORRECTED LINES ---
            
            # Get other basic properties directly from the pcbnew.FOOTPRINT object
            footprint_description = footprint.GetLibDescription() # Footprint's own description
            footprint_layer = footprint.GetLayerName()         # Layer the footprint is on (e.g., "F.Cu")
            footprint_pos = footprint.GetPosition()            # Position as a wxPoint-like object
            footprint_rot = footprint.GetOrientation()         # Rotation in tenths of a degree

            # Compile general properties into a dictionary
            general_properties = {
                "Reference": footprint_ref,
                "Value": footprint_value,
                "Footprint Name": footprint_full_name, # Use the correctly obtained full name
                # Handle description: if it's empty or default "No description", show "N/A"
                "Description": footprint_description if footprint_description and footprint_description != "No description" else "N/A",
                "Layer": footprint_layer,
                # Convert internal units (nanometers) to millimeters for display
                "Position (X, Y)": f"({footprint_pos.x / 1000000.0:.2f}mm, {footprint_pos.y / 1000000.0:.2f}mm)",
                # Convert rotation from tenths of a degree to degrees
                "Rotation": f"{footprint_rot.AsDegrees():.1f}°" 
            }

            pin_data = []
            for pad in footprint.Pads():
                pad_name = pad.GetPadName() # e.g., "1", "A1"
                net_name = "" # Initialize net name as empty
                net = pad.GetNet() # Get the net object associated with the pad
                if net: # If a net is assigned
                    net_name = net.GetNetname() # Get the name of the net
                pin_data.append({
                    "Pad Name/Number": pad_name,
                    "Net Name": net_name
                })
            
            # Store all extracted data for the current footprint
            extracted_data_by_footprint[footprint_ref] = {
                "general_properties": general_properties,
                "pin_data": pin_data
            }
        return extracted_data_by_footprint
        """
        Extracts relevant properties and pin details from the selected footprints.
        Returns a dictionary where keys are footprint reference designators,
        and values contain general properties and pin-specific data.
        """
        extracted_data_by_footprint = {}
        for footprint in self.selected_footprints:
            footprint_ref = footprint.GetReference() # e.g., "J1"
            footprint_value = footprint.GetValue()   # e.g., "CONN_01x02"
            
            # Get the full footprint name (e.g., "Connector_Generic:CONN_01x02")
            # This involves getting the LIB_ID object and then extracting its components.
            footprint_id = footprint.GetFPID()
            library_nickname = footprint_id.GetLibNickname()
            footprint_name_in_lib = footprint_id.GetFootprintName()
            footprint_full_name = f"{library_nickname}:{footprint_name_in_lib}"
            
            # Get other basic properties directly from the pcbnew.FOOTPRINT object
            footprint_description = footprint.GetDescription() # Footprint's own description
            footprint_layer = footprint.GetLayerName()         # Layer the footprint is on (e.g., "F.Cu")
            footprint_pos = footprint.GetPosition()            # Position as a wxPoint-like object
            footprint_rot = footprint.GetOrientation()         # Rotation in tenths of a degree

            # Compile general properties into a dictionary
            general_properties = {
                "Reference": footprint_ref,
                "Value": footprint_value,
                "Footprint Name": footprint_full_name,
                # Handle description: if it's empty or default "No description", show "N/A"
                "Description": footprint_description if footprint_description and footprint_description != "No description" else "N/A",
                "Layer": footprint_layer,
                # Convert internal units (nanometers) to millimeters for display
                "Position (X, Y)": f"({footprint_pos.x / 1000000.0:.2f}mm, {footprint_pos.y / 1000000.0:.2f}mm)",
                # Convert rotation from tenths of a degree to degrees
                "Rotation": f"{footprint_rot / 10.0:.1f}°" 
            }

            pin_data = []
            for pad in footprint.Pads():
                pad_name = pad.GetPadName() # e.g., "1", "A1"
                net_name = "" # Initialize net name as empty
                net = pad.GetNet() # Get the net object associated with the pad
                if net: # If a net is assigned
                    net_name = net.GetNetname() # Get the name of the net
                pin_data.append({
                    "Pad Name/Number": pad_name,
                    "Net Name": net_name
                })
            
            # Store all extracted data for the current footprint
            extracted_data_by_footprint[footprint_ref] = {
                "general_properties": general_properties,
                "pin_data": pin_data
            }
        return extracted_data_by_footprint

    def generate_markdown(self, data_by_footprint):
        """
        Generates a Markdown formatted string from the extracted data.
        Each component gets its own section with a general properties table and a pin details table.
        """
        markdown = "# Extracted Component Pin Data\n\n"
        
        # Iterate through each component's data
        for ref, component_data in data_by_footprint.items():
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            # Add a main heading for each component
            markdown += f"## Component: {ref}\n\n"
            
            # Add a sub-heading for general properties
            markdown += "### General Properties\n\n"
            markdown += "| Property | Value |\n"
            markdown += "|:---------|:------|\n" # Markdown table header separator for left alignment
            # Populate the general properties table
            for prop_name, prop_value in general_props.items():
                markdown += f"| {prop_name} | {prop_value} |\n"
            markdown += "\n" # Add a newline to separate from the next table

            # Add a sub-heading for pin details if pins exist
            if pin_data:
                markdown += "### Pin Details\n\n"
                markdown += "| Pad Name/Number | Net Name |\n"
                markdown += "|:----------------|:---------|\n" # Markdown table header separator for left alignment
                # Populate the pin details table
                for pin_row in pin_data:
                    markdown += f"| {pin_row['Pad Name/Number']} | {pin_row['Net Name']} |\n"
                markdown += "\n" # Add a newline to separate tables
            else:
                markdown += "No pins found for this component.\n\n"
        
        return markdown

    def generate_csv(self, data_by_footprint):
        """
        Generates a CSV formatted string from the extracted data.
        The CSV is flattened, meaning each row represents a single pin,
        and general component properties are repeated for each pin of that component.
        """
        output = StringIO() # Use StringIO to write CSV data to an in-memory string buffer
        
        # Define a fixed set of general headers for the CSV, in a desired display order.
        # This ensures consistent column order regardless of which properties are present for each component.
        fixed_general_headers = ["Reference", "Value", "Footprint Name", "Description", "Layer", "Position (X, Y)", "Rotation"]
        pin_headers = ["Pad Name/Number", "Net Name"]
        
        # Combine all headers to form the complete list of CSV column names
        fieldnames = fixed_general_headers + pin_headers
        
        # Create a CSV writer. 'extrasaction='ignore'' prevents errors if a row dictionary
        # contains keys not present in 'fieldnames'.
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader() # Write the header row to the CSV file

        # Iterate through each component's data to populate the CSV rows
        for ref, component_data in data_by_footprint.items():
            general_props = component_data["general_properties"]
            pin_data = component_data["pin_data"]

            # Create a base row with general component properties.
            # Use .get() with an empty string as default to handle cases where a property might be missing.
            base_row = {header: general_props.get(header, "") for header in fixed_general_headers}

            if not pin_data: # If a component has no pins (e.g., a mounting hole), write its general info only
                writer.writerow(base_row)
            else:
                # For each pin, create a new row by combining the base component info with pin-specific data
                for pin_row in pin_data:
                    combined_row = base_row.copy() # Create a copy to avoid modifying the original base_row
                    combined_row.update(pin_row) # Add pin-specific data to the copied row
                    writer.writerow(combined_row) # Write the combined row to the CSV
                    
        return output.getvalue() # Return the complete CSV data as a string

    def save_file_dialog(self, content, wildcard, title, default_filename):
        """
        Opens a standard file dialog, prompting the user to select a location
        and filename to save the provided content.
        
        Args:
            content (str): The string content to be saved (e.g., Markdown or CSV data).
            wildcard (str): File type filter for the dialog (e.g., "Text Files (*.txt)|*.txt").
            title (str): The title of the save dialog window.
            default_filename (str): The default filename suggested to the user.
        """
        # Create a wx.FileDialog for saving a file
        with wx.FileDialog(
            None, # Parent window (None for a top-level dialog)
            title, # Title of the dialog
            wildcard=wildcard, # File type filter
            defaultFile=default_filename, # Default filename suggestion
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT # Save mode, and prompt if file exists
        ) as file_dialog:
            # Show the dialog. If the user cancels, ShowModal() returns wx.ID_CANCEL.
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return # Exit if the user cancels

            pathname = file_dialog.GetPath() # Get the full path selected by the user
            try:
                # Open the file in write mode ('w') with UTF-8 encoding
                with open(pathname, 'w', encoding='utf-8') as f:
                    f.write(content) # Write the provided content to the file
                # Show a success message to the user
                wx.MessageBox(f"File saved successfully to:\n{pathname}", "Success", wx.OK | wx.ICON_INFORMATION)
            except Exception as e:
                # If any error occurs during file saving, show an error message
                wx.MessageBox(f"Error saving file:\n{e}", "Error", wx.OK | wx.ICON_ERROR)