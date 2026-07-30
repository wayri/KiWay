"""KiWay PCM entry point for Kilo — KiCad Localizer."""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

import wx

if wx.GetApp() is not None:
    from kilo.plugin.action_plugin import register

    register()
