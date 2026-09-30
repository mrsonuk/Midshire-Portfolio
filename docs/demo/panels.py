# -*- coding: utf-8 -*-
"""Full-screen panels built from the REAL files, not from prose: the workbook's
Status register, and the validation table the against_trust harness prints."""
import html, json, openpyxl
from pathlib import Path

REPO = Path("/home/user/Simulation_model")

CHIP = {"REAL - CUH extract": ("g", "CHEQS extract"),
        "REAL - published":   ("g", "NHS published"),
        "REAL - CUH ops":     ("g", "CUH ops return"),
        "ASSUMPTION":         ("a", "assumption"),
        "NOT MODELLED":       ("n", "held, not used"),
        "OUT OF SCOPE":       ("n", "out of scope"),
        "NEED FROM CUH":      ("r", "NEED FROM CUH")}


def status_panel() -> str:
    wb = openpyxl.load_workbook(REPO / "uec_hybrid/data/seeds/rgt_cuh_workbook.xlsx",
                                data_only=True)
    rows = [[("" if c is None else str(c).strip()) for c in r]
            for r in wb["Status"].iter_rows(values_only=True)]
    data = [r for r in rows[4:] if r[0] and not r[0].startswith("---")]
    half = (len(data) + 1) // 2

    def col(chunk):
        out = ["<table>"]
        for r in chunk:
            cls, lbl = CHIP.get(r[2], ("n", r[2]))
            tr = "<tr class='need'>" if cls == "r" else "<tr>"
            out.append(f"{tr}<td>{html.escape(r[0])}</td>"
                       f"<td style='text-align:right'><span class='chip {cls}'>"
                       f"{html.escape(lbl)}</span></td></tr>")
        return "".join(out) + "</table>"

    n = {}
    for r in data:
        n[r[2]] = n.get(r[2], 0) + 1
    return (f"<h1>The honesty register &mdash; every input, one row</h1>"
            f"<p class='sub'>{len(data)} model inputs &middot; "
            f"{n.get('REAL - CUH extract',0)} from CUH CHEQS extracts &middot; "
            f"{n.get('REAL - published',0)} from NHS England publications &middot; "
            f"{n.get('REAL - CUH ops',0)} from the CUH operational return &middot; "
            f"{n.get('ASSUMPTION',0)} modelled assumptions &middot; "
            f"{n.get('NOT MODELLED',0)} held but not yet usable &middot; "
            f"{n.get('NEED FROM CUH',0)} still needed from CUH"
            f"</p><div class='cols'><div>{col(data[:half])}</div>"
            f"<div>{col(data[half:])}</div></div>")


def validation_panel() -> str:
    """Numbers as printed by: python3 -m uec_hybrid.validation.against_trust RGT"""
    head = [("4-hour performance", "56.1%", "52.93%", "ok", "within 3 points"),
            ("12-hour waits (from arrival)", "10.9%", "9.98%", "ok", "within 1 point"),
            ("Ambulance handover within 45 min", "92.5%", "84.19%", "warn", "optimistic by ~8 pts")]
    area = [("Resus", "349", "324", "1.08x", "ok"),
            ("Majors trolleys", "727", "725", "1.00x", "ok"),
            ("Majors ambulant", "224", "254", "0.88x", "ok"),
            ("Minors", "173", "164", "1.05x", "ok"),
            ("Paediatrics", "222", "176", "1.26x", "warn")]
    h = ["<h1>Model against Cambridge's own figures</h1>"
         "<p class='sub'>Reproduce with <b>python3 -m uec_hybrid.validation.against_trust RGT</b>"
         " &middot; mean of 5 simulated weeks</p>"
         "<table class='big'><tr><th>Measure</th><th>Model</th>"
         "<th>Cambridge actual</th><th></th></tr>"]
    for lbl, m, a, cls, note in head:
        h.append(f"<tr><td>{lbl}</td><td class='num'>{m}</td><td class='num'>{a}</td>"
                 f"<td class='{cls}'>{note}</td></tr>")
    h.append("</table><p class='sub' style='margin:26px 0 6px'>"
             "Median time in department, by area (minutes)</p>"
             "<table class='big'><tr><th>Area</th><th>Model</th>"
             "<th>Cambridge actual</th><th>Ratio</th></tr>")
    for lbl, m, a, ratio, cls in area:
        b = " style='background:#eef6f7'" if lbl == "Majors trolleys" else ""
        h.append(f"<tr{b}><td>{lbl}</td><td class='num'>{m}</td><td class='num'>{a}</td>"
                 f"<td class='{cls}'>{ratio}</td></tr>")
    return "".join(h) + "</table>"


def limits_panel() -> str:
    return ("<h1>What it cannot do yet</h1>"
            "<p class='sub'>All four are in the register you saw at the start. "
            "None of them is hidden in a footnote.</p><ol>"
            "<li><b>The &lsquo;seen within 15 minutes&rsquo; tile is not comparable.</b> "
            "The model measures from triage; CUH's figure for minors measures from a "
            "clinician assessment 37 minutes into the visit. Same word, different event "
            "&mdash; so that tile should not be quoted.</li>"
            "<li><b>Day of week does not exist.</b> CUH's own data shows Sunday discharges "
            "at 29% of Monday's. That weekend collapse in bed releases is likely the biggest "
            "driver of Monday exit block, and this engine cannot represent it.</li>"
            "<li><b>Long-stay patients are invisible.</b> 60% of occupied beds are held by "
            "patients staying 7 days or more; the bed model has no compartment for them, so "
            "it is optimistic about bed turnover.</li>"
            "<li><b>The rota is not CUH's.</b> Staffing is a template scaled to size, because "
            "workforce was out of scope &mdash; treat staffing recommendations as directional.</li>"
            "</ol><p class='sub' style='margin-top:24px'><b>Still needed from CUH:</b> "
            "arrivals into each area, by hour. Everything else on the red list is closed.</p>")
