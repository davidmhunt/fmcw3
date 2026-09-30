"""Build parts.csv (one row per BOM group in bom_pcb.csv) for the fmcw3 BOM.

Run from the fmcw3 repo root:  python parts/gen_parts_csv.py
Needs `kicad-cli` (netlist export, used only to infer rail voltages for caps).
This script is the source of truth for parts.csv: the curated MPN table and the
inference rules are below. Nothing here touches the .kicad_* files.

kind:
  mpn      part has (or needs) an exact manufacturer part number; looked up on DigiKey
  generic  passive/connector known only by value+footprint: spec only, NO MPN suggested
  dnp      footprint marked DNP in the schematic: not sourced
  nopart   PCB feature or mechanical item (via, test point, mounting hole, printed coupler)
Spec columns (generic rows): values that are NOT in the schematic are labelled
"unspecified" (tolerance, dielectric) or "(inferred)" (minimum voltage).  *_hint
columns are suggestions for David, never applied to the schematic.
"""
import csv
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ---- curated exact-MPN parts: key = first ref of the BOM group -------------------
# (search_term, candidates "A|B", needs_david, notes)
MPN = {
    "U1": ("ADF4158CCPZ", "", "", "PLL; MPN from schematic manf# field"),
    "U2": ("LP5907MFX-1.8/NOPB", "", "", "LDO; MFX = SOT-23-5 (matches footprint)"),
    "U20": ("LP5907MFX-3.0/NOPB", "", "", "LDO; MFX = SOT-23-5"),
    "U21": ("LP2985A-10DBVR", "", "", "LDO, 1.0 V fixed; value field is the full MPN"),
    "U22": ("TPS7A9101DSKT", "", "", "adjustable LDO (FB nets present), DSK = 10-SON 2.5x2.5; DSKR is the same die in 3000-pc reel"),
    "U25": ("MIC5301-3.3YD5-TR", "", "", "3.3 V LDO; footprint SOT-23-5 -> YD5 (TSOT-23-5); the old YMT pick was 6-pin 1.6x1.6 MLF, wrong package"),
    "U17": ("L7980TR", "", "", "buck; footprint DFN-8-1EP 3x3 -> L7980 (VFQFPN 3x3); the old L7980ATR pick was HSOP8, wrong package"),
    "U3": ("PAT1220-C-6DB-T5", "", "", "Susumu 0805 attenuator: C=50 ohm, 06=6 dB, T5=tape"),
    "U4": ("", "KT2520K26000ZAW18TAS|KT2520K40000DAW18TAS|KT2520K37400ZAW18TBS|KT2520K38400ZAW18TES|KT2520K16369ACW18TAS", "needs-David",
           "TCXO: frequency and stability not in schematic or docs; supply is 1.8 V (net 1V8_OSC) so only 1.8 V variants listed; family mostly Obsolete"),
    "U5": ("NC7S04P5X", "", "", ""),
    "U6": ("NB3N551MNR4G", "", "", "clock buffer; DFN-8 2x2 footprint (onsemi 506CN) -> MN variant, only DFN8 orderable code"),
    "U7": ("TLV172IDCKR", "", "", "value TLV172DCK; I grade, SC70-5 reel"),
    "U8": ("", "LTC2292CUP#PBF|LTC2292IUP#PBF", "needs-David", "dual ADC, 64-QFN 9x9 = UP package; C (0-70 C) vs I (-40-85 C) grade not in schematic"),
    "U9": ("TRF37A73IDSGR", "", "", "RF amp, WSON-8 2x2; IDSGT is the 250-pc reel of the same part"),
    "U10": ("HMC431LP4ETR", "", "", "VCO; MPN from schematic manf# field"),
    "U11": ("SKY65404-31", "", "", "LNA 4.9-5.9 GHz"),
    "U14": ("MGA-25203-BLKG", "", "", "PA; MPN from schematic manf# field"),
    "U15": ("CONSMA003.062", "", "", "Linx edge-launch SMA"),
    "P1": ("CONSMA003.062", "", "", "Linx edge-launch SMA (same footprint as U15)"),
    "U26": ("5400BL15B0050001E", "", "", "Johanson balun; 050 = 50 ohm balanced (0100/0200 are 100/200 ohm variants)"),
    "U29": ("ADL5802ACPZ-R7", "", "", "mixer; only A-grade LFCSP-24 4x4 orderable code"),
    "U30": ("XC7A15T-1FTG256C", "", "", "Artix-7 FPGA; 7 schematic units A-G = 1 physical part"),
    "U31": ("", "10118194-0001LF|0473460001|1050170001|629105136821", "needs-David",
            "micro-B USB receptacle; footprint USB_MICRO is 5 pads at 0.65 mm pitch (0.4x1.35) plus shield pads; no MPN anywhere in the design; compare footprint to candidate drawings"),
    "U32": ("93LC46BT-I/OT", "", "", "EEPROM, SOT-23-6 = OT package; I temp grade chosen as default (E/OT also exists)"),
    "U33": ("FT2232HL-REEL", "", "", "USB bridge, LQFP-64 10x10 = HL; FT2232HL-TRAY is the tray pack"),
    "U34": ("ADA4940-2ACPZ-R7", "", "", "dual ADC driver, LFCSP-24; U34/U35 are 2 physical ICs (units A,B each); -R2/-RL are other reel sizes"),
    "U40": ("W25Q32JVZPIQ", "", "", "DFN-S-8 6x5 = WSON-8 (ZP)"),
    "Y1": ("ABM10-167-12.000MHZ-T3", "", "", "crystal"),
    "Q1": ("RE1C002UNTCL", "", "", "MOSFET SOT-416FL; TCL = taping"),
    "D2": ("SS13FL", "", "", "Schottky SOD-123F"),
    "FB1": ("BLM18PG181SN1D", "", "", "ferrite"),
    "FB4": ("CIC21P101NE", "", "", "ferrite"),
    "L1": ("LQW15AN9N9J80D", "", "", "9.9 nH RF inductor"),
    "L5": ("SRR6040A-330M", "", "", "33 uH buck inductor"),
    "CON1": ("DM3BT-DSF-PEJS", "", "", "SD card socket"),
    "CON2": ("EJ508A", "", "", "barrel jack"),
    "SW2": ("EVP-AWBA2A", "", "", "tactile switch"),
}
QTY_OVERRIDE = {"U34": 2, "U30": 1}     # units counted as parts in the BOM export
NOPART_REFS = {"F1", "P5", "P6", "Z1"}   # first refs of nopart groups
NOPART_NOTE = {"F1": "RF via footprint (PCB feature)", "P5": "M3 mounting hole (mechanical)",
               "P6": "1 mm test-point pad (PCB feature)", "Z1": "printed 15 dB coupler (PCB copper, footprint 'coupler')"}
GENERIC_CONN = {"P3": "2x4 2.54 mm SMD pin header, footprint Pin_Header_Straight_2x04_Pitch2.54mm_SMD; MPN to be picked by David"}

RAIL_V = {"12V": 15.0}  # 12 V input; docs/hardware/fmcw3/fmcw3_integration.md: RT6236 6-15 V in
E96 = set("""100 102 105 107 110 113 115 118 121 124 127 130 133 137 140 143 147 150 154 158 162 165 169 174
178 182 187 191 196 200 205 210 215 221 226 232 237 243 249 255 261 267 274 280 287 294 301 309 316 324
332 340 348 357 365 374 383 392 402 412 422 432 442 453 464 475 487 499 511 523 536 549 562 576 590 604
619 634 649 665 681 698 715 732 750 768 787 806 825 845 866 887 909 931 953 976""".split())
E24 = set("""100 110 120 130 150 160 180 200 220 240 270 300 330 360 390 430 470 510 560 620 680 750 820 910""".split())
RF_NET = re.compile(r"RFIN|RFOUT|RF_IN|RF_OUT|LOIP|LOIN|/LO$|/RF\d$|U15-Pad1|U3-Pad2|U12-Pad2|U14-RF|U2[678]-OUT|U29-(LO|RF)|U1[16]-RF|R11-Pad|C11-Pad1|R17-Pad2")


RF_FORCE = {"L2", "L4"}  # 0.6 nH LNA bias chokes (supply side of U11/U16 but RF-critical)


def parse_val(s, unit):
    m = re.fullmatch(r"([\d.]+)\s*([pnuµm]?)", s.strip())
    if not m:
        return None
    return float(m.group(1)) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1}[m.group(2)]


def fmt_cap(s):
    return s.replace("p", " pF").replace("n", " nF").replace("u", " uF")


def fmt_res(s):
    if s.endswith("k"):
        return s[:-1] + " kohm"
    return s + " ohm"


def pkg(fp):
    m = re.search(r"(0402|0603|0805|1206|1210)", fp)
    return m.group(1) if m else fp


def net_voltage(name):
    base = name.split("/")[-1]
    if base in RAIL_V:
        return RAIL_V[base]
    m = re.fullmatch(r"(\d+)V(\d?)(?:[A-Z_].*)?", base)
    if m:
        return float(m.group(1) + ("." + m.group(2) if m.group(2) else ""))
    if base == "USB_5V":
        return 5.0
    return None


def min_rating(v):
    need = 1.5 * v
    for r in (6.3, 10, 16, 25, 35, 50):
        if need <= r:
            return r
    return 100


SW_NODES = ("Net-(D2-K)", "Net-(D3-K)", "Net-(D4-K)")  # buck switch nodes swing to Vin (12 V rail)
VALS = {}


def series_ok(ref):
    """Propagate a rail only through series supply parts: ferrites, inductors, R <= 100 ohm.
    Bigger resistors form dividers (e.g. EN, FB nodes) whose node voltage is not the rail."""
    if ref.startswith(("FB", "L")):
        return True
    v = parse_val(VALS.get(ref, "x"), "ohm") if ref.startswith("R") else None
    return v is not None and v <= 100


def load_nets():
    with tempfile.TemporaryDirectory() as td:
        xml = Path(td) / "n.xml"
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadxml",
                        "-o", str(xml), str(ROOT / "hardware" / "fmcw3.kicad_sch")],
                       check=True, capture_output=True)
        t = ET.parse(xml).getroot()
    comps = {c.get("ref"): {"nets": {}} for c in t.find("components")}
    for c in t.find("components"):
        VALS[c.get("ref")] = c.findtext("value") or ""
    for n in t.find("nets"):
        for nd in n.findall("node"):
            comps.setdefault(nd.get("ref"), {"nets": {}})["nets"][nd.get("pin")] = n.get("name")
    # propagate rail voltage through series R / ferrite / inductor
    volt = {}
    for c in comps.values():
        for n in c["nets"].values():
            v = net_voltage(n)
            if v is not None:
                volt[n] = v
    for n in SW_NODES:
        volt[n] = RAIL_V["12V"]
    changed = True
    while changed:
        changed = False
        for ref, c in comps.items():
            if re.match(r"(R|FB|L)\d", ref) and len(c["nets"]) == 2 and series_ok(ref):
                a, b = c["nets"].values()
                for x, y in ((a, b), (b, a)):
                    if y != "GND" and y not in SW_NODES and x not in SW_NODES and x in volt and volt[x] > volt.get(y, 0):
                        volt[y] = volt[x]
                        changed = True
    return comps, volt


def expand(refs):
    out = []
    for tok in refs.split(","):
        m = re.fullmatch(r"([A-Z]+)(\d+)-\1(\d+)", tok)
        if m:
            out += [f"{m.group(1)}{i}" for i in range(int(m.group(2)), int(m.group(3)) + 1)]
        else:
            out.append(tok)
    # multi-unit parts appear as U30A?..U30G? / U34A? etc.: collapse units to the physical ref
    out = [re.sub(r"^([A-Z]+\d+)[A-G]\?$", r"\1", x) for x in out]
    return list(dict.fromkeys(out))


def main():
    comps, volt = load_nets()
    cols = ["refs", "qty", "value", "footprint", "kind", "search_term", "candidates", "needs_david",
            "package", "tolerance", "voltage", "dielectric", "tolerance_hint", "dielectric_hint", "notes"]
    rows = []
    def vmax_of(x):
        return max([volt.get(n, 0) for n in comps[x]["nets"].values()] + [0])

    def isrf(x):
        return x in RF_FORCE or any(RF_NET.search(n) for n in comps[x]["nets"].values())

    groups = []
    for g in csv.DictReader((HERE / "bom_pcb.csv").open()):
        refs = expand(g["Refs"])
        kl = re.match(r"[A-Z]+", refs[0]).group(0)
        if kl in ("C", "R", "L") and refs[0] not in MPN and not g["Value"].startswith("DNP"):
            # split a BOM group into RF-path / non-RF members (and, for caps, by inferred rating class)
            key = (lambda x: (isrf(x), 0 if isrf(x) or kl != "C" else (min_rating(vmax_of(x)) if vmax_of(x) else 0)))
            sub = {}
            for x in refs:
                sub.setdefault(key(x), []).append(x)
            for k in sorted(sub):
                groups.append((dict(g, Qty=str(len(sub[k]))), sub[k]))
        else:
            groups.append((g, refs))
    for g, refs in groups:
        first, val, fp = refs[0], g["Value"], g["Footprint"]
        r = dict.fromkeys(cols, "")
        r.update(refs=";".join(refs), qty=QTY_OVERRIDE.get(first, int(g["Qty"])), value=val, footprint=fp)
        kind_letter = re.match(r"[A-Z]+", first).group(0)
        if first in MPN:
            st, cand, nd, note = MPN[first]
            r.update(kind="mpn", search_term=st, candidates=cand, needs_david=nd, notes=note)
        elif first in NOPART_REFS:
            r.update(kind="nopart", notes=NOPART_NOTE[first])
        elif val.startswith("DNP"):
            r.update(kind="dnp", notes="DNP in schematic: footprint only, not sourced")
        elif first in GENERIC_CONN:
            r.update(kind="generic", package="SMD 2x4 2.54 mm", tolerance="n/a", notes=GENERIC_CONN[first])
        elif kind_letter == "C":
            r.update(kind="generic", package=pkg(fp), tolerance="unspecified", dielectric="unspecified", value=fmt_cap(val))
            vs = [max([volt.get(n, 0) for n in comps[x]["nets"].values()] + [0]) for x in refs]
            vmax = max(vs)
            if vmax > 0:
                rail = [n for x in refs for n in comps[x]["nets"].values() if volt.get(n) == vmax][0]
                r["voltage"] = f">={min_rating(vmax):g} V (inferred: {vmax:g} V on {rail.split('/')[-1]})"
            else:
                r["voltage"] = ">=6.3 V (inferred default: no supply rail on these nets)"
            cv = parse_val(val, "F")
            if cv < 1e-9:
                r["dielectric_hint"] = "C0G/NP0"
            elif cv <= 1e-6:
                r["dielectric_hint"] = "X7R"
            else:
                r["dielectric_hint"] = "X5R or X7R"
            if first in ("C208",):
                r["dielectric_hint"] = "C0G/NP0 (crystal load caps)"
            r["tolerance_hint"] = ""
            r["notes"] = ""
        elif kind_letter == "R":
            digits = re.sub(r"\D", "", val.replace("k", "")).lstrip("0")
            digits = (digits + "00")[:3] if digits else ""
            r.update(kind="generic", package=pkg(fp), tolerance="unspecified", value=fmt_res(val),
                     notes="power rating not in schematic (0402 default 1/16 W)")
            if val == "0":
                r["tolerance_hint"] = "0 ohm jumper"
            elif digits in E96:
                r["tolerance_hint"] = "E96 value, 1% implied"
            elif digits in E24:
                r["tolerance_hint"] = "E24 value, 5% implied"
            else:
                r["tolerance_hint"] = "value outside E24/E96"
        elif kind_letter == "L":
            r.update(kind="generic", package=pkg(fp), tolerance="unspecified", value=fmt_cap(val).replace("pF", "pH").replace("nF", "nH").replace("uF", "uH"),
                     notes="current/saturation rating, DCR, SRF not in schematic")
        elif kind_letter == "D":
            r.update(kind="generic", package="0603", tolerance="n/a", notes="LED: colour, Vf, current not in schematic")
        else:
            r.update(kind="generic", notes="unclassified")
        # RF-critical flag (value-only parts on RF nets)
        if r["kind"] == "generic" and kind_letter in "CRL":
            rf = any(isrf(x) for x in refs)
            if rf:
                r["needs_david"] = "needs-David"
                r["notes"] = (r["notes"] + "; " if r["notes"] else "") + "RF-path part given by value only: vendor/series/tolerance/SRF decide performance"
        rows.append(r)
    with (HERE / "parts.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows")


if __name__ == "__main__":
    main()
