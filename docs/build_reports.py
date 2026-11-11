"""Build the two Word reports on the 2026-11-11 simulation work.

    sim/sil/.venv/Scripts/python docs/build_reports.py

Writes (into docs/):
    MPPT_simulation_report_technical.docx   - technical, presentation-ready summary
    MPPT_simulation_explained.docx          - plain-language guide for a teammate new to the project
All numbers come from the committed results (docs/simulation_results.md, sim/*/results/).
"""
import os

from docx import Document
from docx.enum.section import WD_ORIENT  # noqa: F401  (kept for future landscape pages)
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
LT = os.path.join(ROOT, "sim", "ltspice", "results")
SIL = os.path.join(ROOT, "sim", "sil", "results")

NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREY = RGBColor(0x52, 0x51, 0x4E)
HEAD_FILL = "1F3A5F"
ZEBRA = "F2F5F9"
NOTE_FILL = "EEF4FB"
WARN_FILL = "FDF3E7"


# ======================================================================== helpers
def new_doc(title, subtitle, date_line):
    d = Document()
    sec = d.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)         # A4
    for side in ("left_margin", "right_margin"):
        setattr(sec, side, Cm(2.2))
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(2.0)

    st = d.styles
    st["Normal"].font.name = "Calibri"
    st["Normal"].font.size = Pt(10.5)
    st["Normal"].paragraph_format.space_after = Pt(5)
    st["Normal"].paragraph_format.line_spacing = 1.12
    rpr = st["Normal"].element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.append(rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), "Calibri")
    for name, size, before, after in (("Heading 1", 16, 16, 6), ("Heading 2", 12.5, 12, 4), ("Heading 3", 11, 8, 2)):
        s = st[name]
        s.font.name, s.font.size, s.font.bold, s.font.color.rgb = "Calibri", Pt(size), True, NAVY
        s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(before), Pt(after)
        s.paragraph_format.keep_with_next = True
        r = s.element.get_or_add_rPr()
        f = r.find(qn("w:rFonts"))
        if f is None:
            f = OxmlElement("w:rFonts")
            r.append(f)
        for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            f.set(qn(a), "Calibri")
    for name in ("List Bullet", "List Number"):
        st[name].font.size = Pt(10.5)
        st[name].paragraph_format.space_after = Pt(3)

    # title block
    p = d.add_paragraph()
    p.paragraph_format.space_before = Pt(36)
    r = p.add_run(title)
    r.bold, r.font.size, r.font.color.rgb = True, Pt(24), NAVY
    p = d.add_paragraph()
    r = p.add_run(subtitle)
    r.font.size, r.font.color.rgb = Pt(13), GREY
    p = d.add_paragraph()
    r = p.add_run(date_line)
    r.font.size, r.font.color.rgb = Pt(10), GREY
    rule(d)

    # footer: page number
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = fp.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)
    run.font.size, run.font.color.rgb = Pt(9), GREY
    return d


def rule(d):
    p = d.add_paragraph()
    ppr = p._p.get_or_add_pPr()
    b = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", "8"), ("w:space", "1"), ("w:color", HEAD_FILL)):
        bottom.set(qn(k), v)
    b.append(bottom)
    ppr.append(b)


def para(d, text, bold_prefix=None, italic=False, size=None, color=None, after=None):
    p = d.add_paragraph()
    if bold_prefix:
        p.add_run(bold_prefix).bold = True
    r = p.add_run(text)
    r.italic = italic
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    return p


def rich(d, parts, style=None):
    """parts: list of (text, bold) tuples in one paragraph."""
    p = d.add_paragraph(style=style)
    for text, b in parts:
        p.add_run(text).bold = b
    return p


def bullets(d, items, numbered=False):
    for it in items:
        if isinstance(it, tuple):
            rich(d, [(it[0], True), (it[1], False)], style="List Number" if numbered else "List Bullet")
        else:
            d.add_paragraph(it, style="List Number" if numbered else "List Bullet")


def shade(cell, fill):
    tcpr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), fill)
    tcpr.append(sh)


def keep_together(t):
    """Stop a table splitting across pages: rows can't break, and every row is kept with the next one."""
    n = len(t.rows)
    for i, tr in enumerate(t.rows):
        trpr = tr._tr.get_or_add_trPr()
        cs = OxmlElement("w:cantSplit")
        cs.set(qn("w:val"), "true")
        trpr.append(cs)
        if i < n - 1:
            for c in tr.cells:
                for p in c.paragraphs:
                    p.paragraph_format.keep_with_next = True


def table(d, header, rows, widths_cm, font=9, bold_first_col=False):
    t = d.add_table(rows=1 + len(rows), cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, w in enumerate(widths_cm):
        t.columns[i].width = Cm(w)
    for r_i, row in enumerate([header] + rows):
        tr = t.rows[r_i]
        if r_i == 0:   # repeat header row on page breaks
            trpr = tr._tr.get_or_add_trPr()
            h = OxmlElement("w:tblHeader")
            h.set(qn("w:val"), "true")
            trpr.append(h)
        for c_i, val in enumerate(row):
            cell = tr.cells[c_i]
            cell.width = Cm(widths_cm[c_i])
            cell.text = ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.space_before = Pt(1)
            txt, bold = (val if isinstance(val, tuple) else (str(val), False))
            run = p.add_run(txt)
            run.font.size = Pt(font)
            if r_i == 0:
                run.bold = True
                run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
                shade(cell, HEAD_FILL)
            else:
                run.bold = bold or (bold_first_col and c_i == 0)
                if r_i % 2 == 0:
                    shade(cell, ZEBRA)
    keep_together(t)
    d.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def box(d, title, lines, fill=NOTE_FILL, width_cm=16.6):
    t = d.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    t.columns[0].width = Cm(width_cm)
    c = t.rows[0].cells[0]
    c.width = Cm(width_cm)
    shade(c, fill)
    tcpr = c._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "single" if side == "left" else "nil")
        if side == "left":
            e.set(qn("w:sz"), "24")
            e.set(qn("w:color"), HEAD_FILL if fill == NOTE_FILL else "E59A3C")
        borders.append(e)
    tcpr.append(borders)
    p = c.paragraphs[0]
    r = p.add_run(title)
    r.bold, r.font.color.rgb = True, NAVY
    for ln in lines:
        q = c.add_paragraph()
        q.paragraph_format.space_after = Pt(2)
        if isinstance(ln, tuple):
            q.add_run(ln[0]).bold = True
            q.add_run(ln[1])
        else:
            q.add_run(ln)
    keep_together(t)
    for q in c.paragraphs[:-1]:
        q.paragraph_format.keep_together = True
    d.add_paragraph().paragraph_format.space_after = Pt(2)


def figure(d, path, caption, width_cm=16.0):
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(path, width=Cm(width_cm))
    c = d.add_paragraph()
    c.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = c.add_run(caption)
    r.italic, r.font.size, r.font.color.rgb = True, Pt(9), GREY


def page_break(d):
    d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ======================================================================== technical report
def technical():
    d = new_doc("MPPT Solar Charger: Simulation Results",
                "STM32F401 synchronous-buck MPPT charger, technical summary of the 11 Nov 2026 work",
                "Status: designed and simulated. No hardware built, no bench data; nothing here is hardware-validated.")

    d.add_heading("1. Summary", level=1)
    bullets(d, [
        ("Power stage (LTspice v1.5 to v1.8): ", "the maximum power point is at D = 0.68 (12 V battery) and D = 0.80 "
         "(14.4 V), inside the 0.60 to 0.85 clamp range, with the decided 100 kHz / 300 ns / Schottky / IRF3205 / IR2110 "
         "configuration. Panel to battery efficiency in the most realistic model (v1.8): 94.1 % at the 12 V MPP."),
        ("Dead time: ", "a driver-level study (v1.7) showed shoot-through at 200 ns, caused mainly by a Miller kick on the "
         "low-side gate. Dead time was changed to 300 ns (DECIDED). 300 ns plus a 2.2 nF gate-source capacitor removes "
         "the overlap at typical driver timing (capacitor still PROPOSED)."),
        ("Firmware: ", "Perturb & Observe tracker and a six-state charge state machine (float32, no HAL, no heap). "
         "Compiles for the Cortex-M4F with zero warnings; not yet run on the MCU."),
        ("Software-in-the-loop: ", "the same C files driven by an averaged plant calibrated to LTspice. Tracking "
         "efficiency 99.88 to 99.98 %, correct CC / CV / float sequence, night shutdown and latched fault all behave "
         "as designed."),
        ("Reproducibility: ", "one command (sh setup.sh --test) rebuilds everything on another PC and checks the "
         "results match."),
    ])

    d.add_heading("2. Design baseline (DECIDED)", level=1)
    para(d, "Values set by the user and cross-checked against the datasheets in the repository. None is contradicted "
            "by a datasheet.")
    table(d, ["Parameter", "Value", "Basis / datasheet check"], [
        ["Switching frequency", "100 kHz", "TIM1 ARR = 419, centre-aligned, 420 counts"],
        ["Dead time", ("300 ns", True), "TIM1 DTG = 0x19 (297.6 ns). Changed from 200 ns after v1.7 (Section 4.3)"],
        ["Duty limits", "0.60 / 0.85", "MPP must lie inside; low-side on-time at 0.85 = 0.9 µs"],
        ["PV input", "Series Schottky", "Blocks reverse current at night (part not yet chosen)"],
        ["Charge current limit", "0.6 A", "Amptek AT-series sheet: < 0.28 C (scaled from the 1.3 Ah model)"],
        ["Absorption / float", "14.4 V / 13.6 V", "Amptek: cycle 14.4 to 15.0 V, standby 13.5 to 13.8 V"],
        ["P&O step / period", "1 count (0.24 %) / 20 ms", "Longer than the INA219 conversion time (about 4.3 ms)"],
        ["MOSFET model", "IRF3205 vendor model, unmodified", "Ciss 3.6 nF in model vs 3247 pF datasheet"],
    ], [3.6, 4.0, 9.0], bold_first_col=True)

    d.add_heading("3. LTspice versions", level=1)
    table(d, ["Version", "What changed", "Purpose"], [
        ["1.4 (previous)", "50 kHz, 100 ns, IRFZ44N stand-in, no input diode", "Starting point"],
        ["1.5", "100 kHz, 200 ns, Schottky at PV input, 12 V and 14.4 V battery", "Hardware frequency, reverse blocking"],
        ["1.6", "IRF3205 vendor SPICE model", "Real MOSFET"],
        ["1.7", "IR2110 delays + output resistance, gate-resistor network, 32-case sweep", "Dead-time margin"],
        ["1.8", "300 ns, IR2110 typical timing, 12 V gate drive", "Decided configuration, duty sweep"],
    ], [2.6, 8.8, 5.2], bold_first_col=True)
    table(d, ["Result at Iph = 0.8 A", "v1.4", "v1.5", "v1.6", "v1.8 (decided)"], [
        ["MPP duty, 12 V battery", "0.70*", "0.68", "0.68", ("0.68", True)],
        ["Panel power at MPP", "13.20 W", "13.34 W", "13.35 W", ("13.35 W", True)],
        ["Efficiency panel to battery", "99.7 %", "97.0 %", "95.1 %", ("94.1 %", True)],
        ["Converter only (after diode)", "n/a", "98.7 %", "96.9 %", ("95.8 %", True)],
        ["MPP duty, 14.4 V battery", "n/a", "0.80", "0.80", ("0.80", True)],
        ["Shoot-through per cycle", "n/a", "n/a", "n/a", ("9.5 ns", True)],
    ], [5.4, 2.4, 2.4, 2.4, 4.0], bold_first_col=True)
    para(d, "* v1.4 sampled only 0.65 and 0.70; the true model maximum is 13.351 W at 17.92 V. Inductor ripple at "
            "D = 0.70: 0.36 A peak-to-peak, matching the hand calculation Vout(1 - D)/(L fsw).", italic=True, size=9,
         color=GREY)
    figure(d, os.path.join(LT, "ltspice_compare_versions.png"),
           "Figure 1. Panel power and efficiency versus duty for each LTspice version.")
    para(d, "Where the efficiency goes (v1.4 to v1.8): about 1.9 points to the Schottky diode (0.33 V at 0.76 A); "
            "about 1 point to doubling switching frequency and dead time; about 2 points to the IRF3205 model's "
            "body-diode reverse recovery; about 1 point to the real gate driver and residual shoot-through.")

    d.add_heading("4. Switching-level findings", level=1)
    d.add_heading("4.1 Reverse-current blocking", level=2)
    para(d, "With a 14.4 V battery and D ≤ 0.66 the converter would need more than the panel's open-circuit voltage. "
            "In v1.4 this pushed current back into the panel. From v1.5 the Schottky blocks it: the panel stays at "
            "Voc (21.19 V) with essentially zero current. The inductor current still goes negative there (forced CCM "
            "with complementary PWM), but only circulates between the battery and the input capacitor.")
    d.add_heading("4.2 IRF3205 model and body-diode recovery", level=2)
    para(d, "Turn-off in the model matches the datasheet (td(off) 50 ns + tf 65 ns). The 1.9-point efficiency drop "
            "from v1.5 to v1.6 was traced to body-diode reverse recovery: the vendor model stores charge for "
            "TT = 100 µs, far more than the datasheet recovery charge implies at 1 A.")
    table(d, ["Body-diode TT", "Converter efficiency", "Panel to battery"], [
        ["100 µs (vendor model, kept)", "96.85 %", "95.09 %"],
        ["2.3 ns (from datasheet Qrr / IF)", "98.90 %", "97.10 %"],
        ["0 (no recovery)", "98.93 %", "97.14 %"],
    ], [7.0, 4.8, 4.8])
    para(d, "Decision: the vendor model is kept unmodified and efficiency is quoted as a range until bench data "
            "exists.")

    d.add_heading("4.3 Dead time and the Miller kick (v1.7)", level=2)
    para(d, "v1.7 adds the IR2110 delays (on 120 ns, off 94 ns typical; datasheet p.3), its ~6 Ω output resistance "
            "and an external gate network. Margins are measured on the MOSFET's internal gate against its 3.73 V "
            "threshold.")
    bullets(d, [
        ("Finding: ", "at 200 ns both MOSFETs overlap for about 22 ns per cycle, even with no gate resistor. "
         "Symmetric gate resistors of 10 Ω or more break the converter in the model."),
        ("Mechanism: ", "when the high side turns on, the switch node rises about 17 V in tens of nanoseconds and "
         "couples through Cgd into the low-side gate, lifting it above threshold (Miller kick)."),
        ("Fixes: ", "a longer dead time gives the gate time to discharge first; a gate-source capacitor makes a divider "
         "with Cgd, so the kick is smaller."),
    ])
    table(d, ["Dead time", "Driver timing", "Gate-source cap", "Overlap", "Low-side kick", "Converter eff."], [
        ["200 ns", "typical", "none", ("22 ns", True), "4.37 V", "94.7 %"],
        ["200 ns", "pessimistic", "none", ("86 ns", True), "5.41 V", "68.5 %"],
        ["300 ns", "typical", "none", "9 ns", "3.88 V", "95.8 %"],
        ["300 ns", "typical", "2.2 nF", ("0", True), "3.60 V", "95.9 %"],
        ["300 ns", "pessimistic", "2.2 nF", "19 ns", "4.10 V", "96.0 %"],
        ["400 ns", "pessimistic", "2.2 nF", ("0", True), "3.55 V", "95.6 %"],
    ], [2.4, 2.8, 2.8, 2.2, 2.8, 3.6])
    figure(d, os.path.join(LT, "ltspice_v1.7_edgeB_waveforms.png"),
           "Figure 2. Low-side gate (orange) pushed above threshold as the high side turns on.", width_cm=15.5)
    d.add_heading("4.4 Decided configuration (v1.8, 300 ns)", level=2)
    para(d, "The MPP is unchanged. The high-side-off edge has 175 to 250 ns of margin everywhere. The low-side-off "
            "edge keeps a 6 to 14 ns residual overlap at most powered points (kick 3.8 to 4.0 V), which is why the "
            "2.2 nF gate-source capacitor pads stay recommended.")
    figure(d, os.path.join(LT, "ltspice_v1.8_waveforms_D0.70_V12.png"),
           "Figure 3. v1.8 at D = 0.70, 12 V: gate drive (driver and internal), switch node, inductor current.")

    d.add_heading("5. Firmware", level=1)
    table(d, ["Module", "Contents"], [
        ["mppt_po.c/.h", "P&O: if power rose keep direction, else reverse; step 1 count; clamps reverse the direction. "
                         "Sign convention: increasing D lowers the PV voltage"],
        ["charger_fsm.c/.h", "IDLE, BULK_MPPT, CC_LIMIT, CV_ABSORB, FLOAT, FAULT. Pure transition function fsm_step() "
                             "plus charger_update() that runs P&O or integral CC / CV / float control"],
    ], [3.6, 13.0], bold_first_col=True)
    table(d, ["Transition", "Condition"], [
        ["IDLE to BULK_MPPT", "Vpv > Vbat + 1.0 V for 1 s (restart hold-off), Vbat ≥ 10.5 V"],
        ["BULK_MPPT to CC_LIMIT", "Ibat ≥ 0.6 A"],
        ["BULK or CC to CV_ABSORB", "Vbat ≥ 14.4 V"],
        ["CV_ABSORB to FLOAT", "Ibat < 0.11 A (tail)"],
        ["running to IDLE", "Vpv < Vbat + 0.3 V (night) or Ibat < -0.2 A"],
        ["any to FAULT (latched)", "Vbat > 15 V, Ibat > 1.5 A, or sensor reading invalid"],
    ], [5.0, 11.6], bold_first_col=True)
    para(d, "Compiled with arm-none-eabi-gcc 14.3 for the Cortex-M4F (hard-float), zero warnings, 1.3 kB of code, "
            "hardware FPU instructions only. PV voltage must be sensed on the panel side of the Schottky. Thresholds "
            "and gains other than the decided baseline are PROPOSED.")

    d.add_heading("6. Software-in-the-loop", level=1)
    para(d, "The unchanged firmware C files are built into a DLL and called every 20 ms from Python. Plant: the same "
            "single-diode PV model as LTspice, the Schottky, an averaged buck with efficiency from LTspice, and a "
            "C + R battery. The plant matches LTspice within 0.2 % at the MPP points.")
    table(d, ["Run", "Test", "Result"], [
        ["a", "Irradiance step 0.8 → 0.5 → 0.8 A", "99.98 / 99.89 / 99.98 % tracking; re-settles in 0.14 to 0.26 s"],
        ["b", "Step size 1 / 2 / 4 counts", "All ≥ 99.88 %; sensor noise, not step size, limits accuracy"],
        ["c", "Full vs partial sun", "Full sun: CC holds 0.600 A (58 % of available power); partial: MPPT 99.95 %"],
        ["d", "Charge cycle", "CC → CV at 14.4 V → taper → float holds 13.60 V (time-scaled 440x)"],
        ["e", "Night and fault", "PWM off at Iph = 5 mA, one clean restart at dawn; injected overvoltage latches FAULT"],
    ], [1.2, 5.0, 10.4], bold_first_col=True)
    figure(d, os.path.join(SIL, "sil_c_full_vs_partial_sun.png"),
           "Figure 4. Run c: the current limit dominates in full sun; MPPT takes over in partial sun.", width_cm=12.5)
    figure(d, os.path.join(SIL, "sil_d_cc_cv_float.png"),
           "Figure 5. Run d: CC → CV → float sequence with a 50 mA IoT load.", width_cm=12.5)
    para(d, "Fixes found by reviewing the plots: the float voltage gain was lowered from 0.5 to 0.10 (the first "
            "value nearly oscillated near Voc), and the current gain was raised to shorten an overshoot from "
            "300 ms to 150 ms.")

    d.add_heading("7. Limitations", level=1)
    bullets(d, [
        "PV model calibrated to open-circuit voltage only; panel datasheet (Isc, Imp) still missing.",
        "Battery is an ideal source (LTspice) or a scaled C + R (SIL): no real SLA chemistry; taper timing unrealistic.",
        "SIL plant is averaged and quasi-static: no switching ripple, constant efficiency, Gaussian sensor noise.",
        "MOSFET level-1 model exaggerates current near threshold; gate-drain capacitance not checked against the "
        "datasheet; driver modelled as delays and a resistor; no PCB inductance or bootstrap droop.",
        "Firmware compiled but not run on the Nucleo. No bench data: results are simulated, not validated.",
    ])
    d.add_heading("8. Open items", level=1)
    bullets(d, [
        "Choose the PV-input Schottky part.",
        "Decide whether the 2.2 nF gate-source capacitor and split gate-resistor pads become part of the PCB.",
        "Edge-aligned PWM (840 counts) vs centre-aligned (420 counts): 420 counts causes ±21 to 87 mA ripple in "
        "current-limit and float.",
        "Confirm the PROPOSED charger thresholds and gains; decide on an absorption timer.",
        "Hardware bring-up: clock, PWM (scope the dead time and the low-side gate), ADC, INA219, main loop, bench "
        "tests.",
    ])
    d.add_heading("9. Reproducing the results", level=1)
    para(d, "On any Windows PC with Git Bash, Python, MSYS2 gcc, LTspice and STM32CubeIDE: clone the repository and "
            "run sh setup.sh --test. It builds everything and reports whether the SIL and LTspice results match the "
            "committed ones. Full detail: docs/simulation_results.md and PROJECT_STATE.md.")
    return d


# ======================================================================== teammate guide
def explainer():
    d = new_doc("What We Did Today, Explained",
                "A plain-language guide to the MPPT solar charger simulations (11 Nov 2026)",
                "Read this first if you are new to the project. No electronics background needed.")

    box(d, "The one-minute version", [
        "We are building a box that takes power from a small solar panel and charges a 12 V battery as efficiently "
        "as possible.",
        "Today we did not touch any hardware. We tested the design on the computer in three ways: a circuit "
        "simulator, the real control code, and a test rig that runs that code against a fake solar panel and "
        "battery.",
        "The design works in simulation. We found and fixed one real risk (the two power switches could briefly "
        "turn on together), and the whole project can now be set up on any laptop with one command.",
    ])

    d.add_heading("1. What are we building?", level=1)
    para(d, "A solar charge controller. It sits between a 12 W solar panel and a 12 V battery that powers a small "
            "sensor device (an IoT node). It has two jobs:")
    bullets(d, [
        ("Get the most power out of the panel. ", "A solar panel has one best operating point, the maximum power "
         "point (MPP). Pull too little current and the voltage is high but power is low; pull too much and the "
         "voltage collapses. The controller keeps hunting for that sweet spot. That is what MPPT (maximum power "
         "point tracking) means."),
        ("Charge the battery safely. ", "A lead-acid battery wants a gentle current limit, then a fixed voltage, "
         "then a lower holding voltage once it is full."),
    ])
    box(d, "Analogy: filling a glass from a tap", [
        "Fill fast at first (bulk), slow down near the top (constant voltage, current tapers off), then just keep it "
        "topped up (float). The controller does the same with the battery.",
    ])

    d.add_heading("2. How does it work?", level=1)
    para(d, "The heart is a buck converter: two electronic switches (MOSFETs) that turn on and off 100 000 times "
            "a second, plus a coil (inductor) that smooths the result. The fraction of time the top switch is on is "
            "called the duty cycle, D.")
    bullets(d, [
        "Turning D up pulls more current from the panel and lowers the panel's voltage.",
        "Turning D down does the opposite.",
        "So the microcontroller (an STM32 chip) controls everything by adjusting one number: D.",
    ])
    para(d, "The hunting method is called Perturb and Observe. Every 20 ms the code nudges D a tiny bit and checks "
            "whether power went up. If yes, it keeps going that way; if no, it turns around. It is like walking "
            "uphill in fog: take a step, check whether you are higher, and turn back if not.")
    box(d, "Two terms you will hear a lot", [
        ("Duty cycle (D): ", "how long the top switch is on in each cycle, from 0 to 1. Ours stays between 0.60 "
         "and 0.85."),
        ("Dead time: ", "a tiny pause (now 300 billionths of a second) when both switches are off, so they are "
         "never on together. If they were, the input would be shorted. That is called shoot-through."),
    ])

    d.add_heading("3. What we did today, step by step", level=1)
    table(d, ["Step", "What it means in plain words"], [
        ["Fixed the design numbers", "Agreed the switching speed, duty limits, charging voltages and current limit, "
                                     "and checked each against the part datasheets."],
        ["Circuit simulation (LTspice)", "Built a virtual version of the circuit and ran it at many duty cycles to "
                                         "find the sweet spot and the efficiency."],
        ["Added a protection diode", "Stops the battery pushing power back into the panel at night."],
        ["Used the real transistor model", "Swapped a stand-in part for the manufacturer's model of the real one."],
        ["Checked the switch timing", "Modelled the real gate-driver chip and found the switches could overlap. "
                                      "Raised the dead time from 200 to 300 ns."],
        ["Wrote the control code", "The tracking algorithm and the battery-charging logic, in C, for the STM32 chip."],
        ["Software-in-the-loop test", "Ran that exact code against a fake panel and battery on the PC, in five "
                                      "scenarios."],
        ["Made it portable", "One command sets the project up on the laptop and checks the results match."],
    ], [4.6, 12.0], bold_first_col=True)

    d.add_heading("4. What did we find?", level=1)
    d.add_heading("The sweet spot is where we expected", level=2)
    para(d, "With a 12 V battery the best duty cycle is about 0.68, giving about 13.3 W from the panel. With a full "
            "14.4 V battery it moves to about 0.80. Both are inside our allowed range of 0.60 to 0.85.")
    figure(d, os.path.join(LT, "ltspice_compare_versions.png"),
           "Top: panel power against duty cycle (the peak is the sweet spot). Bottom: efficiency. Each colour is "
           "one version of the simulation.", width_cm=15.5)
    d.add_heading("Efficiency is about 94 to 97 %", level=2)
    para(d, "Every improvement to the model made it more realistic and a bit less efficient, which is normal: the "
            "early numbers (99.7 %) ignored real losses. The protection diode costs about 2 %, the real "
            "transistor and driver cost a few more. The true figure is somewhere between about 94 and 97 % and "
            "will only be known from measurement.")
    d.add_heading("We found and fixed a real risk", level=2)
    para(d, "When the top switch turns on, the voltage at the middle of the circuit jumps very fast. That jump "
            "leaks through a tiny built-in capacitance into the bottom switch's control pin and briefly turns it "
            "back on, even though it should be off. That is called a Miller kick. For a few nanoseconds both "
            "switches conduct, wasting power and stressing the parts.")
    box(d, "Analogy: two doors in a corridor", [
        "The two switches are like two doors that must never be open together. Dead time is the pause between "
        "closing one and opening the other. The Miller kick is like slamming one door so hard that the air pressure "
        "pushes the other one ajar.",
        "The fixes are a longer pause (we went from 200 to 300 ns) and a small capacitor that holds the second door "
        "shut (proposed, not yet decided).",
    ], fill=WARN_FILL)
    d.add_heading("The control code does the right things", level=2)
    para(d, "In the software-in-the-loop tests the code:")
    bullets(d, [
        "tracks the sweet spot to within 0.1 % and re-finds it within a quarter of a second after clouds change;",
        "limits the charge current to 0.6 A in full sun (so in bright sun it deliberately does not use all the "
        "panel's power, to protect the battery);",
        "goes through bulk, constant voltage and float charging in the right order;",
        "switches off at night, restarts cleanly at dawn, and locks into a safe FAULT state if a reading looks "
        "dangerous.",
    ])
    figure(d, os.path.join(SIL, "sil_e_night_and_fault.png"),
           "Night test: as the light fades the charger switches off (IDLE), restarts at dawn, then a simulated "
           "overvoltage locks it in FAULT.", width_cm=9.0)

    d.add_heading("5. What is not done yet", level=1)
    bullets(d, [
        "Nothing has been built or measured. Everything above is simulation. Always say \"designed and simulated\", "
        "never \"validated\", until we have bench measurements.",
        "The code compiles for the STM32 but has not been run on the board yet.",
        "Still to choose: the exact protection diode part, whether to add the small gate capacitors, and a few "
        "charger settings.",
    ])

    d.add_heading("6. If someone asks you...", level=1)
    table(d, ["Question", "Short answer"], [
        ["Why MPPT?", "A panel only gives its full power at one operating point; MPPT finds and holds it."],
        ["Why simulate before building?", "It is cheap and safe to find problems like the switch overlap on a "
                                          "computer instead of burning parts."],
        ["What is software-in-the-loop?", "Running the real control code against a simulated panel and battery, to "
                                          "test the logic before the hardware exists."],
        ["Why is efficiency not 99 %?", "The diode, the switching and the transistors all lose a little. 94 to 97 % "
                                        "is realistic for this design."],
        ["Why 300 ns dead time?", "200 ns let the switches overlap in the realistic model; 300 ns almost "
                                  "removes it, at a cost of about 0.1 % efficiency."],
        ["Is it proven?", "No. It is designed and simulated. Bench tests come next."],
    ], [5.0, 11.6], bold_first_col=True)

    d.add_heading("7. Words to know", level=1)
    table(d, ["Word", "Meaning"], [
        ["MPPT / MPP", "Maximum power point (tracking): the panel's best operating point, and finding it."],
        ["Buck converter", "A circuit that turns a higher voltage into a lower one by switching quickly."],
        ["Duty cycle (D)", "Fraction of each cycle the top switch is on."],
        ["MOSFET", "The electronic switch. Ours is the IRF3205."],
        ["Gate driver", "Chip that turns the MOSFETs on and off (IR2110)."],
        ["Dead time", "Pause with both switches off, to prevent shoot-through."],
        ["Shoot-through", "Both switches on at once; shorts the input."],
        ["Miller kick", "A fast voltage jump that briefly turns a switch back on through its internal capacitance."],
        ["CC / CV / float", "Charging stages: constant current, constant voltage, then a lower holding voltage."],
        ["LTspice", "Free circuit simulator."],
        ["SIL", "Software-in-the-loop: real code, simulated hardware."],
        ["P&O", "Perturb and Observe: the nudge-and-check tracking method."],
    ], [4.0, 12.6], font=9.5, bold_first_col=True)

    d.add_heading("8. Getting the project on your laptop", level=1)
    para(d, "Install Git for Windows, Python (64-bit), MSYS2 with gcc, LTspice and STM32CubeIDE. Then in Git Bash, "
            "clone the repository and run:")
    p = para(d, "sh setup.sh --test", size=10.5)
    p.runs[0].font.name = "Consolas"
    para(d, "It finds the tools, sets everything up and should finish with two \"MATCHES this repo\" lines. The full "
            "technical story is in docs/simulation_results.md, and PROJECT_STATE.md is the project's source of "
            "truth.")
    return d


if __name__ == "__main__":
    for name, builder in (("MPPT_simulation_report_technical.docx", technical),
                          ("MPPT_simulation_explained.docx", explainer)):
        out = os.path.join(HERE, name)
        builder().save(out)
        print("written", out)
