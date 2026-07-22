"""KiWay Test Point Descriptor Extractor plugin entry point."""

from .test_point_descriptor_plugin import TestPointDescriptorPlugin

import wx

if wx.GetApp() is not None:
    TestPointDescriptorPlugin().register()

