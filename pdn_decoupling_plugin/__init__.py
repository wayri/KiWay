from .pdn_decoupling_plugin import PdnDecouplingPlugin
try:
    import wx
    if wx.GetApp() is not None:PdnDecouplingPlugin().register()
except Exception:pass
