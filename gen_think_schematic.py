#!/usr/bin/env python3
"""
KiCad 9 Schematic Generator
Think City EV – Main electrical systems
Based on: think-300dpi_koblingsskema.pdf
Sheets covered: 01 (fuses), 02 (ignition/start), 03 (BMS/contactor),
                04 (HV power/motor), 05 (motor ctrl signals), 10 (DC/DC),
                11 (BMS sensors/charger), 35/36 (HV box)
"""

import uuid, os

OUTPUT = "/home/hw/Projects/Trabbi-schematic/Data/Trabbi Schematic/think_city.kicad_sch"

def uid():
    return str(uuid.uuid4())

lib_syms = []
elems    = []
sym_defs = {}

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
            s.append(f'        (text "{line}" (at 0 {-i*3:.1f} 0)')
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
    pm = sym_defs.get(lib_id, {})
    s = []
    s.append(f'  (symbol (lib_id "{lib_id}") (at {x:.3f} {y:.3f} {ang})')
    s.append(f'    (unit 1) (in_bom yes) (on_board yes) (dnp no)')
    s.append(f'    (uuid "{uid()}")')
    for prop, pval, dx, dy in [
        ("Reference", ref,  0, -8),
        ("Value",     val,  0,  8),
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

# 114V Traction Battery (TB)
defsym("Think:BATT_HV", 24, 32,
    tpins=[("+", "power_out")],
    bpins=[("-", "power_in")],
    body_label="114V\\nBATTERY\\n(TB)",
    ref_pfx="BT")

# 12V Auxiliary Battery (E04)
defsym("Think:BATT_12V", 20, 24,
    tpins=[("+", "power_out")],
    bpins=[("-", "power_in")],
    body_label="12V\\nBATT\\n(E04)",
    ref_pfx="BT")

# Fuse (generic)
defsym("Think:FUSE", 14, 8,
    lpins=["A"],
    rpins=["B"],
    body_label="FUSE",
    ref_pfx="F")

# SPST Switch (generic)
defsym("Think:SW_SPST", 14, 8,
    lpins=["A"],
    rpins=["B"],
    body_label="SW",
    ref_pfx="SW")

# Relay SPDT (DIN 72 551 / 72 652): pins 86(+coil), 85(-coil), 30(common), 87(NO), 87a(NC)
defsym("Think:RELAY_SPDT", 20, 30,
    lpins=["86_COIL+", "85_COIL-"],
    rpins=["30_COM", ("87_NO", "output"), ("87a_NC", "output")],
    body_label="RELAY",
    ref_pfx="K")

# Contactor box – main power switching unit
# Left: +114V_IN, -114V_IN
# Right: +114V_OUT (to inverter), -114V_OUT, +12V_OUT, PRECHARGE_OUT
# Top: CB_DRIFT (enable), BMS_KOMM, LADESTART, FORVARMING, LADE
# Bottom: JORD (GND_CLEAN)
defsym("Think:CONTACTOR_BOX", 40, 60,
    lpins=[("+114V_IN","power_in"), ("-114V_IN","power_in")],
    rpins=[("+114V_OUT","power_out"), ("-114V_OUT","power_out"),
           ("+12V_OUT","power_out"), ("PRECHARGE_OUT","power_out")],
    tpins=["CB_RUN", "BMS_CMD", "CHG_START", "PREHEAT", "CHARGE"],
    bpins=["GND"],
    body_label="CONTACTOR\\nBOX",
    ref_pfx="U")

# Motor Controller (Traction inverter / TIM)
# Left: +114V, -114V (HV in)
# Right: L1, L2, L3 (to motor), +12V_BAT, -12V_BAT
# Top: KJOR (drive enable), START (start signal), KJORKLAR (ready),
#      FEIL (fault), EFFEKT (torque cmd), RED_EFFEKT (reduced power),
#      BREMSE_KONTAKT, REVERS, GIRLÅS, DRIFT_MON
# Bottom: K_LINE, L_LINE
defsym("Think:MOTOR_CTRL", 50, 80,
    lpins=[("+114V","power_in"), ("-114V","power_in")],
    rpins=["L1", "L2", "L3",
           ("+12V_BAT","power_out"), ("-12V_BAT","power_out")],
    tpins=["DRIVE", "START", "DRIVE_RDY", "FAULT", "POWER",
           "RED_PWR", "BRAKE_SW", "REVERSE", "GEAR_LOCK", "RAD_FAN"],
    bpins=["K_LINE", "L_LINE"],
    body_label="MOTOR\\nCTRL\\n(TIM)",
    ref_pfx="U")

# 3-phase AC motor
defsym("Think:MOTOR_3PH", 28, 36,
    lpins=["L1", "L2", "L3", ("PE","power_in")],
    body_label="M\\n3~\\nMAIN\\nMOTOR",
    ref_pfx="M")

# BMS (Battery Monitoring System)
# Left: BAT+12V, BAT-12V (local power), CHG_START_IN, DC_LO_PWR
# Right: CHG_STATUS_OK, CHG_START_OUT, BMS_CMD, K_LINE, L_LINE
# Top: CURR_SENSE, BATT_COOLING, TWINNET (current sense inputs)
# Bottom: TEMP1, TEMP2 (temp sensor inputs)
defsym("Think:BMS", 40, 54,
    lpins=["BAT+12V", "BAT-12V", "DC_LO_PWR", "CHG_START_IN"],
    rpins=["CHG_STATUS_OK", "CHG_START_OUT", "BMS_CMD",
           "K_LINE", "L_LINE"],
    tpins=["CURR_SENS+12V", "CURR_SENS-12V", "CURR_SENSE", "BATT_COOLING"],
    bpins=["TEMP1", "TEMP2", "TEMP1_GND", "TEMP2_GND"],
    body_label="BATTERY\\nMONITOR\\n(BMS)",
    ref_pfx="U")

# DC/DC Converter (114V → 12V)
# Left: +114V_IN, -114V_IN (via HV distribution box)
# Right: +12V_OUT, -12V_OUT
# Top: HI_PWR (from motor ctrl), LO_PWR (to BMS)
# Bottom: FAULT output
defsym("Think:DCDC_CONV", 30, 36,
    lpins=[("+114V_IN","power_in"), ("-114V_IN","power_in")],
    rpins=[("+12V_OUT","power_out"), ("-12V_OUT","power_out")],
    tpins=["HI_PWR_IN"],
    bpins=["LO_PWR_OUT", "FAULT"],
    body_label="DC/DC\\nCONVERTER",
    ref_pfx="U")

# Charger (230V AC → 114V DC)
# Left: L1_AC, L2_AC, GND_AC (230V input)
# Right: +114V_DC, -114V_DC (HV output)
# Top: CHG_START, CHG_STATUS_OK (from/to BMS)
# Bottom: K_LINE, L_LINE (RS485 to BMS)
defsym("Think:CHARGER", 30, 40,
    lpins=["L1_AC", "L2_AC", "GND_AC"],
    rpins=[("+114V_DC","power_out"), ("-114V_DC","power_out")],
    tpins=["CHG_START", "CHG_STATUS_OK"],
    bpins=["K_LINE", "L_LINE"],
    body_label="CHARGER\\n(230VAC\\n→114VDC)",
    ref_pfx="U")

# HV Distribution Box
# Distributes 114V HV to Kontaktorboks, DC/DC, Charger
defsym("Think:HV_DIST_BOX", 28, 40,
    lpins=[("+114V_IN","power_in"), ("-114V_IN","power_in")],
    rpins=[("+114V_KONTAK","power_out"), ("-114V_KONTAK","power_out"),
            ("+114V_DCDC","power_out"),   ("-114V_DCDC","power_out"),
            ("+114V_CHRG","power_out"),  ("-114V_CHRG","power_out")],
    body_label="HV\\nDIST\\nBOX",
    ref_pfx="U")

# Gear selector – Park/Reverse/Drive/Free positions with switches
defsym("Think:GEAR_SEL", 22, 36,
    lpins=["GND"],
    rpins=["DRIVE", "REVERSE", "PARK", "FREE"],
    body_label="GEAR\\nSELECTOR",
    ref_pfx="SW")

# Ignition switch – Off/Accessory/Drive/Start
defsym("Think:IGN_SWITCH", 20, 28,
    lpins=["BAT_IN"],
    rpins=["ACCESSORY", "DRIVE_OUT", "START_OUT"],
    body_label="IGN\\nSWITCH",
    ref_pfx="SW")

# Fuse box C01 (simplified – just input/output bus)
# Left: +12V_IN (from battery)
# Right: Fused outputs labeled by fuse number
defsym("Think:FUSE_BOX", 30, 80,
    lpins=[("+12V_IN","power_in")],
    rpins=["F1_30A", "F2_40A", "F3_40A", "F4_40A",
           "F5_30A", "F6_15A", "F7_10A", "F8_25A",
           "F9_15A", "F10_15A", "F11_5A", "F12_10A",
           "F13_15A", "F14_25A", "F15_10A", "F16_10A",
           "F17_10A", "F18_10A", "F22_25A", "F24_20A",
           "F28_20A", "F29_15A", "F30_20A", "F31_15A"],
    body_label="C01\\nFUSE\\nBOX",
    ref_pfx="F")

# Start Inhibit Relay B – prevents start unless conditions met
defsym("Think:START_INHIB_B", 16, 16,
    lpins=["A2_COIL-"],
    rpins=["A2_COIL+"],
    tpins=["3_COM"],
    bpins=["4_NO"],
    body_label="START\\nINHIBIT B",
    ref_pfx="K")

# Radiator fans (two motors)
defsym("Think:RAD_FAN", 20, 16,
    lpins=["1_E11A"],
    rpins=["2_E11A"],
    body_label="RAD\\nFAN",
    ref_pfx="M")

# Coolant pump
defsym("Think:COOLANT_PUMP", 20, 16,
    lpins=["1_E16"],
    rpins=["2_E16"],
    body_label="COOLANT\\nPUMP",
    ref_pfx="M")

# Throttle pedal – analog position + pull signal
defsym("Think:THROTTLE", 24, 28,
    lpins=["+5V_RUN", "ANALOG_GND"],
    rpins=["POSITION", "THROTTLE_PULL"],
    body_label="THROTTLE\\nPEDAL",
    ref_pfx="BP")

# ──────────────────────────────────────────────────────────────
# Layout – A0 page (1189 × 841 mm)
# ──────────────────────────────────────────────────────────────
#
#  Col A (x=60-130):   HV Battery + 250A fuse
#  Col B (x=160-230):  HV Fordelingsboks
#  Col C (x=270-350):  Kontaktorboks
#  Col D (x=400-500):  Motorstyring (TIM inverter)
#  Col E (x=560-620):  Motor
#  Col F (x=700-780):  Fuse box C01 / 12V system
#  Col G (x=820-880):  12V battery + ignition
#
#  Row 1 (y=160-220):  HV power rail
#  Row 2 (y=320-420):  BMS + sensors
#  Row 3 (y=480-560):  DC/DC + charger + HV fordeling
#  Row 4 (y=620-700):  Control signals / gear selector / throttle
#  Row 5 (y=740-800):  Text annotations

# ── HV Battery ──
BT1_X, BT1_Y = 80, 180
place("Think:BATT_HV", "BT1", "114V Traction Battery", BT1_X, BT1_Y)

# ── 250A HV Main Fuse ──
F_HV_X, F_HV_Y = 80, 110
place("Think:FUSE", "F_HV", "250A HV FUSE (Mega)", F_HV_X, F_HV_Y)

# ── HV Distribution Box ──
HVFD_X, HVFD_Y = 200, 180
place("Think:HV_DIST_BOX", "U_HVF", "HV Distribution Box", HVFD_X, HVFD_Y)

# ── Contactor Box ──
KB_X, KB_Y = 330, 180
place("Think:CONTACTOR_BOX", "U_KB", "Contactor Box", KB_X, KB_Y)

# ── Motor Controller (TIM traction inverter) ──
MS_X, MS_Y = 500, 200
place("Think:MOTOR_CTRL", "U_MS", "Motor Controller (TIM)", MS_X, MS_Y)

# ── Traction Motor ──
MOT_X, MOT_Y = 650, 200
place("Think:MOTOR_3PH", "M1", "Main Motor AC", MOT_X, MOT_Y)

# ── DC/DC Converter ──
DCDC_X, DCDC_Y = 200, 420
place("Think:DCDC_CONV", "U_DC", "DC/DC Converter (114V→12V)", DCDC_X, DCDC_Y)

# ── Charger ──
LAD_X, LAD_Y = 380, 420
place("Think:CHARGER", "U_LAD", "Charger (230VAC→114VDC)", LAD_X, LAD_Y)

# ── BMS ──
BMS_X, BMS_Y = 330, 580
place("Think:BMS", "U_BMS", "Battery Monitoring System", BMS_X, BMS_Y)

# ── 12V Auxiliary Battery ──
BT2_X, BT2_Y = 870, 200
place("Think:BATT_12V", "BT2", "12V Battery (E04)", BT2_X, BT2_Y)

# ── Fuse Box C01 ──
FSB_X, FSB_Y = 780, 200
place("Think:FUSE_BOX", "F_C01", "C01 Fuse Box", FSB_X, FSB_Y)

# ── Ignition / Start switch ──
IGN_X, IGN_Y = 900, 470
place("Think:IGN_SWITCH", "SW_IGN", "Ignition Switch (C21-C23)", IGN_X, IGN_Y)

# ── Start Inhibit Relay B ──
SSPB_X, SSPB_Y = 760, 470
place("Think:START_INHIB_B", "K_SSPB", "Start Inhibit Relay B", SSPB_X, SSPB_Y)

# ── Gear Selector ──
GV_X, GV_Y = 640, 470
place("Think:GEAR_SEL", "SW_GV", "Gear Selector (D7)", GV_X, GV_Y)

# ── Throttle Pedal ──
GP_X, GP_Y = 1020, 470
place("Think:THROTTLE", "BP_GP", "Throttle Pedal (C02)", GP_X, GP_Y)

# ── Radiator Fans ──
RVA_X, RVA_Y = 700, 650
place("Think:RAD_FAN", "M_RVA", "Radiator Fan A (E11A)", RVA_X, RVA_Y)
RVB_X, RVB_Y = 700, 680
place("Think:RAD_FAN", "M_RVB", "Radiator Fan B (E11B)", RVB_X, RVB_Y)

# ── Coolant Pump ──
KP_X, KP_Y = 820, 650
place("Think:COOLANT_PUMP", "M_KP", "Coolant Pump (E16)", KP_X, KP_Y)

# ──────────────────────────────────────────────────────────────
# Wiring – HV Power Circuit (sheet 04/13)
# ──────────────────────────────────────────────────────────────

# BT1+ → F_HV → HV_FORDELING +IN
wire(BT1_X, BT1_Y - 16, BT1_X, F_HV_Y + 4)         # battery + up to fuse
wire(F_HV_X + 7, F_HV_Y, HVFD_X - 16, F_HV_Y)       # fuse → HV fordeling top
wire(HVFD_X - 16, F_HV_Y, HVFD_X - 16, HVFD_Y - 20) # down to HV_FORDELING +IN
label(F_HV_X + 7, F_HV_Y, "+114V_FUSED")

# BT1- → HV_FORDELING -IN
wire(BT1_X, BT1_Y + 16, BT1_X, BT1_Y + 35)
wire(BT1_X, BT1_Y + 35, HVFD_X - 16, BT1_Y + 35)
wire(HVFD_X - 16, BT1_Y + 35, HVFD_X - 16, HVFD_Y - 7)
label(BT1_X + 5, BT1_Y + 35, "-114V")

# HV Distribution → Contactor Box
wire(HVFD_X + 16, HVFD_Y - 14, KB_X - 22, HVFD_Y - 14)
wire(HVFD_X + 16, HVFD_Y - 5, KB_X - 22, HVFD_Y - 5)
label(HVFD_X + 16, HVFD_Y - 14, "+114V_KONTAK")
label(HVFD_X + 16, HVFD_Y - 5, "-114V_KONTAK")

# HV Distribution → DC/DC
wire(HVFD_X + 16, HVFD_Y + 4, HVFD_X + 40, HVFD_Y + 4)
wire(HVFD_X + 40, HVFD_Y + 4, DCDC_X - 17, DCDC_Y - 14)
label(HVFD_X + 40, HVFD_Y + 4, "+114V_DCDC")

wire(HVFD_X + 16, HVFD_Y + 13, HVFD_X + 45, HVFD_Y + 13)
wire(HVFD_X + 45, HVFD_Y + 13, DCDC_X - 17, DCDC_Y - 5)
label(HVFD_X + 45, HVFD_Y + 13, "-114V_DCDC")

# HV Distribution → Charger
wire(HVFD_X + 16, HVFD_Y + 22, LAD_X - 17, LAD_Y - 15)
wire(HVFD_X + 16, HVFD_Y + 30, LAD_X - 17, LAD_Y - 7)
label(HVFD_X + 16, HVFD_Y + 22, "+114V_CHRG")
label(HVFD_X + 16, HVFD_Y + 30, "-114V_CHRG")

# Contactor Box → Motor Controller HV
wire(KB_X + 22, KB_Y - 20, MS_X - 27, MS_Y - 30)
wire(KB_X + 22, KB_Y - 10, MS_X - 27, MS_Y - 10)
label(KB_X + 22, KB_Y - 20, "+114V_TO_MS")
label(KB_X + 22, KB_Y - 10, "-114V_TO_MS")

# Motor Controller → Motor L1/L2/L3
for i in range(3):
    my_pin = MS_Y - 16 + i * 11
    mm_pin = MOT_Y - 12 + i * 8
    wire(MS_X + 27, my_pin, MS_X + 45, my_pin)
    wire(MS_X + 45, my_pin, MOT_X - 16, mm_pin)
label(MS_X + 27, MS_Y - 16, "L1")
label(MS_X + 27, MS_Y - 5, "L2")
label(MS_X + 27, MS_Y + 6, "L3")

# Motor PE → Chassis GND
wire(MOT_X - 16, MOT_Y + 14, MOT_X - 30, MOT_Y + 14)
label(MOT_X - 30, MOT_Y + 14, "CHASSIS_GND")

# ──────────────────────────────────────────────────────────────
# Wiring – 12V system
# ──────────────────────────────────────────────────────────────

# BT2 → Fuse box +12V
wire(BT2_X, BT2_Y - 12, BT2_X, BT2_Y - 30)
wire(BT2_X, BT2_Y - 30, FSB_X + 17, BT2_Y - 30)
wire(FSB_X + 17, BT2_Y - 30, FSB_X + 17, FSB_Y - 40)
label(BT2_X - 10, BT2_Y - 30, "+12V_ALWAYS")

wire(BT2_X, BT2_Y + 12, BT2_X, BT2_Y + 30)
label(BT2_X - 10, BT2_Y + 30, "CHASSIS_GND")

# DC/DC → BT2 (charging 12V battery)
wire(DCDC_X + 17, DCDC_Y - 9, DCDC_X + 55, DCDC_Y - 9)
label(DCDC_X + 55, DCDC_Y - 9, "+12V_ALWAYS")
wire(DCDC_X + 17, DCDC_Y, DCDC_X + 60, DCDC_Y)
label(DCDC_X + 60, DCDC_Y, "CHASSIS_GND")

# DC/DC high power enable from Motor Controller
wire(MS_X - 27, MS_Y + 35, MS_X - 60, MS_Y + 35)
label(MS_X - 60, MS_Y + 35, "DC_HI_PWR")
wire(DCDC_X, DCDC_Y - 20, DCDC_X, DCDC_Y - 30)
label(DCDC_X, DCDC_Y - 30, "DC_HI_PWR")

# DC/DC LO_PWR → BMS
wire(DCDC_X, DCDC_Y + 20, DCDC_X, DCDC_Y + 35)
label(DCDC_X, DCDC_Y + 35, "DC_LO_PWR")
wire(BMS_X - 22, BMS_Y - 22, BMS_X - 50, BMS_Y - 22)
label(BMS_X - 50, BMS_Y - 22, "DC_LO_PWR")

# ──────────────────────────────────────────────────────────────
# Wiring – BMS connections (sheet 03/11)
# ──────────────────────────────────────────────────────────────

# BMS ← +12V / -12V (from contactor box)
wire(KB_X + 22, KB_Y + 5, KB_X + 70, KB_Y + 5)
label(KB_X + 70, KB_Y + 5, "+12V_KB")
wire(BMS_X - 22, BMS_Y - 14, BMS_X - 50, BMS_Y - 14)
label(BMS_X - 50, BMS_Y - 14, "+12V_KB")

# BMS CMD → Contactor Box
wire(BMS_X + 22, BMS_Y - 8, BMS_X + 60, BMS_Y - 8)
label(BMS_X + 60, BMS_Y - 8, "BMS_CMD")
wire(KB_X, KB_Y + 12, KB_X, KB_Y + 50)
label(KB_X, KB_Y + 50, "BMS_CMD")

# BMS CHG_START → Charger
wire(BMS_X + 22, BMS_Y - 16, BMS_X + 80, BMS_Y - 16)
label(BMS_X + 80, BMS_Y - 16, "CHG_START")
wire(LAD_X, LAD_Y - 22, LAD_X, LAD_Y - 40)
label(LAD_X, LAD_Y - 40, "CHG_START")

# BMS K/L-line → Motor Controller
wire(BMS_X + 22, BMS_Y + 10, BMS_X + 100, BMS_Y + 10)
label(BMS_X + 100, BMS_Y + 10, "K_LINE")
wire(MS_X, MS_Y + 42, MS_X, MS_Y + 60)
label(MS_X, MS_Y + 60, "K_LINE")

# ──────────────────────────────────────────────────────────────
# Wiring – Control signals (sheet 05/06)
# ──────────────────────────────────────────────────────────────

# Ignition DRIVE → Start Inhibit → Motor Controller DRIVE
wire(IGN_X - 12, IGN_Y + 5, SSPB_X + 10, IGN_Y + 5)
label(SSPB_X + 10, IGN_Y + 5, "15_DRIVE")

wire(SSPB_X, SSPB_Y - 10, SSPB_X, SSPB_Y - 25)
label(SSPB_X, SSPB_Y - 25, "DRIVE_TO_MC")
wire(MS_X, MS_Y - 42, MS_X, MS_Y - 60)
label(MS_X, MS_Y - 60, "DRIVE_TO_MC")

# Ignition START → Motor Controller START
wire(IGN_X - 12, IGN_Y + 14, IGN_X - 35, IGN_Y + 14)
label(IGN_X - 35, IGN_Y + 14, "50_START")
wire(MS_X + 5, MS_Y - 42, MS_X + 5, MS_Y - 60)
label(MS_X + 5, MS_Y - 60, "50_START")

# Gear selector → Motor Controller
wire(GV_X + 13, GV_Y - 12, GV_X + 40, GV_Y - 12)
label(GV_X + 40, GV_Y - 12, "GV_DRIVE")
wire(MS_X + 20, MS_Y - 42, MS_X + 20, MS_Y - 60)
label(MS_X + 20, MS_Y - 60, "GV_DRIVE")

wire(GV_X + 13, GV_Y - 2, GV_X + 45, GV_Y - 2)
label(GV_X + 45, GV_Y - 2, "GV_REVERSE")
wire(MS_X - 5, MS_Y - 42, MS_X - 5, MS_Y - 60)
label(MS_X - 5, MS_Y - 60, "GV_REVERSE")

# Throttle pedal → Motor Controller
wire(GP_X - 14, GP_Y - 8, GP_X - 40, GP_Y - 8)
label(GP_X - 40, GP_Y - 8, "+5V_RUN")
wire(GP_X + 14, GP_Y - 8, GP_X + 35, GP_Y - 8)
label(GP_X + 35, GP_Y - 8, "THROTTLE_PULL")
wire(MS_X + 15, MS_Y - 42, MS_X + 15, MS_Y - 65)
label(MS_X + 15, MS_Y - 65, "THROTTLE_PULL")

# Motor Controller FAULT → label
wire(MS_X - 10, MS_Y - 42, MS_X - 10, MS_Y - 70)
label(MS_X - 10, MS_Y - 70, "MC_FAULT")

# Motor Controller → Radiator fans
wire(MS_X + 25, MS_Y - 42, MS_X + 25, MS_Y - 55)
label(MS_X + 25, MS_Y - 55, "RAD_FAN_CMD")
wire(RVA_X - 12, RVA_Y, RVA_X - 30, RVA_Y)
label(RVA_X - 30, RVA_Y, "RAD_FAN_CMD")

# ──────────────────────────────────────────────────────────────
# Text annotations
# ──────────────────────────────────────────────────────────────

text(50, 760, "THINK CITY – ELECTRICAL SYSTEM OVERVIEW", 2.0)
text(50, 772, "Source: think-300dpi_koblingsskema.pdf (Semcon/Think Nordic, ~2000)", 1.1)
text(50, 779, "Drawing no: 05125-01-105 (LV EDS) / 05125-02-031 (HV Box)", 1.1)

text(50, 790, "KEY SYSTEMS:", 1.3)
text(50, 797, "Sheet 01-02: C01 Fuse Box, Ignition Switch", 1.0)
text(50, 803, "Sheet 03-04: Contactor Box (main/aux/precharge relays), 114V battery, motor", 1.0)
text(50, 809, "Sheet 05-07: Motor Controller (TIM traction inverter) control signals, gear lock", 1.0)
text(50, 815, "Sheet 08-09: Throttle pedal, gear selector, regen braking, 230V relay", 1.0)
text(50, 821, "Sheet 10-11: DC/DC converter, BMS, battery sensors, charger cooling", 1.0)
text(50, 827, "Sheet 12-13: Charger, HV distribution box, 230V AC input", 1.0)
text(50, 833, "HV Box dwg 05125-02-031: Contactor box internal (precharge circuit, LEM LA-205-S)", 1.0)

text(650, 760, "FUSE BOX C01 (selected fuses):", 1.3)
fuses = [
    ("F1 30A", "Heated windscreen"),
    ("F2 40A", "Power to light switch / High beams / Low beams / Horn"),
    ("F3 40A", "Additional heater (Webasto)"),
    ("F4 40A", "Ignition lock"),
    ("F5 30A", "Ventilation fan motor (heater)"),
    ("F6 15A", "Radiator cooling fan"),
    ("F10 15A","Water pump (during charging)"),
    ("F11 5A", "Start function"),
    ("F12 10A","Brake lights"),
    ("F22 25A","Brake vacuum pump"),
    ("F28 20A","Power supply: drive system / Charger / Contactor Box"),
    ("F29 15A","Water pump (during driving)"),
    ("F30 20A","Alarm / Diagnostic / Radio / Instrument"),
]
for i, (fn, desc) in enumerate(fuses):
    text(650, 770 + i*5, f"{fn:8s}  {desc}", 0.9)

text(50, 720, "RELAY LIST (R1-R18, DIN 72551/72552):", 1.2)
relays = [
    "R1:Wiper(Mini Timer)  R2:Heated screen(Mini)  R3:Flasher(Mini Flasher)",
    "R4:Charge cooling     R5:DRL                  R6:Cluster timer pre-heat",
    "R7:Reverse lamp       R8/R9/R10:Gear lock      R11:Radiator fans",
    "R12:Blower motor      R13:Tailgate release     R14/R15:Recirc motor",
    "R16:Combustion heater  R17/R18: (spare)",
]
for i, r in enumerate(relays):
    text(50, 728 + i*5, r, 0.95)

# ──────────────────────────────────────────────────────────────
# Assemble and write
# ──────────────────────────────────────────────────────────────

out = []
out.append('(kicad_sch (version 20241209) (generator "python_gen") (generator_version "9.0")')
out.append('  (paper "A0")')
out.append('  (title_block')
out.append('    (title "Think City EV – Main Electrical Systems Overview")')
out.append('    (date "2026-03-22")')
out.append('    (rev "1")')
out.append('    (company "Think Nordic / Semcon")')
out.append('    (comment 1 "Based on koblingsskjema PDF (Drawing 05125-01-105 / 05125-02-031)")')
out.append('    (comment 2 "Sheets 01-13: power, BMS, motor controller, 12V system")')
out.append('    (comment 3 "HV: 114V nominal traction battery")')
out.append('    (comment 4 "DANGER: High voltage traction system. Service by qualified personnel only.")')
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
