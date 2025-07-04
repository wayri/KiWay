# extract_pins_plugin.py
# Located in: your_kicad_plugin_directory/extract_pins_plugin/extract_pins_plugin.py

import pcbnew
import wx
import os

# Import the custom dialog class from 'plugin_dialog.py'
from .plugin_dialog import PluginDialog 

class ExtractPinsPlugin(pcbnew.ActionPlugin):
    """
    Main KiCad ActionPlugin for extracting pin data and highlighting nets.
    This plugin acts as the entry point, launching the GUI dialog.
    """
    def defaults(self):
        """
        Sets the metadata for the plugin, which KiCad displays in its menus.
        """
        self.name = "Extract Component Pins with GUI" # The name visible in KiCad's 'Tools -> External Plugins' menu
        self.category = "Utilities" # Category under which the plugin will be listed
        self.description = "Opens a GUI to extract pin data and highlight nets from selected footprints."
        self.show_toolbar_button = True # Set to True to display a button on the toolbar
        # Define the path to the optional icon file. It should be in the same directory.
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'epp_favicon.png')
        self.version = "1.1.0"

    def Run(self):
        """
        This method is called by KiCad when the user activates the plugin.
        It retrieves the current PCB board and selected footprints, then launches the GUI.
        """
        board = pcbnew.GetBoard() # Get a reference to the currently active PCB board

        # Retrieve all footprints on the board and filter for those that are currently selected.
        # This is the robust way to get user-selected footprints in KiCad 9's pcbnew API.
        selected_footprints = [f for f in board.GetFootprints() if f.IsSelected()]

        if not selected_footprints:
            # If no footprints are selected, inform the user and exit.
            wx.MessageBox(
                "Please select at least one footprint on the PCB before running the plugin.",
                "No Footprints Selected",
                wx.OK | wx.ICON_INFORMATION # Standard message box style
            )
            return # Exit the Run method if no footprints are selected

        # Create an instance of our custom PluginDialog.
        # 'None' is passed as the parent window, making it a top-level dialog.
        # The list of selected footprints is passed to the dialog for processing.
        dialog = PluginDialog(None, selected_footprints) 
        
        # The dialog's ShowModal() method will display the dialog and block further execution
        # of the current thread until the dialog is closed by the user.
        # The dialog is responsible for its own destruction (Destroy()) upon closing.
        # Once the dialog is closed, this Run() method simply finishes.