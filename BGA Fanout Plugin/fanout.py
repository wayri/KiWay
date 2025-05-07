import pcbnew
import math

class FanOutPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Fan Out Pads (Quadrant / Diagonal)"
        self.category = "Routing Tools"
        self.description = "Automatically fan out pads with vias in various styles"

    def Run(self):
        board = pcbnew.GetBoard()
        modules = board.GetFootprints()

        # === Configurable Parameters ===
        fanout_style = 'diagonal'  # 'quadrant', 'diagonal', or 'angled'
        trace_length_mm = 0.25     # Distance from pad to via
        trace_width_mm = 0.15      # Width of the fanout trace
        via_diameter_mm = 0.3      # Total via diameter
        via_drill_mm = 0.15         # Via drill size
        start_layer = pcbnew.F_Cu
        end_layer = pcbnew.In1_Cu  # Change depending on your stackup

        # Convert to KiCad internal units (nanometers)
        trace_length = pcbnew.FromMM(trace_length_mm)
        trace_width = pcbnew.FromMM(trace_width_mm)
        via_diameter = pcbnew.FromMM(via_diameter_mm)
        via_drill = pcbnew.FromMM(via_drill_mm)

        for footprint in modules:
            if not footprint.IsSelected():
                continue

            center = footprint.GetPosition()

            for pad in footprint.Pads():
                if not pad.IsConnected():
                    continue

                pad_pos = pad.GetPosition()

                if fanout_style == 'quadrant':
                    dx, dy = quadrant_direction(pad_pos, center)
                elif fanout_style == 'diagonal':
                    dx, dy = diagonal_direction(pad_pos, center)
                else:  # fallback to angled
                    angle_rad = math.radians(pad.GetOrientation().AsDegrees())
                    dx = math.cos(angle_rad)
                    dy = math.sin(angle_rad)

                dx *= trace_length
                dy *= trace_length
                via_pos = pcbnew.VECTOR2I(int(pad_pos.x + dx), int(pad_pos.y + dy))

                # Create track
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pad_pos)
                track.SetEnd(via_pos)
                track.SetLayer(pad.GetLayer())
                track.SetWidth(trace_width)
                board.Add(track)

                # Create via
                via = pcbnew.PCB_VIA(board)
                via.SetPosition(via_pos)
                via.SetWidth(via_diameter)
                via.SetDrill(via_drill)
                via.SetLayerPair(start_layer, end_layer)
                board.Add(via)

        pcbnew.Refresh()

def quadrant_direction(pad_pos, center_pos):
    """Determine cardinal fanout direction based on quadrant."""
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y
    if abs(dx) > abs(dy):
        return (1, 0) if dx > 0 else (-1, 0)
    else:
        return (0, 1) if dy > 0 else (0, -1)

def diagonal_direction(pad_pos, center_pos):
    """Fan out diagonally based on position relative to center."""
    dx = pad_pos.x - center_pos.x
    dy = pad_pos.y - center_pos.y
    return (
        1 if dx > 0 else -1,
        1 if dy > 0 else -1
    )
