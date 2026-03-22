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

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
OUT_DIR = "/home/hw/Projects/Trabbi-schematic/Data/Trabbi Schematic"

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

    # -- UID helper --------------------------------------------------------
    @staticmethod
    def uid():
        return str(uuid.uuid4())

    # -- Pin line helper ---------------------------------------------------
    @staticmethod
    def _pin_line(name, num, ptype, x, y, ang, plen=2.54):
        return (
            f'        (pin {ptype} line (at {x:.3f} {y:.3f} {ang}) (length {plen:.3f})\n'
            f'          (name "{name}" (effects (font (size 1.016 1.016))))\n'
            f'          (number "{num}" (effects (font (size 1.016 1.016))))\n'
            f'        )'
        )

    # -- Symbol definition -------------------------------------------------
    def defsym(self, lib_id, w, h,
               lpins=(), rpins=(), tpins=(), bpins=(),
               body_label="", ref_pfx="U"):
        """Define a schematic symbol and register its pin map."""
        name = lib_id.split(":")[-1]
        hw2, hh = w / 2, h / 2
        pl = 2.54
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
        s.append(f'      )')
        s.append(f'      (symbol "{name}_1_1"')

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
                s.append(self._pin_line(pname, n[0], ptype, px, py, ang, pl))
                pin_map[pname] = str(n[0])
                n[0] += 1

        add_side(lpins, 'L', h)
        add_side(rpins, 'R', h)
        add_side(tpins, 'T', w)
        add_side(bpins, 'B', w)
        s.append(f'      )')
        s.append(f'    )')

        self.lib_syms.extend(s)
        self.sym_defs[lib_id] = pin_map
        return lib_id, pin_map

    # -- Place component instance ------------------------------------------
    def place(self, lib_id, ref, val, x, y, ang=0):
        pm = self.sym_defs.get(lib_id, {})
        s = []
        s.append(f'  (symbol (lib_id "{lib_id}") (at {x:.3f} {y:.3f} {ang})')
        s.append(f'    (unit 1) (in_bom yes) (on_board yes) (dnp no)')
        s.append(f'    (uuid "{self.uid()}")')
        for prop, pval, dx, dy in [
            ("Reference", ref,  0, -8),
            ("Value",     val,  0,  8),
            ("Footprint", "",   0,  0),
            ("Datasheet", "",   0,  0),
        ]:
            hide = " hide" if prop in ("Footprint", "Datasheet") else ""
            s.append(f'    (property "{prop}" "{pval}" (at {x + dx:.3f} {y + dy:.3f} 0)')
            s.append(f'      (effects (font (size 1.27 1.27)){hide})')
            s.append(f'    )')
        for pname, pnum in pm.items():
            s.append(f'    (pin "{pnum}" (uuid "{self.uid()}"))')
        s.append(f'  )')
        self.elems.extend(s)

    # -- Wire --------------------------------------------------------------
    def wire(self, x1, y1, x2, y2):
        self.elems.append(
            f'  (wire (pts (xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f}))\n'
            f'    (stroke (width 0) (type default))\n'
            f'    (uuid "{self.uid()}")\n'
            f'  )'
        )

    # -- Net label (local to sheet) ----------------------------------------
    def label(self, x, y, name, ang=0):
        self.elems.append(
            f'  (label "{name}" (at {x:.3f} {y:.3f} {ang})\n'
            f'    (effects (font (size 1.27 1.27)))\n'
            f'    (uuid "{self.uid()}")\n'
            f'  )'
        )

    # -- Global label (cross-sheet connection) -----------------------------
    def glabel(self, x, y, name, ang=0, shape="bidirectional"):
        u = self.uid()
        self.elems.append(
            f'  (global_label "{name}" (shape {shape}) (at {x:.3f} {y:.3f} {ang})\n'
            f'    (effects (font (size 1.27 1.27)))\n'
            f'    (uuid "{u}")\n'
            f'    (property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {x:.3f} {y:.3f} 0)\n'
            f'      (effects (font (size 1.27 1.27)) hide)\n'
            f'    )\n'
            f'  )'
        )

    # -- Power port (standard KiCad power symbols) -------------------------
    def power_flag(self, x, y, name, ang=0):
        """Add a global label styled as a power symbol."""
        shape = "input" if "GND" in name else "output"
        self.glabel(x, y, name, ang, shape)

    # -- Junction ----------------------------------------------------------
    def junction(self, x, y):
        self.elems.append(
            f'  (junction (at {x:.3f} {y:.3f}) (diameter 0) (color 0 0 0 0)'
            f' (uuid "{self.uid()}"))'
        )

    # -- No-connect --------------------------------------------------------
    def no_connect(self, x, y):
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

def def_relay_spdt(sh):
    return sh.defsym("Think:RELAY_SPDT", 20, 30,
        lpins=["86_COIL+", "85_COIL-"],
        rpins=["30_COM", ("87_NO", "output"), ("87a_NC", "output")],
        body_label="RELAY", ref_pfx="K")

def def_relay_spst(sh):
    return sh.defsym("Think:RELAY_SPST", 18, 16,
        lpins=["86_COIL+", "85_COIL-"],
        rpins=["30_COM", ("87_NO", "output")],
        body_label="RELAY", ref_pfx="K")

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
        sh.wire(x - 9, y, x - 16, y)
        sh.wire(x + 9, y, x + 16, y)
        sh.glabel(x - 16, y, lbl + "_IN", 180)
        sh.glabel(x + 16, y, lbl, 0)


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
    sh.wire(BT_X, BT_Y - 12, BT_X, BT_Y - 25)
    sh.wire(BT_X, BT_Y - 25, 140, BT_Y - 25)
    sh.wire(140, BT_Y - 25, 140, 75)
    sh.wire(140, 75, FB_X - 22, 75)
    sh.text(BT_X + 5, BT_Y - 28, "Wire: 6mm2 RED", 1.0)
    sh.glabel(BT_X, BT_Y - 25, "+12V_ALWAYS", 180, "output")

    # Battery GND
    sh.wire(BT_X, BT_Y + 12, BT_X, BT_Y + 25)
    sh.glabel(BT_X, BT_Y + 25, "GND", 270, "input")
    sh.text(BT_X + 5, BT_Y + 20, "Wire: 6mm2 BLK", 1.0)

    # Ignition switch → fuse box power inputs
    sh.wire(IGN_X + 14, IGN_Y - 10, FB_X - 22, IGN_Y - 10)
    sh.label(IGN_X + 18, IGN_Y - 10, "+12V_ACC_RUN (pos 15/2)")
    sh.text(80, IGN_Y - 14, "Wire: 6mm2 YEL", 1.0)

    sh.wire(IGN_X + 14, IGN_Y - 2, FB_X - 22, IGN_Y - 2)
    sh.label(IGN_X + 18, IGN_Y - 2, "+12V_IGN (pos 15)")

    sh.wire(IGN_X + 14, IGN_Y + 6, FB_X - 22, IGN_Y + 6)
    sh.label(IGN_X + 18, IGN_Y + 6, "+12V_RUN_START (pos 15/1)")

    sh.wire(IGN_X + 14, IGN_Y + 14, FB_X - 22, IGN_Y + 14)
    sh.label(IGN_X + 18, IGN_Y + 14, "+12V_START (pos 50)")

    # Ignition BAT_IN from battery
    sh.wire(IGN_X - 14, IGN_Y, IGN_X - 30, IGN_Y)
    sh.glabel(IGN_X - 30, IGN_Y, "+12V_ALWAYS", 180)

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

    n_fuses = len(fuse_rpins)
    body_h = 180
    fuse_sp = body_h / (n_fuses + 1)
    for i, (fpn, glbl) in enumerate(fuse_globals):
        fy = FB_Y - body_h / 2 + fuse_sp * (i + 1)
        sh.wire(FB_X + 22, fy, FB_X + 40, fy)
        sh.glabel(FB_X + 40, fy, glbl, 0, "output")

    # GND bus at bottom of fuse box
    sh.wire(FB_X, FB_Y + 92, FB_X, FB_Y + 105)
    sh.glabel(FB_X, FB_Y + 105, "GND", 270, "input")

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
    sh.wire(BT_X, BT_Y - 16, BT_X, FH_Y + 4)
    sh.text(BT_X + 3, BT_Y - 20, "Wire: HV Orange (35mm2)", 0.9)

    # Fuse → Contactor Box VA
    sh.wire(FH_X + 9, FH_Y, 100, FH_Y)
    sh.wire(100, FH_Y, 100, CB_Y - 20)
    sh.wire(100, CB_Y - 20, CB_X - 22, CB_Y - 20)
    sh.label(FH_X + 12, FH_Y, "+114V_FUSED")

    # Battery- → Contactor Box VB
    sh.wire(BT_X, BT_Y + 16, BT_X, BT_Y + 35)
    sh.wire(BT_X, BT_Y + 35, 100, BT_Y + 35)
    sh.wire(100, BT_Y + 35, 100, CB_Y - 10)
    sh.wire(100, CB_Y - 10, CB_X - 22, CB_Y - 10)
    sh.label(BT_X + 5, BT_Y + 35, "-114V")

    # Contactor Box → Motor Controller HV
    sh.wire(CB_X + 22, CB_Y - 20, MC_X - 27, MC_Y - 30)
    sh.wire(CB_X + 22, CB_Y - 10, MC_X - 27, MC_Y - 10)
    sh.label(CB_X + 25, CB_Y - 20, "+114V_TO_MC")
    sh.label(CB_X + 25, CB_Y - 10, "-114V_TO_MC")

    # Motor Controller → Motor L1/L2/L3
    for i, lbl in enumerate(["L1", "L2", "L3"]):
        my_y = MC_Y - 16 + i * 11
        mm_y = MOT_Y - 12 + i * 8
        sh.wire(MC_X + 27, my_y, MC_X + 40, my_y)
        sh.wire(MC_X + 40, my_y, MOT_X - 16, mm_y)
        sh.label(MC_X + 30, my_y, lbl)

    # Motor PE
    sh.wire(MOT_X - 16, MOT_Y + 14, MOT_X - 30, MOT_Y + 14)
    sh.glabel(MOT_X - 30, MOT_Y + 14, "CHASSIS_GND", 180, "input")

    # -- Global labels for inter-sheet connections --
    sh.glabel(CB_X, CB_Y + 32, "GND", 270, "input")
    sh.wire(CB_X, CB_Y + 30, CB_X, CB_Y + 32)

    # Contactor Box control signals (global for cross-sheet)
    ctrl_pins = ["CB_RUN", "BMS_CMD", "CHG_START", "PREHEAT", "CHARGE"]
    for i, cname in enumerate(ctrl_pins):
        px = CB_X - 16 + i * 8
        sh.wire(px, CB_Y - 32, px, CB_Y - 45)
        sh.glabel(px, CB_Y - 45, cname, 90)

    # Motor Controller signals (global)
    mc_top_sigs = ["DRIVE", "START", "DRIVE_RDY", "FAULT", "POWER",
                   "RED_PWR", "BRAKE_SW", "REVERSE", "GEAR_LOCK", "RAD_FAN_CMD"]
    for i, sig in enumerate(mc_top_sigs):
        px = MC_X - 22 + i * 5
        sh.wire(px, MC_Y - 42, px, MC_Y - 55)
        sh.glabel(px, MC_Y - 55, sig, 90)

    # Motor Controller K_LINE / L_LINE
    sh.wire(MC_X - 5, MC_Y + 42, MC_X - 5, MC_Y + 55)
    sh.glabel(MC_X - 5, MC_Y + 55, "K_LINE", 270)
    sh.wire(MC_X + 5, MC_Y + 42, MC_X + 5, MC_Y + 55)
    sh.glabel(MC_X + 5, MC_Y + 55, "L_LINE", 270)

    # +114V global for DC/DC and charger
    sh.glabel(CB_X + 22, CB_Y + 5, "+114V", 0, "output")
    sh.glabel(CB_X + 22, CB_Y + 15, "+12V_FROM_CB", 0, "output")

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
    body_h = 70
    sp = body_h / (len(mc_l_sigs) + 1)
    for i, sig in enumerate(mc_l_sigs):
        py = MC_Y - body_h / 2 + sp * (i + 1)
        sh.wire(MC_X - 27, py, MC_X - 45, py)
        sh.glabel(MC_X - 45, py, sig, 180)

    mc_r_sigs = ["GEAR_LOCK", "RAD_FAN_CMD", "K_LINE", "L_LINE",
                 "+12V_BAT", "GND", "POWER"]
    sp_r = body_h / (len(mc_r_sigs) + 1)
    for i, sig in enumerate(mc_r_sigs):
        py = MC_Y - body_h / 2 + sp_r * (i + 1)
        sh.wire(MC_X + 27, py, MC_X + 45, py)
        if sig in ("GND", "+12V_BAT"):
            sh.glabel(MC_X + 45, py, sig, 0, "input" if sig == "GND" else "output")
        else:
            sh.glabel(MC_X + 45, py, sig, 0)

    # BMS signals
    bms_r_sigs = ["BMS_CMD", "CHG_STATUS_OK", "K_LINE", "L_LINE"]
    sp_b = 40 / (len(bms_r_sigs) + 1)
    for i, sig in enumerate(bms_r_sigs):
        py = BMS_Y - 20 + sp_b * (i + 1)
        sh.wire(BMS_X + 17, py, BMS_X + 35, py)
        sh.glabel(BMS_X + 35, py, sig, 0)

    # Brake switch connection
    sh.wire(BS_X - 10, BS_Y, BS_X - 25, BS_Y)
    sh.glabel(BS_X - 25, BS_Y, "BRAKE_SW", 180)
    sh.wire(BS_X + 10, BS_Y, BS_X + 25, BS_Y)
    sh.glabel(BS_X + 25, BS_Y, "BRAKE_LIGHT_FEED", 0)

    # Radiator fan relay
    sh.glabel(280 + 11, 150 - 6, "RAD_FAN_CMD", 0)
    sh.wire(280 + 11, 150 - 6, 280 + 20, 150 - 6)

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
    pos_sigs = ["POS_SENSE_1", "POS_SENSE_2", "POS_SENSE_3",
                "POS_SENSE_4", "POS_SENSE_5", "POS_SENSE_6"]
    sp = 50 / (6 + 1)
    for i, sig in enumerate(pos_sigs):
        py = PS_Y - 25 + sp * (i + 1)
        sh.wire(PS_X - 17, py, PS_X - 35, py)
        sh.glabel(PS_X - 35, py, sig, 180)

    # Right side
    r_sigs = ["MOTOR_TEMP_POS", "MOTOR_TEMP_NEG", "+5V_SENSOR", "GND", "SHIELD_GND"]
    sp_r = 50 / (5 + 1)
    for i, sig in enumerate(r_sigs):
        py = PS_Y - 25 + sp_r * (i + 1)
        sh.wire(PS_X + 17, py, PS_X + 35, py)
        shape = "input" if "GND" in sig else "bidirectional"
        sh.glabel(PS_X + 35, py, sig, 0, shape)

    # -- Gear Selector connections --
    gs_sigs = ["PARK_SW", "FREE_SW", "DRIVE", "REVERSE"]
    sp_gs = 36 / (4 + 1)
    for i, sig in enumerate(gs_sigs):
        py = GS_Y - 18 + sp_gs * (i + 1)
        sh.wire(GS_X + 13, py, GS_X + 30, py)
        sh.glabel(GS_X + 30, py, sig, 0)

    sh.wire(GS_X - 13, GS_Y, GS_X - 25, GS_Y)
    sh.glabel(GS_X - 25, GS_Y, "GND", 180, "input")

    # -- Throttle Pedal connections --
    sh.wire(TP_X - 14, TP_Y - 8, TP_X - 30, TP_Y - 8)
    sh.glabel(TP_X - 30, TP_Y - 8, "+5V_RUN", 180, "output")
    sh.wire(TP_X - 14, TP_Y + 8, TP_X - 30, TP_Y + 8)
    sh.glabel(TP_X - 30, TP_Y + 8, "ANALOG_GND", 180, "input")
    sh.wire(TP_X + 14, TP_Y - 8, TP_X + 30, TP_Y - 8)
    sh.glabel(TP_X + 30, TP_Y - 8, "THROTTLE_POS", 0)
    sh.wire(TP_X + 14, TP_Y + 8, TP_X + 30, TP_Y + 8)
    sh.glabel(TP_X + 30, TP_Y + 8, "THROTTLE_PULL", 0)
    sh.text(TP_X + 35, TP_Y + 5, "Wire: 0.75mm2 YEL", 0.9)

    # DC/DC reference
    sh.wire(300 - 10, 160, 300 - 25, 160)
    sh.glabel(300 - 25, 160, "DC_HI_PWR", 180)
    sh.wire(300 + 10, 160, 300 + 25, 160)
    sh.glabel(300 + 25, 160, "POWER", 0)

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
    # HV Distribution → 100A fuse → DC/DC +114V
    sh.wire(HVDB_X + 16, HVDB_Y - 8, 121, 85)
    sh.wire(139, 85, DCDC_X - 17, DCDC_Y - 9)
    sh.label(135, 82, "+114V_DCDC")

    # HV Distribution → DC/DC -114V
    sh.wire(HVDB_X + 16, HVDB_Y - 1, 120, DCDC_Y)
    sh.wire(120, DCDC_Y, DCDC_X - 17, DCDC_Y)
    sh.label(125, DCDC_Y - 3, "-114V_DCDC")

    # DC/DC +12V out
    sh.wire(DCDC_X + 17, DCDC_Y - 9, DCDC_X + 35, DCDC_Y - 9)
    sh.glabel(DCDC_X + 35, DCDC_Y - 9, "+12V_ALWAYS", 0, "output")
    sh.text(DCDC_X + 37, DCDC_Y - 13, "To 12V battery -> Sheet 01", 0.9)

    # DC/DC -12V out (GND)
    sh.wire(DCDC_X + 17, DCDC_Y, DCDC_X + 35, DCDC_Y)
    sh.glabel(DCDC_X + 35, DCDC_Y, "GND", 0, "input")

    # DC/DC HI_PWR_IN (from motor controller)
    sh.wire(DCDC_X, DCDC_Y - 20, DCDC_X, DCDC_Y - 35)
    sh.glabel(DCDC_X, DCDC_Y - 35, "DC_HI_PWR", 90)
    sh.text(DCDC_X + 3, DCDC_Y - 33, "From Motor Ctrl -> Sheet 02", 0.9)

    # DC/DC LO_PWR_OUT (to BMS)
    sh.wire(DCDC_X - 5, DCDC_Y + 20, DCDC_X - 5, DCDC_Y + 35)
    sh.glabel(DCDC_X - 5, DCDC_Y + 35, "DC_LO_PWR", 270)
    sh.text(DCDC_X - 2, DCDC_Y + 33, "To BMS -> Sheet 06", 0.9)

    # DC/DC FAULT
    sh.wire(DCDC_X + 5, DCDC_Y + 20, DCDC_X + 5, DCDC_Y + 35)
    sh.glabel(DCDC_X + 5, DCDC_Y + 35, "DCDC_FAULT", 270)

    # HV Distribution input from battery
    sh.wire(HVDB_X - 16, HVDB_Y - 8, HVDB_X - 30, HVDB_Y - 8)
    sh.glabel(HVDB_X - 30, HVDB_Y - 8, "+114V", 180)
    sh.wire(HVDB_X - 16, HVDB_Y + 1, HVDB_X - 30, HVDB_Y + 1)
    sh.glabel(HVDB_X - 30, HVDB_Y + 1, "-114V", 180)

    # HV Distribution to Contactor Box
    sh.wire(HVDB_X + 16, HVDB_Y - 15, HVDB_X + 35, HVDB_Y - 15)
    sh.glabel(HVDB_X + 35, HVDB_Y - 15, "+114V_CB", 0)
    sh.wire(HVDB_X + 16, HVDB_Y - 8, HVDB_X + 35, HVDB_Y - 22)

    # HV Distribution to Charger
    sh.wire(HVDB_X + 16, HVDB_Y + 8, HVDB_X + 35, HVDB_Y + 8)
    sh.glabel(HVDB_X + 35, HVDB_Y + 8, "+114V_CHARGER", 0)
    sh.wire(HVDB_X + 16, HVDB_Y + 15, HVDB_X + 35, HVDB_Y + 15)
    sh.glabel(HVDB_X + 35, HVDB_Y + 15, "-114V_CHARGER", 0)
    sh.text(HVDB_X + 37, HVDB_Y + 12, "To Charger -> Sheet 06", 0.9)

    # Control lamp
    sh.wire(300 - 9, 200, 300 - 20, 200)
    sh.glabel(300 - 20, 200, "REGEN_LAMP", 180)
    sh.wire(300 + 9, 200, 300 + 20, 200)
    sh.glabel(300 + 20, 200, "GND", 0, "input")

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
    bms_l = ["BAT_12V", "GND", "DC_LO_PWR", "CHG_START_IN"]
    sp = 54 / (4 + 1)
    for i, sig in enumerate(bms_l):
        py = BMS_Y - 27 + sp * (i + 1)
        sh.wire(BMS_X - 22, py, BMS_X - 38, py)
        shape = "input" if sig == "GND" else "bidirectional"
        if sig == "BAT_12V":
            sh.glabel(BMS_X - 38, py, "+12V_F28_DRIVE", 180)
        elif sig == "GND":
            sh.glabel(BMS_X - 38, py, "GND", 180, "input")
        else:
            sh.glabel(BMS_X - 38, py, sig, 180)

    # BMS right side
    bms_r = ["CHG_STATUS_OK", "CHG_START_OUT", "BMS_CMD", "K_LINE", "L_LINE"]
    sp_r = 54 / (5 + 1)
    for i, sig in enumerate(bms_r):
        py = BMS_Y - 27 + sp_r * (i + 1)
        sh.wire(BMS_X + 22, py, BMS_X + 38, py)
        sh.glabel(BMS_X + 38, py, sig, 0)

    # BMS top side - current sense
    bms_t = ["CURR_S_12V", "CURR_S_GND", "CURR_SENSE", "BATT_COOLING"]
    sp_t = 40 / (4 + 1)
    for i, sig in enumerate(bms_t):
        px = BMS_X - 20 + sp_t * (i + 1) * 2
        sh.wire(px, BMS_Y - 29, px, BMS_Y - 42)
        sh.glabel(px, BMS_Y - 42, sig, 90)

    # BMS bottom - temp sensors
    bms_b = ["TEMP1", "TEMP2", "TEMP3", "TEMP4"]
    sp_b = 40 / (4 + 1)
    for i, sig in enumerate(bms_b):
        px = BMS_X - 20 + sp_b * (i + 1) * 2
        sh.wire(px, BMS_Y + 29, px, BMS_Y + 40)
        sh.label(px, BMS_Y + 40, sig)
        # Connect to temp sensors
        sh.wire(px, BMS_Y + 40, 60 + i * 25, 174)

    # Charger wiring
    # Charger left (AC)
    chg_l = ["L1_AC", "L2_AC", "GND_AC"]
    sp_cl = 40 / (3 + 1)
    for i, sig in enumerate(chg_l):
        py = CHG_Y - 20 + sp_cl * (i + 1)
        sh.wire(CHG_X - 17, py, CHG_X - 30, py)
        sh.label(CHG_X - 30, py, sig)

    # Charger right (HV DC out)
    sh.wire(CHG_X + 17, CHG_Y - 8, CHG_X + 32, CHG_Y - 8)
    sh.glabel(CHG_X + 32, CHG_Y - 8, "+114V_CHARGER", 0)
    sh.wire(CHG_X + 17, CHG_Y + 2, CHG_X + 32, CHG_Y + 2)
    sh.glabel(CHG_X + 32, CHG_Y + 2, "-114V_CHARGER", 0)

    # Charger top (control)
    sh.wire(CHG_X - 5, CHG_Y - 22, CHG_X - 5, CHG_Y - 35)
    sh.glabel(CHG_X - 5, CHG_Y - 35, "CHG_START", 90)
    sh.wire(CHG_X + 5, CHG_Y - 22, CHG_X + 5, CHG_Y - 35)
    sh.glabel(CHG_X + 5, CHG_Y - 35, "CHG_STATUS_OK", 90)

    # Charger bottom (diagnostic)
    sh.wire(CHG_X - 5, CHG_Y + 22, CHG_X - 5, CHG_Y + 35)
    sh.glabel(CHG_X - 5, CHG_Y + 35, "K_LINE", 270)
    sh.wire(CHG_X + 5, CHG_Y + 22, CHG_X + 5, CHG_Y + 35)
    sh.glabel(CHG_X + 5, CHG_Y + 35, "L_LINE", 270)

    # 230V relay → AC connector
    sh.wire(300 + 11, 200 - 4, 380 - 11, 200 - 4)
    sh.label(330, 197, "230V_L1")

    # Cooling relay
    sh.wire(50 - 11, 240 - 4, 50 - 25, 240 - 4)
    sh.glabel(50 - 25, 236, "BATT_COOLING", 180)

    # Radiator fan power
    sh.wire(100 - 10, 230, 100 - 22, 230)
    sh.glabel(100 - 22, 230, "+12V_F6_RADFAN", 180)
    sh.wire(100 + 10, 230, 100 + 18, 230)
    sh.glabel(100 + 18, 230, "GND", 0, "input")

    sh.wire(100 - 10, 255, 100 - 22, 255)
    sh.glabel(100 - 22, 255, "+12V_F6_RADFAN", 180)
    sh.wire(100 + 10, 255, 100 + 18, 255)
    sh.glabel(100 + 18, 255, "GND", 0, "input")

    # Coolant pump power
    sh.wire(200 - 10, 240, 200 - 22, 240)
    sh.glabel(200 - 22, 240, "+12V_F10_WPUMP_CHG", 180)
    sh.wire(200 + 10, 240, 200 + 18, 240)
    sh.glabel(200 + 18, 240, "GND", 0, "input")

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
    sh.wire(HSW_X - 15, HSW_Y, HSW_X - 30, HSW_Y)
    sh.glabel(HSW_X - 30, HSW_Y, "+12V_F2_LIGHTS", 180)
    sh.text(HSW_X - 28, HSW_Y - 4, "From F2 (40A)", 0.9)

    # Switch → DRL relay
    sh.wire(HSW_X + 15, HSW_Y - 10, 151, 50 - 4)
    sh.label(90, HSW_Y - 12, "PARK_OUT")

    # Switch → Park light relay
    sh.wire(HSW_X + 15, HSW_Y - 3, 151, 100 - 4)

    # Switch → Low beam
    hw_sp = 36 / 5
    sh.wire(HSW_X + 15, HSW_Y + hw_sp, 200, HSW_Y + hw_sp)
    sh.label(100, HSW_Y + hw_sp - 3, "LOW_BEAM_OUT")

    # Switch → High beam
    sh.wire(HSW_X + 15, HSW_Y + 2 * hw_sp, 200, HSW_Y + 2 * hw_sp)
    sh.label(100, HSW_Y + 2 * hw_sp - 3, "HIGH_BEAM_OUT")

    # Relay outputs to parking lights
    sh.wire(160 + 11, 50 - 4, 255, 40)
    sh.wire(160 + 11, 50, 255, 60)

    # Relay outputs to park/rear lights
    sh.wire(160 + 11, 100 - 4, 200, 96)

    # Low beam power routing
    sh.wire(200, HSW_Y + hw_sp, 200, 100)
    sh.wire(200, 100, 255, 100)
    sh.wire(200, 100, 200, 120)
    sh.wire(200, 120, 255, 120)
    sh.junction(200, 100)

    # High beam
    sh.wire(200, HSW_Y + 2 * hw_sp, 200, 160)
    sh.wire(200, 160, 255, 160)
    sh.wire(200, 160, 200, 180)
    sh.wire(200, 180, 255, 180)
    sh.junction(200, 160)

    # All bulb grounds
    for y in [40, 60, 100, 120, 160, 180, 210, 230]:
        sh.wire(265, y, 280, y)
        sh.glabel(280, y, "GND", 0, "input")

    # License plate power
    sh.wire(255, 210, 230, 210)
    sh.glabel(230, 210, "+12V_F23_LICENSE", 180)
    sh.wire(255, 230, 230, 230)
    sh.glabel(230, 230, "+12V_F23_LICENSE", 180)

    # Fuse power globals
    sh.glabel(255, 40, "+12V_F16_PARK_FRT", 180)
    sh.glabel(255, 100, "+12V_F27_LOBEAML", 180)
    sh.glabel(255, 120, "+12V_F26_LOBEAMR", 180)
    sh.glabel(255, 160, "+12V_F25_HIBEAMR", 180)

    # Collision lamp
    sh.wire(160 - 8, 230, 160 - 20, 230)
    sh.glabel(160 - 20, 230, "+12V_F17_COLL_ALM", 180)
    sh.wire(160 + 8, 230, 160 + 20, 230)
    sh.glabel(160 + 20, 230, "GND", 0, "input")

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
    sh.wire(80 - 11, 60 - 4, 80 - 25, 56)
    sh.glabel(80 - 25, 56, "+12V_F15_HTDW_REV", 180)
    sh.wire(80 - 11, 60 + 4, 80 - 25, 64)
    sh.glabel(80 - 25, 64, "REVERSE", 180)
    sh.text(80 - 23, 52, "From F15 (10A)", 0.9)

    # Reverse relay → reverse lights
    sh.wire(80 + 11, 60 - 4, 215, 40)
    sh.wire(80 + 11, 60, 200, 60)
    sh.wire(200, 60, 215, 60)

    # Brake light switch input
    sh.wire(80 - 11, 120, 80 - 25, 120)
    sh.glabel(80 - 25, 120, "+12V_F12_BRAKE", 180)
    sh.text(80 - 23, 116, "From F12 (10A)", 0.9)

    # Brake switch → brake lights
    sh.wire(80 + 11, 120, 150, 120)
    sh.wire(150, 120, 150, 100)
    sh.wire(150, 100, 215, 100)
    sh.wire(150, 120, 215, 120)
    sh.wire(150, 120, 150, 145)
    sh.wire(150, 145, 215, 145)
    sh.junction(150, 120)

    # Brake switch also feeds secondary fuse F20
    sh.glabel(80 - 25, 130, "+12V_F20_BRAKE2", 180)
    sh.text(80 - 23, 133, "Alt feed from F20 (15A)", 0.9)

    # All bulb grounds
    for y in [40, 60, 100, 120, 145, 175, 195, 225]:
        sh.wire(225, y, 240, y)
        sh.glabel(240, y, "GND", 0, "input")

    # Turn signal feeds
    sh.wire(215, 175, 180, 175)
    sh.glabel(180, 175, "TURN_SIG_LH_REAR", 180)
    sh.wire(215, 195, 180, 195)
    sh.glabel(180, 195, "TURN_SIG_RH_REAR", 180)

    # Rear fog
    sh.wire(215, 225, 180, 225)
    sh.glabel(180, 225, "+12V_F21_FOGR", 180)
    sh.text(182, 221, "From F21 (5A)", 0.9)

    # Control lamp
    sh.wire(350 - 7, 120, 350 - 18, 120)
    sh.glabel(350 - 18, 120, "BRAKE_LIGHT_FEED", 180)
    sh.wire(350 + 7, 120, 350 + 18, 120)
    sh.glabel(350 + 18, 120, "GND", 0, "input")

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
    sh.wire(80 - 10, 40, 80 - 25, 40)
    sh.glabel(80 - 25, 40, "+12V_F9_HORN_DOME", 180)
    sh.wire(80 + 10, 40, 80 + 25, 40)
    sh.glabel(80 + 25, 40, "GND", 0, "input")

    # Horn contact
    sh.wire(80 - 8, 70, 80 - 25, 70)
    sh.glabel(80 - 25, 70, "+12V_F9_HORN_DOME", 180)
    sh.wire(80 + 8, 70, 80 + 25, 70)
    sh.label(80 + 25, 70, "HORN_ACTIVE")

    # Flasher relay input
    sh.wire(180 - 11, 40 - 4, 180 - 25, 36)
    sh.glabel(180 - 25, 36, "+12V_F24_TURNSIG", 180)
    sh.text(180 - 23, 32, "From F24 (20A)", 0.9)
    sh.wire(180 - 11, 40 + 4, 180 - 25, 44)
    sh.glabel(180 - 25, 44, "GND", 180, "input")

    # Flasher relay → turn signal switch
    sh.wire(180 + 11, 36, 200, 36)
    sh.wire(200, 36, 200, 100)
    sh.wire(200, 100, 180 - 12, 110)

    # Turn signal switch → left bulbs
    sh.wire(180 + 12, 110 - 4, 250, 106)
    sh.wire(250, 106, 250, 80)
    sh.wire(250, 80, 295, 80)
    sh.wire(250, 106, 250, 125)
    sh.wire(250, 125, 295, 125)
    sh.wire(250, 125, 250, 170)
    sh.wire(250, 170, 295, 170)
    sh.junction(250, 106)
    sh.junction(250, 125)

    # Turn signal switch → right bulbs
    sh.wire(180 + 12, 110 + 4, 270, 114)
    sh.wire(270, 114, 270, 100)
    sh.wire(270, 100, 295, 100)
    sh.wire(270, 114, 270, 145)
    sh.wire(270, 145, 295, 145)
    sh.wire(270, 145, 270, 190)
    sh.wire(270, 190, 295, 190)
    sh.junction(270, 114)
    sh.junction(270, 145)

    # Hazard switch
    sh.wire(180, 110 - 14, 180, 110 - 25)
    sh.glabel(180, 110 - 25, "+12V_F24_TURNSIG", 90)

    # All bulb grounds
    for y in [80, 100, 125, 145, 170, 190]:
        sh.wire(305, y, 320, y)
        sh.glabel(320, y, "GND", 0, "input")

    # Global labels for turn signal rear (cross-sheet with S08)
    sh.glabel(295, 170, "TURN_SIG_LH_REAR", 180)
    sh.glabel(295, 190, "TURN_SIG_RH_REAR", 180)

    # Dome light
    sh.wire(80 - 9, 170, 80 - 25, 170)
    sh.glabel(80 - 25, 170, "+12V_F9_HORN_DOME", 180)
    sh.wire(80 + 9, 170, 80 + 25, 170)
    sh.label(80 + 25, 170, "DOME_SW")

    # Door switches → dome light control
    sh.wire(80 - 8, 200, 80 - 25, 200)
    sh.glabel(80 - 25, 200, "DOOR_SW_DRIVER", 180)
    sh.wire(80 + 8, 200, 80 + 25, 200)
    sh.glabel(80 + 25, 200, "DOME_SW", 0)

    sh.wire(80 - 8, 220, 80 - 25, 220)
    sh.glabel(80 - 25, 220, "DOOR_SW_PASS", 180)
    sh.wire(80 + 8, 220, 80 + 25, 220)
    sh.glabel(80 + 25, 220, "DOME_SW", 0)

    # Tailgate switch
    sh.wire(80 - 9, 245, 80 - 25, 245)
    sh.glabel(80 - 25, 245, "TAILGATE_SW", 180)

    # Power outlet
    sh.wire(300 - 9, 230, 300 - 25, 230)
    sh.glabel(300 - 25, 230, "+12V_F8_OUTLET", 180)
    sh.wire(300 + 9, 230, 300 + 25, 230)
    sh.glabel(300 + 25, 230, "GND", 0, "input")
    sh.text(300 - 23, 226, "From F8 (25A)", 0.9)

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
    sh.wire(WSW_X - 14, WSW_Y, WSW_X - 30, WSW_Y)
    sh.glabel(WSW_X - 30, WSW_Y, "+12V_F14_WIPER", 180)
    sh.text(WSW_X - 28, WSW_Y - 4, "From F14 (25A)", 0.9)

    # Wiper switch → relay
    sp_w = 30 / 6
    sh.wire(WSW_X + 14, WSW_Y - sp_w, 151, 50 - 4)

    # Wiper relay → motor
    sh.wire(160 + 11, 50 - 4, WM_X - 12, WM_Y - 5)
    sh.wire(160 + 11, 50, WM_X - 12, WM_Y)

    # Wiper motor fast speed
    sh.wire(WSW_X + 14, WSW_Y + 2 * sp_w, 200, WSW_Y + 2 * sp_w)
    sh.wire(200, WSW_Y + 2 * sp_w, WM_X - 12, WM_Y + 5)

    # Wiper motor GND
    sh.wire(WM_X + 12, WM_Y + 5, WM_X + 25, WM_Y + 5)
    sh.glabel(WM_X + 25, WM_Y + 5, "GND", 0, "input")
    sh.wire(WM_X + 12, WM_Y - 5, WM_X + 25, WM_Y - 5)
    sh.label(WM_X + 25, WM_Y - 5, "WIPER_COM")

    # Washer pump
    sh.wire(260 - 9, 110, 260 - 25, 110)
    sh.glabel(260 - 25, 110, "+12V_F14_WIPER", 180)
    sh.wire(260 + 9, 110, 260 + 25, 110)
    sh.glabel(260 + 25, 110, "GND", 0, "input")

    # Alarm unit connections
    alm_l = ["DOOR_DR", "DOOR_PS", "TAILGATE", "+12V_BAT"]
    sp_a = 40 / (4 + 1)
    for i, sig in enumerate(alm_l):
        py = ALM_Y - 20 + sp_a * (i + 1)
        sh.wire(ALM_X - 17, py, ALM_X - 30, py)
        if sig == "+12V_BAT":
            sh.glabel(ALM_X - 30, py, "+12V_F17_COLL_ALM", 180)
        else:
            sh.glabel(ALM_X - 30, py, sig, 180)

    alm_r = ["SIREN_OUT", "TURN_SIG_ALARM", "IGN_SENSE", "DOOR_LOCK", "DOOR_UNLOCK"]
    sp_ar = 40 / (5 + 1)
    for i, sig in enumerate(alm_r):
        py = ALM_Y - 20 + sp_ar * (i + 1)
        sh.wire(ALM_X + 17, py, ALM_X + 30, py)
        sh.glabel(ALM_X + 30, py, sig, 0)

    sh.wire(ALM_X, ALM_Y + 22, ALM_X, ALM_Y + 32)
    sh.glabel(ALM_X, ALM_Y + 32, "GND", 270, "input")

    # Siren
    sh.wire(260 - 9, 210, 260 - 22, 210)
    sh.glabel(260 - 22, 210, "SIREN_OUT", 180)
    sh.wire(260 + 9, 210, 260 + 22, 210)
    sh.glabel(260 + 22, 210, "GND", 0, "input")

    # Tailgate release relay
    sh.wire(260 - 11, 170 - 4, 260 - 25, 166)
    sh.glabel(260 - 25, 166, "+12V_F9_HORN_DOME", 180)
    sh.text(260 - 23, 162, "From F9 (15A)", 0.9)
    sh.wire(260 + 11, 170 - 4, 260 + 25, 166)
    sh.glabel(260 + 25, 166, "TAILGATE_RELEASE", 0)

    # Door switch globals
    sh.glabel(ALM_X - 30, ALM_Y - 12, "DOOR_SW_DRIVER", 180)
    sh.glabel(ALM_X - 30, ALM_Y - 4, "DOOR_SW_PASS", 180)
    sh.glabel(ALM_X - 30, ALM_Y + 4, "TAILGATE_SW", 180)

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
    # K-LINE
    dc_l_sp = 42 / 9
    kline_y = DC_Y - 21 + dc_l_sp * 7
    sh.wire(DC_X - 16, kline_y, DC_X - 30, kline_y)
    sh.glabel(DC_X - 30, kline_y, "K_LINE", 180)
    sh.text(DC_X - 28, kline_y - 3, "Pin 7: K-LINE", 0.9)

    # L-LINE (right side pin 15)
    dc_r_sp = 42 / 9
    lline_y = DC_Y - 21 + dc_r_sp * 7
    sh.wire(DC_X + 16, lline_y, DC_X + 30, lline_y)
    sh.glabel(DC_X + 30, lline_y, "L_LINE", 0)
    sh.text(DC_X + 32, lline_y - 3, "Pin 15: L-LINE", 0.9)

    # +12V_BAT (right side pin 16)
    bat_y = DC_Y - 21 + dc_r_sp * 8
    sh.wire(DC_X + 16, bat_y, DC_X + 30, bat_y)
    sh.glabel(DC_X + 30, bat_y, "+12V_ALWAYS", 0)
    sh.text(DC_X + 32, bat_y - 3, "Pin 16: +12V_BAT", 0.9)

    # Signal ground
    gnd_y = DC_Y - 21 + dc_l_sp * 5
    sh.wire(DC_X - 16, gnd_y, DC_X - 30, gnd_y)
    sh.glabel(DC_X - 30, gnd_y, "GND", 180, "input")
    sh.text(DC_X - 28, gnd_y - 3, "Pin 5: Signal GND", 0.9)

    # Multi-connector
    mc_l_sigs = ["DRIVE", "START", "DRIVE_RDY", "FAULT", "RED_PWR"]
    mc_l_sp = 30 / 6
    for i, sig in enumerate(mc_l_sigs):
        py = MC_Y - 15 + mc_l_sp * (i + 1)
        sh.wire(MC_X - 14, py, MC_X - 30, py)
        sh.glabel(MC_X - 30, py, sig, 180)

    mc_r_sigs = ["BRAKE_SW", "REVERSE", "GEAR_LOCK", "RAD_FAN_CMD", "POWER"]
    for i, sig in enumerate(mc_r_sigs):
        py = MC_Y - 15 + mc_l_sp * (i + 1)
        sh.wire(MC_X + 14, py, MC_X + 30, py)
        sh.glabel(MC_X + 30, py, sig, 0)

    # Collision sensor
    sh.wire(CS_X - 14, CS_Y - 3, CS_X - 28, CS_Y - 3)
    sh.glabel(CS_X - 28, CS_Y - 3, "K_LINE", 180)
    sh.wire(CS_X - 14, CS_Y + 3, CS_X - 28, CS_Y + 3)
    sh.glabel(CS_X - 28, CS_Y + 3, "+12V_F17_COLL_ALM", 180)

    sh.wire(CS_X + 14, CS_Y - 3, CS_X + 28, CS_Y - 3)
    sh.glabel(CS_X + 28, CS_Y - 3, "GND", 0, "input")
    sh.wire(CS_X + 14, CS_Y + 3, CS_X + 28, CS_Y + 3)
    sh.glabel(CS_X + 28, CS_Y + 3, "CRASH_SIGNAL", 0)

    # Charge cooling relay
    sh.wire(300 - 11, 180 - 4, 300 - 25, 176)
    sh.glabel(300 - 25, 176, "BATT_COOLING", 180)
    sh.wire(300 + 11, 180 - 4, 300 + 25, 176)
    sh.glabel(300 + 25, 176, "+12V_F10_WPUMP_CHG", 0)

    # Speed signal
    sh.wire(300 - 12, 220 - 3, 300 - 25, 217)
    sh.glabel(300 - 25, 217, "SPEED_SIGNAL", 180)
    sh.wire(300 - 12, 220 + 3, 300 - 25, 223)
    sh.glabel(300 - 25, 223, "+12V_F30_DIAG", 180)

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
    sh.wire(80 - 14, 50 - 5, 80 - 28, 45)
    sh.glabel(80 - 28, 45, "+12V_F7_RADIO", 180)
    sh.wire(80 - 14, 50, 80 - 28, 50)
    sh.glabel(80 - 28, 50, "GND", 180, "input")

    # Radio → speakers
    sh.wire(80 + 14, 50 - 7, 195, 35)
    sh.wire(80 + 14, 50 - 3, 195, 35)
    sh.wire(80 + 14, 50 + 2, 195, 55)
    sh.wire(80 + 14, 50 + 6, 195, 55)

    # Speaker GND
    sh.wire(205, 35, 220, 35)
    sh.glabel(220, 35, "GND", 0, "input")
    sh.wire(205, 55, 220, 55)
    sh.glabel(220, 55, "GND", 0, "input")

    # Antenna
    sh.wire(80 - 7, 20, 80 - 20, 20)
    sh.label(80 - 20, 17, "ANT_SIGNAL")
    sh.wire(80 - 14, 50 + 10, 80 - 14, 20)

    # Heated rear window relay → element
    sh.wire(140 - 11, 90 - 4, 140 - 25, 86)
    sh.glabel(140 - 25, 86, "+12V_F1_HTDWS", 180)
    sh.text(140 - 23, 82, "From F1 (30A)", 0.9)
    sh.wire(140 + 11, 90 - 4, 195, 90)
    sh.wire(200 + 12, 90, 220, 90)
    sh.glabel(220, 90, "GND", 0, "input")

    # Brake vacuum pump
    sh.wire(80 - 11, 120, 80 - 25, 120)
    sh.glabel(80 - 25, 120, "+12V_F22_VACPUMP", 180)
    sh.text(80 - 23, 116, "From F22 (25A)", 0.9)
    sh.wire(80 + 11, 120, 80 + 25, 120)
    sh.glabel(80 + 25, 120, "GND", 0, "input")

    # Heater switch → relay → blower
    sh.wire(80 - 14, 180, 80 - 28, 180)
    sh.glabel(80 - 28, 180, "+12V_F5_BLOWER", 180)
    sh.text(80 - 26, 176, "From F5 (30A)", 0.9)

    sh.wire(80 + 14, 180 - 4, 151, 160 - 4)
    sh.wire(160 + 11, 160 - 4, 245, 160 - 3)

    # Blower GND
    sh.wire(250 + 12, 160 + 3, 250 + 25, 163)
    sh.glabel(250 + 25, 163, "GND", 0, "input")

    # Recirculation
    sh.wire(80 - 9, 230, 80 - 25, 230)
    sh.glabel(80 - 25, 230, "+12V_F5_BLOWER", 180)
    sh.wire(80 + 9, 230, 151, 230)
    sh.wire(160 + 11, 230 - 4, 245, 240)
    sh.wire(250 + 10, 240, 270, 240)
    sh.glabel(270, 240, "GND", 0, "input")

    # Webasto heater
    sh.wire(350 - 14, 100 - 5, 350 - 28, 95)
    sh.glabel(350 - 28, 95, "+12V_F3_HEATER", 180)
    sh.text(350 - 26, 91, "From F3 (40A)", 0.9)
    sh.wire(350 - 14, 100 + 5, 350 - 28, 105)
    sh.glabel(350 - 28, 105, "GND", 180, "input")

    sh.wire(350 + 14, 100 + 2, 350 + 28, 102)
    sh.glabel(350 + 28, 102, "WEBASTO_CTRL", 0)

    # Webasto relay
    sh.wire(350 - 11, 50 - 4, 350 - 25, 46)
    sh.glabel(350 - 25, 46, "+12V_F33_WEBASTO", 180)

    # Tailgate release
    sh.wire(350 - 9, 170, 350 - 22, 170)
    sh.glabel(350 - 22, 170, "TAILGATE_RELEASE", 180)
    sh.wire(350 + 9, 170, 350 + 22, 170)
    sh.glabel(350 + 22, 170, "GND", 0, "input")

    sh.wire(350 - 9, 200, 350 - 22, 200)
    sh.glabel(350 - 22, 200, "+12V_F9_HORN_DOME", 180)

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
    cc_l = ["K_LINE", "+12V_F17_COLL_ALM", "CRASH_SIGNAL"]
    sp_cc = 30 / 4
    for i, sig in enumerate(cc_l):
        py = CC_Y - 15 + sp_cc * (i + 1)
        sh.wire(CC_X - 17, py, CC_X - 30, py)
        shape = "bidirectional"
        if "12V" in sig:
            shape = "output"
        sh.glabel(CC_X - 30, py, sig, 180, shape)

    # Collision control right → pretensioners
    cc_r = ["DRIVER_BELT", "PASS_BELT", "WARNING_LAMP", "GND"]
    sp_cr = 30 / 5
    for i, sig in enumerate(cc_r):
        py = CC_Y - 15 + sp_cr * (i + 1)
        sh.wire(CC_X + 17, py, CC_X + 30, py)
        if sig == "DRIVER_BELT":
            sh.wire(CC_X + 30, py, 245, 45)
        elif sig == "PASS_BELT":
            sh.wire(CC_X + 30, py, 245, 65)
        elif sig == "GND":
            sh.glabel(CC_X + 30, py, "GND", 0, "input")
        else:
            sh.glabel(CC_X + 30, py, sig, 0)

    # Pretensioner GND
    sh.wire(255, 45, 270, 45)
    sh.glabel(270, 45, "GND", 0, "input")
    sh.wire(255, 65, 270, 65)
    sh.glabel(270, 65, "GND", 0, "input")
    sh.text(255, 41, "Wire: 0.5mm2 PNK", 0.9)

    # -- Contactor box internal connections --
    # Left side
    cb_l = ["+114V_IN", "-114V_IN", "MAIN_RELAY_COIL", "AUX_RELAY_COIL", "HEATER_RELAY_COIL"]
    sp_cbl = 80 / 6
    for i, sig in enumerate(cb_l):
        py = CB_Y - 40 + sp_cbl * (i + 1)
        sh.wire(CB_X - 32, py, CB_X - 45, py)
        if "114V" in sig:
            sh.glabel(CB_X - 45, py, sig.replace("_IN", ""), 180)
        else:
            sh.label(CB_X - 45, py, sig)

    # Right side
    cb_r = ["+114V_OUT", "-114V_OUT", "PRECHARGE_OUT", "LEM_SENSE+", "LEM_SENSE-"]
    sp_cbr = 80 / 6
    for i, sig in enumerate(cb_r):
        py = CB_Y - 40 + sp_cbr * (i + 1)
        sh.wire(CB_X + 32, py, CB_X + 45, py)
        if "114V" in sig:
            sh.glabel(CB_X + 45, py, sig.replace("_OUT", "_TO_MC"), 0)
        elif "LEM" in sig:
            sh.glabel(CB_X + 45, py, sig, 0)
        else:
            sh.label(CB_X + 45, py, sig)

    # Top control signals
    cb_t = ["CB_RUN", "BMS_CMD", "CHG_START", "PREHEAT", "CHARGE", "+12V_CTRL"]
    sp_cbt = 60 / 7
    for i, sig in enumerate(cb_t):
        px = CB_X - 30 + sp_cbt * (i + 1) * 2
        sh.wire(px, CB_Y - 42, px, CB_Y - 55)
        if sig == "+12V_CTRL":
            sh.glabel(px, CB_Y - 55, "+12V_F28_DRIVE", 90)
        else:
            sh.glabel(px, CB_Y - 55, sig, 90)

    # Bottom
    sh.wire(CB_X - 10, CB_Y + 42, CB_X - 10, CB_Y + 52)
    sh.glabel(CB_X - 10, CB_Y + 52, "GND", 270, "input")
    sh.wire(CB_X + 10, CB_Y + 42, CB_X + 10, CB_Y + 52)
    sh.glabel(CB_X + 10, CB_Y + 52, "DIAG_CB", 270)

    # -- HV Distribution box detail --
    hvd_l = ["+114V_BATT", "-114V_BATT"]
    sp_hvl = 40 / 3
    for i, sig in enumerate(hvd_l):
        py = HVD_Y - 20 + sp_hvl * (i + 1)
        sh.wire(HVD_X - 22, py, HVD_X - 35, py)
        sh.glabel(HVD_X - 35, py, "+114V" if "+" in sig else "-114V", 180)

    hvd_r = ["VA_CB+", "VB_CB-", "VD_DCDC+", "VD_DCDC-", "VQ_CHG+", "VQ_CHG-"]
    sp_hvr = 40 / 7
    for i, sig in enumerate(hvd_r):
        py = HVD_Y - 20 + sp_hvr * (i + 1)
        sh.wire(HVD_X + 22, py, HVD_X + 35, py)
        sh.label(HVD_X + 35, py, sig)

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
        ("think_s01_power_dist.kicad_sch",   build_s01_power_dist),
        ("think_s02_hv_power.kicad_sch",     build_s02_hv_power),
        ("think_s03_motor_ctrl.kicad_sch",    build_s03_motor_ctrl),
        ("think_s04_sensors.kicad_sch",       build_s04_sensors),
        ("think_s05_regen_dcdc.kicad_sch",    build_s05_regen_dcdc),
        ("think_s06_bms_charger.kicad_sch",   build_s06_bms_charger),
        ("think_s07_headlights.kicad_sch",    build_s07_headlights),
        ("think_s08_rear_lights.kicad_sch",   build_s08_rear_lights),
        ("think_s09_signals_horn.kicad_sch",  build_s09_signals_horn),
        ("think_s10_wipers_alarm.kicad_sch",  build_s10_wipers_alarm),
        ("think_s11_diag_speed.kicad_sch",    build_s11_diag_speed),
        ("think_s12_radio_hvac.kicad_sch",    build_s12_radio_hvac),
        ("think_s13_safety_hv.kicad_sch",     build_s13_safety_hv),
    ]

    print("Generating sub-sheets...")
    for fname, builder in builders:
        sheet = builder()
        sheet.save(os.path.join(OUT_DIR, fname))

    print()
    print("Generating root sheet...")
    root = build_root()
    root.save(os.path.join(OUT_DIR, "think_city_complete.kicad_sch"))

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
