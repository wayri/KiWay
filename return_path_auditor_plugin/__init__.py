from .return_path_auditor_plugin import ReturnPathAuditorPlugin

try:
    import wx
    if wx.GetApp() is not None:
        ReturnPathAuditorPlugin().register()
except Exception:
    pass
