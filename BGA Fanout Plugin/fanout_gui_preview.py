import pcbnew
import wx
import math

class FanoutPreviewCanvas(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(wx.WHITE)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, self.on_size)
        self.size = (300, 300)
        self.center = (self.size[0] // 2, self.size[1] // 2)
        self.angle = 0
        self.style = 'angled'

    def on_size(self, event):
        self.size = self.GetSize()
        self.center = (self.size[0] // 2, self.size[1] // 2)
        self.Refresh()

    def on_paint(self, event):
        dc = wx.PaintDC(self)
        dc.Clear()
        dc.SetPen(wx.Pen(wx.BLACK, 2))
        dc.SetBrush(wx.Brush(wx.Colour(255, 255, 255), wx.SOLID))

        dc.DrawCircle(self.center[0], self.center[1], 5)

        if self.style == 'angled':
            self.draw_angled(dc)
        elif self.style == 'quadrant':
            self.draw_quadrant(dc)
        elif self.style == 'diagonal':
            self.draw_diagonal(dc)
        elif self.style == 'square quadrant':
            self.draw_square_quadrant(dc)

    def draw_angled(self, dc):
        angle_rad = math.radians(self.angle)
        dx = math.cos(angle_rad) * 100
        dy = math.sin(angle_rad) * 100
        dc.DrawLine(self.center[0], self.center[1], self.center[0] + dx, self.center[1] + dy)

    def draw_quadrant(self, dc):
        angles = [0, 90, 180, 270]
        for a in angles:
            r = math.radians(a + self.angle)
            dx = math.cos(r) * 100
            dy = math.sin(r) * 100
            dc.DrawLine(self.center[0], self.center[1], self.center[0] + dx, self.center[1] + dy)

    def draw_diagonal(self, dc):
        for dx, dy in [(-100, -100), (100, 100)]:
            dc.DrawLine(self.center[0], self.center[1], self.center[0] + dx, self.center[1] + dy)

    def draw_square_quadrant(self, dc):
        for dx, dy in [(-100, -100), (100, -100), (100, 100), (-100, 100)]:
            angle_rad = math.radians(self.angle)
            rdx = dx * math.cos(angle_rad) - dy * math.sin(angle_rad)
            rdy = dx * math.sin(angle_rad) + dy * math.cos(angle_rad)
            dc.DrawLine(self.center[0], self.center[1], self.center[0] + rdx, self.center[1] + rdy)

    def update_preview(self, angle, style):
        self.angle = angle
        self.style = style
        self.Refresh()


class FanoutDialog(wx.Dialog):
    def __init__(self, parent, title):
        super().__init__(parent, title=title)
        self.panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.preview_canvas = FanoutPreviewCanvas(self.panel)
        vbox.Add(self.preview_canvas, 0, wx.EXPAND | wx.ALL, 5)

        # Style
        self.style_choice = wx.Choice(self.panel, choices=["Angled", "Quadrant", "Diagonal", "Square Quadrant"])
        self.style_choice.SetSelection(0)
        self.style_choice.Bind(wx.EVT_CHOICE, self.update_preview)
        vbox.Add(wx.StaticText(self.panel, label="Fanout Style:"), 0, wx.ALL, 5)
        vbox.Add(self.style_choice, 0, wx.EXPAND | wx.ALL, 5)

        # Angle
        self.angle_choice = wx.Choice(self.panel, choices=["0", "45", "90", "-45", "-90"])
        self.angle_choice.SetSelection(0)
        self.angle_choice.Bind(wx.EVT_CHOICE, self.update_preview)
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

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        ok_btn = wx.Button(self.panel, id=wx.ID_OK)
        cancel_btn = wx.Button(self.panel, id=wx.ID_CANCEL)
        hbox.Add(ok_btn, 1, wx.ALL, 5)
        hbox.Add(cancel_btn, 1, wx.ALL, 5)
        vbox.Add(hbox, 0, wx.ALIGN_CENTER)

        self.panel.SetSizer(vbox)
        self.SetSize((400, 550))
        self.Fit()

        self.update_preview(None)

    def update_preview(self, event):
        angle = int(self.angle_choice.GetStringSelection())
        style = self.style_choice.GetStringSelection().lower()
        self.preview_canvas.update_preview(angle, style)


class FanOutPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Fan Out Pads with GUI"
        self.category = "Routing Tools"
        self.description = "Fan out pads with configurable settings and live preview"

    def Run(self):
        dialog = FanoutDialog(None, "Fanout Settings")
        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return

        fanout_style = dialog.style_choice.GetStringSelection().lower()
        trace_width = float(dialog.trace_width_ctrl.GetValue())
        trace_length = float(dialog.trace_length_ctrl.GetValue())
        via_diameter = float(dialog.via_diameter_ctrl.GetValue())
        via_drill = float(dialog.via_drill_ctrl.GetValue())
        angle_deg = int(dialog.angle_choice.GetStringSelection())
        angle_rad = math.radians(angle_deg)

        dialog.Destroy()

        board = pcbnew.GetBoard()
        trace_width_internal = pcbnew.FromMM(trace_width)
        trace_length_internal = pcbnew.FromMM(trace_length)
        via_diameter_internal = pcbnew.FromMM(via_diameter)
        via_drill_internal = pcbnew.FromMM(via_drill)

        for footprint in board.GetFootprints():
            if not footprint.IsSelected():
                continue

            center = footprint.GetPosition()
            for pad in footprint.Pads():
                if not pad.IsConnected():
                    continue

                pad_pos = pad.GetPosition()

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

                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pad_pos)
                track.SetEnd(via_pos)
                track.SetLayer(pad.GetLayer())
                track.SetWidth(trace_width_internal)
                board.Add(track)

                via = pcbnew.PCB_VIA(board)
                via.SetPosition(via_pos)
                via.SetWidth(via_diameter_internal)
                via.SetDrill(via_drill_internal)
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.In1_Cu)
                board.Add(via)

        pcbnew.Refresh()


def quadrant_direction(pad_pos, center_pos):
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y
    return (1, 0) if abs(dx) > abs(dy) else (0, 1) if dy > 0 else (0, -1)


def diagonal_direction(pad_pos, center_pos):
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y
    return (1 if dx > 0 else -1, 1 if dy > 0 else -1)


def square_quadrant_direction(pad_pos, center_pos):
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y
    if dx < 0 and dy < 0:
        return (-1, -1)
    elif dx >= 0 and dy < 0:
        return (1, -1)
    elif dx >= 0 and dy >= 0:
        return (1, 1)
    else:
        return (-1, 1)


def rotate_vector(x, y, angle_rad):
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    return (x * cos_a - y * sin_a, x * sin_a + y * cos_a)
