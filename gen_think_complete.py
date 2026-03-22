#!/usr/bin/env python3
"""
KiCad 9 Schematic Generator – Think City EV Complete Electrical System
Generates a hierarchical schematic with 13 sub-sheets + 1 root sheet.

Based on: think-300dpi_koblingsskema.pdf (38 pages)
Drawing no: 05125-01-105 (LV EDS) / 05125-02-031 (HV Box)

Output: 14 .kicad_sch files in Data/Trabbi Schematic/
"""

import uuid
import os
import math

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
OUT_DIR = "/home/hw/Projects/Trabbi-schematic/Data/Trabbi Schematic"

# Grid size for snapping all coordinates (1.27mm = 50mil, KiCad standard)
GRID = 1.27

# ---------------------------------------------------------------------------
# Sheet class – encapsulates all builder methods for one .kicad_sch file
# ---------------------------------------------------------------------------

class Sheet:
    """Builder for a single KiCad 9 .kicad_sch file."""

    def __init__(self, paper="A3", title="", date="2026-03-22", rev="2",
                 company="Think Nordic / Semcon",
                 comment1="", comment2="", comment3="", comment4=""):
        self.paper = paper
        self.title = title
        self.date = date
        self.rev = rev
        self.company = company
        self.comments = [comment1, comment2, comment3, comment4]
        self.lib_syms = []      # lines for (lib_symbols ...)
        self.elems = []         # top-level elements (symbols, wires, labels, ...)
        self.sym_defs = {}      # lib_id -> {pin_name: pin_number}
        self.hier_sheets = []   # hierarchical sheet blocks (root only)
        self._sym_local_pins = {}  # lib_id -> {pin_name: (local_x, local_y)}
        self._sym_dims = {}       # lib_id -> (w, h)
        self._placements = {}     # ref -> (lib_id, x, y, ang)
        self._glabel_positions = {}  # name -> [(x, y, ang), ...]
        self.sheet_num = None     # set externally for cross-ref

    # -- UID helper --------------------------------------------------------
    @staticmethod
    def uid():
        return str(uuid.uuid4())

    # -- Pin line helper ---------------------------------------------------
    @staticmethod
    def _pin_line(name, num, ptype, x, y, ang, plen=3.81):
        return (
            f'        (pin {ptype} line (at {x:.3f} {y:.3f} {ang}) (length {plen:.3f})\n'
            f'          (name "{name}" (effects (font (size 0.762 0.762))))\n'
            f'          (number "{num}" (effects (font (size 0.762 0.762)) hide))\n'
            f'        )'
        )

    # -- Symbol definition -------------------------------------------------
    def defsym(self, lib_id, w, h,
               lpins=(), rpins=(), tpins=(), bpins=(),
               body_label="", ref_pfx="U", body_gfx=()):
        """Define a schematic symbol and register its pin map.
        body_gfx: optional list of S-expression strings for body graphics
        (added inside the _0_1 sub-symbol)."""
        name = lib_id.split(":")[-1]
        hw2, hh = w / 2, h / 2
        pl = 3.81
        pin_map = {}
        n = [1]

        def norm(p):
            return (p, "passive") if isinstance(p, str) else p

        s = []
        s.append(f'    (symbol "{lib_id}"')
        s.append(f'      (pin_names (offset 1.016))')
        s.append(f'      (in_bom yes) (on_board yes)')
        for prop, val, dy in [
            ("Reference", ref_pfx,  hh + 3.81),
            ("Value",     name,     hh + 6.35),
            ("Footprint", "",       hh + 8.89),
            ("Datasheet", "",       hh + 11.43),
        ]:
            hide = " hide" if prop in ("Footprint", "Datasheet") else ""
            s.append(f'      (property "{prop}" "{val}" (at 0 {dy:.3f} 0)')
            s.append(f'        (effects (font (size 1.27 1.27)){hide})')
            s.append(f'      )')
        s.append(f'      (symbol "{name}_0_1"')
        s.append(f'        (rectangle (start {-hw2:.3f} {-hh:.3f}) (end {hw2:.3f} {hh:.3f})')
        s.append(f'          (stroke (width 0.254) (type default))')
        s.append(f'          (fill (type background))')
        s.append(f'        )')
        if body_label:
            for i, line in enumerate(body_label.split("\\n")):
                s.append(f'        (text "{line}" (at 0 {-i * 3:.1f} 0)')
                s.append(f'          (effects (font (size 1.4 1.4) bold))')
                s.append(f'        )')
        for gline in body_gfx:
            s.append(gline)
        s.append(f'      )')
        s.append(f'      (symbol "{name}_1_1"')

        pin_local = {}

        def add_side(pins, side, body_dim):
            np2 = len(pins)
            if not np2:
                return
            sp = body_dim / (np2 + 1)
            for i, p in enumerate(pins):
                pname, ptype = norm(p)
                pos = body_dim / 2 - sp * (i + 1)
                if side == 'L':
                    px, py, ang = -hw2 - pl, pos, 0
                elif side == 'R':
                    px, py, ang = hw2 + pl, pos, 180
                elif side == 'T':
                    px, py, ang = pos, hh + pl, 270
                else:
                    px, py, ang = pos, -hh - pl, 90
                px = round(px / GRID) * GRID
                py = round(py / GRID) * GRID
                s.append(self._pin_line(pname, n[0], ptype, px, py, ang, pl))
                pin_map[pname] = str(n[0])
                pin_local[pname] = (px, py)
                n[0] += 1

        add_side(lpins, 'L', h)
        add_side(rpins, 'R', h)
        add_side(tpins, 'T', w)
        add_side(bpins, 'B', w)
        s.append(f'      )')
        s.append(f'    )')

        self.lib_syms.extend(s)
        self.sym_defs[lib_id] = pin_map
        self._sym_local_pins[lib_id] = pin_local
        self._sym_dims[lib_id] = (w, h)
        return lib_id, pin_map

    # -- Place component instance ------------------------------------------
    def place(self, lib_id, ref, val, x, y, ang=0):
        x, y = self._g(x), self._g(y)
        self._placements[ref] = (lib_id, x, y, ang)
        pm = self.sym_defs.get(lib_id, {})
        # Position Ref above body, Value below body
        _w, _h = self._sym_dims.get(lib_id, (20, 16))
        hh = _h / 2
        ref_dy = -(hh + 3)   # above top edge
        val_dy = hh + 3      # below bottom edge
        s = []
        s.append(f'  (symbol (lib_id "{lib_id}") (at {x:.3f} {y:.3f} {ang})')
        s.append(f'    (unit 1) (in_bom yes) (on_board yes) (dnp no)')
        s.append(f'    (uuid "{self.uid()}")')
        for prop, pval, dx, dy in [
            ("Reference", ref,  0, ref_dy),
            ("Value",     val,  0, val_dy),
            ("Footprint", "",   0, 0),
            ("Datasheet", "",   0, 0),
        ]:
            hide = " hide" if prop in ("Footprint", "Datasheet") else ""
            s.append(f'    (property "{prop}" "{pval}" (at {x + dx:.3f} {y + dy:.3f} 0)')
            s.append(f'      (effects (font (size 1.27 1.27)){hide})')
            s.append(f'    )')
        for pname, pnum in pm.items():
            s.append(f'    (pin "{pnum}" (uuid "{self.uid()}"))')
        s.append(f'  )')
        self.elems.extend(s)

    # -- Grid snap helper ---------------------------------------------------
    @staticmethod
    def _g(val):
        """Snap a coordinate to the nearest 1.27mm grid point."""
        return round(val / GRID) * GRID

    # -- Pin position lookup ------------------------------------------------
    def p(self, ref, pin_name):
        """Return exact schematic (x, y) of the connection point of a pin,
        snapped to the 1.27mm grid."""
        lib_id, sx, sy, ang = self._placements[ref]
        lx, ly = self._sym_local_pins[lib_id][pin_name]
        if ang == 0:
            rx, ry = sx + lx, sy - ly
        elif ang == 90:
            rx, ry = sx - ly, sy - lx
        elif ang == 180:
            rx, ry = sx - lx, sy + ly
        elif ang == 270:
            rx, ry = sx + ly, sy + lx
        else:
            rad = math.radians(ang)
            c, s = math.cos(rad), math.sin(rad)
            rx, ry = sx + lx * c - ly * s, sy - lx * s - ly * c
        return (self._g(rx), self._g(ry))

    # -- Wire --------------------------------------------------------------
    def wire(self, x1, y1, x2, y2):
        x1, y1, x2, y2 = self._g(x1), self._g(y1), self._g(x2), self._g(y2)
        self.elems.append(
            f'  (wire (pts (xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f}))\n'
            f'    (stroke (width 0) (type default))\n'
            f'    (uuid "{self.uid()}")\n'
            f'  )'
        )

    # -- Orthogonal L-shaped wire ------------------------------------------
    def wire_l(self, x1, y1, x2, y2, h_first=True):
        """Connect two points with an L-shaped route (no diagonals).
        h_first=True: horizontal first then vertical.
        h_first=False: vertical first then horizontal."""
        x1, y1, x2, y2 = self._g(x1), self._g(y1), self._g(x2), self._g(y2)
        if x1 == x2 or y1 == y2:
            # Already orthogonal, single segment
            self.wire(x1, y1, x2, y2)
        elif h_first:
            self.wire(x1, y1, x2, y1)  # horizontal
            self.wire(x2, y1, x2, y2)  # vertical
        else:
            self.wire(x1, y1, x1, y2)  # vertical
            self.wire(x1, y2, x2, y2)  # horizontal

    # -- Net label (local to sheet) ----------------------------------------
    def label(self, x, y, name, ang=0):
        x, y = self._g(x), self._g(y)
        self.elems.append(
            f'  (label "{name}" (at {x:.3f} {y:.3f} {ang})\n'
            f'    (effects (font (size 1.27 1.27)) (justify left))\n'
            f'    (uuid "{self.uid()}")\n'
            f'  )'
        )

    # -- Global label (cross-sheet connection) -----------------------------
    def glabel(self, x, y, name, ang=0, shape="bidirectional"):
        x, y = self._g(x), self._g(y)
        u = self.uid()
        self.elems.append(
            f'  (global_label "{name}" (shape {shape}) (at {x:.3f} {y:.3f} {ang})\n'
            f'    (effects (font (size 1.27 1.27)) (justify left))\n'
            f'    (uuid "{u}")\n'
            f'    (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {x:.3f} {y:.3f} 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide)\n'
            f'    )\n'
            f'  )'
        )
        # Track for cross-reference annotations
        self._glabel_positions.setdefault(name, []).append((x, y, ang))

    # -- Power port (standard KiCad power symbols) -------------------------
    def power_flag(self, x, y, name, ang=0):
        """Add a global label styled as a power symbol."""
        shape = "input" if "GND" in name else "output"
        self.glabel(x, y, name, ang, shape)

    # -- Junction ----------------------------------------------------------
    def junction(self, x, y):
        x, y = self._g(x), self._g(y)
        self.elems.append(
            f'  (junction (at {x:.3f} {y:.3f}) (diameter 0) (color 0 0 0 0)'
            f' (uuid "{self.uid()}"))'
        )

    # -- No-connect --------------------------------------------------------
    def no_connect(self, x, y):
        x, y = self._g(x), self._g(y)
        self.elems.append(
            f'  (no_connect (at {x:.3f} {y:.3f}) (uuid "{self.uid()}"))'
        )

    # -- Text annotation ---------------------------------------------------
    def text(self, x, y, txt, size=1.27, ang=0):
        safe = txt.replace('"', '\\"')
        self.elems.append(
            f'  (text "{safe}" (at {x:.3f} {y:.3f} {ang})\n'
            f'    (effects (font (size {size:.3f} {size:.3f})))\n'
            f'    (uuid "{self.uid()}")\n'
            f'  )'
        )

    # -- Cross-reference annotations ---------------------------------------
    def add_crossrefs(self, net_to_sheets):
        """Add small text annotations next to each global label showing
        which other sheets share the same net.
        net_to_sheets: {net_name: [sheet_num, ...]}"""
        for net_name, positions in self._glabel_positions.items():
            other = sorted(s for s in net_to_sheets.get(net_name, [])
                           if s != self.sheet_num)
            if not other:
                continue
            ref_str = "→S" + ",S".join(f"{s:02d}" for s in other)
            for x, y, ang in positions:
                # Place text near the label, offset to avoid overlap
                if ang == 0:      # label points right → text below-right
                    tx, ty = x + 3, y + 2.5
                elif ang == 180:  # label points left → text below-left
                    tx, ty = x - 3, y + 2.5
                elif ang == 90:   # label points up → text to the right
                    tx, ty = x + 3, y - 2
                else:             # 270 label points down → text to the right
                    tx, ty = x + 3, y + 2
                self.text(tx, ty, ref_str, size=0.8)

    # -- Hierarchical sheet block (root sheet only) ------------------------
    def add_hier_sheet(self, sx, sy, sw, sh, sheet_name, sheet_file):
        self.hier_sheets.append(
            f'  (sheet (at {sx:.3f} {sy:.3f}) (size {sw:.3f} {sh:.3f})\n'
            f'    (stroke (width 0.1524) (type solid))\n'
            f'    (fill (color 0 0 0 0.0000))\n'
            f'    (uuid "{self.uid()}")\n'
            f'    (property "Sheetname" "{sheet_name}" (at {sx:.3f} {sy - 1.5:.3f} 0)\n'
            f'      (effects (font (size 1.27 1.27)) (justify left bottom))\n'
            f'    )\n'
            f'    (property "Sheetfile" "{sheet_file}" (at {sx:.3f} {sy + sh + 1:.3f} 0)\n'
            f'      (effects (font (size 1.27 1.27)) (justify left top))\n'
            f'    )\n'
            f'  )'
        )

    # -- Serialize to .kicad_sch string ------------------------------------
    def render(self):
        out = []
        out.append('(kicad_sch (version 20241209) (generator "eeschema") (generator_version "9.0")')
        out.append(f'  (paper "{self.paper}")')
        out.append('  (title_block')
        out.append(f'    (title "{self.title}")')
        out.append(f'    (date "{self.date}")')
        out.append(f'    (rev "{self.rev}")')
        out.append(f'    (company "{self.company}")')
        for i, c in enumerate(self.comments, 1):
            if c:
                out.append(f'    (comment {i} "{c}")')
        out.append('  )')
        out.append('  (lib_symbols')
        out.extend(self.lib_syms)
        out.append('  )')
        out.extend(self.hier_sheets)
        out.extend(self.elems)
        out.append('  (symbol_instances)')
        out.append(')')
        return '\n'.join(out)

    # -- Save to file ------------------------------------------------------
    def save(self, filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.render())
        nsyms = len(self.sym_defs)
        nelems = len(self.elems)
        print(f"  Written: {os.path.basename(filepath)}  ({nsyms} syms, {nelems} elems)")


# ============================================================================
# COMMON SYMBOL DEFINITIONS – factory functions so each Sheet gets its own copy
# ============================================================================

def def_fuse(sh):
    return sh.defsym("Think:FUSE", 14, 8,
        lpins=["A"], rpins=["B"], body_label="FUSE", ref_pfx="F")

def _gfx_polyline(pts, stroke="default"):
    xy = " ".join(f"(xy {x:.2f} {y:.2f})" for x, y in pts)
    return (
        f'        (polyline (pts {xy})\n'
        f'          (stroke (width 0.254) (type {stroke}))\n'
        f'          (fill (type none))\n'
        f'        )'
    )

def _gfx_arc(sx, sy, mx, my, ex, ey):
    return (
        f'        (arc (start {sx:.2f} {sy:.2f}) (mid {mx:.2f} {my:.2f}) (end {ex:.2f} {ey:.2f})\n'
        f'          (stroke (width 0.254) (type default))\n'
        f'          (fill (type none))\n'
        f'        )'
    )

def _gfx_circle(cx, cy, r):
    return (
        f'        (circle (center {cx:.2f} {cy:.2f}) (radius {r:.2f})\n'
        f'          (stroke (width 0.254) (type default))\n'
        f'          (fill (type none))\n'
        f'        )'
    )

def _relay_gfx(hw2, coil_top, coil_bot, com_y, no_y, nc_y=None):
    """Build relay body graphics: coil (left) + switch contacts (right)."""
    gfx = []
    # -- Coil (left half) --
    cx = -hw2 / 2  # coil center x
    # Connecting lines from body edge to coil
    gfx.append(_gfx_polyline([(-hw2, coil_top), (cx, coil_top)]))
    gfx.append(_gfx_polyline([(-hw2, coil_bot), (cx, coil_bot)]))
    # 4 arcs (inductor humps)
    n_arcs = 4
    bump_h = (coil_top - coil_bot) / n_arcs
    for i in range(n_arcs):
        ys = coil_top - i * bump_h
        ye = coil_top - (i + 1) * bump_h
        ym = (ys + ye) / 2
        xm = cx + (1.5 if i % 2 == 0 else -1.5)
        gfx.append(_gfx_arc(cx, ys, xm, ym, cx, ye))

    # -- Switch contacts (right half) --
    sx = hw2 / 2  # switch center x
    r = 0.6
    # Connecting lines from body edge to contacts
    gfx.append(_gfx_polyline([(hw2, com_y), (sx + r, com_y)]))
    gfx.append(_gfx_polyline([(hw2, no_y), (sx + r, no_y)]))
    if nc_y is not None:
        gfx.append(_gfx_polyline([(hw2, nc_y), (sx + r, nc_y)]))
    # Contact circles
    gfx.append(_gfx_circle(sx, com_y, r))
    gfx.append(_gfx_circle(sx, no_y, r))
    if nc_y is not None:
        gfx.append(_gfx_circle(sx, nc_y, r))
    # Arm (open contact) — from COM toward NO, not quite reaching
    arm_end_y = com_y + (no_y - com_y) * 0.75
    gfx.append(_gfx_polyline([(sx, com_y - r), (sx + 1.5, arm_end_y)]))
    # Separator line (dashed) between coil and switch
    hh = max(abs(coil_top), abs(coil_bot), abs(com_y), abs(no_y))
    if nc_y is not None:
        hh = max(hh, abs(nc_y))
    gfx.append(_gfx_polyline([(0, -hh - 1), (0, hh + 1)], stroke="dash"))
    return gfx


def def_relay_spdt(sh):
    w, h = 20, 30
    hw2 = w / 2  # 10
    # Left pins (coil): 2 pins on h=30 → sp=10 → y = 5, -5 → snapped 5.08, -5.08
    coil_top, coil_bot = 5.08, -5.08
    # Right pins (switch): 3 pins on h=30 → sp=7.5 → y = 7.5, 0, -7.5 → snapped 7.62, 0, -7.62
    com_y, no_y, nc_y = 7.62, 0.0, -7.62
    gfx = _relay_gfx(hw2, coil_top, coil_bot, com_y, no_y, nc_y)
    return sh.defsym("Think:RELAY_SPDT", w, h,
        lpins=["86_COIL+", "85_COIL-"],
        rpins=["30_COM", ("87_NO", "output"), ("87a_NC", "output")],
        body_label="", ref_pfx="K", body_gfx=gfx)

def def_relay_spst(sh):
    w, h = 18, 16
    hw2 = w / 2  # 9
    # Left pins (coil): 2 pins on h=16 → sp=5.33 → y = 2.67, -2.67 → snapped 2.54, -2.54
    coil_top, coil_bot = 2.54, -2.54
    # Right pins (switch): 2 pins on h=16 → sp=5.33 → y = 2.67, -2.67 → snapped 2.54, -2.54
    com_y, no_y = 2.54, -2.54
    gfx = _relay_gfx(hw2, coil_top, coil_bot, com_y, no_y)
    return sh.defsym("Think:RELAY_SPST", w, h,
        lpins=["86_COIL+", "85_COIL-"],
        rpins=["30_COM", ("87_NO", "output")],
        body_label="", ref_pfx="K", body_gfx=gfx)

def def_switch(sh):
    return sh.defsym("Think:SW_SPST", 14, 8,
        lpins=["A"], rpins=["B"], body_label="SW", ref_pfx="SW")

def def_bulb(sh):
    return sh.defsym("Think:BULB", 10, 10,
        lpins=["+"], rpins=["-"], body_label="BULB", ref_pfx="DS")

def def_motor_small(sh):
    return sh.defsym("Think:MOTOR_SM", 16, 12,
        lpins=["M+"], rpins=["M-"], body_label="M", ref_pfx="M")

def def_resistor(sh):
    return sh.defsym("Think:RESISTOR", 10, 6,
        lpins=["1"], rpins=["2"], body_label="R", ref_pfx="R")

def def_connector_2(sh, lib_id="Think:CONN_2P", label="CONN"):
    return sh.defsym(lib_id, 14, 10,
        lpins=["1"], rpins=["2"], body_label=label, ref_pfx="J")

def def_connector_generic(sh, lib_id, n_pins, label="CONN", ref_pfx="J"):
    """Generic connector with n_pins on the right side."""
    pins = [str(i+1) for i in range(n_pins)]
    h = max(12, n_pins * 4 + 4)
    return sh.defsym(lib_id, 16, h,
        rpins=pins, body_label=label, ref_pfx=ref_pfx)


# ============================================================================
# HELPER: place a row of fuses with labels
# ============================================================================

def place_fuse_row(sh, fuse_id, fuses_info, start_x, start_y, dx=0, dy=18):
    """Place a column of fuses. fuses_info = [(ref, value_text, label_name), ...]"""
    for i, (ref, val, lbl) in enumerate(fuses_info):
        x = start_x + i * dx
        y = start_y + i * dy
        sh.place(fuse_id, ref, val, x, y)
        ax, ay = sh.p(ref, "A")
        bx, by = sh.p(ref, "B")
        sh.wire(ax, ay, ax - 7, ay)
        sh.wire(bx, by, bx + 7, by)
        sh.glabel(ax - 7, ay, lbl + "_IN", 180)
        sh.glabel(bx + 7, by, lbl, 0)


# ============================================================================
# SUB-SHEET GENERATORS
# ============================================================================

def build_s01_power_dist():
    """S01: Power Distribution – PDF pages 6-7, sheets 01-02."""
    sh = Sheet(
        paper="A3",
        title="01 - Power Distribution",
        comment1="12V Battery, Fuse Box C01 (33 fuses), Ignition Switch",
        comment2="PDF pages 6-7, Original sheets 01-02",
        comment3="Wire: 6mm2 RED main battery feeds, 6mm2 YEL ignition feeds",
        comment4="All labels in English",
    )

    # -- Symbol definitions --
    sh.defsym("Think:BATT_12V", 20, 24,
        tpins=[("+", "power_out")],
        bpins=[("-", "power_in")],
        body_label="12V\\nBATTERY\\n(E04)", ref_pfx="BT")

    sh.defsym("Think:IGN_SWITCH", 24, 34,
        lpins=["BAT_IN"],
        rpins=["ACC_RUN", "DRIVE_OUT", "RUN_START", "START_OUT"],
        body_label="IGNITION\\nSWITCH\\n(C21-C23)", ref_pfx="SW")

    # Fuse box – comprehensive with all 33 fuses
    fuse_rpins = [
        "F1_30A", "F2_40A", "F3_40A", "F4_40A", "F5_30A",
        "F6_15A", "F7_10A", "F8_25A", "F9_15A", "F10_15A",
        "F11_5A", "F12_10A", "F13_15A", "F14_25A", "F15_10A",
        "F16_10A", "F17_10A", "F18_10A", "F19_10A", "F20_15A",
        "F21_5A", "F22_25A", "F23_10A", "F24_20A", "F25_15A",
        "F26_10A", "F27_10A", "F28_20A", "F29_15A", "F30_20A",
        "F31_15A", "F32_10A", "F33_10A",
    ]
    sh.defsym("Think:FUSE_BOX_C01", 40, 180,
        lpins=[("+12V_BAT30", "power_in"), ("+12V_IGN15", "power_in"),
               ("+12V_RUN15_1", "power_in"), ("+12V_ACC15_2", "power_in"),
               ("+12V_START50", "power_in")],
        rpins=fuse_rpins,
        bpins=["GND"],
        body_label="C01\\nFUSE BOX\\n33 Fuses\\n+5 Maxi",
        ref_pfx="FB")

    # -- Place components --
    BT_X, BT_Y = 50, 80
    sh.place("Think:BATT_12V", "BT1", "12V Battery (E04)", BT_X, BT_Y)

    IGN_X, IGN_Y = 50, 190
    sh.place("Think:IGN_SWITCH", "SW1", "Ignition Switch", IGN_X, IGN_Y)

    FB_X, FB_Y = 240, 145
    sh.place("Think:FUSE_BOX_C01", "FB1", "Fuse Box C01", FB_X, FB_Y)

    # -- Battery to fuse box wiring --
    bt_pos = sh.p("BT1", "+")
    fb_bat = sh.p("FB1", "+12V_BAT30")
    sh.wire(*bt_pos, bt_pos[0], bt_pos[1] - 15)
    sh.wire(bt_pos[0], bt_pos[1] - 15, 140, bt_pos[1] - 15)
    sh.wire(140, bt_pos[1] - 15, 140, fb_bat[1])
    sh.wire(140, fb_bat[1], *fb_bat)
    sh.text(BT_X + 5, bt_pos[1] - 18, "Wire: 6mm2 RED", 1.0)
    sh.glabel(bt_pos[0], bt_pos[1] - 15, "+12V_ALWAYS", 180, "output")

    # Battery GND
    bt_neg = sh.p("BT1", "-")
    sh.wire(*bt_neg, bt_neg[0], bt_neg[1] + 15)
    sh.glabel(bt_neg[0], bt_neg[1] + 15, "GND", 270, "input")
    sh.text(BT_X + 5, bt_neg[1] + 10, "Wire: 6mm2 BLK", 1.0)

    # Ignition switch → fuse box power inputs (routed via intermediate X=160)
    ROUTE_X = 160
    ign_pairs = [
        ("ACC_RUN",   "+12V_ACC15_2", "+12V_ACC_RUN (pos 15/2)"),
        ("DRIVE_OUT", "+12V_IGN15",   "+12V_IGN (pos 15)"),
        ("RUN_START", "+12V_RUN15_1", "+12V_RUN_START (pos 15/1)"),
        ("START_OUT", "+12V_START50", "+12V_START (pos 50)"),
    ]
    for sw_pin, fb_pin, lbl_text in ign_pairs:
        sx, sy = sh.p("SW1", sw_pin)
        fx, fy = sh.p("FB1", fb_pin)
        sh.wire(sx, sy, ROUTE_X, sy)
        sh.wire(ROUTE_X, sy, ROUTE_X, fy)
        sh.wire(ROUTE_X, fy, fx, fy)
        sh.label(sx + 10, sy, lbl_text)
        ROUTE_X += 8  # offset each route to avoid overlaps
    sh.text(80, sh.p("SW1", "ACC_RUN")[1] - 4, "Wire: 6mm2 YEL", 1.0)

    # Ignition BAT_IN from battery
    bat_in = sh.p("SW1", "BAT_IN")
    sh.wire(*bat_in, bat_in[0] - 16, bat_in[1])
    sh.glabel(bat_in[0] - 16, bat_in[1], "+12V_ALWAYS", 180)

    # -- Global labels on fuse outputs --
    fuse_globals = [
        ("F1_30A",  "+12V_F1_HTDWS"),
        ("F2_40A",  "+12V_F2_LIGHTS"),
        ("F3_40A",  "+12V_F3_HEATER"),
        ("F4_40A",  "+12V_F4_IGN"),
        ("F5_30A",  "+12V_F5_BLOWER"),
        ("F6_15A",  "+12V_F6_RADFAN"),
        ("F7_10A",  "+12V_F7_RADIO"),
        ("F8_25A",  "+12V_F8_OUTLET"),
        ("F9_15A",  "+12V_F9_HORN_DOME"),
        ("F10_15A", "+12V_F10_WPUMP_CHG"),
        ("F11_5A",  "+12V_F11_START"),
        ("F12_10A", "+12V_F12_BRAKE"),
        ("F13_15A", "+12V_F13_PARKLOCK"),
        ("F14_25A", "+12V_F14_WIPER"),
        ("F15_10A", "+12V_F15_HTDW_REV"),
        ("F16_10A", "+12V_F16_PARK_FRT"),
        ("F17_10A", "+12V_F17_COLL_ALM"),
        ("F18_10A", "+12V_F18_TIMER"),
        ("F19_10A", "+12V_F19_BKGND"),
        ("F20_15A", "+12V_F20_BRAKE2"),
        ("F21_5A",  "+12V_F21_FOGR"),
        ("F22_25A", "+12V_F22_VACPUMP"),
        ("F23_10A", "+12V_F23_LICENSE"),
        ("F24_20A", "+12V_F24_TURNSIG"),
        ("F25_15A", "+12V_F25_HIBEAMR"),
        ("F26_10A", "+12V_F26_LOBEAMR"),
        ("F27_10A", "+12V_F27_LOBEAML"),
        ("F28_20A", "+12V_F28_DRIVE"),
        ("F29_15A", "+12V_F29_WPUMP_DRV"),
        ("F30_20A", "+12V_F30_DIAG"),
        ("F31_15A", "+12V_F31_WARN"),
        ("F32_10A", "+12V_F32_TAIL"),
        ("F33_10A", "+12V_F33_WEBASTO"),
    ]

    for fpn, glbl in fuse_globals:
        fx, fy = sh.p("FB1", fpn)
        sh.wire(fx, fy, fx + 18, fy)
        sh.glabel(fx + 18, fy, glbl, 0, "output")

    # GND bus at bottom of fuse box
    gx, gy = sh.p("FB1", "GND")
    sh.wire(gx, gy, gx, gy + 13)
    sh.glabel(gx, gy + 13, "GND", 270, "input")

    # -- Fuse description annotations --
    fuse_descs = [
        "F1:30A Heated windshield", "F2:40A Lights", "F3:40A Webasto heater",
        "F4:40A Ignition lock", "F5:30A Ventilation fan", "F6:15A Radiator fan",
        "F7:10A Radio", "F8:25A Power outlet", "F9:15A Horn/Dome/Tailgate",
        "F10:15A Water pump (charge)", "F11:5A Start function", "F12:10A Brake lights",
        "F13:15A Park lock", "F14:25A Wipers", "F15:10A Htd window/Rev/Fresh air",
        "F16:10A Parking front", "F17:10A Collision/Alarm", "F18:10A Timer/Start inhib",
        "F19:10A Background light", "F20:15A Brake lights 2", "F21:5A Rear fog",
        "F22:25A Vacuum pump (brakes)", "F23:10A License plate", "F24:20A Turn signals",
        "F25:15A High beam right", "F26:10A Low beam right", "F27:10A Low beam left",
        "F28:20A Drive sys/Charger/CB", "F29:15A Water pump (drive)", "F30:20A Alarm/Diag/Radio",
        "F31:15A Warning lights", "F32:10A Tail lights", "F33:10A Webasto aux",
    ]
    sh.text(310, 25, "FUSE BOX C01 – FUSE ASSIGNMENTS", 1.8)
    for i, desc in enumerate(fuse_descs):
        sh.text(310, 33 + i * 5.5, desc, 0.9)

    # -- Cross-reference annotations --
    sh.text(310, 230, "Cross-references:", 1.3)
    sh.text(310, 238, "F2,F16,F24-F27 -> Sheet 07: Headlights", 1.0)
    sh.text(310, 244, "F12,F15,F20,F21 -> Sheet 08: Rear Lights", 1.0)
    sh.text(310, 250, "F8,F9,F17,F24 -> Sheet 09: Signals & Horn", 1.0)
    sh.text(310, 256, "F9,F14,F17 -> Sheet 10: Wipers & Alarm", 1.0)
    sh.text(310, 262, "F28 -> Sheet 02: HV Power", 1.0)
    sh.text(310, 268, "F1,F3,F5,F7,F22,F30 -> Sheet 12: Radio & HVAC", 1.0)

    return sh


def build_s02_hv_power():
    """S02: HV Power – PDF pages 8-9, sheets 03-04."""
    sh = Sheet(
        paper="A3",
        title="02 - HV Power System",
        comment1="114V Traction Battery, 250A HV Fuse, Contactor Box, Motor",
        comment2="PDF pages 8-9, Original sheets 03-04",
        comment3="HV: 114V nominal, heavy cables HV orange",
        comment4="DANGER: High voltage traction system",
    )

    # -- Symbol definitions --
    sh.defsym("Think:BATT_HV", 24, 32,
        tpins=[("+", "power_out")],
        bpins=[("-", "power_in")],
        body_label="114V\\nTRACTION\\nBATTERY\\n(TB)", ref_pfx="BT")

    def_fuse(sh)

    sh.defsym("Think:CONTACTOR_BOX", 40, 60,
        lpins=[("+114V_IN", "power_in"), ("-114V_IN", "power_in")],
        rpins=[("+114V_OUT", "power_out"), ("-114V_OUT", "power_out"),
               ("+12V_OUT", "power_out"), ("PRECHARGE_OUT", "power_out")],
        tpins=["CB_RUN", "BMS_CMD", "CHG_START", "PREHEAT", "CHARGE"],
        bpins=["GND"],
        body_label="CONTACTOR\\nBOX", ref_pfx="U")

    sh.defsym("Think:MOTOR_CTRL", 50, 80,
        lpins=[("+114V", "power_in"), ("-114V", "power_in")],
        rpins=["L1", "L2", "L3",
               ("+12V_BAT", "power_out"), ("-12V_BAT", "power_out")],
        tpins=["DRIVE", "START", "DRIVE_RDY", "FAULT", "POWER",
               "RED_PWR", "BRAKE_SW", "REVERSE", "GEAR_LOCK", "RAD_FAN"],
        bpins=["K_LINE", "L_LINE"],
        body_label="MOTOR\\nCONTROLLER\\n(TIM)", ref_pfx="U")

    sh.defsym("Think:MOTOR_3PH", 28, 36,
        lpins=["L1", "L2", "L3", ("PE", "power_in")],
        body_label="M\\n3~\\nMAIN\\nMOTOR", ref_pfx="M")

    def_relay_spst(sh)
    def_switch(sh)

    sh.defsym("Think:BATT_LOCK_SW", 16, 10,
        lpins=["A"], rpins=["B"],
        body_label="BATTERY\\nLOCK", ref_pfx="SW")

    # -- Place components --
    BT_X, BT_Y = 40, 100
    sh.place("Think:BATT_HV", "BT1", "114V Traction Battery", BT_X, BT_Y)

    FH_X, FH_Y = 40, 45
    sh.place("Think:FUSE", "F_HV", "250A HV Fuse (Mega)", FH_X, FH_Y)

    CB_X, CB_Y = 150, 100
    sh.place("Think:CONTACTOR_BOX", "U1", "Contactor Box", CB_X, CB_Y)

    MC_X, MC_Y = 280, 110
    sh.place("Think:MOTOR_CTRL", "U2", "Motor Controller (TIM)", MC_X, MC_Y)

    MOT_X, MOT_Y = 380, 110
    sh.place("Think:MOTOR_3PH", "M1", "Main Motor AC", MOT_X, MOT_Y)

    # Start Inhibit Relay A
    sh.place("Think:RELAY_SPST", "K1", "Start Inhibit Relay A", 150, 200)

    # Battery Lock Switch
    sh.place("Think:BATT_LOCK_SW", "SW1", "Battery Lock Switch", 40, 170)

    # Main Current Switch
    sh.place("Think:SW_SPST", "SW2", "Main Current Switch", 40, 200)

    # -- Wiring: HV power path --
    # Battery+ → Fuse
    bt_pos = sh.p("BT1", "+")
    fh_a = sh.p("F_HV", "A")
    sh.wire(*bt_pos, bt_pos[0], fh_a[1])
    sh.wire(bt_pos[0], fh_a[1], *fh_a)
    sh.text(BT_X + 3, BT_Y - 20, "Wire: HV Orange (35mm2)", 0.9)

    # Fuse → Contactor Box +114V_IN
    fh_b = sh.p("F_HV", "B")
    cb_pv = sh.p("U1", "+114V_IN")
    sh.wire(*fh_b, 100, fh_b[1])
    sh.wire(100, fh_b[1], 100, cb_pv[1])
    sh.wire(100, cb_pv[1], *cb_pv)
    sh.label(fh_b[0] + 10, fh_b[1], "+114V_FUSED")

    # Battery- → Contactor Box -114V_IN
    bt_neg = sh.p("BT1", "-")
    cb_nv = sh.p("U1", "-114V_IN")
    sh.wire(*bt_neg, bt_neg[0], bt_neg[1] + 19)
    sh.wire(bt_neg[0], bt_neg[1] + 19, 100, bt_neg[1] + 19)
    sh.wire(100, bt_neg[1] + 19, 100, cb_nv[1])
    sh.wire(100, cb_nv[1], *cb_nv)
    sh.label(BT_X + 10, bt_neg[1] + 19, "-114V")

    # Contactor Box → Motor Controller HV
    cb_pout = sh.p("U1", "+114V_OUT")
    cb_nout = sh.p("U1", "-114V_OUT")
    mc_pv = sh.p("U2", "+114V")
    mc_nv = sh.p("U2", "-114V")
    sh.wire_l(*cb_pout, *mc_pv)
    sh.wire_l(*cb_nout, *mc_nv)
    sh.label(cb_pout[0] + 10, cb_pout[1], "+114V_TO_MC")
    sh.label(cb_nout[0] + 10, cb_nout[1], "-114V_TO_MC")

    # Motor Controller → Motor L1/L2/L3
    for lbl in ["L1", "L2", "L3"]:
        mcx, mcy = sh.p("U2", lbl)
        mmx, mmy = sh.p("M1", lbl)
        sh.wire(mcx, mcy, mcx + 13, mcy)
        sh.wire_l(mcx + 13, mcy, mmx, mmy)
        sh.label(mcx + 10, mcy, lbl)

    # Motor PE
    pe = sh.p("M1", "PE")
    sh.wire(*pe, pe[0] - 14, pe[1])
    sh.glabel(pe[0] - 14, pe[1], "CHASSIS_GND", 180, "input")

    # -- Global labels for inter-sheet connections --
    cb_gnd = sh.p("U1", "GND")
    sh.wire(*cb_gnd, cb_gnd[0], cb_gnd[1] + 10)
    sh.glabel(cb_gnd[0], cb_gnd[1] + 10, "GND", 270, "input")

    # Contactor Box control signals (global for cross-sheet)
    for cname in ["CB_RUN", "BMS_CMD", "CHG_START", "PREHEAT", "CHARGE"]:
        cx, cy = sh.p("U1", cname)
        sh.wire(cx, cy, cx, cy - 13)
        sh.glabel(cx, cy - 13, cname, 90)

    # Motor Controller top signals (global)
    mc_top_sigs = ["DRIVE", "START", "DRIVE_RDY", "FAULT", "POWER",
                   "RED_PWR", "BRAKE_SW", "REVERSE", "GEAR_LOCK", "RAD_FAN"]
    for sig in mc_top_sigs:
        mx, my = sh.p("U2", sig)
        sh.wire(mx, my, mx, my - 13)
        sh.glabel(mx, my - 13, sig if sig != "RAD_FAN" else "RAD_FAN_CMD", 90)

    # Motor Controller K_LINE / L_LINE
    kx, ky = sh.p("U2", "K_LINE")
    sh.wire(kx, ky, kx, ky + 13)
    sh.glabel(kx, ky + 13, "K_LINE", 270)
    lx, ly = sh.p("U2", "L_LINE")
    sh.wire(lx, ly, lx, ly + 13)
    sh.glabel(lx, ly + 13, "L_LINE", 270)

    # +114V / +12V globals from Contactor Box right side
    pch = sh.p("U1", "+12V_OUT")
    sh.wire(*pch, pch[0] + 10, pch[1])
    sh.glabel(pch[0] + 10, pch[1], "+12V_FROM_CB", 0, "output")
    prch = sh.p("U1", "PRECHARGE_OUT")
    sh.wire(*prch, prch[0] + 10, prch[1])
    sh.glabel(prch[0] + 10, prch[1], "+114V", 0, "output")

    # +12V from fuse F28
    sh.glabel(150, 240, "+12V_F28_DRIVE", 180)
    sh.text(155, 237, "From F28 (20A) -> Sheet 01", 0.9)

    # -- Wire color annotations --
    sh.text(105, CB_Y - 22, "Wire: HV Orange (35mm2)", 0.9)
    sh.text(CB_X + 25, CB_Y - 22, "Wire: HV Orange (35mm2)", 0.9)
    sh.text(MC_X + 30, MC_Y - 18, "Wire: HV Orange (16mm2)", 0.9)
    sh.text(50, BT_Y + 32, "Wire: HV Orange (35mm2)", 0.9)
    sh.text(155, 242, "Wire: 0.75mm2 WHT (ctrl signals)", 0.9)

    # -- Annotations --
    sh.text(30, 250, "HV POWER CIRCUIT", 1.8)
    sh.text(30, 258, "TB+ -> 250A Mega Fuse -> Contactor Box VA", 1.0)
    sh.text(30, 264, "TB- -> Contactor Box VB", 1.0)
    sh.text(30, 270, "Contactor Box -> Motor Controller +114V/-114V", 1.0)
    sh.text(30, 276, "Motor Controller L1/L2/L3 -> Main Motor", 1.0)
    sh.text(250, 250, "Cross-references:", 1.3)
    sh.text(250, 258, "+114V -> Sheet 05: DC/DC, Sheet 06: Charger", 1.0)
    sh.text(250, 264, "Control signals -> Sheet 03: Motor Control", 1.0)
    sh.text(250, 270, "CB_RUN, CHG_START -> Sheet 06: BMS & Charger", 1.0)

    return sh


def build_s03_motor_ctrl():
    """S03: Motor Control – PDF pages 10-11, sheets 05-06."""
    sh = Sheet(
        paper="A3",
        title="03 - Motor Control Signals",
        comment1="Motor Controller E01 signal connections, BMS E02, Gear Lock",
        comment2="PDF pages 10-11, Original sheets 05-06",
        comment3="Wire: 0.75mm2 various colors",
        comment4="Control logic and safety interlocks",
    )

    # -- Symbol definitions --
    sh.defsym("Think:MC_SIGNALS", 50, 70,
        lpins=["DRIVE", "START", "DRIVE_RDY", "FAULT",
               "RED_PWR", "BRAKE_SW", "REVERSE"],
        rpins=["GEAR_LOCK", "RAD_FAN_CMD", "K_LINE", "L_LINE",
               "+12V_BAT", "GND", "POWER"],
        body_label="MOTOR\\nCONTROLLER\\n(E01)\\nSignal Side",
        ref_pfx="U")

    sh.defsym("Think:BMS_CTRL", 30, 40,
        lpins=["CHG_START_IN", "DC_LO_PWR", "BAT_12V", "GND"],
        rpins=["BMS_CMD", "CHG_STATUS_OK", "K_LINE", "L_LINE"],
        body_label="BMS\\n(E02)", ref_pfx="U")

    sh.defsym("Think:START_INHIB_B", 16, 16,
        lpins=["COIL-"],
        rpins=["COIL+"],
        tpins=["COM"],
        bpins=["NO"],
        body_label="START\\nINHIB B", ref_pfx="K")

    def_relay_spst(sh)

    sh.defsym("Think:BRAKE_SWITCH", 16, 10,
        lpins=["IN"], rpins=["OUT"],
        body_label="BRAKE\\nSWITCH\\n(C12)", ref_pfx="SW")

    sh.defsym("Think:GEAR_LOCK_MOTOR", 20, 14,
        lpins=["M+", "M-"],
        rpins=["SW1", "SW2"],
        body_label="GEAR LOCK\\nMOTOR\\n(E20/E21)", ref_pfx="M")

    # -- Place components --
    MC_X, MC_Y = 120, 100
    sh.place("Think:MC_SIGNALS", "U1", "Motor Controller E01 Signals", MC_X, MC_Y)

    BMS_X, BMS_Y = 120, 220
    sh.place("Think:BMS_CTRL", "U2", "BMS (E02)", BMS_X, BMS_Y)

    SIB_X, SIB_Y = 280, 60
    sh.place("Think:START_INHIB_B", "K1", "Start Inhibit Relay B", SIB_X, SIB_Y)

    BS_X, BS_Y = 280, 110
    sh.place("Think:BRAKE_SWITCH", "SW1", "Brake Light Switch (C12)", BS_X, BS_Y)

    sh.place("Think:RELAY_SPST", "K2", "Radiator Fan Relay (R11)", 280, 150)

    sh.place("Think:GEAR_LOCK_MOTOR", "M1", "Gear Lock Motor E20/E21", 280, 200)

    # Gear lock relays R8, R9, R10
    sh.place("Think:RELAY_SPST", "K3", "Gear Lock Relay R8", 350, 170)
    sh.place("Think:RELAY_SPST", "K4", "Gear Lock Relay R9", 350, 200)
    sh.place("Think:RELAY_SPST", "K5", "Gear Lock Relay R10", 350, 230)

    # -- Global labels for cross-sheet --
    mc_l_sigs = ["DRIVE", "START", "DRIVE_RDY", "FAULT",
                 "RED_PWR", "BRAKE_SW", "REVERSE"]
    for sig in mc_l_sigs:
        px, py = sh.p("U1", sig)
        sh.wire(px, py, px - 18, py)
        sh.glabel(px - 18, py, sig, 180)

    mc_r_sigs = ["GEAR_LOCK", "RAD_FAN_CMD", "K_LINE", "L_LINE",
                 "+12V_BAT", "GND", "POWER"]
    for sig in mc_r_sigs:
        px, py = sh.p("U1", sig)
        sh.wire(px, py, px + 18, py)
        if sig in ("GND", "+12V_BAT"):
            sh.glabel(px + 18, py, sig, 0, "input" if sig == "GND" else "output")
        else:
            sh.glabel(px + 18, py, sig, 0)

    # BMS signals
    bms_r_sigs = ["BMS_CMD", "CHG_STATUS_OK", "K_LINE", "L_LINE"]
    for sig in bms_r_sigs:
        px, py = sh.p("U2", sig)
        sh.wire(px, py, px + 18, py)
        sh.glabel(px + 18, py, sig, 0)

    # Brake switch connection
    bs_in = sh.p("SW1", "IN")
    sh.wire(*bs_in, bs_in[0] - 15, bs_in[1])
    sh.glabel(bs_in[0] - 15, bs_in[1], "BRAKE_SW", 180)
    bs_out = sh.p("SW1", "OUT")
    sh.wire(*bs_out, bs_out[0] + 15, bs_out[1])
    sh.glabel(bs_out[0] + 15, bs_out[1], "BRAKE_LIGHT_FEED", 0)

    # Radiator fan relay
    k2_coil_p = sh.p("K2", "86_COIL+")
    sh.wire(*k2_coil_p, k2_coil_p[0] + 12, k2_coil_p[1])
    sh.glabel(k2_coil_p[0] + 12, k2_coil_p[1], "RAD_FAN_CMD", 0)

    # -- Wire color annotations --
    sh.text(30, 260, "Wire colors:", 1.3)
    sh.text(30, 267, "0.75mm2 WHT - Drive, Start signals", 1.0)
    sh.text(30, 273, "0.75mm2 GRN - Drive Ready, Gear Lock", 1.0)
    sh.text(30, 279, "0.75mm2 PNK - Fault, Reduced Power", 1.0)
    sh.text(30, 285, "0.75mm2 GRY - Brake contact, Reverse", 1.0)

    sh.text(250, 260, "Cross-references:", 1.3)
    sh.text(250, 267, "DRIVE, START -> Sheet 01: Ignition Switch", 1.0)
    sh.text(250, 273, "BRAKE_SW -> Sheet 08: Rear Lights", 1.0)
    sh.text(250, 279, "K_LINE, L_LINE -> Sheet 11: Diagnostics", 1.0)
    sh.text(250, 285, "RAD_FAN_CMD -> Sheet 06: BMS/Cooling", 1.0)

    return sh


def build_s04_sensors():
    """S04: Sensors – PDF pages 12-13, sheets 07-08."""
    sh = Sheet(
        paper="A3",
        title="04 - Sensors & Inputs",
        comment1="Motor Position Sensor E05, Gear Selector D7, Throttle C02",
        comment2="PDF pages 12-13, Original sheets 07-08",
        comment3="Wire: 0.5-1mm2 various",
        comment4="Analog and digital sensor inputs to Motor Controller",
    )

    # -- Symbol definitions --
    sh.defsym("Think:MOTOR_POS_SENSOR", 30, 50,
        lpins=["POS1", "POS2", "POS3", "POS4", "POS5", "POS6"],
        rpins=["MOTOR_TEMP+", "MOTOR_TEMP-", "+5V", "GND", "SHIELD"],
        body_label="MOTOR\\nPOSITION\\nSENSOR\\n(E05)", ref_pfx="U")

    sh.defsym("Think:GEAR_SELECTOR", 22, 36,
        lpins=["GND"],
        rpins=["PARK", "FREE", "DRIVE", "REVERSE"],
        body_label="GEAR\\nSELECTOR\\n(D7)", ref_pfx="SW")

    sh.defsym("Think:THROTTLE_PEDAL", 24, 28,
        lpins=[("+5V_RUN", "power_in"), ("ANALOG_GND", "passive")],
        rpins=["POSITION", ("THROTTLE_PULL", "output")],
        body_label="THROTTLE\\nPEDAL\\n(C02)", ref_pfx="BP")

    sh.defsym("Think:DCDC_HI_REF", 16, 10,
        lpins=["IN"], rpins=["OUT"],
        body_label="DC/DC\\nHI REF", ref_pfx="U")

    # -- Place components --
    PS_X, PS_Y = 100, 80
    sh.place("Think:MOTOR_POS_SENSOR", "U1", "Motor Position Sensor (E05)", PS_X, PS_Y)

    GS_X, GS_Y = 100, 190
    sh.place("Think:GEAR_SELECTOR", "SW1", "Gear Selector (D7)", GS_X, GS_Y)

    TP_X, TP_Y = 300, 80
    sh.place("Think:THROTTLE_PEDAL", "BP1", "Throttle Pedal (C02)", TP_X, TP_Y)

    sh.place("Think:DCDC_HI_REF", "U2", "DC/DC High Effect Ref", 300, 160)

    # -- Motor Position Sensor connections --
    ps_l_pins = ["POS1", "POS2", "POS3", "POS4", "POS5", "POS6"]
    ps_l_labels = ["POS_SENSE_1", "POS_SENSE_2", "POS_SENSE_3",
                   "POS_SENSE_4", "POS_SENSE_5", "POS_SENSE_6"]
    for pin, sig in zip(ps_l_pins, ps_l_labels):
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px - 18, py)
        sh.glabel(px - 18, py, sig, 180)

    # Right side
    ps_r_pins = ["MOTOR_TEMP+", "MOTOR_TEMP-", "+5V", "GND", "SHIELD"]
    ps_r_labels = ["MOTOR_TEMP_POS", "MOTOR_TEMP_NEG", "+5V_SENSOR", "GND", "SHIELD_GND"]
    for pin, sig in zip(ps_r_pins, ps_r_labels):
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px + 18, py)
        shape = "input" if "GND" in sig else "bidirectional"
        sh.glabel(px + 18, py, sig, 0, shape)

    # -- Gear Selector connections --
    gs_r_pins = ["PARK", "FREE", "DRIVE", "REVERSE"]
    gs_r_labels = ["PARK_SW", "FREE_SW", "DRIVE", "REVERSE"]
    for pin, sig in zip(gs_r_pins, gs_r_labels):
        px, py = sh.p("SW1", pin)
        sh.wire(px, py, px + 17, py)
        sh.glabel(px + 17, py, sig, 0)

    gs_gnd = sh.p("SW1", "GND")
    sh.wire(*gs_gnd, gs_gnd[0] - 12, gs_gnd[1])
    sh.glabel(gs_gnd[0] - 12, gs_gnd[1], "GND", 180, "input")

    # -- Throttle Pedal connections --
    for pin, sig, dx, shape in [
        ("+5V_RUN",       "+5V_RUN",       -16, "output"),
        ("ANALOG_GND",    "ANALOG_GND",    -16, "input"),
        ("POSITION",      "THROTTLE_POS",   16, "bidirectional"),
        ("THROTTLE_PULL", "THROTTLE_PULL",  16, "bidirectional"),
    ]:
        px, py = sh.p("BP1", pin)
        sh.wire(px, py, px + dx, py)
        sh.glabel(px + dx, py, sig, 180 if dx < 0 else 0, shape)
    sh.text(TP_X + 35, TP_Y + 5, "Wire: 0.75mm2 YEL", 0.9)

    # DC/DC reference
    u2_in = sh.p("U2", "IN")
    sh.wire(*u2_in, u2_in[0] - 15, u2_in[1])
    sh.glabel(u2_in[0] - 15, u2_in[1], "DC_HI_PWR", 180)
    u2_out = sh.p("U2", "OUT")
    sh.wire(*u2_out, u2_out[0] + 15, u2_out[1])
    sh.glabel(u2_out[0] + 15, u2_out[1], "POWER", 0)

    # -- Annotations --
    sh.text(30, 255, "SENSOR CONNECTIONS", 1.8)
    sh.text(30, 263, "All sensor signals routed to Motor Controller E01", 1.0)
    sh.text(30, 269, "Position sensors: Hall-effect, 6 channels", 1.0)
    sh.text(30, 275, "Throttle pedal: Analog position + pull confirmation", 1.0)

    sh.text(250, 255, "Wire colors:", 1.3)
    sh.text(250, 263, "0.5mm2 WHT - Position sensors", 1.0)
    sh.text(250, 269, "0.75mm2 YEL - Throttle signals", 1.0)
    sh.text(250, 275, "0.75mm2 GRY - Gear selector", 1.0)
    sh.text(250, 281, "1mm2 BLU - Motor temp sensor", 1.0)
    sh.text(250, 287, "-> See Sheet 03: Motor Control for E01 connections", 1.0)

    return sh


def build_s05_regen_dcdc():
    """S05: Regen & DC/DC – PDF pages 14-15, sheets 09-10."""
    sh = Sheet(
        paper="A3",
        title="05 - Regenerative Braking & DC/DC Converter",
        comment1="Regen braking control, DC/DC Converter E07, HV Distribution Box",
        comment2="PDF pages 14-15, Original sheets 09-10",
        comment3="114V -> 12V conversion, 100A Mega fuse",
        comment4="",
    )

    # -- Symbol definitions --
    sh.defsym("Think:DCDC_CONV", 30, 36,
        lpins=[("+114V_IN", "power_in"), ("-114V_IN", "power_in")],
        rpins=[("+12V_OUT", "power_out"), ("-12V_OUT", "power_out")],
        tpins=["HI_PWR_IN"],
        bpins=["LO_PWR_OUT", "FAULT"],
        body_label="DC/DC\\nCONVERTER\\n(E07)", ref_pfx="U")

    sh.defsym("Think:HV_DIST_BOX", 28, 40,
        lpins=[("+114V_IN", "power_in"), ("-114V_IN", "power_in")],
        rpins=[("+114V_CB", "power_out"), ("-114V_CB", "power_out"),
               ("+114V_DCDC", "power_out"), ("-114V_DCDC", "power_out"),
               ("+114V_CHG", "power_out"), ("-114V_CHG", "power_out")],
        body_label="HV\\nDIST\\nBOX", ref_pfx="U")

    def_fuse(sh)

    sh.defsym("Think:CONTROL_LAMP", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="CTRL\\nLAMP\\n14/176", ref_pfx="DS")

    # -- Place components --
    DCDC_X, DCDC_Y = 200, 100
    sh.place("Think:DCDC_CONV", "U1", "DC/DC Converter (E07)", DCDC_X, DCDC_Y)

    HVDB_X, HVDB_Y = 60, 100
    sh.place("Think:HV_DIST_BOX", "U2", "HV Distribution Box", HVDB_X, HVDB_Y)

    # 100A Mega fuse between HV dist and DC/DC
    sh.place("Think:FUSE", "F1", "100A Mega Fuse", 130, 85)

    # Control lamp for regen braking
    sh.place("Think:CONTROL_LAMP", "DS1", "Control Lamp (14/176)", 300, 200)

    # -- Wiring --
    # HV Distribution +114V_DCDC → 100A fuse → DC/DC +114V_IN
    hvdb_dcdc_p = sh.p("U2", "+114V_DCDC")
    f1_a = sh.p("F1", "A")
    f1_b = sh.p("F1", "B")
    dcdc_pv = sh.p("U1", "+114V_IN")
    sh.wire(*hvdb_dcdc_p, f1_a[0], hvdb_dcdc_p[1])
    sh.wire(f1_a[0], hvdb_dcdc_p[1], *f1_a)
    sh.wire(*f1_b, dcdc_pv[0], f1_b[1])
    sh.wire(dcdc_pv[0], f1_b[1], *dcdc_pv)
    sh.label(f1_b[0] + 10, f1_b[1], "+114V_DCDC")

    # HV Distribution -114V_DCDC → DC/DC -114V_IN
    hvdb_dcdc_n = sh.p("U2", "-114V_DCDC")
    dcdc_nv = sh.p("U1", "-114V_IN")
    sh.wire(*hvdb_dcdc_n, 120, hvdb_dcdc_n[1])
    sh.wire(120, hvdb_dcdc_n[1], 120, dcdc_nv[1])
    sh.wire(120, dcdc_nv[1], *dcdc_nv)
    sh.label(125, dcdc_nv[1] - 3, "-114V_DCDC")

    # DC/DC +12V out
    dcdc_12p = sh.p("U1", "+12V_OUT")
    sh.wire(*dcdc_12p, dcdc_12p[0] + 18, dcdc_12p[1])
    sh.glabel(dcdc_12p[0] + 18, dcdc_12p[1], "+12V_ALWAYS", 0, "output")
    sh.text(dcdc_12p[0] + 20, dcdc_12p[1] - 4, "To 12V battery -> Sheet 01", 0.9)

    # DC/DC -12V out (GND)
    dcdc_12n = sh.p("U1", "-12V_OUT")
    sh.wire(*dcdc_12n, dcdc_12n[0] + 18, dcdc_12n[1])
    sh.glabel(dcdc_12n[0] + 18, dcdc_12n[1], "GND", 0, "input")

    # DC/DC HI_PWR_IN (from motor controller)
    dcdc_hi = sh.p("U1", "HI_PWR_IN")
    sh.wire(*dcdc_hi, dcdc_hi[0], dcdc_hi[1] - 15)
    sh.glabel(dcdc_hi[0], dcdc_hi[1] - 15, "DC_HI_PWR", 90)
    sh.text(dcdc_hi[0] + 3, dcdc_hi[1] - 13, "From Motor Ctrl -> Sheet 02", 0.9)

    # DC/DC LO_PWR_OUT (to BMS)
    dcdc_lo = sh.p("U1", "LO_PWR_OUT")
    sh.wire(*dcdc_lo, dcdc_lo[0], dcdc_lo[1] + 15)
    sh.glabel(dcdc_lo[0], dcdc_lo[1] + 15, "DC_LO_PWR", 270)
    sh.text(dcdc_lo[0] + 3, dcdc_lo[1] + 13, "To BMS -> Sheet 06", 0.9)

    # DC/DC FAULT
    dcdc_flt = sh.p("U1", "FAULT")
    sh.wire(*dcdc_flt, dcdc_flt[0], dcdc_flt[1] + 15)
    sh.glabel(dcdc_flt[0], dcdc_flt[1] + 15, "DCDC_FAULT", 270)

    # HV Distribution input from battery
    hvdb_pi = sh.p("U2", "+114V_IN")
    sh.wire(*hvdb_pi, hvdb_pi[0] - 14, hvdb_pi[1])
    sh.glabel(hvdb_pi[0] - 14, hvdb_pi[1], "+114V", 180)
    hvdb_ni = sh.p("U2", "-114V_IN")
    sh.wire(*hvdb_ni, hvdb_ni[0] - 14, hvdb_ni[1])
    sh.glabel(hvdb_ni[0] - 14, hvdb_ni[1], "-114V", 180)

    # HV Distribution to Contactor Box
    hvdb_cb_p = sh.p("U2", "+114V_CB")
    sh.wire(*hvdb_cb_p, hvdb_cb_p[0] + 19, hvdb_cb_p[1])
    sh.glabel(hvdb_cb_p[0] + 19, hvdb_cb_p[1], "+114V_CB", 0)
    hvdb_cb_n = sh.p("U2", "-114V_CB")
    sh.wire(*hvdb_cb_n, hvdb_cb_n[0] + 19, hvdb_cb_n[1])
    sh.glabel(hvdb_cb_n[0] + 19, hvdb_cb_n[1], "-114V_CB", 0)

    # HV Distribution to Charger
    hvdb_chg_p = sh.p("U2", "+114V_CHG")
    sh.wire(*hvdb_chg_p, hvdb_chg_p[0] + 19, hvdb_chg_p[1])
    sh.glabel(hvdb_chg_p[0] + 19, hvdb_chg_p[1], "+114V_CHARGER", 0)
    hvdb_chg_n = sh.p("U2", "-114V_CHG")
    sh.wire(*hvdb_chg_n, hvdb_chg_n[0] + 19, hvdb_chg_n[1])
    sh.glabel(hvdb_chg_n[0] + 19, hvdb_chg_n[1], "-114V_CHARGER", 0)
    sh.text(hvdb_chg_p[0] + 21, hvdb_chg_p[1] - 2, "To Charger -> Sheet 06", 0.9)

    # Control lamp
    ds1_p = sh.p("DS1", "+")
    sh.wire(*ds1_p, ds1_p[0] - 11, ds1_p[1])
    sh.glabel(ds1_p[0] - 11, ds1_p[1], "REGEN_LAMP", 180)
    ds1_n = sh.p("DS1", "-")
    sh.wire(*ds1_n, ds1_n[0] + 11, ds1_n[1])
    sh.glabel(ds1_n[0] + 11, ds1_n[1], "GND", 0, "input")

    # -- Annotations --
    sh.text(30, 240, "DC/DC CONVERTER & HV DISTRIBUTION", 1.8)
    sh.text(30, 248, "HV Distribution Box distributes 114V to:", 1.0)
    sh.text(30, 254, "  - Contactor Box (VA/VB) -> Sheet 02", 1.0)
    sh.text(30, 260, "  - DC/DC Converter (VD) -> 12V system", 1.0)
    sh.text(30, 266, "  - Charger (VQ) -> Sheet 06", 1.0)
    sh.text(30, 275, "Wire: 0.75mm2 YEL for charge cooling relay signal", 1.0)

    return sh


def build_s06_bms_charger():
    """S06: BMS & Charger – PDF pages 16-18, sheets 11-12-13."""
    sh = Sheet(
        paper="A3",
        title="06 - BMS & Charger",
        comment1="BMS E02, Charger E03, 230V AC Connection, Cooling System",
        comment2="PDF pages 16-18, Original sheets 11-12-13",
        comment3="Battery temp sensors, charge current control",
        comment4="Cooling: Radiator fans E11A/E11B, Coolant pump E16",
    )

    # -- Symbol definitions --
    sh.defsym("Think:BMS", 40, 54,
        lpins=["BAT_12V", "BAT_GND", "DC_LO_PWR", "CHG_START_IN"],
        rpins=["CHG_STATUS_OK", "CHG_START_OUT", "BMS_CMD",
               "K_LINE", "L_LINE"],
        tpins=["CURR_S_12V", "CURR_S_GND", "CURR_SENSE", "BATT_COOLING"],
        bpins=["TEMP1", "TEMP2", "TEMP3", "TEMP4"],
        body_label="BATTERY\\nMONITOR\\nSYSTEM\\n(BMS E02)",
        ref_pfx="U")

    sh.defsym("Think:CHARGER", 30, 40,
        lpins=["L1_AC", "L2_AC", "GND_AC"],
        rpins=[("+114V_DC", "power_out"), ("-114V_DC", "power_out")],
        tpins=["CHG_START", "CHG_STATUS_OK"],
        bpins=["K_LINE", "L_LINE"],
        body_label="CHARGER\\n(E03)\\n230VAC\\n->114VDC",
        ref_pfx="U")

    def_relay_spst(sh)

    sh.defsym("Think:AC_CONN", 18, 20,
        rpins=["L1", "L2", "PE"],
        body_label="230V AC\\nCONNECTION", ref_pfx="J")

    sh.defsym("Think:CHG_CURR_SW", 16, 14,
        lpins=["COM"],
        rpins=["HI", "LO"],
        body_label="CHARGE\\nCURRENT\\nSWITCH", ref_pfx="SW")

    def_motor_small(sh)

    sh.defsym("Think:TEMP_SENSOR", 14, 8,
        lpins=["T+"], rpins=["T-"],
        body_label="TEMP", ref_pfx="RT")

    # -- Place components --
    BMS_X, BMS_Y = 100, 100
    sh.place("Think:BMS", "U1", "Battery Monitoring System (E02)", BMS_X, BMS_Y)

    CHG_X, CHG_Y = 300, 100
    sh.place("Think:CHARGER", "U2", "Charger (E03)", CHG_X, CHG_Y)

    # 230V relay
    sh.place("Think:RELAY_SPST", "K1", "230V Relay", 300, 200)

    # AC connection
    sh.place("Think:AC_CONN", "J1", "230V AC Mains Connection", 380, 200)

    # Charge current switch
    sh.place("Think:CHG_CURR_SW", "SW1", "Charge Current Switch", 200, 200)

    # Radiator fans
    sh.place("Think:MOTOR_SM", "M1", "Radiator Fan A (E11A)", 100, 230)
    sh.place("Think:MOTOR_SM", "M2", "Radiator Fan B (E11B)", 100, 255)

    # Coolant pump
    sh.place("Think:MOTOR_SM", "M3", "Coolant Pump (E16)", 200, 240)

    # Charge cooling relay R4
    sh.place("Think:RELAY_SPST", "K2", "Charge Cooling Relay R4", 50, 240)

    # Temp sensors (BT01 connections)
    for i in range(4):
        sh.place("Think:TEMP_SENSOR", f"RT{i+1}", f"Battery Temp {i+1}", 60 + i * 25, 170)

    # -- BMS wiring --
    # BMS left side
    bms_l_map = [("BAT_12V", "+12V_F28_DRIVE"), ("BAT_GND", "GND"),
                 ("DC_LO_PWR", "DC_LO_PWR"), ("CHG_START_IN", "CHG_START_IN")]
    for pin, sig in bms_l_map:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px - 16, py)
        shape = "input" if sig == "GND" else "bidirectional"
        sh.glabel(px - 16, py, sig, 180, shape)

    # BMS right side
    bms_r_pins = ["CHG_STATUS_OK", "CHG_START_OUT", "BMS_CMD", "K_LINE", "L_LINE"]
    for pin in bms_r_pins:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px + 16, py)
        sh.glabel(px + 16, py, pin, 0)

    # BMS top side - current sense
    bms_t_pins = ["CURR_S_12V", "CURR_S_GND", "CURR_SENSE", "BATT_COOLING"]
    for pin in bms_t_pins:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px, py - 13)
        sh.glabel(px, py - 13, pin, 90)

    # BMS bottom - temp sensors
    bms_b_pins = ["TEMP1", "TEMP2", "TEMP3", "TEMP4"]
    for i, pin in enumerate(bms_b_pins):
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px, py + 11)
        sh.label(px, py + 11, pin)
        # Connect to temp sensors
        rt_p = sh.p(f"RT{i+1}", "T+")
        sh.wire_l(px, py + 11, *rt_p, h_first=False)

    # Charger wiring
    # Charger left (AC)
    for pin in ["L1_AC", "L2_AC", "GND_AC"]:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px - 13, py)
        sh.label(px - 13, py, pin)

    # Charger right (HV DC out)
    for pin, sig in [("+114V_DC", "+114V_CHARGER"), ("-114V_DC", "-114V_CHARGER")]:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px + 15, py)
        sh.glabel(px + 15, py, sig, 0)

    # Charger top (control)
    for pin, sig in [("CHG_START", "CHG_START"), ("CHG_STATUS_OK", "CHG_STATUS_OK")]:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px, py - 13)
        sh.glabel(px, py - 13, sig, 90)

    # Charger bottom (diagnostic)
    for pin in ["K_LINE", "L_LINE"]:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px, py + 13)
        sh.glabel(px, py + 13, pin, 270)

    # 230V relay → AC connector
    k1_com = sh.p("K1", "30_COM")
    j1_l1 = sh.p("J1", "L1")
    sh.wire_l(*k1_com, *j1_l1)
    sh.label(k1_com[0] + 15, k1_com[1], "230V_L1")

    # Cooling relay
    k2_coil_p = sh.p("K2", "86_COIL+")
    sh.wire(*k2_coil_p, k2_coil_p[0] - 14, k2_coil_p[1])
    sh.glabel(k2_coil_p[0] - 14, k2_coil_p[1], "BATT_COOLING", 180)

    # Radiator fan power
    for ref in ["M1", "M2"]:
        mp = sh.p(ref, "M+")
        mn = sh.p(ref, "M-")
        sh.wire(*mp, mp[0] - 12, mp[1])
        sh.glabel(mp[0] - 12, mp[1], "+12V_F6_RADFAN", 180)
        sh.wire(*mn, mn[0] + 8, mn[1])
        sh.glabel(mn[0] + 8, mn[1], "GND", 0, "input")

    # Coolant pump power
    m3p = sh.p("M3", "M+")
    m3n = sh.p("M3", "M-")
    sh.wire(*m3p, m3p[0] - 12, m3p[1])
    sh.glabel(m3p[0] - 12, m3p[1], "+12V_F10_WPUMP_CHG", 180)
    sh.wire(*m3n, m3n[0] + 8, m3n[1])
    sh.glabel(m3n[0] + 8, m3n[1], "GND", 0, "input")

    # -- Wire color annotations --
    sh.text(30, 268, "Wire: 0.75mm2 WHT (BMS control signals)", 0.9)
    sh.text(30, 273, "Wire: 0.5mm2 RED/VIO (sensor signals)", 0.9)
    sh.text(30, 278, "Wire: 1.5mm2 GRN (coolant pump)", 0.9)
    sh.text(30, 283, "Wire: 0.75mm2 YEL (charge status)", 0.9)
    sh.text(250, 268, "Wire: 0.75mm2 GRN (BMS K-line)", 0.9)
    sh.text(250, 273, "Wire: 0.75mm2 RED (BMS L-line)", 0.9)

    # -- Annotations --
    sh.text(30, 291, "BMS & CHARGER SYSTEM", 1.8)
    sh.text(30, 298, "BMS monitors battery temps via BT01 connector", 1.0)
    sh.text(30, 304, "Charger: 230V AC -> 114V DC, controlled by BMS", 1.0)
    sh.text(250, 291, "Cross-references:", 1.3)
    sh.text(250, 298, "BMS_CMD -> Sheet 02: Contactor Box", 1.0)
    sh.text(250, 304, "K_LINE/L_LINE -> Sheet 11: Diagnostics", 1.0)
    sh.text(250, 310, "+114V_CHARGER -> Sheet 05: HV Distribution", 1.0)

    return sh


def build_s07_headlights():
    """S07: Headlights – PDF pages 19-20, sheets 14-15."""
    sh = Sheet(
        paper="A3",
        title="07 - Headlights & Front Lights",
        comment1="Headlight Switch C25, DRL Relay R5, Low/High Beam, Parking Lights",
        comment2="PDF pages 19-20, Original sheets 14-15",
        comment3="Wire: 2.5mm2 PNK, 0.75mm2 BLU",
        comment4="License plate lights NO1/NO2",
    )

    # -- Symbol definitions --
    sh.defsym("Think:HEADLIGHT_SW", 26, 36,
        lpins=["BAT_IN"],
        rpins=["PARK", "LOW_BEAM", "HIGH_BEAM", "FLASH"],
        body_label="HEADLIGHT\\nSWITCH\\n(C25)\\nPARK/LOW/\\nHIGH/FLASH",
        ref_pfx="SW")

    def_relay_spst(sh)
    def_bulb(sh)
    def_fuse(sh)

    sh.defsym("Think:COLLISION_LAMP", 12, 8,
        lpins=["+"], rpins=["-"],
        body_label="COLL\\nLAMP", ref_pfx="DS")

    # -- Place components --
    HSW_X, HSW_Y = 60, 80
    sh.place("Think:HEADLIGHT_SW", "SW1", "Headlight Switch (C25)", HSW_X, HSW_Y)

    # DRL Relay R5
    sh.place("Think:RELAY_SPST", "K1", "DRL Relay R5", 160, 50)

    # Rear/Park Light Relay R17
    sh.place("Think:RELAY_SPST", "K2", "Park Light Relay R17", 160, 100)

    # Left parking light FA3
    sh.place("Think:BULB", "DS1", "LH Parking Light (FA3)", 260, 40)
    # Right parking light FA4
    sh.place("Think:BULB", "DS2", "RH Parking Light (FA4)", 260, 60)
    # Left low beam FA1
    sh.place("Think:BULB", "DS3", "LH Low Beam (FA1)", 260, 100)
    # Right low beam FA2
    sh.place("Think:BULB", "DS4", "RH Low Beam (FA2)", 260, 120)
    # Left high beam
    sh.place("Think:BULB", "DS5", "LH High Beam", 260, 160)
    # Right high beam
    sh.place("Think:BULB", "DS6", "RH High Beam", 260, 180)
    # License plate LH NO1
    sh.place("Think:BULB", "DS7", "LH License Plate (NO1)", 260, 210)
    # License plate RH NO2
    sh.place("Think:BULB", "DS8", "RH License Plate (NO2)", 260, 230)

    # Collision sensor lamp
    sh.place("Think:COLLISION_LAMP", "DS9", "Collision Sensor Lamp", 160, 230)

    # -- Wiring --
    # Headlight switch input
    hsw_in = sh.p("SW1", "BAT_IN")
    sh.wire(*hsw_in, hsw_in[0] - 15, hsw_in[1])
    sh.glabel(hsw_in[0] - 15, hsw_in[1], "+12V_F2_LIGHTS", 180)
    sh.text(hsw_in[0] - 13, hsw_in[1] - 4, "From F2 (40A)", 0.9)

    # Switch → DRL relay coil
    sw_park = sh.p("SW1", "PARK")
    k1_coil_p = sh.p("K1", "86_COIL+")
    sh.wire_l(*sw_park, *k1_coil_p)
    sh.label(sw_park[0] + 10, sw_park[1] - 2, "PARK_OUT")

    # Switch → Park light relay coil
    sw_low = sh.p("SW1", "LOW_BEAM")
    k2_coil_p = sh.p("K2", "86_COIL+")
    sh.wire_l(*sw_low, *k2_coil_p)

    # Switch → Low beam routing
    sw_high = sh.p("SW1", "HIGH_BEAM")
    sh.wire(*sw_high, 200, sw_high[1])
    sh.label(sw_high[0] + 10, sw_high[1] - 3, "LOW_BEAM_OUT")

    # Switch → High beam / flash routing
    sw_flash = sh.p("SW1", "FLASH")
    sh.wire(*sw_flash, 200, sw_flash[1])
    sh.label(sw_flash[0] + 10, sw_flash[1] - 3, "HIGH_BEAM_OUT")

    # DRL relay → parking lights
    k1_com = sh.p("K1", "30_COM")
    k1_no = sh.p("K1", "87_NO")
    ds1_p = sh.p("DS1", "+")
    ds2_p = sh.p("DS2", "+")
    sh.wire_l(*k1_com, *ds1_p)
    sh.wire_l(*k1_no, *ds2_p)

    # Park light relay → park/rear
    k2_com = sh.p("K2", "30_COM")
    sh.wire(*k2_com, 200, k2_com[1])

    # Low beam power routing
    sh.wire(200, sw_high[1], 200, ds3_y := sh.p("DS3", "+")[1])
    ds3_p = sh.p("DS3", "+")
    sh.wire(200, ds3_y, *ds3_p)
    ds4_p = sh.p("DS4", "+")
    sh.wire(200, ds3_y, 200, ds4_p[1])
    sh.wire(200, ds4_p[1], *ds4_p)
    sh.junction(200, ds3_y)

    # High beam
    ds5_p = sh.p("DS5", "+")
    ds6_p = sh.p("DS6", "+")
    sh.wire(200, sw_flash[1], 200, ds5_p[1])
    sh.wire(200, ds5_p[1], *ds5_p)
    sh.wire(200, ds5_p[1], 200, ds6_p[1])
    sh.wire(200, ds6_p[1], *ds6_p)
    sh.junction(200, ds5_p[1])

    # All bulb grounds
    for ref in ["DS1", "DS2", "DS3", "DS4", "DS5", "DS6", "DS7", "DS8"]:
        nx, ny = sh.p(ref, "-")
        sh.wire(nx, ny, nx + 15, ny)
        sh.glabel(nx + 15, ny, "GND", 0, "input")

    # License plate power
    ds7_p = sh.p("DS7", "+")
    sh.wire(*ds7_p, ds7_p[0] - 25, ds7_p[1])
    sh.glabel(ds7_p[0] - 25, ds7_p[1], "+12V_F23_LICENSE", 180)
    ds8_p = sh.p("DS8", "+")
    sh.wire(*ds8_p, ds8_p[0] - 25, ds8_p[1])
    sh.glabel(ds8_p[0] - 25, ds8_p[1], "+12V_F23_LICENSE", 180)

    # Fuse power globals on bulb + pins
    ds1_pp = sh.p("DS1", "+")
    sh.glabel(ds1_pp[0] - 12, ds1_pp[1], "+12V_F16_PARK_FRT", 180)
    ds3_pp = sh.p("DS3", "+")
    sh.glabel(ds3_pp[0] - 12, ds3_pp[1], "+12V_F27_LOBEAML", 180)
    ds4_pp = sh.p("DS4", "+")
    sh.glabel(ds4_pp[0] - 12, ds4_pp[1], "+12V_F26_LOBEAMR", 180)
    ds5_pp = sh.p("DS5", "+")
    sh.glabel(ds5_pp[0] - 12, ds5_pp[1], "+12V_F25_HIBEAMR", 180)

    # Collision lamp
    ds9_p = sh.p("DS9", "+")
    ds9_n = sh.p("DS9", "-")
    sh.wire(*ds9_p, ds9_p[0] - 12, ds9_p[1])
    sh.glabel(ds9_p[0] - 12, ds9_p[1], "+12V_F17_COLL_ALM", 180)
    sh.wire(*ds9_n, ds9_n[0] + 12, ds9_n[1])
    sh.glabel(ds9_n[0] + 12, ds9_n[1], "GND", 0, "input")

    # -- Annotations --
    sh.text(30, 255, "HEADLIGHT SYSTEM", 1.8)
    sh.text(30, 263, "C25 headlight switch: PARK/LOW/HIGH/FLASH positions", 1.0)
    sh.text(30, 269, "DRL relay R5 enables daytime running lights", 1.0)
    sh.text(30, 275, "Park light relay R17 for rear + parking lights", 1.0)
    sh.text(250, 255, "Bulb designators:", 1.3)
    sh.text(250, 263, "FA1/FA2: Low beam LH/RH", 1.0)
    sh.text(250, 269, "FA3/FA4: Parking LH/RH", 1.0)
    sh.text(250, 275, "NO1/NO2: License plate LH/RH", 1.0)
    sh.text(250, 281, "Wire: 2.5mm2 PNK, 0.75mm2 BLU", 1.0)
    sh.text(250, 287, "Power from F2(40A), F16(10A), F24(20A), F25-F27", 1.0)

    return sh


def build_s08_rear_lights():
    """S08: Rear Lights – PDF pages 21-22, sheets 16-17."""
    sh = Sheet(
        paper="A3",
        title="08 - Rear Lights",
        comment1="Reverse lights, Brake lights, High-mounted brake light, Fog lights",
        comment2="PDF pages 21-22, Original sheets 16-17",
        comment3="Wire: 0.75mm2 GRY, BLK, GRN, PNK",
        comment4="",
    )

    # -- Symbol definitions --
    def_relay_spst(sh)
    def_bulb(sh)
    def_switch(sh)

    sh.defsym("Think:BRAKE_LIGHT_SW", 18, 10,
        lpins=["IN"], rpins=["OUT"],
        body_label="BRAKE\\nLIGHT SW\\n(C12)", ref_pfx="SW")

    sh.defsym("Think:HIGH_BRAKE", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="HIGH\\nBRAKE", ref_pfx="DS")

    # -- Place components --
    # Reverse light relay R7
    sh.place("Think:RELAY_SPST", "K1", "Reverse Light Relay R7", 80, 60)

    # Brake light switch
    sh.place("Think:BRAKE_LIGHT_SW", "SW1", "Brake Light Switch (C12)", 80, 120)

    # Reverse lights
    sh.place("Think:BULB", "DS1", "LH Reverse Light", 220, 40)
    sh.place("Think:BULB", "DS2", "RH Reverse Light", 220, 60)

    # Brake lights
    sh.place("Think:BULB", "DS3", "LH Brake Light (B01)", 220, 100)
    sh.place("Think:BULB", "DS4", "RH Brake Light (B03)", 220, 120)

    # High mounted brake light
    sh.place("Think:HIGH_BRAKE", "DS5", "High Mounted Brake Light", 220, 145)

    # Turn signal / backup combos
    sh.place("Think:BULB", "DS6", "LH Blink/Reverse (B02)", 220, 175)
    sh.place("Think:BULB", "DS7", "RH Blink/Reverse (B04)", 220, 195)

    # Rear fog light
    sh.place("Think:BULB", "DS8", "Rear Fog Light (B05)", 220, 225)

    # Control lamp
    sh.place("Think:BULB", "DS9", "Control Lamp", 350, 120)

    # -- Wiring --
    # Reverse relay coil
    k1_cp = sh.p("K1", "86_COIL+")
    k1_cn = sh.p("K1", "85_COIL-")
    sh.wire(*k1_cp, k1_cp[0] - 14, k1_cp[1])
    sh.glabel(k1_cp[0] - 14, k1_cp[1], "+12V_F15_HTDW_REV", 180)
    sh.wire(*k1_cn, k1_cn[0] - 14, k1_cn[1])
    sh.glabel(k1_cn[0] - 14, k1_cn[1], "REVERSE", 180)
    sh.text(k1_cp[0] - 12, k1_cp[1] - 4, "From F15 (10A)", 0.9)

    # Reverse relay → reverse lights
    k1_com = sh.p("K1", "30_COM")
    k1_no = sh.p("K1", "87_NO")
    ds1_p = sh.p("DS1", "+")
    ds2_p = sh.p("DS2", "+")
    sh.wire_l(*k1_com, *ds1_p)
    sh.wire(*k1_no, 200, k1_no[1])
    sh.wire(200, k1_no[1], 200, ds2_p[1])
    sh.wire(200, ds2_p[1], *ds2_p)

    # Brake light switch input
    sw1_in = sh.p("SW1", "IN")
    sh.wire(*sw1_in, sw1_in[0] - 14, sw1_in[1])
    sh.glabel(sw1_in[0] - 14, sw1_in[1], "+12V_F12_BRAKE", 180)
    sh.text(sw1_in[0] - 12, sw1_in[1] - 4, "From F12 (10A)", 0.9)

    # Brake switch → brake lights
    sw1_out = sh.p("SW1", "OUT")
    ds3_p = sh.p("DS3", "+")
    ds4_p = sh.p("DS4", "+")
    ds5_p = sh.p("DS5", "+")
    sh.wire(*sw1_out, 150, sw1_out[1])
    sh.wire(150, sw1_out[1], 150, ds3_p[1])
    sh.wire(150, ds3_p[1], *ds3_p)
    sh.wire(150, sw1_out[1], 150, ds4_p[1])
    sh.wire(150, ds4_p[1], *ds4_p)
    sh.wire(150, sw1_out[1], 150, ds5_p[1])
    sh.wire(150, ds5_p[1], *ds5_p)
    sh.junction(150, sw1_out[1])

    # Brake switch also feeds secondary fuse F20
    sh.glabel(sw1_in[0] - 14, sw1_in[1] + 10, "+12V_F20_BRAKE2", 180)
    sh.text(sw1_in[0] - 12, sw1_in[1] + 13, "Alt feed from F20 (15A)", 0.9)

    # All bulb grounds
    for ref in ["DS1", "DS2", "DS3", "DS4", "DS5", "DS6", "DS7", "DS8"]:
        nx, ny = sh.p(ref, "-")
        sh.wire(nx, ny, nx + 15, ny)
        sh.glabel(nx + 15, ny, "GND", 0, "input")

    # Turn signal feeds
    ds6_p = sh.p("DS6", "+")
    sh.wire(*ds6_p, ds6_p[0] - 35, ds6_p[1])
    sh.glabel(ds6_p[0] - 35, ds6_p[1], "TURN_SIG_LH_REAR", 180)
    ds7_p = sh.p("DS7", "+")
    sh.wire(*ds7_p, ds7_p[0] - 35, ds7_p[1])
    sh.glabel(ds7_p[0] - 35, ds7_p[1], "TURN_SIG_RH_REAR", 180)

    # Rear fog
    ds8_p = sh.p("DS8", "+")
    sh.wire(*ds8_p, ds8_p[0] - 35, ds8_p[1])
    sh.glabel(ds8_p[0] - 35, ds8_p[1], "+12V_F21_FOGR", 180)
    sh.text(ds8_p[0] - 33, ds8_p[1] - 4, "From F21 (5A)", 0.9)

    # Control lamp
    ds9_p = sh.p("DS9", "+")
    ds9_n = sh.p("DS9", "-")
    sh.wire(*ds9_p, ds9_p[0] - 11, ds9_p[1])
    sh.glabel(ds9_p[0] - 11, ds9_p[1], "BRAKE_LIGHT_FEED", 180)
    sh.wire(*ds9_n, ds9_n[0] + 11, ds9_n[1])
    sh.glabel(ds9_n[0] + 11, ds9_n[1], "GND", 0, "input")

    # -- Annotations --
    sh.text(30, 255, "REAR LIGHTS", 1.8)
    sh.text(30, 263, "Reverse signal from Gear Selector -> Sheet 04", 1.0)
    sh.text(30, 269, "Brake switch C12 activates brake + high-mount lights", 1.0)
    sh.text(30, 275, "Turn signals shared with Sheet 09: Signals & Horn", 1.0)
    sh.text(250, 255, "Bulb designators:", 1.3)
    sh.text(250, 263, "B01/B03: LH/RH Brake/Stop", 1.0)
    sh.text(250, 269, "B02/B04: LH/RH Blink/Reverse", 1.0)
    sh.text(250, 275, "B05: Rear fog light", 1.0)
    sh.text(250, 281, "Power from F12, F15, F20, F21", 1.0)

    return sh


def build_s09_signals_horn():
    """S09: Signals & Horn – PDF pages 23-24, sheets 18-19."""
    sh = Sheet(
        paper="A3",
        title="09 - Turn Signals, Horn & Interior Lights",
        comment1="Horn E15, Dome Light, Door Switches, Flasher Relay R3, Hazard",
        comment2="PDF pages 23-24, Original sheets 18-19",
        comment3="Wire: 0.75mm2 VIO, 1.5mm2 GRN, 2.5mm2 PNK/BLU",
        comment4="Turn signal bulbs: FA5-FA8 front/side, B02/B04 rear",
    )

    # -- Symbol definitions --
    sh.defsym("Think:HORN", 16, 12,
        lpins=[("+", "power_in")], rpins=[("-", "passive")],
        body_label="HORN\\n(E15)", ref_pfx="BZ")

    sh.defsym("Think:HORN_CONTACT", 12, 8,
        lpins=["IN"], rpins=["OUT"],
        body_label="HORN\\nBTN", ref_pfx="SW")

    def_bulb(sh)
    def_switch(sh)
    def_relay_spst(sh)

    sh.defsym("Think:FLASHER_RELAY", 18, 16,
        lpins=["49_IN", "31_GND"],
        rpins=["49a_OUT"],
        body_label="FLASHER\\nRELAY\\n(R3)", ref_pfx="K")

    sh.defsym("Think:TURN_SIG_SW", 20, 24,
        lpins=["IN"],
        rpins=["LEFT", "RIGHT"],
        tpins=["HAZARD"],
        body_label="TURN SIG\\nSWITCH\\n(D14)", ref_pfx="SW")

    sh.defsym("Think:DOME_LIGHT", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="DOME\\nLIGHT", ref_pfx="DS")

    sh.defsym("Think:DOOR_SW", 12, 8,
        lpins=["COM"], rpins=["NO"],
        body_label="DOOR\\nSW", ref_pfx="SW")

    sh.defsym("Think:POWER_OUTLET", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="POWER\\nOUTLET\\n(D60)", ref_pfx="J")

    # -- Place components --
    # Horn
    sh.place("Think:HORN", "BZ1", "Horn (E15)", 80, 40)
    sh.place("Think:HORN_CONTACT", "SW1", "Horn Contact (steering wheel)", 80, 70)

    # Flasher relay
    sh.place("Think:FLASHER_RELAY", "K1", "Flasher Relay R3", 180, 40)

    # Turn signal switch
    sh.place("Think:TURN_SIG_SW", "SW2", "Turn Signal / Hazard Switch (D14)", 180, 110)

    # Turn signal bulbs - front
    sh.place("Think:BULB", "DS1", "LH Front Turn (FA5)", 300, 80)
    sh.place("Think:BULB", "DS2", "RH Front Turn (FA6)", 300, 100)
    # Side
    sh.place("Think:BULB", "DS3", "LH Side Marker (FA7)", 300, 125)
    sh.place("Think:BULB", "DS4", "RH Side Marker (FA8)", 300, 145)
    # Rear
    sh.place("Think:BULB", "DS5", "LH Rear Turn (B02)", 300, 170)
    sh.place("Think:BULB", "DS6", "RH Rear Turn (B04)", 300, 190)

    # Dome light
    sh.place("Think:DOME_LIGHT", "DS7", "Dome Light", 80, 170)

    # Door switches
    sh.place("Think:DOOR_SW", "SW3", "Driver Door Switch (C30)", 80, 200)
    sh.place("Think:DOOR_SW", "SW4", "Passenger Door Switch (C31)", 80, 220)

    # Tailgate switch
    sh.place("Think:SW_SPST", "SW5", "Tailgate Switch (B10)", 80, 245)

    # Power outlet
    sh.place("Think:POWER_OUTLET", "J1", "Power Outlet (D60)", 300, 230)

    # -- Wiring --
    # Horn power
    hz_p = sh.p("BZ1", "+")
    hz_n = sh.p("BZ1", "-")
    sh.wire(*hz_p, hz_p[0] - 15, hz_p[1])
    sh.glabel(hz_p[0] - 15, hz_p[1], "+12V_F9_HORN_DOME", 180)
    sh.wire(*hz_n, hz_n[0] + 15, hz_n[1])
    sh.glabel(hz_n[0] + 15, hz_n[1], "GND", 0, "input")

    # Horn contact
    hc_in = sh.p("SW1", "IN")
    hc_out = sh.p("SW1", "OUT")
    sh.wire(*hc_in, hc_in[0] - 17, hc_in[1])
    sh.glabel(hc_in[0] - 17, hc_in[1], "+12V_F9_HORN_DOME", 180)
    sh.wire(*hc_out, hc_out[0] + 17, hc_out[1])
    sh.label(hc_out[0] + 17, hc_out[1], "HORN_ACTIVE")

    # Flasher relay input
    fr_49 = sh.p("K1", "49_IN")
    fr_31 = sh.p("K1", "31_GND")
    sh.wire(*fr_49, fr_49[0] - 14, fr_49[1])
    sh.glabel(fr_49[0] - 14, fr_49[1], "+12V_F24_TURNSIG", 180)
    sh.text(fr_49[0] - 12, fr_49[1] - 4, "From F24 (20A)", 0.9)
    sh.wire(*fr_31, fr_31[0] - 14, fr_31[1])
    sh.glabel(fr_31[0] - 14, fr_31[1], "GND", 180, "input")

    # Flasher relay → turn signal switch
    fr_out = sh.p("K1", "49a_OUT")
    ts_in = sh.p("SW2", "IN")
    sh.wire(*fr_out, 200, fr_out[1])
    sh.wire(200, fr_out[1], 200, ts_in[1])
    sh.wire(200, ts_in[1], *ts_in)

    # Turn signal switch → left bulbs
    ts_left = sh.p("SW2", "LEFT")
    ds1_p = sh.p("DS1", "+")
    ds3_p = sh.p("DS3", "+")
    ds5_p = sh.p("DS5", "+")
    sh.wire(*ts_left, 250, ts_left[1])
    sh.wire(250, ts_left[1], 250, ds1_p[1])
    sh.wire(250, ds1_p[1], *ds1_p)
    sh.wire(250, ts_left[1], 250, ds3_p[1])
    sh.wire(250, ds3_p[1], *ds3_p)
    sh.wire(250, ds3_p[1], 250, ds5_p[1])
    sh.wire(250, ds5_p[1], *ds5_p)
    sh.junction(250, ts_left[1])
    sh.junction(250, ds3_p[1])

    # Turn signal switch → right bulbs
    ts_right = sh.p("SW2", "RIGHT")
    ds2_p = sh.p("DS2", "+")
    ds4_p = sh.p("DS4", "+")
    ds6_p = sh.p("DS6", "+")
    sh.wire(*ts_right, 270, ts_right[1])
    sh.wire(270, ts_right[1], 270, ds2_p[1])
    sh.wire(270, ds2_p[1], *ds2_p)
    sh.wire(270, ts_right[1], 270, ds4_p[1])
    sh.wire(270, ds4_p[1], *ds4_p)
    sh.wire(270, ds4_p[1], 270, ds6_p[1])
    sh.wire(270, ds6_p[1], *ds6_p)
    sh.junction(270, ts_right[1])
    sh.junction(270, ds4_p[1])

    # Hazard switch
    ts_haz = sh.p("SW2", "HAZARD")
    sh.wire(*ts_haz, ts_haz[0], ts_haz[1] - 11)
    sh.glabel(ts_haz[0], ts_haz[1] - 11, "+12V_F24_TURNSIG", 90)

    # All bulb grounds
    for ref in ["DS1", "DS2", "DS3", "DS4", "DS5", "DS6"]:
        nx, ny = sh.p(ref, "-")
        sh.wire(nx, ny, nx + 15, ny)
        sh.glabel(nx + 15, ny, "GND", 0, "input")

    # Global labels for turn signal rear (cross-sheet with S08)
    sh.wire(*ds5_p, ds5_p[0] - 16, ds5_p[1])
    sh.glabel(ds5_p[0] - 16, ds5_p[1], "TURN_SIG_LH_REAR", 180)
    sh.wire(*ds6_p, ds6_p[0] - 16, ds6_p[1])
    sh.glabel(ds6_p[0] - 16, ds6_p[1], "TURN_SIG_RH_REAR", 180)

    # Dome light
    dl_p = sh.p("DS7", "+")
    dl_n = sh.p("DS7", "-")
    sh.wire(*dl_p, dl_p[0] - 16, dl_p[1])
    sh.glabel(dl_p[0] - 16, dl_p[1], "+12V_F9_HORN_DOME", 180)
    sh.wire(*dl_n, dl_n[0] + 16, dl_n[1])
    sh.label(dl_n[0] + 16, dl_n[1], "DOME_SW")

    # Door switches → dome light control
    for ref, sig_l, sig_r in [("SW3", "DOOR_SW_DRIVER", "DOME_SW"),
                               ("SW4", "DOOR_SW_PASS", "DOME_SW")]:
        pin_l = sh.p(ref, "COM")
        pin_r = sh.p(ref, "NO")
        sh.wire(*pin_l, pin_l[0] - 17, pin_l[1])
        sh.glabel(pin_l[0] - 17, pin_l[1], sig_l, 180)
        sh.wire(*pin_r, pin_r[0] + 17, pin_r[1])
        sh.glabel(pin_r[0] + 17, pin_r[1], sig_r, 0)

    # Tailgate switch
    sw5_a = sh.p("SW5", "A")
    sh.wire(*sw5_a, sw5_a[0] - 16, sw5_a[1])
    sh.glabel(sw5_a[0] - 16, sw5_a[1], "TAILGATE_SW", 180)

    # Power outlet
    j1_p = sh.p("J1", "+")
    j1_n = sh.p("J1", "-")
    sh.wire(*j1_p, j1_p[0] - 16, j1_p[1])
    sh.glabel(j1_p[0] - 16, j1_p[1], "+12V_F8_OUTLET", 180)
    sh.wire(*j1_n, j1_n[0] + 16, j1_n[1])
    sh.glabel(j1_n[0] + 16, j1_n[1], "GND", 0, "input")
    sh.text(j1_p[0] - 14, j1_p[1] - 4, "From F8 (25A)", 0.9)

    # -- Annotations --
    sh.text(30, 265, "TURN SIGNALS, HORN & INTERIOR", 1.8)
    sh.text(30, 273, "Flasher relay R3 provides turn signal timing", 1.0)
    sh.text(30, 279, "Hazard switch activates both sides simultaneously", 1.0)
    sh.text(250, 265, "Turn signal bulbs:", 1.3)
    sh.text(250, 273, "FA5/FA6: Front LH/RH", 1.0)
    sh.text(250, 279, "FA7/FA8: Side markers LH/RH", 1.0)
    sh.text(250, 285, "B02/B04: Rear LH/RH (shared w/ Sheet 08)", 1.0)
    sh.text(250, 291, "Power from F8, F9, F17, F24", 1.0)

    return sh


def build_s10_wipers_alarm():
    """S10: Wipers & Alarm – PDF pages 25-26, sheets 20-21."""
    sh = Sheet(
        paper="A3",
        title="10 - Wipers & Alarm System",
        comment1="Wiper Switch C26, Wiper Motor E19, Washer Pump E10",
        comment2="PDF pages 25-26, Original sheets 20-21",
        comment3="Alarm Control Unit P4, Siren A3, Tailgate Release R13",
        comment4="Wire: 2.5mm2 WHT/GRN/BLU, 0.75mm2 RED/VIO",
    )

    # -- Symbol definitions --
    sh.defsym("Think:WIPER_SW", 24, 30,
        lpins=["BAT_IN"],
        rpins=["OFF", "INTERVAL", "SLOW", "FAST", "WASH"],
        body_label="WIPER\\nSWITCH\\n(C26)", ref_pfx="SW")

    def_relay_spst(sh)
    def_motor_small(sh)

    sh.defsym("Think:WIPER_MOTOR", 20, 20,
        lpins=["PARK", "SLOW", "FAST"],
        rpins=["COM", "GND"],
        body_label="WIPER\\nMOTOR\\n(E19)", ref_pfx="M")

    sh.defsym("Think:WASHER_PUMP", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="WASHER\\nPUMP\\n(E10)", ref_pfx="M")

    sh.defsym("Think:ALARM_UNIT", 30, 40,
        lpins=["DOOR_DR", "DOOR_PS", "TAILGATE", "+12V_BAT"],
        rpins=["SIREN", "TURN_SIG", "IGN_SENSE", "LOCK", "UNLOCK"],
        bpins=["GND"],
        body_label="ALARM\\nCONTROL\\nUNIT\\n(P4)", ref_pfx="U")

    sh.defsym("Think:SIREN", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="SIREN\\n(A3)", ref_pfx="BZ")

    # -- Place components --
    WSW_X, WSW_Y = 60, 70
    sh.place("Think:WIPER_SW", "SW1", "Wiper Switch (C26)", WSW_X, WSW_Y)

    sh.place("Think:RELAY_SPST", "K1", "Wiper Relay R1", 160, 50)

    WM_X, WM_Y = 260, 60
    sh.place("Think:WIPER_MOTOR", "M1", "Wiper Motor (E19)", WM_X, WM_Y)

    sh.place("Think:WASHER_PUMP", "M2", "Washer Pump (E10)", 260, 110)

    ALM_X, ALM_Y = 120, 190
    sh.place("Think:ALARM_UNIT", "U1", "Alarm Control Unit (P4)", ALM_X, ALM_Y)

    sh.place("Think:RELAY_SPST", "K2", "Tailgate Release Relay R13", 260, 170)

    sh.place("Think:SIREN", "BZ1", "Siren (A3)", 260, 210)

    # -- Wiring --
    # Wiper switch input
    wsw_in = sh.p("SW1", "BAT_IN")
    sh.wire(*wsw_in, wsw_in[0] - 16, wsw_in[1])
    sh.glabel(wsw_in[0] - 16, wsw_in[1], "+12V_F14_WIPER", 180)
    sh.text(wsw_in[0] - 14, wsw_in[1] - 4, "From F14 (25A)", 0.9)

    # Wiper switch INTERVAL → relay coil
    wsw_intv = sh.p("SW1", "INTERVAL")
    k1_cp = sh.p("K1", "86_COIL+")
    sh.wire_l(*wsw_intv, *k1_cp)

    # Wiper relay → motor PARK/SLOW
    k1_com = sh.p("K1", "30_COM")
    k1_no = sh.p("K1", "87_NO")
    wm_park = sh.p("M1", "PARK")
    wm_slow = sh.p("M1", "SLOW")
    sh.wire_l(*k1_com, *wm_park)
    sh.wire_l(*k1_no, *wm_slow)

    # Wiper motor fast speed
    wsw_fast = sh.p("SW1", "FAST")
    wm_fast = sh.p("M1", "FAST")
    sh.wire(*wsw_fast, 200, wsw_fast[1])
    sh.wire_l(200, wsw_fast[1], *wm_fast)

    # Wiper motor right side
    wm_com = sh.p("M1", "COM")
    wm_gnd = sh.p("M1", "GND")
    sh.wire(*wm_gnd, wm_gnd[0] + 13, wm_gnd[1])
    sh.glabel(wm_gnd[0] + 13, wm_gnd[1], "GND", 0, "input")
    sh.wire(*wm_com, wm_com[0] + 13, wm_com[1])
    sh.label(wm_com[0] + 13, wm_com[1], "WIPER_COM")

    # Washer pump
    m2_p = sh.p("M2", "+")
    m2_n = sh.p("M2", "-")
    sh.wire(*m2_p, m2_p[0] - 16, m2_p[1])
    sh.glabel(m2_p[0] - 16, m2_p[1], "+12V_F14_WIPER", 180)
    sh.wire(*m2_n, m2_n[0] + 16, m2_n[1])
    sh.glabel(m2_n[0] + 16, m2_n[1], "GND", 0, "input")

    # Alarm unit left connections
    alm_l_map = [("DOOR_DR", "DOOR_DR"), ("DOOR_PS", "DOOR_PS"),
                 ("TAILGATE", "TAILGATE"), ("+12V_BAT", "+12V_F17_COLL_ALM")]
    for pin, sig in alm_l_map:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px - 13, py)
        sh.glabel(px - 13, py, sig, 180)

    # Alarm unit right connections
    alm_r_map = [("SIREN", "SIREN_OUT"), ("TURN_SIG", "TURN_SIG_ALARM"),
                 ("IGN_SENSE", "IGN_SENSE"), ("LOCK", "DOOR_LOCK"), ("UNLOCK", "DOOR_UNLOCK")]
    for pin, sig in alm_r_map:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px + 13, py)
        sh.glabel(px + 13, py, sig, 0)

    # Alarm GND
    alm_gnd = sh.p("U1", "GND")
    sh.wire(*alm_gnd, alm_gnd[0], alm_gnd[1] + 10)
    sh.glabel(alm_gnd[0], alm_gnd[1] + 10, "GND", 270, "input")

    # Siren
    bz_p = sh.p("BZ1", "+")
    bz_n = sh.p("BZ1", "-")
    sh.wire(*bz_p, bz_p[0] - 13, bz_p[1])
    sh.glabel(bz_p[0] - 13, bz_p[1], "SIREN_OUT", 180)
    sh.wire(*bz_n, bz_n[0] + 13, bz_n[1])
    sh.glabel(bz_n[0] + 13, bz_n[1], "GND", 0, "input")

    # Tailgate release relay
    k2_cp = sh.p("K2", "86_COIL+")
    k2_cn = sh.p("K2", "85_COIL-")
    sh.wire(*k2_cp, k2_cp[0] - 14, k2_cp[1])
    sh.glabel(k2_cp[0] - 14, k2_cp[1], "+12V_F9_HORN_DOME", 180)
    sh.text(k2_cp[0] - 12, k2_cp[1] - 4, "From F9 (15A)", 0.9)
    k2_com = sh.p("K2", "30_COM")
    sh.wire(*k2_com, k2_com[0] + 14, k2_com[1])
    sh.glabel(k2_com[0] + 14, k2_com[1], "TAILGATE_RELEASE", 0)

    # Door switch globals (additional references for alarm cross-wiring)
    sh.glabel(sh.p("U1", "DOOR_DR")[0] - 13, sh.p("U1", "DOOR_DR")[1] - 8, "DOOR_SW_DRIVER", 180)
    sh.glabel(sh.p("U1", "DOOR_PS")[0] - 13, sh.p("U1", "DOOR_PS")[1] - 8, "DOOR_SW_PASS", 180)
    sh.glabel(sh.p("U1", "TAILGATE")[0] - 13, sh.p("U1", "TAILGATE")[1] - 8, "TAILGATE_SW", 180)

    # -- Annotations --
    sh.text(30, 245, "WIPERS & ALARM SYSTEM", 1.8)
    sh.text(30, 253, "Wiper motor E19: 5 wires (park, slow, fast, common, ground)", 1.0)
    sh.text(30, 259, "Alarm P4: monitors doors C30/C31, tailgate B10", 1.0)
    sh.text(30, 265, "Siren A3 activated by alarm unit", 1.0)
    sh.text(250, 245, "Wire colors:", 1.3)
    sh.text(250, 253, "2.5mm2 WHT - Wiper motor park", 1.0)
    sh.text(250, 259, "2.5mm2 GRN - Wiper motor slow", 1.0)
    sh.text(250, 265, "2.5mm2 BLU - Wiper motor fast", 1.0)
    sh.text(250, 271, "0.75mm2 RED/VIO - Alarm signals", 1.0)
    sh.text(250, 277, "Power from F9, F14(25A), F17", 1.0)

    return sh


def build_s11_diag_speed():
    """S11: Diagnostics & Speed – PDF pages 27-29, sheets 22-23-24."""
    sh = Sheet(
        paper="A3",
        title="11 - Diagnostics & Speedometer",
        comment1="Diagnostic Connector C09, K-LINE/L-LINE, Multi-connector D01-D03",
        comment2="PDF pages 27-29, Original sheets 22-23-24",
        comment3="OBD-II style diagnostic, Collision Sensor C050",
        comment4="Wire: 0.75mm2 WHT/GRN/YEL/PNK/RED",
    )

    # -- Symbol definitions --
    sh.defsym("Think:DIAG_CONN", 28, 42,
        lpins=["PIN1", "PIN2", "PIN3", "PIN4", "PIN5", "PIN6", "PIN7_KLINE", "PIN8"],
        rpins=["PIN9", "PIN10", "PIN11", "PIN12", "PIN13", "PIN14", "PIN15_LLINE", "PIN16_BAT"],
        body_label="DIAGNOSTIC\\nCONNECTOR\\n(C09)\\n16-pin OBD-II",
        ref_pfx="J")

    sh.defsym("Think:MULTI_CONN", 24, 30,
        lpins=["D01_1", "D01_2", "D01_3", "D01_4", "D01_5"],
        rpins=["D02_1", "D02_2", "D02_3", "D02_4", "D02_5"],
        body_label="MULTI\\nCONNECTOR\\n(D01/D02/D03)",
        ref_pfx="J")

    sh.defsym("Think:COLL_SENSOR", 24, 16,
        lpins=["KLINE", "+12V"],
        rpins=["GND", "CRASH_OUT"],
        body_label="COLLISION\\nSENSOR\\n(C050)", ref_pfx="U")

    def_relay_spst(sh)

    sh.defsym("Think:SPEEDOMETER", 20, 16,
        lpins=["SPEED_IN", "+12V"],
        rpins=["GND", "SIGNAL_OUT"],
        body_label="SPEED\\nSIGNAL", ref_pfx="U")

    # -- Place components --
    DC_X, DC_Y = 100, 80
    sh.place("Think:DIAG_CONN", "J1", "Diagnostic Connector (C09)", DC_X, DC_Y)

    MC_X, MC_Y = 300, 80
    sh.place("Think:MULTI_CONN", "J2", "Multi-connector D01/D02/D03", MC_X, MC_Y)

    CS_X, CS_Y = 100, 180
    sh.place("Think:COLL_SENSOR", "U1", "Collision Sensor (C050)", CS_X, CS_Y)

    sh.place("Think:RELAY_SPST", "K1", "Charge Cooling Relay R4", 300, 180)

    sh.place("Think:SPEEDOMETER", "U2", "Speed Signal", 300, 220)

    # -- Diagnostic connector wiring --
    # K-LINE (left pin 7)
    kl = sh.p("J1", "PIN7_KLINE")
    sh.wire(*kl, kl[0] - 14, kl[1])
    sh.glabel(kl[0] - 14, kl[1], "K_LINE", 180)
    sh.text(kl[0] - 12, kl[1] - 3, "Pin 7: K-LINE", 0.9)

    # L-LINE (right side pin 15)
    ll = sh.p("J1", "PIN15_LLINE")
    sh.wire(*ll, ll[0] + 14, ll[1])
    sh.glabel(ll[0] + 14, ll[1], "L_LINE", 0)
    sh.text(ll[0] + 16, ll[1] - 3, "Pin 15: L-LINE", 0.9)

    # +12V_BAT (right side pin 16)
    bat = sh.p("J1", "PIN16_BAT")
    sh.wire(*bat, bat[0] + 14, bat[1])
    sh.glabel(bat[0] + 14, bat[1], "+12V_ALWAYS", 0)
    sh.text(bat[0] + 16, bat[1] - 3, "Pin 16: +12V_BAT", 0.9)

    # Signal ground (left pin 5)
    gnd = sh.p("J1", "PIN5")
    sh.wire(*gnd, gnd[0] - 14, gnd[1])
    sh.glabel(gnd[0] - 14, gnd[1], "GND", 180, "input")
    sh.text(gnd[0] - 12, gnd[1] - 3, "Pin 5: Signal GND", 0.9)

    # Multi-connector left
    mc_l_pins = ["D01_1", "D01_2", "D01_3", "D01_4", "D01_5"]
    mc_l_sigs = ["DRIVE", "START", "DRIVE_RDY", "FAULT", "RED_PWR"]
    for pin, sig in zip(mc_l_pins, mc_l_sigs):
        px, py = sh.p("J2", pin)
        sh.wire(px, py, px - 16, py)
        sh.glabel(px - 16, py, sig, 180)

    # Multi-connector right
    mc_r_pins = ["D02_1", "D02_2", "D02_3", "D02_4", "D02_5"]
    mc_r_sigs = ["BRAKE_SW", "REVERSE", "GEAR_LOCK", "RAD_FAN_CMD", "POWER"]
    for pin, sig in zip(mc_r_pins, mc_r_sigs):
        px, py = sh.p("J2", pin)
        sh.wire(px, py, px + 16, py)
        sh.glabel(px + 16, py, sig, 0)

    # Collision sensor
    for pin, sig, dx, shape in [
        ("KLINE", "K_LINE", -14, "bidirectional"),
        ("+12V", "+12V_F17_COLL_ALM", -14, "bidirectional"),
        ("GND", "GND", 14, "input"),
        ("CRASH_OUT", "CRASH_SIGNAL", 14, "bidirectional"),
    ]:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px + dx, py)
        sh.glabel(px + dx, py, sig, 180 if dx < 0 else 0, shape)

    # Charge cooling relay
    k1_cp = sh.p("K1", "86_COIL+")
    k1_cn = sh.p("K1", "85_COIL-")
    sh.wire(*k1_cp, k1_cp[0] - 14, k1_cp[1])
    sh.glabel(k1_cp[0] - 14, k1_cp[1], "BATT_COOLING", 180)
    k1_com = sh.p("K1", "30_COM")
    sh.wire(*k1_com, k1_com[0] + 14, k1_com[1])
    sh.glabel(k1_com[0] + 14, k1_com[1], "+12V_F10_WPUMP_CHG", 0)

    # Speed signal
    for pin, sig, dx in [("SPEED_IN", "SPEED_SIGNAL", -13), ("+12V", "+12V_F30_DIAG", -13)]:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px + dx, py)
        sh.glabel(px + dx, py, sig, 180)

    # -- Annotations --
    sh.text(30, 255, "DIAGNOSTICS & SPEED", 1.8)
    sh.text(30, 263, "C09: 16-pin OBD-II style diagnostic connector", 1.0)
    sh.text(30, 269, "K-LINE sources: Motor Ctrl E01, BMS E02, Charger E03, Collision C050", 1.0)
    sh.text(30, 275, "Multi-connector D01/D02/D03 carries motor control signals", 1.0)
    sh.text(250, 255, "Cross-references:", 1.3)
    sh.text(250, 263, "K_LINE/L_LINE -> Sheet 03: Motor Ctrl, Sheet 06: BMS", 1.0)
    sh.text(250, 269, "Collision sensor -> Sheet 13: Safety", 1.0)
    sh.text(250, 275, "Wire: 0.75mm2 WHT/GRN/YEL/PNK/RED", 1.0)

    return sh


def build_s12_radio_hvac():
    """S12: Radio & HVAC – PDF pages 30-33, sheets 25-26-27-28."""
    sh = Sheet(
        paper="A3",
        title="12 - Radio, HVAC & Auxiliary Systems",
        comment1="Radio, Speakers, Heated Rear Window, Brake Vacuum Pump",
        comment2="PDF pages 30-33, Original sheets 25-26-27-28",
        comment3="Heater Blower, Recirculation Motor, Supplementary Heater",
        comment4="Wire: 0.75mm2 GRN/BLU/RED/YEL, 2.5mm2 for motors",
    )

    # -- Symbol definitions --
    sh.defsym("Think:RADIO", 24, 20,
        lpins=["+12V_BAT", "GND", "ANT"],
        rpins=["SPK_L+", "SPK_L-", "SPK_R+", "SPK_R-"],
        body_label="RADIO\\nUNIT",
        ref_pfx="U")

    sh.defsym("Think:SPEAKER", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="SPEAKER", ref_pfx="LS")

    sh.defsym("Think:ANTENNA", 10, 8,
        lpins=["SIG"], rpins=["GND"],
        body_label="ANT", ref_pfx="AN")

    def_relay_spst(sh)
    def_motor_small(sh)
    def_resistor(sh)
    def_switch(sh)

    sh.defsym("Think:HEATED_RW", 20, 14,
        lpins=["+12V"], rpins=["GND"],
        body_label="HEATED\\nREAR\\nWINDOW\\n(B07)", ref_pfx="HR")

    sh.defsym("Think:VAC_PUMP", 18, 12,
        lpins=["+"], rpins=["-"],
        body_label="BRAKE\\nVACUUM\\nPUMP\\n(E14)", ref_pfx="M")

    sh.defsym("Think:BLOWER_MOTOR", 20, 16,
        lpins=["M+", "M-"],
        rpins=["SPD1", "SPD2"],
        body_label="HEATER\\nBLOWER\\nMOTOR", ref_pfx="M")

    sh.defsym("Think:HEATER_SW", 20, 24,
        lpins=["IN"],
        rpins=["OFF", "SPD1", "SPD2", "SPD3", "SPD4"],
        body_label="HEATER\\nSWITCH", ref_pfx="SW")

    sh.defsym("Think:RECIRC_MOTOR", 16, 10,
        lpins=["M+"], rpins=["M-"],
        body_label="RECIRC\\nMOTOR", ref_pfx="M")

    sh.defsym("Think:WEBASTO", 24, 20,
        lpins=["+12V", "GND"],
        rpins=["FUEL", "EXHAUST", "CTRL"],
        body_label="SUPPLEMENTARY\\nHEATER\\n(Webasto COS1)",
        ref_pfx="U")

    sh.defsym("Think:TAILGATE_SOL", 14, 10,
        lpins=["+"], rpins=["-"],
        body_label="TAILGATE\\nSOL\\n(BD10)", ref_pfx="SOL")

    # -- Place components --
    # Radio section
    sh.place("Think:RADIO", "U1", "Radio Unit", 80, 50)
    sh.place("Think:SPEAKER", "LS1", "LH Speaker (D06)", 200, 35)
    sh.place("Think:SPEAKER", "LS2", "RH Speaker (D06)", 200, 55)
    sh.place("Think:ANTENNA", "AN1", "Antenna", 80, 20)

    # Heated rear window
    sh.place("Think:HEATED_RW", "HR1", "Heated Rear Window (B07)", 200, 90)
    sh.place("Think:RELAY_SPST", "K1", "Heated RW Relay R2", 140, 90)

    # Brake vacuum pump
    sh.place("Think:VAC_PUMP", "M1", "Brake Vacuum Pump (E14)", 80, 120)

    # Heater blower system
    sh.place("Think:HEATER_SW", "SW1", "Heater Switch", 80, 180)
    sh.place("Think:BLOWER_MOTOR", "M2", "Heater Blower Motor", 250, 160)
    sh.place("Think:RELAY_SPST", "K2", "Blower Relay R12", 160, 160)

    # Resistance unit (speed control)
    sh.place("Think:RESISTOR", "R1", "Resistance Unit SPD1", 250, 185)
    sh.place("Think:RESISTOR", "R2", "Resistance Unit SPD2", 250, 200)
    sh.place("Think:RESISTOR", "R3", "Resistance Unit SPD3", 250, 215)

    # Recirculation
    sh.place("Think:SW_SPST", "SW2", "Recirculation Switch", 80, 230)
    sh.place("Think:RELAY_SPST", "K3", "Recirculation Relay R14", 160, 230)
    sh.place("Think:RECIRC_MOTOR", "M3", "Recirculation Motor", 250, 240)

    # Supplementary heater (Webasto)
    sh.place("Think:WEBASTO", "U2", "Supplementary Heater (Webasto)", 350, 100)
    sh.place("Think:RELAY_SPST", "K4", "Combustion Heater Relay R16", 350, 50)

    # Tailgate release
    sh.place("Think:TAILGATE_SOL", "SOL1", "Tailgate Release (BD10)", 350, 170)
    sh.place("Think:SW_SPST", "SW3", "Tailgate Release Switch", 350, 200)

    # -- Wiring --
    # Radio power
    r_12v = sh.p("U1", "+12V_BAT")
    r_gnd = sh.p("U1", "GND")
    sh.wire(*r_12v, r_12v[0] - 14, r_12v[1])
    sh.glabel(r_12v[0] - 14, r_12v[1], "+12V_F7_RADIO", 180)
    sh.wire(*r_gnd, r_gnd[0] - 14, r_gnd[1])
    sh.glabel(r_gnd[0] - 14, r_gnd[1], "GND", 180, "input")

    # Radio → speakers
    for rpin, sref in [("SPK_L+", "LS1"), ("SPK_L-", "LS1"),
                        ("SPK_R+", "LS2"), ("SPK_R-", "LS2")]:
        rx, ry = sh.p("U1", rpin)
        spin = "+" if "+" in rpin else "-"
        sx, sy = sh.p(sref, spin)
        sh.wire_l(rx, ry, sx, sy)

    # Speaker GND
    for ref in ["LS1", "LS2"]:
        nx, ny = sh.p(ref, "-")
        sh.wire(nx, ny, nx + 15, ny)
        sh.glabel(nx + 15, ny, "GND", 0, "input")

    # Antenna
    an_sig = sh.p("AN1", "SIG")
    sh.wire(*an_sig, an_sig[0] - 13, an_sig[1])
    sh.label(an_sig[0] - 13, an_sig[1] - 3, "ANT_SIGNAL")
    r_ant = sh.p("U1", "ANT")
    sh.wire(*r_ant, r_ant[0], an_sig[1])

    # Heated rear window relay → element
    k1_cp = sh.p("K1", "86_COIL+")
    sh.wire(*k1_cp, k1_cp[0] - 14, k1_cp[1])
    sh.glabel(k1_cp[0] - 14, k1_cp[1], "+12V_F1_HTDWS", 180)
    sh.text(k1_cp[0] - 12, k1_cp[1] - 4, "From F1 (30A)", 0.9)
    k1_com = sh.p("K1", "30_COM")
    hr_12v = sh.p("HR1", "+12V")
    sh.wire_l(*k1_com, *hr_12v)
    hr_gnd = sh.p("HR1", "GND")
    sh.wire(*hr_gnd, hr_gnd[0] + 12, hr_gnd[1])
    sh.glabel(hr_gnd[0] + 12, hr_gnd[1], "GND", 0, "input")

    # Brake vacuum pump
    vp_p = sh.p("M1", "+")
    vp_n = sh.p("M1", "-")
    sh.wire(*vp_p, vp_p[0] - 14, vp_p[1])
    sh.glabel(vp_p[0] - 14, vp_p[1], "+12V_F22_VACPUMP", 180)
    sh.text(vp_p[0] - 12, vp_p[1] - 4, "From F22 (25A)", 0.9)
    sh.wire(*vp_n, vp_n[0] + 14, vp_n[1])
    sh.glabel(vp_n[0] + 14, vp_n[1], "GND", 0, "input")

    # Heater switch → relay → blower
    hs_in = sh.p("SW1", "IN")
    sh.wire(*hs_in, hs_in[0] - 14, hs_in[1])
    sh.glabel(hs_in[0] - 14, hs_in[1], "+12V_F5_BLOWER", 180)
    sh.text(hs_in[0] - 12, hs_in[1] - 4, "From F5 (30A)", 0.9)

    hs_spd1 = sh.p("SW1", "SPD1")
    k2_cp = sh.p("K2", "86_COIL+")
    sh.wire_l(*hs_spd1, *k2_cp)
    k2_com = sh.p("K2", "30_COM")
    bm_mp = sh.p("M2", "M+")
    sh.wire_l(*k2_com, *bm_mp)

    # Blower GND
    bm_mn = sh.p("M2", "M-")
    sh.wire(*bm_mn, bm_mn[0] + 13, bm_mn[1])
    sh.glabel(bm_mn[0] + 13, bm_mn[1], "GND", 0, "input")

    # Recirculation
    sw2_a = sh.p("SW2", "A")
    sh.wire(*sw2_a, sw2_a[0] - 16, sw2_a[1])
    sh.glabel(sw2_a[0] - 16, sw2_a[1], "+12V_F5_BLOWER", 180)
    sw2_b = sh.p("SW2", "B")
    k3_cp = sh.p("K3", "86_COIL+")
    sh.wire_l(*sw2_b, *k3_cp)
    k3_com = sh.p("K3", "30_COM")
    rm_p = sh.p("M3", "M+")
    sh.wire_l(*k3_com, *rm_p)
    rm_n = sh.p("M3", "M-")
    sh.wire(*rm_n, rm_n[0] + 12, rm_n[1])
    sh.glabel(rm_n[0] + 12, rm_n[1], "GND", 0, "input")

    # Webasto heater
    wb_12v = sh.p("U2", "+12V")
    wb_gnd = sh.p("U2", "GND")
    sh.wire(*wb_12v, wb_12v[0] - 14, wb_12v[1])
    sh.glabel(wb_12v[0] - 14, wb_12v[1], "+12V_F3_HEATER", 180)
    sh.text(wb_12v[0] - 12, wb_12v[1] - 4, "From F3 (40A)", 0.9)
    sh.wire(*wb_gnd, wb_gnd[0] - 14, wb_gnd[1])
    sh.glabel(wb_gnd[0] - 14, wb_gnd[1], "GND", 180, "input")

    wb_ctrl = sh.p("U2", "CTRL")
    sh.wire(*wb_ctrl, wb_ctrl[0] + 14, wb_ctrl[1])
    sh.glabel(wb_ctrl[0] + 14, wb_ctrl[1], "WEBASTO_CTRL", 0)

    # Webasto relay
    k4_cp = sh.p("K4", "86_COIL+")
    sh.wire(*k4_cp, k4_cp[0] - 14, k4_cp[1])
    sh.glabel(k4_cp[0] - 14, k4_cp[1], "+12V_F33_WEBASTO", 180)

    # Tailgate release
    sol_p = sh.p("SOL1", "+")
    sol_n = sh.p("SOL1", "-")
    sh.wire(*sol_p, sol_p[0] - 13, sol_p[1])
    sh.glabel(sol_p[0] - 13, sol_p[1], "TAILGATE_RELEASE", 180)
    sh.wire(*sol_n, sol_n[0] + 13, sol_n[1])
    sh.glabel(sol_n[0] + 13, sol_n[1], "GND", 0, "input")

    sw3_a = sh.p("SW3", "A")
    sh.wire(*sw3_a, sw3_a[0] - 13, sw3_a[1])
    sh.glabel(sw3_a[0] - 13, sw3_a[1], "+12V_F9_HORN_DOME", 180)

    # -- Annotations --
    sh.text(30, 260, "RADIO, HVAC & AUXILIARY", 1.8)
    sh.text(30, 268, "Blower motor: Multi-speed via resistance unit (4 speeds)", 1.0)
    sh.text(30, 274, "Webasto COS1: Supplementary heater for cabin/battery", 1.0)
    sh.text(30, 280, "Heated rear window: Relay R2, powered from F1 (30A)", 1.0)
    sh.text(250, 260, "Cross-references:", 1.3)
    sh.text(250, 268, "Power from F1, F3, F5, F7, F9, F22, F30", 1.0)
    sh.text(250, 274, "Tailgate release -> Sheet 09/10", 1.0)
    sh.text(250, 280, "Webasto control -> Sheet 01 (F3, F33)", 1.0)

    return sh


def build_s13_safety_hv():
    """S13: Safety & HV Detail – PDF pages 34-38, sheets 29+HV."""
    sh = Sheet(
        paper="A3",
        title="13 - Safety Systems & HV Contactor Box Detail",
        comment1="Collision Control C050, Seatbelt Pretensioners C55/C56",
        comment2="PDF pages 34-38, Original sheet 29 + HV box sheets",
        comment3="Contactor Box internals: PTC precharge, LEM LA-205-S",
        comment4="HV Distribution Box connector layout",
    )

    # -- Symbol definitions --
    sh.defsym("Think:COLL_CTRL", 30, 30,
        lpins=["K_LINE", "+12V_BAT", "CRASH_IN"],
        rpins=["DRIVER_BELT", "PASS_BELT", "WARNING_LAMP", "GND"],
        body_label="COLLISION\\nCONTROL\\nUNIT\\n(C050)",
        ref_pfx="U")

    sh.defsym("Think:BELT_PRETENS", 16, 10,
        lpins=["FIRE+"], rpins=["FIRE-"],
        body_label="SEATBELT\\nPRETENS", ref_pfx="SB")

    # Contactor box internals
    sh.defsym("Think:CB_INTERNAL", 60, 80,
        lpins=[("+114V_IN", "power_in"), ("-114V_IN", "power_in"),
               ("MAIN_RELAY_COIL", "passive"), ("AUX_RELAY_COIL", "passive"),
               ("HEATER_RELAY_COIL", "passive")],
        rpins=[("+114V_OUT", "power_out"), ("-114V_OUT", "power_out"),
               ("PRECHARGE_OUT", "power_out"),
               ("LEM_SENSE+", "output"), ("LEM_SENSE-", "output")],
        tpins=["CB_RUN", "BMS_CMD", "CHG_START", "PREHEAT",
               "CHARGE", "+12V_CTRL"],
        bpins=["GND", "DIAG"],
        body_label="CONTACTOR BOX\\nINTERNAL DETAIL\\n\\nPTC Precharge\\nMain Relay\\nAux Relay\\nHeater Relay\\nLEM LA-205-S\\nCurrent Sensor\\n\\nTime Delay: 0.5s\\nD5 Diode\\nR1-R5 Resistors\\nT1 Transistor",
        ref_pfx="U")

    sh.defsym("Think:HV_DIST_DETAIL", 40, 40,
        lpins=[("+114V_BATT", "power_in"), ("-114V_BATT", "power_in")],
        rpins=[("VA_CB+", "power_out"), ("VB_CB-", "power_out"),
               ("VD_DCDC+", "power_out"), ("VD_DCDC-", "power_out"),
               ("VQ_CHG+", "power_out"), ("VQ_CHG-", "power_out")],
        tpins=["VH_HEAT", "VK_CTRL"],
        body_label="HV\\nDISTRIBUTION\\nBOX\\nDetail",
        ref_pfx="U")

    def_resistor(sh)

    # -- Place components --
    # Collision control unit
    CC_X, CC_Y = 100, 60
    sh.place("Think:COLL_CTRL", "U1", "Collision Control Unit (C050)", CC_X, CC_Y)

    # Seatbelt pretensioners
    sh.place("Think:BELT_PRETENS", "SB1", "Driver Seatbelt Pretensioner (C56)", 250, 45)
    sh.place("Think:BELT_PRETENS", "SB2", "Passenger Seatbelt Pretensioner (C55)", 250, 65)

    # Contactor box internal detail
    CB_X, CB_Y = 200, 180
    sh.place("Think:CB_INTERNAL", "U2", "Contactor Box Internal Detail", CB_X, CB_Y)

    # HV Distribution box detail
    HVD_X, HVD_Y = 60, 200
    sh.place("Think:HV_DIST_DETAIL", "U3", "HV Distribution Box Detail", HVD_X, HVD_Y)

    # -- Collision control wiring --
    cc_l_map = [("K_LINE", "K_LINE", "bidirectional"),
                ("+12V_BAT", "+12V_F17_COLL_ALM", "output"),
                ("CRASH_IN", "CRASH_SIGNAL", "bidirectional")]
    for pin, sig, shape in cc_l_map:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px - 13, py)
        sh.glabel(px - 13, py, sig, 180, shape)

    # Collision control right → pretensioners
    cc_r_pins = ["DRIVER_BELT", "PASS_BELT", "WARNING_LAMP", "GND"]
    for pin in cc_r_pins:
        px, py = sh.p("U1", pin)
        sh.wire(px, py, px + 13, py)
        if pin == "DRIVER_BELT":
            sb1_f = sh.p("SB1", "FIRE+")
            sh.wire_l(px + 13, py, *sb1_f)
        elif pin == "PASS_BELT":
            sb2_f = sh.p("SB2", "FIRE+")
            sh.wire_l(px + 13, py, *sb2_f)
        elif pin == "GND":
            sh.glabel(px + 13, py, "GND", 0, "input")
        else:
            sh.glabel(px + 13, py, pin, 0)

    # Pretensioner GND
    sb1_n = sh.p("SB1", "FIRE-")
    sh.wire(*sb1_n, sb1_n[0] + 15, sb1_n[1])
    sh.glabel(sb1_n[0] + 15, sb1_n[1], "GND", 0, "input")
    sb2_n = sh.p("SB2", "FIRE-")
    sh.wire(*sb2_n, sb2_n[0] + 15, sb2_n[1])
    sh.glabel(sb2_n[0] + 15, sb2_n[1], "GND", 0, "input")
    sh.text(sb1_n[0] + 5, sb1_n[1] - 4, "Wire: 0.5mm2 PNK", 0.9)

    # -- Contactor box internal connections --
    # Left side
    cb_l_pins = ["+114V_IN", "-114V_IN", "MAIN_RELAY_COIL", "AUX_RELAY_COIL", "HEATER_RELAY_COIL"]
    for pin in cb_l_pins:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px - 13, py)
        if "114V" in pin:
            sh.glabel(px - 13, py, pin.replace("_IN", ""), 180)
        else:
            sh.label(px - 13, py, pin)

    # Right side
    cb_r_pins = ["+114V_OUT", "-114V_OUT", "PRECHARGE_OUT", "LEM_SENSE+", "LEM_SENSE-"]
    for pin in cb_r_pins:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px + 13, py)
        if "114V" in pin:
            sh.glabel(px + 13, py, pin.replace("_OUT", "_TO_MC"), 0)
        elif "LEM" in pin:
            sh.glabel(px + 13, py, pin, 0)
        else:
            sh.label(px + 13, py, pin)

    # Top control signals
    cb_t_pins = ["CB_RUN", "BMS_CMD", "CHG_START", "PREHEAT", "CHARGE", "+12V_CTRL"]
    for pin in cb_t_pins:
        px, py = sh.p("U2", pin)
        sh.wire(px, py, px, py - 13)
        if pin == "+12V_CTRL":
            sh.glabel(px, py - 13, "+12V_F28_DRIVE", 90)
        else:
            sh.glabel(px, py - 13, pin, 90)

    # Bottom
    cb_gnd = sh.p("U2", "GND")
    sh.wire(*cb_gnd, cb_gnd[0], cb_gnd[1] + 10)
    sh.glabel(cb_gnd[0], cb_gnd[1] + 10, "GND", 270, "input")
    cb_diag = sh.p("U2", "DIAG")
    sh.wire(*cb_diag, cb_diag[0], cb_diag[1] + 10)
    sh.glabel(cb_diag[0], cb_diag[1] + 10, "DIAG_CB", 270)

    # -- HV Distribution box detail --
    for pin, sig in [("+114V_BATT", "+114V"), ("-114V_BATT", "-114V")]:
        px, py = sh.p("U3", pin)
        sh.wire(px, py, px - 13, py)
        sh.glabel(px - 13, py, sig, 180)

    hvd_r_pins = ["VA_CB+", "VB_CB-", "VD_DCDC+", "VD_DCDC-", "VQ_CHG+", "VQ_CHG-"]
    for pin in hvd_r_pins:
        px, py = sh.p("U3", pin)
        sh.wire(px, py, px + 13, py)
        sh.label(px + 13, py, pin)

    # HV Dist top pins
    for pin in ["VH_HEAT", "VK_CTRL"]:
        px, py = sh.p("U3", pin)
        sh.wire(px, py, px, py - 10)
        sh.label(px, py - 10, pin)

    # -- Annotations --
    sh.text(30, 260, "SAFETY SYSTEMS & HV DETAIL", 1.8)
    sh.text(30, 268, "Collision control C050: K-LINE diagnostic, crash detection", 1.0)
    sh.text(30, 274, "Seatbelt pretensioners: pyrotechnic firing circuit", 1.0)
    sh.text(30, 280, "Contactor box: PTC precharge, 0.5s time delay (IC1)", 1.0)
    sh.text(250, 260, "Contactor Box Internals:", 1.3)
    sh.text(250, 268, "Main precharge: PTC + IC1 timer", 1.0)
    sh.text(250, 274, "LEM LA-205-S: Hall-effect current sensor", 1.0)
    sh.text(250, 280, "D5 diode, R1-R5 resistors, T1 transistor", 1.0)
    sh.text(250, 286, "HV Dist: VA(CB), VD(DC/DC), VQ(Charger)", 1.0)
    sh.text(30, 290, "Wire: 0.5mm2 PNK, 0.75mm2 RED/WHT/VIO", 1.0)

    return sh


# ============================================================================
# ROOT SHEET
# ============================================================================

def build_root():
    """Root sheet with hierarchical sheet blocks."""
    sh = Sheet(
        paper="A1",
        title="Think City EV - Complete Electrical System",
        comment1="Based on wiring diagram PDF Drawing 05125-01-105",
        comment2="All 38 pages - Complete vehicle electrical system",
        comment3="HV: 114V nominal traction battery",
        comment4="All labels in English, wire colors annotated",
    )

    # Sheet definitions: (name, file, description)
    sheets = [
        ("01 Power Distribution",       "think_s01_power_dist.kicad_sch",
         "12V Battery, Fuse Box C01, Ignition Switch"),
        ("02 HV Power",                 "think_s02_hv_power.kicad_sch",
         "114V Battery, Contactor Box, Motor Controller, Motor"),
        ("03 Motor Control",            "think_s03_motor_ctrl.kicad_sch",
         "Motor Controller signals, BMS control, Gear Lock"),
        ("04 Sensors",                  "think_s04_sensors.kicad_sch",
         "Motor Position Sensor, Gear Selector, Throttle Pedal"),
        ("05 Regen & DC/DC",            "think_s05_regen_dcdc.kicad_sch",
         "Regenerative braking, DC/DC Converter, HV Distribution"),
        ("06 BMS & Charger",            "think_s06_bms_charger.kicad_sch",
         "BMS, Charger, Cooling System, Battery Temp Sensors"),
        ("07 Headlights",               "think_s07_headlights.kicad_sch",
         "Headlight Switch, Low/High Beam, Parking, License"),
        ("08 Rear Lights",              "think_s08_rear_lights.kicad_sch",
         "Brake Lights, Reverse, Turn Signal Rear, Fog"),
        ("09 Signals & Horn",           "think_s09_signals_horn.kicad_sch",
         "Horn, Turn Signals, Dome Light, Door Switches"),
        ("10 Wipers & Alarm",           "think_s10_wipers_alarm.kicad_sch",
         "Wiper Motor, Washer Pump, Alarm Unit, Siren"),
        ("11 Diagnostics & Speed",      "think_s11_diag_speed.kicad_sch",
         "OBD-II Diagnostic, K-LINE/L-LINE, Collision Sensor"),
        ("12 Radio & HVAC",             "think_s12_radio_hvac.kicad_sch",
         "Radio, Speakers, Heated Window, Heater, Webasto"),
        ("13 Safety & HV Detail",       "think_s13_safety_hv.kicad_sch",
         "Collision Control, Pretensioners, Contactor Box Internal"),
    ]

    # Layout: 3 columns x 5 rows on A1 paper (841 x 594 mm)
    # A1 usable area approx 800 x 560 mm
    cols = 3
    sw, sh_h = 80, 25      # sheet block size
    margin_x, margin_y = 40, 60
    col_sp = 260
    row_sp = 38

    for i, (sname, sfile, sdesc) in enumerate(sheets):
        col = i % cols
        row = i // cols
        sx = margin_x + col * col_sp
        sy = margin_y + row * row_sp
        sh.add_hier_sheet(sx, sy, sw, sh_h, sname, sfile)
        # Add description text
        sh.text(sx + sw + 3, sy + sh_h / 2, sdesc, 1.0)

    # Title and overview text
    sh.text(40, 30, "THINK CITY EV - COMPLETE ELECTRICAL SYSTEM", 3.0)
    sh.text(40, 40, "Based on: think-300dpi_koblingsskema.pdf (38 pages)", 1.5)
    sh.text(40, 48, "Drawing: 05125-01-105 (LV) / 05125-02-031 (HV Box)", 1.5)

    # System overview annotations
    overview_y = 280
    sh.text(40, overview_y, "SYSTEM OVERVIEW", 2.5)
    sh.text(40, overview_y + 12, "HIGH VOLTAGE SYSTEM (114V nominal)", 1.8)
    sh.text(40, overview_y + 20, "- 114V Traction Battery -> 250A Mega Fuse -> HV Distribution Box", 1.2)
    sh.text(40, overview_y + 27, "- HV Dist -> Contactor Box -> Motor Controller -> 3-phase AC Motor", 1.2)
    sh.text(40, overview_y + 34, "- HV Dist -> DC/DC Converter (114V -> 12V)", 1.2)
    sh.text(40, overview_y + 41, "- HV Dist -> Charger (230V AC -> 114V DC)", 1.2)

    sh.text(40, overview_y + 55, "LOW VOLTAGE SYSTEM (12V)", 1.8)
    sh.text(40, overview_y + 63, "- 12V Battery (E04) -> Fuse Box C01 (33 fuses + 5 maxi)", 1.2)
    sh.text(40, overview_y + 70, "- Ignition Switch: OFF/ACC/DRIVE/START positions", 1.2)
    sh.text(40, overview_y + 77, "- DC/DC Converter charges 12V battery from 114V HV system", 1.2)

    sh.text(40, overview_y + 91, "CONTROL SYSTEMS", 1.8)
    sh.text(40, overview_y + 99, "- Motor Controller (TIM): drives 3-phase AC traction motor", 1.2)
    sh.text(40, overview_y + 106, "- BMS (E02): monitors battery temp, controls charging", 1.2)
    sh.text(40, overview_y + 113, "- Contactor Box: main HV switching with precharge circuit", 1.2)
    sh.text(40, overview_y + 120, "- K-LINE/L-LINE diagnostic bus to OBD-II connector", 1.2)

    sh.text(450, overview_y, "RELAY LIST", 2.0)
    relays = [
        "R1: Wiper Relay (Mini Timer)",
        "R2: Heated Rear Window Relay (Mini)",
        "R3: Flasher Relay (Mini Flasher)",
        "R4: Charge Cooling Relay",
        "R5: DRL (Daytime Running Light) Relay",
        "R6: Cluster Timer Pre-heat Relay",
        "R7: Reverse Light Relay",
        "R8/R9/R10: Gear Lock Relays",
        "R11: Radiator Fan Relay",
        "R12: Blower Motor Relay",
        "R13: Tailgate Release Relay",
        "R14/R15: Recirculation Motor Relays",
        "R16: Combustion Heater (Webasto) Relay",
        "R17: Park/Rear Light Relay",
        "R18: (spare)",
    ]
    for i, r in enumerate(relays):
        sh.text(450, overview_y + 10 + i * 7, r, 1.1)

    sh.text(450, overview_y + 125, "CONNECTOR REFERENCE", 2.0)
    conns = [
        "BT01/BT02: Battery connectors",
        "C01: Fuse box (33 fuses)",
        "C02: Throttle pedal",
        "C09: Diagnostic connector (OBD-II)",
        "C12: Brake light switch",
        "C21-C23: Ignition switch",
        "C25: Headlight switch / Horn",
        "C26: Wiper switch",
        "C30/C31: Door switches (driver/passenger)",
        "C050: Collision control unit",
        "C55/C56: Seatbelt pretensioners",
        "D7: Gear selector",
        "D01/D02/D03: Multi-connectors",
        "E01: Motor Controller (TIM)",
        "E02: BMS",
        "E03: Charger",
        "E04: 12V Battery",
        "E05: Motor position sensor",
        "E07: DC/DC Converter",
        "E10: Washer pump",
        "E11A/E11B: Radiator fans",
        "E14: Brake vacuum pump",
        "E15: Horn",
        "E16: Coolant pump",
        "E19: Wiper motor",
        "E20/E21: Gear lock motor",
    ]
    for i, c in enumerate(conns):
        sh.text(450, overview_y + 135 + i * 6, c, 1.0)

    return sh


# ============================================================================
# MAIN – Generate all files
# ============================================================================

def main():
    print("=" * 70)
    print("Think City EV – Complete Hierarchical KiCad 9 Schematic Generator")
    print("=" * 70)
    print()

    os.makedirs(OUT_DIR, exist_ok=True)

    builders = [
        (1,  "think_s01_power_dist.kicad_sch",   build_s01_power_dist),
        (2,  "think_s02_hv_power.kicad_sch",     build_s02_hv_power),
        (3,  "think_s03_motor_ctrl.kicad_sch",    build_s03_motor_ctrl),
        (4,  "think_s04_sensors.kicad_sch",       build_s04_sensors),
        (5,  "think_s05_regen_dcdc.kicad_sch",    build_s05_regen_dcdc),
        (6,  "think_s06_bms_charger.kicad_sch",   build_s06_bms_charger),
        (7,  "think_s07_headlights.kicad_sch",    build_s07_headlights),
        (8,  "think_s08_rear_lights.kicad_sch",   build_s08_rear_lights),
        (9,  "think_s09_signals_horn.kicad_sch",  build_s09_signals_horn),
        (10, "think_s10_wipers_alarm.kicad_sch",  build_s10_wipers_alarm),
        (11, "think_s11_diag_speed.kicad_sch",    build_s11_diag_speed),
        (12, "think_s12_radio_hvac.kicad_sch",    build_s12_radio_hvac),
        (13, "think_s13_safety_hv.kicad_sch",     build_s13_safety_hv),
    ]

    # -- Pass 1: build all sheets --
    print("Generating sub-sheets...")
    sheets = []
    for snum, fname, builder in builders:
        sheet = builder()
        sheet.sheet_num = snum
        sheets.append((snum, fname, sheet))

    # -- Collect cross-references: net_name → [sheet_nums] --
    net_to_sheets = {}
    for snum, _fname, sheet in sheets:
        for net_name in sheet._glabel_positions:
            net_to_sheets.setdefault(net_name, []).append(snum)

    # -- Pass 2: add cross-ref annotations and save --
    for snum, fname, sheet in sheets:
        sheet.add_crossrefs(net_to_sheets)
        sheet.save(os.path.join(OUT_DIR, fname))

    print()
    print("Generating root sheet...")
    root = build_root()
    root.save(os.path.join(OUT_DIR, "think_city_complete.kicad_sch"))

    # Print cross-reference summary
    multi = {k: v for k, v in net_to_sheets.items() if len(v) > 1}
    print(f"\nCross-sheet nets: {len(multi)} nets shared across sheets")

    print()
    print("=" * 70)
    print(f"All files written to: {OUT_DIR}")
    print(f"Total files: {len(builders) + 1}")
    print()
    print("To use in KiCad 9:")
    print("  1. Open think_city_complete.kicad_sch as the root schematic")
    print("  2. All 13 sub-sheets will be linked via hierarchical sheet blocks")
    print("  3. Global labels auto-connect matching nets across sheets")
    print("=" * 70)


if __name__ == "__main__":
    main()
