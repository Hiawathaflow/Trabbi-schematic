#!/usr/bin/env python3
"""
KiCad 9 Schematic Generator
Siemens Simovert 6SV1 Long Inverter – Complete EV Drive System
Based on: Metric Mind Engineering Installation Manual, Fig. 9
"""

import uuid, os

OUTPUT = "/home/hw/Projects/Trabbi-schematic/Data/Trabbi Schematic/simovert_ev.kicad_sch"

def uid():
    return str(uuid.uuid4())

# ──────────────────────────────────────────────────────────────
# Low-level builders
# ──────────────────────────────────────────────────────────────

lib_syms = []
elems    = []
sym_defs = {}   # lib_id -> {pin_name: pin_number_str}


def _pin_line(name, num, ptype, x, y, ang, plen=2.54):
    return (
        f'        (pin {ptype} line (at {x:.3f} {y:.3f} {ang}) (length {plen:.3f})\n'
        f'          (name "{name}" (effects (font (size 1.016 1.016))))\n'
        f'          (number "{num}" (effects (font (size 1.016 1.016))))\n'
        f'        )'
    )


def defsym(lib_id, w, h,
           lpins=(), rpins=(), tpins=(), bpins=(),
           body_label="", ref_pfx="U"):
    """
    Define a rectangular KiCad 9 symbol.
    Each pin entry: "name" (passive) or ("name", "ptype").
    Returns (lib_id, pin_map)
    """
    name = lib_id.split(":")[-1]
    hw, hh = w / 2, h / 2
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

    # Body graphics
    s.append(f'      (symbol "{name}_0_1"')
    s.append(f'        (rectangle (start {-hw:.3f} {-hh:.3f}) (end {hw:.3f} {hh:.3f})')
    s.append(f'          (stroke (width 0.254) (type default))')
    s.append(f'          (fill (type background))')
    s.append(f'        )')
    if body_label:
        for i, line in enumerate(body_label.split("\\n")):
            s.append(f'        (text "{line}" (at 0 {-i*3:.1f} 0)')
            s.append(f'          (effects (font (size 1.5 1.5) bold))')
            s.append(f'        )')
    s.append(f'      )')

    # Pins
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
                px, py, ang = -hw - pl, pos, 0
            elif side == 'R':
                px, py, ang = hw + pl, pos, 180
            elif side == 'T':
                px, py, ang = pos, hh + pl, 270
            else:  # B
                px, py, ang = pos, -hh - pl, 90
            s.append(_pin_line(pname, n[0], ptype, px, py, ang, pl))
            pin_map[pname] = str(n[0])
            n[0] += 1

    add_side(lpins, 'L', h)
    add_side(rpins, 'R', h)
    add_side(tpins, 'T', w)
    add_side(bpins, 'B', w)
    s.append(f'      )')
    s.append(f'    )')

    lib_syms.extend(s)
    sym_defs[lib_id] = pin_map
    return lib_id, pin_map


def place(lib_id, ref, val, x, y, ang=0):
    """Place a symbol instance."""
    pm = sym_defs.get(lib_id, {})
    s = []
    s.append(f'  (symbol (lib_id "{lib_id}") (at {x:.3f} {y:.3f} {ang})')
    s.append(f'    (unit 1) (in_bom yes) (on_board yes) (dnp no)')
    s.append(f'    (uuid "{uid()}")')
    for prop, pval, dx, dy in [
        ("Reference", ref,  0, -7),
        ("Value",     val,  0,  7),
        ("Footprint", "",   0,  0),
        ("Datasheet", "",   0,  0),
    ]:
        hide = " hide" if prop in ("Footprint", "Datasheet") else ""
        s.append(f'    (property "{prop}" "{pval}" (at {x+dx:.3f} {y+dy:.3f} 0)')
        s.append(f'      (effects (font (size 1.27 1.27)){hide})')
        s.append(f'    )')
    for pname, pnum in pm.items():
        s.append(f'    (pin "{pnum}" (uuid "{uid()}"))')
    s.append(f'  )')
    elems.extend(s)


def wire(x1, y1, x2, y2):
    elems.append(
        f'  (wire (pts (xy {x1:.3f} {y1:.3f}) (xy {x2:.3f} {y2:.3f}))\n'
        f'    (stroke (width 0) (type default))\n'
        f'    (uuid "{uid()}")\n'
        f'  )'
    )


def label(x, y, name, ang=0):
    elems.append(
        f'  (label "{name}" (at {x:.3f} {y:.3f} {ang})\n'
        f'    (effects (font (size 1.27 1.27)))\n'
        f'    (uuid "{uid()}")\n'
        f'  )'
    )


def junction(x, y):
    elems.append(
        f'  (junction (at {x:.3f} {y:.3f}) (diameter 0) (color 0 0 0 0)'
        f' (uuid "{uid()}"))'
    )


def no_connect(x, y):
    elems.append(
        f'  (no_connect (at {x:.3f} {y:.3f}) (uuid "{uid()}"))'
    )


def text(x, y, s, size=1.27, ang=0):
    s = s.replace('"', '\\"')
    elems.append(
        f'  (text "{s}" (at {x:.3f} {y:.3f} {ang})\n'
        f'    (effects (font (size {size:.3f} {size:.3f})))\n'
        f'    (uuid "{uid()}")\n'
        f'  )'
    )


# ──────────────────────────────────────────────────────────────
# Symbol Definitions
# ──────────────────────────────────────────────────────────────

# Simovert 6SV1 Long Inverter
# Left:   +HV_IN, -HV_IN  (traction battery)
# Right:  L1, L2, L3 (motor), KL30 (+12V out), KL31 (GND out)
# Top:    X1 (35-pin interface - shown as single pin here), X4, X5
defsym("Custom:SIMOVERT_LONG", 50, 90,
    lpins=["+HV_IN", "-HV_IN"],
    rpins=["L1", "L2", "L3",
           ("KL30_+12V", "power_out"),
           ("KL31_GND",  "power_out")],
    tpins=["X1_iface", "X4_encoder", "X5_RS232"],
    body_label="INVERTER\\nSIMOVERT\\n6SV1 LONG",
    ref_pfx="U")

# 3-Phase AC Induction Motor
defsym("Custom:MOTOR_3PH", 30, 40,
    lpins=["L1", "L2", "L3", ("PE", "power_in")],
    body_label="M\\n3~",
    ref_pfx="M")

# Traction Battery Pack (simplified as voltage source)
defsym("Custom:BATT_HV", 20, 30,
    tpins=[("+", "power_out")],
    bpins=[("-", "power_in")],
    body_label="HV\\nBATT",
    ref_pfx="BT")

# 12V Auxiliary Battery
defsym("Custom:BATT_12V", 16, 24,
    tpins=[("+", "power_out")],
    bpins=[("-", "power_in")],
    body_label="12V\\nBATT",
    ref_pfx="BT")

# Fuse / Circuit Breaker
defsym("Custom:FUSE", 12, 8,
    lpins=["A"],
    rpins=["B"],
    body_label="FUSE",
    ref_pfx="F")

# SPST Switch
defsym("Custom:SW_SPST", 12, 8,
    lpins=["A"],
    rpins=["B"],
    body_label="SW",
    ref_pfx="SW")

# Pushbutton
defsym("Custom:PUSHBUTTON", 12, 8,
    lpins=["A"],
    rpins=["B"],
    body_label="PB",
    ref_pfx="SW")

# 3-Terminal Potentiometer
defsym("Custom:POT3", 12, 18,
    lpins=["LO"],
    rpins=["HI"],
    bpins=["WIP"],
    body_label="POT",
    ref_pfx="RV")

# Indicator Lamp
defsym("Custom:LAMP", 10, 8,
    lpins=["+12V"],
    rpins=["K"],
    body_label="LAMP",
    ref_pfx="H")

# 35-Pin X1 Interface Connector
# We'll show it as a block with all 35 pins on the right side
x1_pins = [
    ("P1_IGN_DRIVE",    "passive"),
    ("P2_EMERG_OFF",    "passive"),
    ("P3_NC",           "passive"),
    ("P4_FAN",          "passive"),
    ("P5_NC",           "passive"),
    ("P6_NC",           "passive"),
    ("P7_INV_FAIL",     "passive"),
    ("P8_DCDC_FAIL",    "passive"),
    ("P9_PWR_RED_IND",  "passive"),
    ("P10_MOT_SPD",     "passive"),
    ("P11_NC",          "passive"),
    ("P12_NC",          "passive"),
    ("P13_BRAKE_CONTACT","passive"),
    ("P14_NC",          "passive"),
    ("P15_NC",          "passive"),
    ("P16_BRAKE_POT_HI","passive"),
    ("P17_BRAKE_WIP",   "passive"),
    ("P18_BRAKE_POT_LO","passive"),
    ("P19_NC",          "passive"),
    ("P20_PWR_REDUCE",  "passive"),
    ("P21_VEH_SPEED",   "passive"),
    ("P22_NC",          "passive"),
    ("P23_REVERSE",     "passive"),
    ("P24_FORWARD",     "passive"),
    ("P25_NC",          "passive"),
    ("P26_NC",          "passive"),
    ("P27_NC",          "passive"),
    ("P28_NC",          "passive"),
    ("P29_REGEN_EN",    "passive"),
    ("P30_IGN_START",   "passive"),
    ("P31_START_INH",   "passive"),
    ("P32_NC",          "passive"),
    ("P33_ACCEL_HI",    "passive"),
    ("P34_ACCEL_WIP",   "passive"),
    ("P35_ACCEL_LO",    "passive"),
]
defsym("Custom:X1_CONN35", 25, 35 * 2.54,   # 35 pins * 2.54mm pitch
    rpins=x1_pins,
    body_label="X1\\n35-PIN",
    ref_pfx="J")

# ──────────────────────────────────────────────────────────────
# Component Placement (coordinates in mm, A0 page 1189x841)
# Layout:
#  Left (x=50-200):   HV Power circuit
#  Center (x=250-450): Inverter
#  Right top (x=550-750): Motor
#  Right (x=800-1100): X1 Interface connector
#  Bottom-left (x=50-300): 12V Aux + control
# ──────────────────────────────────────────────────────────────

# ── Traction Battery Pack ──
BT1_X, BT1_Y = 80, 300
place("Custom:BATT_HV", "BT1", "144V+ Traction Pack", BT1_X, BT1_Y)

# ── Main 300A Circuit Breaker ──
CB1_X, CB1_Y = 160, 280
place("Custom:FUSE", "CB1", "300A Ckt Breaker", CB1_X, CB1_Y)

# ── 40A Fuse (between battery and CB) ──
F1_X, F1_Y = 200, 270
place("Custom:FUSE", "F1", "40A Fuse", F1_X, F1_Y)

# ── Simovert Inverter ──
INV_X, INV_Y = 340, 290
place("Custom:SIMOVERT_LONG", "U1", "Simovert 6SV1 Long", INV_X, INV_Y)

# ── 3-Phase Motor ──
MOT_X, MOT_Y = 530, 290
place("Custom:MOTOR_3PH", "M1", "AC Induction Motor", MOT_X, MOT_Y)

# ── Auxiliary 12V Battery ──
BT2_X, BT2_Y = 160, 520
place("Custom:BATT_12V", "BT2", "12V Aux Battery", BT2_X, BT2_Y)

# ── Ignition Switch (Drive position) ──
IGN_A_X, IGN_A_Y = 80, 120
place("Custom:SW_SPST", "SW1A", "IGN-Drive (FAT-RED)", IGN_A_X, IGN_A_Y)

# ── Ignition Switch (Start position) ──
IGN_B_X, IGN_B_Y = 80, 150
place("Custom:SW_SPST", "SW1B", "IGN-Start (WHT)", IGN_B_X, IGN_B_Y)

# ── Start Button ──
SB_X, SB_Y = 200, 120
place("Custom:PUSHBUTTON", "SW2", "Start Button", SB_X, SB_Y)

# ── Forward Switch ──
FWD_X, FWD_Y = 300, 110
place("Custom:SW_SPST", "SW3", "Forward (VLT)", FWD_X, FWD_Y)

# ── Reverse Switch ──
REV_X, REV_Y = 300, 140
place("Custom:SW_SPST", "SW4", "Reverse (BRN)", REV_X, REV_Y)

# ── Brake Light Switch ──
BRK_X, BRK_Y = 430, 110
place("Custom:SW_SPST", "SW5", "Brake Light Switch (RED-BLU)", BRK_X, BRK_Y)

# ── Acceleration Potentiometer ──
POT_X, POT_Y = 550, 110
place("Custom:POT3", "RV1", "Accel Pot Bosch (YLW-BLK/BLU/YLW-RED)", POT_X, POT_Y)

# ── Brake Potentiometer (optional) ──
BPOT_X, BPOT_Y = 680, 110
place("Custom:POT3", "RV2", "Brake Pot opt. (ORG/ORG-BLK/RED-BLK)", BPOT_X, BPOT_Y)

# ── Indicator Lamps ──
LAMP1_X, LAMP1_Y = 800, 100
place("Custom:LAMP", "H1", "Inverter Failure (GRN)", LAMP1_X, LAMP1_Y)
LAMP2_X, LAMP2_Y = 800, 120
place("Custom:LAMP", "H2", "DC-DC Failure (YLW)", LAMP2_X, LAMP2_Y)
LAMP3_X, LAMP3_Y = 800, 140
place("Custom:LAMP", "H3", "Power Reduction (RED)", LAMP3_X, LAMP3_Y)

# ── X1 35-Pin Interface Connector ──
X1_X, X1_Y = 1000, 350
place("Custom:X1_CONN35", "J1", "X1 35-Pin Vehicle Interface", X1_X, X1_Y)

# ──────────────────────────────────────────────────────────────
# Wiring – Main HV Power Circuit
# ──────────────────────────────────────────────────────────────

# BT1+ → CB1_A
wire(BT1_X, BT1_Y - 15, BT1_X, BT1_Y - 25)    # batt + pin upward
wire(BT1_X, BT1_Y - 25, CB1_X - 6, BT1_Y - 25) # horizontal to CB1
wire(CB1_X - 6, BT1_Y - 25, CB1_X - 6, CB1_Y)  # down to CB1_A

# CB1_B → F1_A
wire(CB1_X + 6, CB1_Y, CB1_X + 6, 260)
wire(CB1_X + 6, 260, F1_X - 6, 260)
wire(F1_X - 6, 260, F1_X - 6, F1_Y)

# F1_B → Inverter +HV_IN
wire(F1_X + 6, F1_Y, F1_X + 6, 255)
wire(F1_X + 6, 255, INV_X - 27.54, 255)         # horizontal
wire(INV_X - 27.54, 255, INV_X - 27.54, INV_Y - 30)  # down to +HV_IN pin

# BT1- → Inverter -HV_IN  (negative rail)
wire(BT1_X, BT1_Y + 15, BT1_X, BT1_Y + 35)
wire(BT1_X, BT1_Y + 35, INV_X - 27.54, BT1_Y + 35)
wire(INV_X - 27.54, BT1_Y + 35, INV_X - 27.54, INV_Y - 18)  # -HV_IN pin

# Inverter L1,L2,L3 → Motor L1,L2,L3
for i in range(3):
    iy = INV_Y - 18 + i * 14.4    # approx right pin positions
    my = MOT_Y - 12 + i * 8       # approx left pin positions
    wire(INV_X + 27.54, iy, INV_X + 55, iy)
    wire(INV_X + 55, iy, MOT_X - 17.54, my)

# Motor PE → GND label
wire(MOT_X - 17.54, MOT_Y + 12, MOT_X - 30, MOT_Y + 12)
label(MOT_X - 30, MOT_Y + 12, "GND_CHASSIS")

# ──────────────────────────────────────────────────────────────
# Wiring – 12V Auxiliary Circuit
# ──────────────────────────────────────────────────────────────

# KL30 (+12V from DC-DC) → BT2+
wire(INV_X + 27.54, INV_Y + 21.6, INV_X + 70, INV_Y + 21.6)  # KL30 pin
wire(INV_X + 70, INV_Y + 21.6, INV_X + 70, BT2_Y - 12)
wire(INV_X + 70, BT2_Y - 12, BT2_X, BT2_Y - 12)
label(INV_X + 60, INV_Y + 21.6, "KL30_+12V")

# KL31 (GND) → BT2-  → Chassis GND
wire(INV_X + 27.54, INV_Y + 36, INV_X + 85, INV_Y + 36)   # KL31 pin
wire(INV_X + 85, INV_Y + 36, INV_X + 85, BT2_Y + 12)
wire(INV_X + 85, BT2_Y + 12, BT2_X, BT2_Y + 12)
label(INV_X + 80, INV_Y + 36, "KL31_GND")

# BT2 to vehicle +12V system
wire(BT2_X + 10, BT2_Y - 12, BT2_X + 40, BT2_Y - 12)
label(BT2_X + 40, BT2_Y - 12, "+12V_VEHICLE")
wire(BT2_X + 10, BT2_Y + 12, BT2_X + 40, BT2_Y + 12)
label(BT2_X + 40, BT2_Y + 12, "GND_CHASSIS")

# ──────────────────────────────────────────────────────────────
# Wiring / Labels – Control Signals (via X1 interface)
# ──────────────────────────────────────────────────────────────

# IGN_DRIVE (Pin 1, FAT RED wire) → Inverter X1 stub
label(INV_X - 27.54, INV_Y - 50, "X1_STUB")   # placeholder for X1 top pin

# Ignition switch drive side: +12V → SW1A_A, SW1A_B → X1/P1
wire(IGN_A_X - 8, IGN_A_Y, 60, IGN_A_Y)
label(60, IGN_A_Y, "+12V_VEHICLE")
wire(IGN_A_X + 8, IGN_A_Y, IGN_A_X + 40, IGN_A_Y)
label(IGN_A_X + 40, IGN_A_Y, "P1_IGN_DRIVE")

# Ignition switch start side
wire(IGN_B_X - 8, IGN_B_Y, 60, IGN_B_Y)
label(60, IGN_B_Y, "+12V_VEHICLE")
wire(IGN_B_X + 8, IGN_B_Y, IGN_B_X + 40, IGN_B_Y)
label(IGN_B_X + 40, IGN_B_Y, "P30_IGN_START")

# Start button → X1/P30 (start signal memorized for 2.5s)
wire(SB_X - 8, SB_Y, 180, SB_Y)
label(180, SB_Y, "P1_IGN_DRIVE")
wire(SB_X + 8, SB_Y, SB_X + 40, SB_Y)
label(SB_X + 40, SB_Y, "P30_IGN_START")

# Forward switch → P24
wire(FWD_X - 8, FWD_Y, FWD_X - 30, FWD_Y)
label(FWD_X - 30, FWD_Y, "GND_CHASSIS")
wire(FWD_X + 8, FWD_Y, FWD_X + 40, FWD_Y)
label(FWD_X + 40, FWD_Y, "P24_FORWARD")

# Reverse switch → P23
wire(REV_X - 8, REV_Y, REV_X - 30, REV_Y)
label(REV_X - 30, REV_Y, "GND_CHASSIS")
wire(REV_X + 8, REV_Y, REV_X + 40, REV_Y)
label(REV_X + 40, REV_Y, "P23_REVERSE")

# Brake switch → P13
wire(BRK_X - 8, BRK_Y, BRK_X - 30, BRK_Y)
label(BRK_X - 30, BRK_Y, "+12V_VEHICLE")
wire(BRK_X + 8, BRK_Y, BRK_X + 40, BRK_Y)
label(BRK_X + 40, BRK_Y, "P13_BRAKE_CONTACT")

# Accel pot: HI → P33, WIP → P34, LO → P35
wire(POT_X + 8, POT_Y, POT_X + 35, POT_Y)
label(POT_X + 35, POT_Y, "P33_ACCEL_HI")
wire(POT_X, POT_Y + 11, POT_X, POT_Y + 25)
label(POT_X, POT_Y + 25, "P34_ACCEL_WIP")
wire(POT_X - 8, POT_Y, POT_X - 35, POT_Y)
label(POT_X - 35, POT_Y, "P35_ACCEL_LO")

# Brake pot: HI → P16, WIP → P17, LO → P18
wire(BPOT_X + 8, BPOT_Y, BPOT_X + 35, BPOT_Y)
label(BPOT_X + 35, BPOT_Y, "P16_BRAKE_POT_HI")
wire(BPOT_X, BPOT_Y + 11, BPOT_X, BPOT_Y + 25)
label(BPOT_X, BPOT_Y + 25, "P17_BRAKE_WIP")
wire(BPOT_X - 8, BPOT_Y, BPOT_X - 35, BPOT_Y)
label(BPOT_X - 35, BPOT_Y, "P18_BRAKE_POT_LO")

# Status lamps: K → GND, +12V → lamp input
for lx, ly, sig in [
    (LAMP1_X, LAMP1_Y, "P7_INV_FAIL"),
    (LAMP2_X, LAMP2_Y, "P8_DCDC_FAIL"),
    (LAMP3_X, LAMP3_Y, "P9_PWR_RED_IND"),
]:
    wire(lx - 7, ly, lx - 30, ly)
    label(lx - 30, ly, "+12V_VEHICLE")
    wire(lx + 7, ly, lx + 30, ly)
    label(lx + 30, ly, sig)

# ──────────────────────────────────────────────────────────────
# No-connects for unused X1 pins
# ──────────────────────────────────────────────────────────────
# (These will be on the right side of the X1_CONN35 symbol)
# NC pins: 3, 5, 6, 11, 12, 14, 15, 19, 22, 25, 26, 27, 28, 32

# ──────────────────────────────────────────────────────────────
# Remaining X1 signal labels (GND connections to inverter inputs)
# ──────────────────────────────────────────────────────────────
# Emergency Off (P2) – pulled to GND, open = E-stop active
text(50, 420, "P2_EMERG_OFF: Connect to GND via E-stop switch (RED-GRN)", 1.0)
text(50, 426, "P20_PWR_REDUCE: GND = normal power, open/+12V = reduced (RED-BRN)", 1.0)
text(50, 432, "P29_REGEN_EN: GND = regen braking enabled (BLK wire)", 1.0)
text(50, 438, "P31_START_INH: GND = start allowed (GRY wire)", 1.0)
text(50, 444, "P21_VEH_SPEED: frequency input 0.7-250Hz (PNK wire)", 1.0)
text(50, 450, "P10_MOT_SPD: frequency output (ORG-RED wire, 4.7kOhm pullup to +12V)", 1.0)
text(50, 456, "X4: motor encoder interface cable (12-wire cable)", 1.0)
text(50, 462, "X5: RS232 diagnostic (SIADIS software, 9600 baud COM1)", 1.0)

# ──────────────────────────────────────────────────────────────
# Key annotations
# ──────────────────────────────────────────────────────────────
text(50, 600, "INSTALLATION NOTES (Simovert 6SV1 Long Inverter):", 1.5)
text(50, 608, "1. KL31 (M6 bolt on case) = -12V DC-DC output. Connect DIRECTLY to BT2- with 10mm2 wire. CRITICAL!", 1.1)
text(50, 614, "2. Connect KL31 FIRST, disconnect LAST. Disconnecting while on WILL damage interface PCB.", 1.1)
text(50, 620, "3. Traction battery (HV) is isolated from chassis. Only KL31/case connects to chassis GND.", 1.1)
text(50, 626, "4. Motor case must be connected to vehicle chassis (GND_CHASSIS).", 1.1)
text(50, 632, "5. CB1: 300A circuit breaker in positive HV cable. F1: 40A fuse.", 1.1)
text(50, 638, "6. Coolant: flow INTO inverter first, then TO motor. Min 8 l/min. Max inlet 55 degC.", 1.1)
text(50, 644, "7. Never connect/disconnect X1, X4, X5 while ignition is ON.", 1.1)
text(50, 650, "8. AccPedRel must read 0% in SIADIS before main contactor will close.", 1.1)
text(50, 656, "9. Motor L1→L1, L2→L2, L3→L3 (polarity matters for rotation direction, bit 1 of Mode_Selector).", 1.1)
text(50, 662, "10. For regen braking: X1/P29 (BLK) must be pulled to GND.", 1.1)

# Wire color reference
text(700, 600, "WIRE COLOR REFERENCE (Appendix C, Long Inverter):", 1.4)
wc = [
    ("P1",  "FAT RED 1.5mm2", "Ignition drive position"),
    ("P2",  "RED/GRN 0.5mm2", "Emergency power off"),
    ("P4",  "BRN 1.5mm2",     "Fan (-)"),
    ("P7",  "GRN 0.5mm2",     "Failure: power inverter"),
    ("P8",  "YLW 0.5mm2",     "Failure: DC/DC converter"),
    ("P9",  "RED 0.5mm2",     "Indication power reduction"),
    ("P10", "ORG-RED 0.5mm2", "Motor speed output"),
    ("P13", "RED-BLU 0.5mm2", "Brake contact"),
    ("P16", "ORG 0.5mm2",     "Brake pot high"),
    ("P17", "ORG-BLK 0.5mm2", "Brake pot wiper"),
    ("P18", "RED-BLK 0.5mm2", "Brake pot low"),
    ("P20", "RED-BRN 0.5mm2", "Power reduction"),
    ("P21", "PNK 0.5mm2",     "Vehicle speed in"),
    ("P23", "BRN 0.5mm2",     "Reverse"),
    ("P24", "VLT 0.5mm2",     "Forward"),
    ("P29", "BLK 0.5mm2",     "Electrical braking enabled"),
    ("P30", "WHT 0.5mm2",     "Ignition start"),
    ("P31", "GRY 0.5mm2",     "Start inhibition"),
    ("P33", "YLW-BLK 0.5mm2", "Accel pot high"),
    ("P34", "BLU 0.5mm2",     "Accel pot wiper"),
    ("P35", "YLW-RED 0.5mm2", "Accel pot low"),
    ("KL30","FAT BRN (16mm2)","DC-DC +12V output"),
    ("KL31","M6 bolt on case", "DC-DC -12V / chassis GND"),
]
for i, (pin, color, desc) in enumerate(wc):
    text(700, 610 + i * 5, f"X1/{pin:3s}  {color:20s}  {desc}", 0.9)

# ──────────────────────────────────────────────────────────────
# Assemble and write the schematic file
# ──────────────────────────────────────────────────────────────

out = []
out.append('(kicad_sch (version 20241209) (generator "python_gen") (generator_version "9.0")')
out.append('  (paper "A0")')
out.append('  (title_block')
out.append('    (title "Siemens Simovert 6SV1 Long Inverter - EV Drive System")')
out.append('    (date "2026-03-22")')
out.append('    (rev "1")')
out.append('    (company "Trabbi EV Conversion")')
out.append('    (comment 1 "Based on Metric Mind Engineering Installation Manual Rev 3.00c")')
out.append('    (comment 2 "Fig. 9: Complete electrical schematic - Long Inverter, no charger")')
out.append('    (comment 3 "Wire colors: see Appendix C / Section 6.3.1")')
out.append('    (comment 4 "DANGER: HV traction battery. See safety warnings in manual.")')
out.append('  )')
out.append('  (lib_symbols')
out.extend(lib_syms)
out.append('  )')
out.extend(elems)
out.append('  (symbol_instances)')
out.append(')')

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write('\n'.join(out))

print(f"Written: {OUTPUT}")
print(f"  Symbols defined: {len(sym_defs)}")
print(f"  Elements:        {len(elems)}")
