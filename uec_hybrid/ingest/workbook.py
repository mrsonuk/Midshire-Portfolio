"""
Workbook ingest: a trust fills in one Excel (or CSV) template and uploads it,
instead of anyone editing JSON/Python. The template mirrors the "Set up my ED"
model exactly, so a non-technical user configures the whole department from a
spreadsheet:

* **Overview**  - name, ODS code, attendances/day, inpatient beds, community
                  capacity, bed occupancy.
* **Areas**     - which of the Model ED areas the trust runs, and their hours.
* **Rota**      - the workforce roster (role, start, end, count).
* **Capacity**  (optional) - the trust's REAL physical counts (cubicles, CDU
                  beds, resus bays…) - no open dataset publishes these.
* **Arrivals**  (optional) - attendances by hour -> a calibration patch.
* **AcuityMix** (optional) - acuity split -> a calibration patch.
* **Costs / ServiceTimes** (optional) - £ figures and measured stage times.

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
from ..department.builder import BASE_RAW
from ..workforce.defaults import DEFAULT_ROTA
from ..workforce.roles import ROLES, STAFF_RESOURCES, default_rates
from ..finance.costbook import DEFAULT_COST_BOOK
from ..model_params import service_params

# cost-book figures a trust can set from the workbook (scalars only)
COST_BOOK_KEYS = ["admission_avoided", "four_hour_breach", "twelve_hour_breach",
                  "agency_premium", "agency_share_pct"]

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
    (None, None) when the sheet is empty (keep the department default).
    '#'-prefixed rows are comments, as on the other sheets."""
    body = [r for r in rows[1:] if r and r[0] not in (None, "")
            and not _norm(r[0]).startswith("#")]
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


def _capacity_catalogue() -> list[dict]:
    """The physical (non-staff) resources a trust can set real counts for, with
    the template default and which area each belongs to."""
    area_of = {}
    for key, meta in AREAS.items():
        for r in meta.get("resources", []):
            area_of.setdefault(r, meta["label"])
    rows = []
    for key, v in BASE_RAW.get("resources", {}).items():
        if key in STAFF_RESOURCES or not isinstance(v, (int, float)):
            continue
        rows.append({"key": key, "default": int(v),
                     "belongs_to": area_of.get(key, "Core ED (always present)")})
    return rows


def _read_capacity(rows):
    """Optional Capacity sheet (resource_key/your_count): the trust's REAL
    physical counts (cubicles, CDU beds, resus bays…). Returns dict or None."""
    body = [r for r in rows[1:] if r and r[0] not in (None, "")]
    valid = {c["key"] for c in _capacity_catalogue()}
    out = {}
    for r in body:
        key = _norm(r[0])
        if key.startswith("#") or key not in valid:
            continue
        v = _num(r[1]) if len(r) > 1 else None
        if v is None or v <= 0:
            continue
        out[key] = int(v)
    return out or None


def _read_costs(rows):
    """Optional Costs sheet (item/value): cost-book figures + per-role hourly
    rates. Returns (cost_book, role_rates), each a dict or None."""
    body = [r for r in rows[1:] if r and r[0] not in (None, "")]
    cost_book, rates = {}, {}
    for r in body:
        item = _norm(r[0])
        v = _num(r[1]) if len(r) > 1 else None
        if v is None:
            continue
        if item in COST_BOOK_KEYS:
            cost_book[item] = v
        elif item in ROLES:
            rates[item] = v
    return (cost_book or None), (rates or None)


def _read_service(rows):
    """Optional ServiceTimes sheet (stage/current/your_mean): per-stage mean
    overrides + an optional global scale. Returns a params dict or None."""
    body = [r for r in rows[1:] if r and r[0] not in (None, "")]
    mean, scale = {}, None
    for r in body:
        key = _norm(r[0])
        if key.startswith("#"):
            continue
        your = _num(r[2]) if len(r) > 2 else None
        if your is None:
            continue
        if key == "service_scale":
            scale = your
        else:
            mean[key] = your
    params = {}
    if scale is not None:
        params["service_scale"] = scale
    if mean:
        params["service_mean"] = mean
    return params or None


def read_workbook(file_or_bytes, filename: str | None = None) -> dict:
    """Parse an uploaded workbook (.xlsx) or a single Overview CSV into a
    Department (+ optional calibration patch, summary, provenance)."""
    data = file_or_bytes if isinstance(file_or_bytes, (bytes, bytearray)) else file_or_bytes.read()
    is_csv = (filename or "").lower().endswith(".csv")
    summary: list[str] = []
    over, areas_enabled, areas_hours, rota, arrivals, acuity = {}, None, None, None, None, None
    cost_book, rates, svc_params, capacity = None, None, None, None

    if is_csv:
        text = data.decode("utf-8-sig", errors="replace")
        over = _read_overview([list(r) for r in csv.reader(io.StringIO(text))])
        summary.append("Read Overview from CSV (areas/rota/arrivals/costs need the Excel template).")
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
        if "capacity" in sheets:
            capacity = _read_capacity(_sheet_rows(sheets["capacity"]))
        if "costs" in sheets:
            cost_book, rates = _read_costs(_sheet_rows(sheets["costs"]))
        if "servicetimes" in sheets:
            svc_params = _read_service(_sheet_rows(sheets["servicetimes"]))

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
    if capacity is not None:
        base["capacity"] = capacity
        summary.append(f"Physical capacity set from workbook ({len(capacity)} "
                       f"resource(s): {', '.join(sorted(capacity))}).")
        for k, v in sorted(capacity.items()):
            prov.append({"field": f"capacity.{k}", "value": v, "source": "workbook"})
    else:
        summary.append("Physical capacity kept at the scaled template default "
                       "(no Capacity sheet) - counts like CDU beds and cubicles "
                       "are modelled assumptions until the trust supplies them.")
        prov.append({"field": "capacity", "value": None, "source": "template default"})
    # keep the ODS code visible in the department name: it links the set-up back
    # to the trust's published figures and lets auto-calibration find the trust's
    # real observed 4-hour performance
    ods = (over.get("ods_code") or "").strip().upper()
    if ods and f"({ods})" not in str(base.get("name") or ""):
        base["name"] = f"{base.get('name') or 'Your Emergency Department'} ({ods})"
        prov.append({"field": "ods_code", "value": ods, "source": "workbook"})
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

    if cost_book:
        summary.append(f"Cost book: {', '.join(sorted(cost_book))} set from workbook.")
    if rates:
        summary.append(f"Role rates: {len(rates)} set from workbook.")
    if svc_params:
        bits = []
        if "service_scale" in svc_params:
            bits.append(f"all x{svc_params['service_scale']}")
        if svc_params.get("service_mean"):
            bits.append(f"{len(svc_params['service_mean'])} stage(s)")
        summary.append("Service times set from workbook (" + ", ".join(bits) + ").")

    return {"department": dept, "patch": (patch or None), "summary": summary,
            "provenance": prov, "cost_book": cost_book, "role_rates": rates,
            "service_params": svc_params}


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
        ["Overview     - your department's headline figures (name, ODS code, attendances/day, beds)."],
        ["Areas        - tick (yes/no) the areas you run, and their opening hours (0-24)."],
        ["Rota         - your workforce roster: role, start hour, end hour, staff count."],
        ["Capacity     - OPTIONAL: your REAL physical counts (cubicles, CDU beds, resus bays...)."],
        ["               Blank rows keep a size-scaled template estimate - a modelled assumption."],
        ["Arrivals     - OPTIONAL: attendances by hour of day (overrides attendances/day)."],
        ["AcuityMix    - OPTIONAL: your acuity split (Acuity 1..5)."],
        ["Costs        - OPTIONAL: cost-book figures and staff hourly rates (£)."],
        ["ServiceTimes - OPTIONAL: your measured stage times (minutes), if you have them."],
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

    cp = wb.create_sheet("Capacity")
    cp.append(["resource_key", "your_count", "template_default", "belongs to"])
    for row in _capacity_catalogue():
        cp.append([row["key"], "", row["default"], row["belongs_to"]])
    cp.append([])
    cp.append(["# Your REAL physical counts. Blank = keep a size-scaled template",
               "", "", ""])
    cp.append(["# estimate (a modelled assumption, flagged as such in the product).",
               "", "", ""])

    arv = wb.create_sheet("Arrivals")
    arv.append(["hour", "attendances"])
    for h in range(24):
        arv.append([h, ""])

    ac = wb.create_sheet("AcuityMix")
    ac.append(["acuity", "share"])
    for i in range(1, 6):
        ac.append([f"Acuity {i}", ""])

    co = wb.create_sheet("Costs")
    co.append(["item", "value", "note"])
    co.append(["# cost book (£, editable planning assumptions)", "", ""])
    for k in COST_BOOK_KEYS:
        co.append([k, DEFAULT_COST_BOOK.get(k), ""])
    co.append(["# staff hourly rates (£/hour incl. on-costs)", "", ""])
    rates = default_rates()
    for role, meta in ROLES.items():
        co.append([role, rates[role], meta["label"]])

    st = wb.create_sheet("ServiceTimes")
    st.append(["stage", "current_mean_min", "your_mean_min", "stage name"])
    st.append(["service_scale", 1.0, "", "OPTIONAL: multiply ALL service times (e.g. 1.1)"])
    for row in service_params(BASE_RAW):
        st.append([row["node"], row["mean"], "", row["label"]])

    return wb


def template_bytes() -> bytes:
    bio = io.BytesIO()
    build_template().save(bio)
    return bio.getvalue()


def write_template(path) -> None:
    build_template().save(path)
