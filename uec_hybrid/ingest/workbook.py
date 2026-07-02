"""
Workbook ingest: a trust fills in one Excel (or CSV) template and uploads it,
instead of anyone editing JSON/Python. The template mirrors the "Set up my ED"
model exactly, so a non-technical user configures the whole department from a
spreadsheet:

* **Overview**  - name, attendances/day, inpatient beds, community capacity,
                  bed occupancy.
* **Areas**     - which of the Model ED areas the trust runs, and their hours.
* **Rota**      - the workforce roster (role, start, end, count).
* **Arrivals**  (optional) - attendances by hour -> a calibration patch.
* **AcuityMix** (optional) - acuity split -> a calibration patch.

``read_workbook`` returns a ready ``Department`` plus an optional calibration
patch (reusing the ECDS seam's ``apply_patch``), a plain-language summary and
per-field provenance. ``write_template`` / ``template_bytes`` generate the blank
workbook, pre-filled with the template defaults so the trust edits real values.
"""
from __future__ import annotations

import csv
import io

from openpyxl import Workbook, load_workbook

from ..department.config import AREAS, DEFAULT_HOURS, Department
from ..workforce.defaults import DEFAULT_ROTA
from ..workforce.roles import ROLES

OVERVIEW_KEYS = {
    "name": "name",
    "attendances_per_day": "attendances_per_day",
    "attendances": "attendances_per_day",
    "inpatient_beds": "inpatient_beds",
    "beds": "inpatient_beds",
    "community_capacity": "community_capacity",
    "community": "community_capacity",
    "baseline_bed_occupancy": "baseline_bed_occupancy",
    "bed_occupancy": "baseline_bed_occupancy",
    "occupancy": "baseline_bed_occupancy",
    "ods_code": "ods_code",
    "ods": "ods_code",
}


def _norm(s) -> str:
    return str(s or "").strip().lower().replace(" ", "_")


def _num(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _truthy(v) -> bool:
    return _norm(v) in ("1", "y", "yes", "true", "on", "x")


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #
def _sheet_rows(ws) -> list[list]:
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _read_overview(rows) -> dict:
    """Overview is a key/value sheet (col A key, col B value)."""
    out = {}
    for r in rows:
        if not r or r[0] is None:
            continue
        key = OVERVIEW_KEYS.get(_norm(r[0]))
        if not key or len(r) < 2:
            continue
        val = r[1]
        if key == "name":
            out["name"] = str(val).strip() if val is not None else None
        elif key == "ods_code":
            out["ods_code"] = str(val).strip() if val is not None else None
        else:
            n = _num(val)
            if n is None:
                continue
            if key == "baseline_bed_occupancy" and n > 1.5:   # entered as a percent
                n = n / 100.0
            out[key] = n
    return {k: v for k, v in out.items() if v is not None}


def _read_areas(rows):
    """Header row then area_key/enabled/open/close. Returns (enabled, hours) or
    (None, None) when the sheet is empty (keep the department default)."""
    body = [r for r in rows[1:] if r and r[0] not in (None, "")]
    if not body:
        return None, None
    enabled, hours = [], {}
    for r in body:
        key = _norm(r[0])
        if key not in AREAS:
            continue
        if len(r) > 1 and _truthy(r[1]):
            enabled.append(key)
        o = _num(r[2]) if len(r) > 2 else None
        c = _num(r[3]) if len(r) > 3 else None
        if o is not None and c is not None:
            hours[key] = [int(o), int(c)]
    return enabled, hours


def _read_rota(rows, summary):
    """Header row then role/start/end/count. Returns a rota list or None."""
    body = [r for r in rows[1:] if r and r[0] not in (None, "")]
    if not body:
        return None
    rota, skipped = [], []
    for r in body:
        role = _norm(r[0])
        if role.startswith("#"):        # helper/comment row in the template
            continue
        if role not in ROLES:
            skipped.append(str(r[0]))
            continue
        start, end, count = (_num(r[1]) if len(r) > 1 else None,
                             _num(r[2]) if len(r) > 2 else None,
                             _num(r[3]) if len(r) > 3 else None)
        if None in (start, end, count):
            continue
        rota.append({"role": role, "start": int(start), "end": int(end), "count": int(count)})
    if skipped:
        summary.append(f"Ignored {len(skipped)} rota row(s) with unknown roles: "
                       f"{', '.join(sorted(set(skipped)))}.")
    return rota or None


def _read_arrivals(rows):
    """Optional hour/attendances sheet -> per-day hourly profile (24 values)."""
    body = [r for r in rows[1:] if r and r[0] is not None]
    if not body:
        return None
    prof = [0.0] * 24
    seen = False
    for r in body:
        h = _num(r[0])
        v = _num(r[1]) if len(r) > 1 else None
        if h is None or v is None:
            continue
        hi = int(h) % 24
        prof[hi] = float(v)
        seen = True
    return prof if seen else None


def _read_acuity(rows):
    """Optional acuity/share sheet -> acuity_mix dict."""
    body = [r for r in rows[1:] if r and r[0] is not None]
    if not body:
        return None
    mix = {}
    for r in body:
        label = str(r[0]).strip()
        v = _num(r[1]) if len(r) > 1 else None
        if not label or v is None:
            continue
        if not label.lower().startswith("acuity"):
            label = f"Acuity {label}"
        mix[label] = float(v)
    return mix or None


def read_workbook(file_or_bytes, filename: str | None = None) -> dict:
    """Parse an uploaded workbook (.xlsx) or a single Overview CSV into a
    Department (+ optional calibration patch, summary, provenance)."""
    data = file_or_bytes if isinstance(file_or_bytes, (bytes, bytearray)) else file_or_bytes.read()
    is_csv = (filename or "").lower().endswith(".csv")
    summary: list[str] = []
    over, areas_enabled, areas_hours, rota, arrivals, acuity = {}, None, None, None, None, None

    if is_csv:
        text = data.decode("utf-8-sig", errors="replace")
        over = _read_overview([list(r) for r in csv.reader(io.StringIO(text))])
        summary.append("Read Overview from CSV (areas/rota/arrivals need the Excel template).")
    else:
        wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        sheets = {name.strip().lower(): wb[name] for name in wb.sheetnames}
        if "overview" in sheets:
            over = _read_overview(_sheet_rows(sheets["overview"]))
        if "areas" in sheets:
            areas_enabled, areas_hours = _read_areas(_sheet_rows(sheets["areas"]))
        if "rota" in sheets:
            rota = _read_rota(_sheet_rows(sheets["rota"]), summary)
        if "arrivals" in sheets:
            arrivals = _read_arrivals(_sheet_rows(sheets["arrivals"]))
        if "acuitymix" in sheets:
            acuity = _read_acuity(_sheet_rows(sheets["acuitymix"]))

    # --- build the department (default for anything the workbook didn't set) ---
    base = Department.default().to_dict()
    prov = []
    for key in ("name", "attendances_per_day", "inpatient_beds",
                "community_capacity", "baseline_bed_occupancy"):
        if key in over:
            base[key] = over[key]
            prov.append({"field": key, "value": over[key], "source": "workbook"})
        else:
            prov.append({"field": key, "value": base.get(key), "source": "template default"})
    if areas_enabled is not None:
        base["enabled"] = areas_enabled
        base["hours"] = {**base.get("hours", {}), **(areas_hours or {})}
        summary.append(f"Areas set from workbook: {', '.join(areas_enabled) or 'none enabled'}.")
    else:
        summary.append("Areas kept at template default (no Areas sheet).")
    if rota is not None:
        base["rota"] = rota
        summary.append(f"Rota set from workbook ({len(rota)} shifts).")
    else:
        summary.append("Rota kept at template default (no Rota sheet).")
    dept = Department.from_dict(base)

    # --- optional calibration patch (reuses the ECDS seam) ---
    patch = {}
    if arrivals is not None:
        patch.setdefault("arrivals", {})["hourly_profile"] = [round(x, 2) for x in arrivals]
        dept.attendances_per_day = round(sum(arrivals), 1)
        summary.append(f"Arrivals-by-hour set from workbook ({round(sum(arrivals))}/day).")
    if acuity is not None:
        tot = sum(acuity.values()) or 1.0
        patch.setdefault("arrivals", {})["acuity_mix"] = {
            k: round(v / tot * 100, 2) for k, v in acuity.items()}
        summary.append("Acuity mix set from workbook.")

    return {"department": dept, "patch": (patch or None), "summary": summary,
            "provenance": prov}


# --------------------------------------------------------------------------- #
# Template generation
# --------------------------------------------------------------------------- #
def build_template() -> Workbook:
    d = Department.default()
    wb = Workbook()

    intro = wb.active
    intro.title = "Instructions"
    for i, line in enumerate([
        ["Model ED Optimiser - department set-up workbook"],
        ["Fill in the tabs, then upload this file in 'Set up my ED'. No coding needed."],
        [""],
        ["Overview  - your department's headline figures (name, attendances/day, beds)."],
        ["Areas     - tick (yes/no) the areas you run, and their opening hours (0-24)."],
        ["Rota      - your workforce roster: role, start hour, end hour, staff count."],
        ["Arrivals  - OPTIONAL: attendances by hour of day (overrides attendances/day)."],
        ["AcuityMix - OPTIONAL: your acuity split (Acuity 1..5)."],
        [""],
        ["Blank cells keep the model's sensible default; nothing is required except a name."],
    ]):
        intro.append(line)

    ov = wb.create_sheet("Overview")
    ov.append(["field", "value"])
    for k, v in [("name", d.name), ("ods_code", ""),
                 ("attendances_per_day", round(d.attendances_per_day)),
                 ("inpatient_beds", d.inpatient_beds),
                 ("community_capacity", d.community_capacity),
                 ("baseline_bed_occupancy", "")]:
        ov.append([k, v])

    ar = wb.create_sheet("Areas")
    ar.append(["area_key", "enabled (yes/no)", "open_hour", "close_hour", "description"])
    for key, meta in AREAS.items():
        oh = DEFAULT_HOURS.get(key, [0, 24])
        ar.append([key, "yes" if key in d.enabled else "no", oh[0], oh[1], meta["label"]])

    ro = wb.create_sheet("Rota")
    ro.append(["role", "start", "end", "count"])
    for s in DEFAULT_ROTA:
        ro.append([s["role"], s["start"], s["end"], s["count"]])
    ro.append([])
    ro.append(["# valid roles:", ", ".join(ROLES)])

    arv = wb.create_sheet("Arrivals")
    arv.append(["hour", "attendances"])
    for h in range(24):
        arv.append([h, ""])

    ac = wb.create_sheet("AcuityMix")
    ac.append(["acuity", "share"])
    for i in range(1, 6):
        ac.append([f"Acuity {i}", ""])

    return wb


def template_bytes() -> bytes:
    bio = io.BytesIO()
    build_template().save(bio)
    return bio.getvalue()


def write_template(path) -> None:
    build_template().save(path)
