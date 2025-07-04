# __init__.py inside your_plugin_folder/

from .extract_pins_plugin import ExtractPinsPlugin

ExtractPinsPlugin().register()