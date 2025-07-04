import pcbnew
import os
import wx
import csv

class ExtractPinsPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Extract Connector Pins"
        self.category = "Utilities"
        self.description = "Extracts pin names and associated net names from selected footprints."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')

    def Run(self):
        board = pcbnew.GetBoard()
        
        # CORRECTED LINE:
        selected_footprints = [f for f in board.GetFootprints() if f.IsSelected()]

        if not selected_footprints:
            wx.MessageBox("Please select at least one footprint.", "No Footprints Selected", wx.OK | wx.ICON_INFORMATION)
            return

        extracted_data = []

        for footprint in selected_footprints:
            footprint_ref = footprint.GetReference()
            for pad in footprint.Pads():
                pad_name = pad.GetPadName()
                net_name = ""
                net = pad.GetNet()
                if net:
                    net_name = net.GetNetname()
                extracted_data.append({
                    "Footprint Ref": footprint_ref,
                    "Pad Name": pad_name,
                    "Net Name": net_name
                })

        if not extracted_data:
            wx.MessageBox("No pins found in the selected footprints.", "No Pin Data", wx.OK | wx.ICON_INFORMATION)
            return

        # Generate Markdown content
        markdown_content = self.generate_markdown(extracted_data)

        # Generate CSV content
        csv_content = self.generate_csv(extracted_data)

        # Prompt user to save Markdown file
        self.save_file_dialog(markdown_content, "Markdown Files (*.md)|*.md", "Save Pin Data (Markdown)", "pin_data.md")

        # Prompt user to save CSV file
        self.save_file_dialog(csv_content, "CSV Files (*.csv)|*.csv", "Save Pin Data (CSV)", "pin_data.csv")

    def generate_markdown(self, data):
        markdown = "# Extracted Pin Data\n\n"
        markdown += "| Footprint Ref | Pad Name | Net Name |\n"
        markdown += "|---|---|---|\n"
        for row in data:
            markdown += f"| {row['Footprint Ref']} | {row['Pad Name']} | {row['Net Name']} |\n"
        return markdown

    def generate_csv(self, data):
        from io import StringIO
        output = StringIO()
        fieldnames = ["Footprint Ref", "Pad Name", "Net Name"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
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

# Register the plugin (if you haven't already moved this to __init__.py)
# ExtractPinsPlugin().register() # Keep this in __init__.py as discussed