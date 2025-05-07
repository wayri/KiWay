import pcbnew
import wx
import math

class FanOutPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Fan Out Pads with GUI"
        self.category = "Routing Tools"
        self.description = "Fan out pads with configurable trace/via settings and direction"

    def Run(self):
        dialog = FanoutDialog(None, "Fanout Settings")
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return

        # Get user inputs
        fanout_style = dialog.style_choice.GetStringSelection().lower()
        trace_width = float(dialog.trace_width_ctrl.GetValue())
        trace_length = float(dialog.trace_length_ctrl.GetValue())
        via_diameter = float(dialog.via_diameter_ctrl.GetValue())
        via_drill = float(dialog.via_drill_ctrl.GetValue())
        angle_deg = int(dialog.angle_choice.GetStringSelection())
        angle_rad = math.radians(angle_deg)

        dialog.Destroy()

        # Unit conversion
        board = pcbnew.GetBoard()
        modules = board.GetFootprints()
        trace_length_internal = pcbnew.FromMM(trace_length)
        trace_width_internal = pcbnew.FromMM(trace_width)
        via_diameter_internal = pcbnew.FromMM(via_diameter)
        via_drill_internal = pcbnew.FromMM(via_drill)
        via_layer_start = pcbnew.F_Cu
        via_layer_end = pcbnew.In1_Cu  # Adjust based on your stackup

        for footprint in modules:
            if not footprint.IsSelected():
                continue

            center = footprint.GetPosition()

            for pad in footprint.Pads():
                if not pad.IsConnected():
                    continue

                pad_pos = pad.GetPosition()

                # Determine direction
                if fanout_style == 'quadrant':
                    dx, dy = quadrant_direction(pad_pos, center)
                    dx, dy = rotate_vector(dx, dy, angle_rad)

                elif fanout_style == 'square quadrant':
                    dx, dy = square_quadrant_direction(pad_pos, center)
                    dx, dy = rotate_vector(dx, dy, angle_rad)

                elif fanout_style == 'diagonal':
                    dx, dy = diagonal_direction(pad_pos, center)

                else:  # angled
                    dx = math.cos(angle_rad)
                    dy = math.sin(angle_rad)

                dx *= trace_length_internal
                dy *= trace_length_internal
                via_pos = pcbnew.VECTOR2I(int(pad_pos.x + dx), int(pad_pos.y + dy))

                # Create track
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pad_pos)
                track.SetEnd(via_pos)
                track.SetLayer(pad.GetLayer())
                track.SetWidth(trace_width_internal)
                board.Add(track)

                # Create via
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(via_pos)
                via.SetWidth(via_diameter_internal)
                via.SetDrill(via_drill_internal)
                via.SetLayerPair(via_layer_start, via_layer_end)
                board.Add(via)

        pcbnew.Refresh()


class FanoutDialog(wx.Dialog):
    def __init__(self, parent, title):
        super().__init__(parent, title=title)

        self.panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        # Fanout style
        self.style_choice = wx.Choice(self.panel, choices=[
            "Angled", "Quadrant", "Diagonal", "Square Quadrant"])
        self.style_choice.SetSelection(0)
        vbox.Add(wx.StaticText(self.panel, label="Fanout Style:"), 0, wx.ALL, 5)
        vbox.Add(self.style_choice, 0, wx.EXPAND | wx.ALL, 5)

        # Angle selection
        self.angle_choice = wx.Choice(self.panel, choices=["0", "45", "90", "-45", "-90"])
        self.angle_choice.SetSelection(0)
        vbox.Add(wx.StaticText(self.panel, label="Angle (degrees):"), 0, wx.ALL, 5)
        vbox.Add(self.angle_choice, 0, wx.EXPAND | wx.ALL, 5)

        # Trace width
        self.trace_width_ctrl = wx.TextCtrl(self.panel, value="0.15")
        vbox.Add(wx.StaticText(self.panel, label="Trace Width (mm):"), 0, wx.ALL, 5)
        vbox.Add(self.trace_width_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        # Trace length
        self.trace_length_ctrl = wx.TextCtrl(self.panel, value="0.25")
        vbox.Add(wx.StaticText(self.panel, label="Trace Length (mm):"), 0, wx.ALL, 5)
        vbox.Add(self.trace_length_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        # Via diameter
        self.via_diameter_ctrl = wx.TextCtrl(self.panel, value="0.6")
        vbox.Add(wx.StaticText(self.panel, label="Via Diameter (mm):"), 0, wx.ALL, 5)
        vbox.Add(self.via_diameter_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        # Via drill
        self.via_drill_ctrl = wx.TextCtrl(self.panel, value="0.3")
        vbox.Add(wx.StaticText(self.panel, label="Via Drill Size (mm):"), 0, wx.ALL, 5)
        vbox.Add(self.via_drill_ctrl, 0, wx.EXPAND | wx.ALL, 5)

        # Buttons
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(self.panel, id=wx.ID_OK)
        cancel_btn = wx.Button(self.panel, id=wx.ID_CANCEL)
        hbox.Add(ok_btn, 1, wx.ALL, 5)
        hbox.Add(cancel_btn, 1, wx.ALL, 5)
        vbox.Add(hbox, 0, wx.ALIGN_CENTER)

        self.panel.SetSizer(vbox)
        self.SetSize((400, 450))  # Large enough window
        self.Fit()


# === Helper Functions ===

def quadrant_direction(pad_pos, center_pos):
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y
    if abs(dx) > abs(dy):
        return (1, 0) if dx > 0 else (-1, 0)
    else:
        return (0, 1) if dy > 0 else (0, -1)

def diagonal_direction(pad_pos, center_pos):
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y
    return (
        1 if dx > 0 else -1,
        1 if dy > 0 else -1
    )

def square_quadrant_direction(pad_pos, center_pos):
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y

    if dx < 0 and dy < 0:
        return (-1, -1)  # Top-left
    elif dx >= 0 and dy < 0:
        return (1, -1)   # Top-right
    elif dx >= 0 and dy >= 0:
        return (1, 1)    # Bottom-right
    else:
        return (-1, 1)   # Bottom-left

def rotate_vector(x, y, angle_rad):
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return (
        x * cos_a - y * sin_a,
        x * sin_a + y * cos_a
    )
