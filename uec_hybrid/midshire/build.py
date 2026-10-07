"""
The ONE model-build pipeline for the Midshire demonstrator.

Baseline, scenarios, the rota editor, the optimiser, the assistant and exports
all call ``build_model(inputs)``; nothing else assembles a Midshire pathway. The
order is fixed and every step is visible:

1. **Rota** - validated (the same rules as the editor and imports). An invalid
   rota stops the build; it is never silently repaired.
2. **Department** - the adult areas, hours, physical capacity, the validated
   rota (``rota_source="supplied"``: used exactly as given, never scaled) and
   the space-staffing table, through the SHARED Department builder - so routing
   around absent areas, opening hours, zero capacity and space staffing behave
   exactly as they do for any trust.
3. **Calibration** - the source trust's published/extract aggregates
   (``rgt_published.json``) as a calibration patch at ADULT volume, with the
   paediatric attribute removed. (Children are removed from demand, not
   re-routed.)
4. **Midshire pathway changes** - adult-only clean-up, SDEC from streaming and
   RAT with an explicit closed fallback, the decision-to-admit milestone, the
   mental-health admission sub-route, plain labels, unreachable nodes pruned.
5. **Hospital (SD) model and run length** - the source hospital's resolved bed
   model; cohort window, warm-up and drain.

The resolved model carries the exact rota, the hour-of-week staffing the engine
runs, physical and staffed capacity, provenance and any warnings, so what is
displayed and costed is what was simulated.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from . import config as mcfg
from ..department.config import Department
from ..department.builder import build as build_dept
from ..demand.ecds_seam import apply_patch
from ..des.pathway import Pathway, validate_schema
from ..ingest import published
from ..workforce.rota import validate_rota, staffing_by_week
from ..workforce.roles import ROLES, STAFF_RESOURCES, RATIO_RESOURCES, AREA_LABEL

MIDSHIRE_NAME = "Midshire University Hospitals Trust (adult ED demonstrator)"


class BuildError(ValueError):
    """Inputs that cannot be simulated as given (with details for the UI)."""

    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details or []


@dataclass
class Model:
    raw: dict
    rota: list
    staffing_week: dict            # staff resource -> 168 headcounts
    physical: dict                 # resource -> 168 physical capacity
    open_capacity: dict            # resource -> 168 staffed/open capacity
    warnings: list = field(default_factory=list)
    provenance: list = field(default_factory=list)
    model_hash: str = ""

    @property
    def pathway(self) -> Pathway:
        return Pathway.from_dict(self.raw)


# --------------------------------------------------------------------------- #
# calibration patch at adult volume
# --------------------------------------------------------------------------- #
def adult_patch(adult_per_day: float) -> tuple[dict, list]:
    """The source trust's aggregates as a calibration patch, at ADULT volume
    and with the paediatric attribute removed."""
    agg = published.load_aggregates(mcfg.fixture()["foundation"]["source_ods"])
    if agg is None:
        raise BuildError("the source trust's committed aggregates are missing")
    patch, summary = published.patch_from_aggregates(agg, attendances_per_day=adult_per_day)
    patch["attributes"].pop("paediatric", None)
    patch.get("service_means", {}).pop("paeds_assessment", None)
    summary = [s for s in summary if not s.lower().startswith("paediatric share")]
    summary.append("Paediatric share removed: the adult demonstrator has no children in demand.")
    return patch, summary


# --------------------------------------------------------------------------- #
# pathway transforms
# --------------------------------------------------------------------------- #
def _nodes(raw):
    return {n["id"]: n for n in raw["nodes"]}


def _route_lists(node):
    """Every [[target, p], ...] list in a node (mutable references)."""
    out = []
    if node.get("routes"):
        out.append(node["routes"])
    for lst in (node.get("routes_by_class") or {}).values():
        out.append(lst)
    for lst in (node.get("routes_by_attribute") or {}).values():
        out.append(lst)
    return out


def _retarget(raw, old, new, skip=()):
    """Point every reference to ``old`` at ``new`` (routes, fallbacks, signal
    diversions and reneging), except inside the nodes in ``skip``."""
    for node in raw["nodes"]:
        if node["id"] in skip:
            continue
        for lst in _route_lists(node):
            for r in lst:
                if r[0] == old:
                    r[0] = new
        for d in node.get("routes_by_signal") or []:
            if d.get("target") == old:
                d["target"] = new
        if node.get("closed_fallback") == old:
            node["closed_fallback"] = new
        if (node.get("renege") or {}).get("to") == old:
            node["renege"]["to"] = new


def _merge(lst):
    acc = {}
    for t, p in lst:
        acc[t] = acc.get(t, 0.0) + float(p)
    tot = sum(acc.values()) or 1.0
    return [[t, round(p / tot, 6)] for t, p in acc.items() if p > 0]


def _split(base_routes, shares: dict) -> list:
    """Take ``shares`` {target: probability} off the top of an existing route
    list, scaling the rest down proportionally (they keep their relative mix)."""
    take = sum(float(v) for v in shares.values())
    if take <= 0:
        return base_routes
    if take >= 1:
        raise BuildError(f"routing shares add to {take:.2f}; they must be below 1")
    rest = [[t, float(p) * (1 - take)] for t, p in base_routes]
    return _merge(rest + [[t, float(p)] for t, p in shares.items() if float(p) > 0])


def make_adult(raw: dict) -> None:
    """Remove every paediatric element the shared builder may have left behind
    (routes keyed on the paediatric attribute, paediatric resources in release
    lists, the paediatric metric hook). Raises if a paediatric node survives."""
    raw.get("arrivals", {}).get("attributes", {}).pop("paediatric", None)
    for s in raw.get("arrivals", {}).get("streams") or []:
        (s.get("attributes") or {}).pop("paediatric", None)
    (raw.get("uec") or {}).pop("paediatric_attr", None)
    for node in raw["nodes"]:
        rba = node.get("routes_by_attribute")
        if rba:
            rba.pop("paediatric", None)
            if not rba:
                node.pop("routes_by_attribute")
        if node.get("release"):
            node["release"] = [r for r in node["release"] if not r.startswith("paeds")]
    for r in list(raw["resources"]):
        if r.startswith("paeds"):
            del raw["resources"][r]
    bad = [n["id"] for n in raw["nodes"] if "paed" in n["id"] or "paed" in n.get("label", "").lower()]
    if bad:
        raise BuildError(f"paediatric nodes survived the adult build: {bad}")


def add_sdec(raw: dict, sdec: dict) -> None:
    """SDEC reachable from streaming and from RAT (and RAT from streaming), an
    explicit closed-hours redirect, and the SDEC stay split into a clinician
    assessment and clinician-free care, ending in an SDEC outcome that is
    either a decision to admit or a discharge FROM SDEC."""
    nodes = _nodes(raw)
    if "sdec" not in nodes:
        return                                    # SDEC switched off in this scenario
    routing = sdec.get("routing") or {}
    st, rat = nodes.get("streaming"), nodes.get("rat")
    for cls, p in (routing.get("from_streaming") or {}).items():
        if st and cls in st.get("routes_by_class", {}):
            extra = {"sdec": p}
            q = (routing.get("streaming_to_rat") or {}).get(cls)
            if q and rat:
                extra["rat"] = q
            st["routes_by_class"][cls] = _split(st["routes_by_class"][cls], extra)
    for cls, q in (routing.get("streaming_to_rat") or {}).items():
        if st and rat and cls in st.get("routes_by_class", {}) \
                and cls not in (routing.get("from_streaming") or {}):
            st["routes_by_class"][cls] = _split(st["routes_by_class"][cls], {"rat": q})
    for cls, p in (routing.get("from_rat") or {}).items():
        if rat and cls in rat.get("routes_by_class", {}):
            rat["routes_by_class"][cls] = _split(rat["routes_by_class"][cls], {"sdec": p})

    node = nodes["sdec"]
    node.update({"label": "SDEC assessment", "band": "emergency_4_12h",
                 "acquire": ["sdec_chair"], "resource": "specialty_doctor",
                 "service": dict(sdec["assessment_service"]),
                 "routes": [["sdec_care", 1.0]], "release": []})
    node.pop("service_by_class", None)
    # the closed-hours redirect: by acuity, to the area the patient would have
    # used without SDEC (never a removal, never an automatic discharge)
    o, c = (sdec.get("hours") or [0, 24])
    # a patient not given an SDEC chair and clinician within the SDEC wait limit
    # (or still queued when SDEC closes and its staff go off) is redirected to
    # the ED area for their acuity - the same explicit fallback as a closure
    if sdec.get("max_wait"):
        node["renege"] = {"patience": dict(sdec["max_wait"]), "to": "sdec_closed"}
        node["renege_includes_space"] = True
    if [int(o), int(c)] != [0, 24]:
        node["open_hours"] = [int(o), int(c)]
        node["closed_fallback"] = "sdec_closed"
    else:
        node.pop("open_hours", None)
        node.pop("closed_fallback", None)
    fb = {cls: tgt for cls, tgt in (sdec.get("closed_fallback") or {}).items() if tgt in nodes}
    raw["nodes"].append({
        "id": "sdec_closed", "type": "process", "label": "SDEC closed: redirected",
        "service": {"dist": "constant", "value": 0},
        "routes_by_class": {cls: [[tgt, 1.0]] for cls, tgt in fb.items()},
        "routes": [["ed_cubicles", 1.0]]})
    raw["nodes"].append({
        "id": "sdec_care", "type": "process", "label": "SDEC care and observation",
        "band": "emergency_4_12h", "bedded_care": False,
        "service": dict(sdec["care_service"]), "routes": [["sdec_outcome", 1.0]]})
    adm = float(sdec.get("admission_rate", 0.0))
    out = nodes.get("sdec_outcome")
    out.update({"label": "SDEC outcome", "band": "emergency_4_12h", "release": ["sdec_chair"],
                "service": {"dist": "constant", "value": 0},
                "routes": [r for r in [["await_inpatient_bed", adm],
                                       ["discharged_sdec", 1.0 - adm]] if r[1] > 0]})
    raw["nodes"].append({"id": "discharged_sdec", "type": "sink", "label": "Discharged from SDEC"})


def add_decision_to_admit(raw: dict, mh_admission_rate: float) -> None:
    """Decision to admit is a MILESTONE (zero duration, an event count) that
    precedes the occupied wait for a bed, which precedes the transfer to the
    ward, which precedes the completed departure. Same for mental health."""
    nodes = _nodes(raw)
    if "await_inpatient_bed" in nodes:
        raw["nodes"].append({"id": "decision_to_admit", "type": "process",
                             "label": "Decision to admit", "band": "admission_12h_plus",
                             "milestone": True, "service": {"dist": "constant", "value": 0},
                             "routes": [["await_inpatient_bed", 1.0]]})
        _retarget(raw, "await_inpatient_bed", "decision_to_admit", skip=("decision_to_admit",))
    if "await_mh_bed" in nodes:
        raw["nodes"].append({"id": "decision_to_admit_mh", "type": "process",
                             "label": "Decision to admit (mental health)",
                             "band": "admission_12h_plus", "milestone": True,
                             "service": {"dist": "constant", "value": 0},
                             "routes": [["await_mh_bed", 1.0]]})
        _retarget(raw, "await_mh_bed", "decision_to_admit_mh", skip=("decision_to_admit_mh",))
        disp = nodes.get("disposition")
        if disp is not None:
            r = float(mh_admission_rate)
            disp.setdefault("routes_by_attribute", {})
            # keep mental health FIRST: attribute routes are tried in order
            rba = {"mental_health": [x for x in [["decision_to_admit_mh", r],
                                                 ["discharge", 1.0 - r]] if x[1] > 0]}
            for k, v in disp["routes_by_attribute"].items():
                if k != "mental_health":
                    rba[k] = v
            disp["routes_by_attribute"] = rba


def _targets(node):
    out = set()
    for lst in _route_lists(node):
        out |= {t for t, _ in lst}
    out |= {d["target"] for d in node.get("routes_by_signal") or []}
    if node.get("closed_fallback"):
        out.add(node["closed_fallback"])
    if (node.get("renege") or {}).get("to"):
        out.add(node["renege"]["to"])
    return out


def prune_unreachable(raw: dict) -> list[str]:
    nodes = _nodes(raw)
    src = next(n["id"] for n in raw["nodes"] if n.get("type") == "source")
    seen, stack = {src}, [src]
    while stack:
        for t in _targets(nodes[stack.pop()]):
            if t in nodes and t not in seen:
                seen.add(t)
                stack.append(t)
    gone = [n["id"] for n in raw["nodes"] if n["id"] not in seen]
    raw["nodes"] = [n for n in raw["nodes"] if n["id"] in seen]
    used = set()
    for n in raw["nodes"]:
        used |= set(n.get("acquire") or []) | set(n.get("resources") or [])
        if n.get("resource"):
            used.add(n["resource"])
    for r in list(raw["resources"]):
        if r not in used:
            del raw["resources"][r]
    for n in raw["nodes"]:
        if n.get("release"):
            n["release"] = [r for r in n["release"] if r in raw["resources"]]
    return gone


# --------------------------------------------------------------------------- #
# the pipeline
# --------------------------------------------------------------------------- #
def validate_inputs(inputs: dict) -> list[dict]:
    """Input checks the UI shows before anything runs. Empty = OK."""
    errs = []
    _, rota_err = validate_rota(inputs.get("rota") or [])
    errs += [{"field": "rota", **e} for e in rota_err]
    for k, v in (inputs.get("capacity") or {}).items():
        try:
            if v is None or int(v) != float(v) or int(v) < 0:
                raise ValueError
        except (TypeError, ValueError):
            errs.append({"field": f"capacity.{k}", "error": "must be a whole number, 0 or more"})
    for e in inputs.get("space_staffing") or []:
        try:
            if float(e.get("spaces_per_staff")) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errs.append({"field": f"space_staffing.{e.get('space')}",
                         "error": "spaces per member of staff must be above 0"})
    for k, (o, c) in (inputs.get("areas") or {}).get("hours", {}).items():
        if not (0 <= int(o) <= 24 and 0 <= int(c) <= 24):
            errs.append({"field": f"hours.{k}", "error": "opening hours must be 0-24"})
    t = inputs.get("target") or {}
    try:
        if not (0 < float(t.get("pct")) <= 100 and 0 < float(t.get("minutes")) <= 2880):
            raise ValueError
    except (TypeError, ValueError):
        errs.append({"field": "target", "error": "target must be 0-100% within 1-2880 minutes"})
    dts = (inputs.get("process") or {}).get("decision_time_scale", 1.0)
    try:
        if not 0.5 <= float(dts) <= 1.5:
            raise ValueError
    except (TypeError, ValueError):
        errs.append({"field": "process.decision_time_scale",
                     "error": "the change in decision time must be between half and one and a half times"})
    scale = (inputs.get("cohort") or {}).get("demand_scale", 1.0)
    try:
        if not 0.2 <= float(scale) <= 2.0:
            raise ValueError
    except (TypeError, ValueError):
        errs.append({"field": "cohort.demand_scale", "error": "demand scale must be 0.2-2.0"})
    return errs


def scale_decision_time(raw: dict, scale: float) -> None:
    """A process change: the "awaiting results, review or decision" step takes
    ``scale`` times as long. The engine uses the per-acuity ``service_by_class``
    times in preference to ``service``, so both are scaled (mean and spread,
    keeping the shape). 1.0 leaves the pathway untouched."""
    if abs(scale - 1.0) < 1e-12:
        return
    for n in raw["nodes"]:
        if n["id"] != "disposition":
            continue
        specs = [n.get("service")] + list((n.get("service_by_class") or {}).values())
        for spec in specs:
            if not spec:
                continue
            for k in ("mean", "stdev"):
                if isinstance(spec.get(k), (int, float)):
                    spec[k] = round(float(spec[k]) * scale, 4)


def build_model(inputs: dict) -> Model:
    errs = validate_inputs(inputs)
    if errs:
        raise BuildError("the scenario inputs are not valid", errs)
    rota, _ = validate_rota(inputs["rota"])
    cohort = inputs["cohort"]
    per_day = float(cohort["adult_attendances_per_day"]) * float(cohort.get("demand_scale", 1.0))
    areas = inputs["areas"]
    enabled = [a for a in areas["enabled"] if a != "paeds"]
    hours = {k: list(v) for k, v in areas.get("hours", {}).items()}
    if "sdec" in enabled and inputs.get("sdec", {}).get("hours"):
        hours["sdec"] = list(inputs["sdec"]["hours"])
    ds = inputs["downstream"]
    dept = Department(name=MIDSHIRE_NAME, attendances_per_day=per_day, enabled=enabled,
                      rota=rota, rota_source="supplied",
                      inpatient_beds=int(ds["inpatient_beds"]),
                      community_capacity=int(ds["community_capacity"]),
                      hours=hours, baseline_bed_occupancy=float(ds["baseline_bed_occupancy"]),
                      capacity={k: int(v) for k, v in inputs["capacity"].items()},
                      space_staffing=copy.deepcopy(inputs["space_staffing"]))
    raw = build_dept(dept)

    patch, cal_summary = adult_patch(per_day)
    raw = apply_patch(raw, patch)

    make_adult(raw)
    add_sdec(raw, inputs.get("sdec") or {})
    add_decision_to_admit(raw, (inputs.get("mental_health") or {}).get("admission_rate", 0.0))
    if int(inputs["downstream"].get("community_capacity") or 0) <= 0:
        # no community capacity: no community diversion route at all
        for n in raw["nodes"]:
            if n.get("routes_by_signal"):
                n["routes_by_signal"] = [d for d in n["routes_by_signal"]
                                         if d.get("target") != "community_referral"]
                if not n["routes_by_signal"]:
                    n.pop("routes_by_signal")
    labels = mcfg.fixture()["labels"]
    for n in raw["nodes"]:
        if n["id"] in labels:
            n["label"] = labels[n["id"]]
    scale_decision_time(raw, float((inputs.get("process") or {}).get("decision_time_scale", 1.0)))
    pruned = prune_unreachable(raw)

    # the hospital is the source hospital; only the ED cohort changes
    sd = raw.setdefault("sd", {})
    for k, v in ds.items():
        if k not in ("reference_beds", "community_turnover_hours"):
            sd[k] = v
    # community clearance follows capacity: each place turns over once per
    # community_turnover_hours (see the fixture's community_note)
    turn = float(ds.get("community_turnover_hours") or 24)
    sd["community_clearance_per_hour"] = round(float(ds["community_capacity"]) / turn, 6)
    ref = ds.get("reference_beds")
    if ref and int(ds["inpatient_beds"]) != int(ref):
        # NEW beds start empty: the original hospital's occupied beds carry over
        sd["initial_occupied_beds"] = round(float(ds["baseline_bed_occupancy"]) * float(ref), 2)

    eng = inputs["engine"]
    raw["warmup_minutes"] = int(eng["warmup_days"]) * 1440
    raw["sim_duration_minutes"] = (int(eng["warmup_days"]) + int(eng["observed_days"])) * 1440 \
        + int(eng["drain_hours"]) * 60
    raw["target_minutes"] = float((inputs.get("target") or {}).get("minutes", 240))
    raw["name"] = MIDSHIRE_NAME
    uec = raw.setdefault("uec", {})
    uec.update({"edition": "midshire", "cohort": "adult",
                "cohort_window": [raw["warmup_minutes"],
                                  (int(eng["warmup_days"]) + int(eng["observed_days"])) * 1440],
                "sdec_boundary": (inputs.get("reporting") or {}).get("sdec_boundary", "inside_ed"),
                "calibration_summary": cal_summary, "pruned_nodes": pruned})

    problems = validate_schema(Pathway.from_dict(raw))
    if problems:
        raise BuildError("the built pathway is not valid", [{"error": p} for p in problems])

    week = staffing_by_week(rota)
    physical, open_cap = {}, {}
    phys = uec.get("physical_spaces") or {}
    for r, cap in raw["resources"].items():
        cap_w = list(cap) * (7 if len(cap) == 24 else 1) if isinstance(cap, list) else [int(cap)] * 168
        open_cap[r] = cap_w
        p = phys.get(r)
        physical[r] = (list(p) * (7 if len(p) == 24 else 1)) if p else (
            cap_w if r not in STAFF_RESOURCES else None)
    warnings = list(uec.get("build_warnings") or [])
    used_staff = set(raw["resources"]) | {e["staff"] for e in inputs["space_staffing"]}
    for sh in rota:
        res = ROLES[sh["role"]]["staffs"]
        if res not in used_staff and res in STAFF_RESOURCES:
            warnings.append(f"{ROLES[sh['role']]['label']} is on the rota but no modelled area "
                            f"uses {AREA_LABEL.get(res, res)} - costed, but it cannot change "
                            f"performance.")
    m = Model(raw=raw, rota=rota, staffing_week=week, physical=physical, open_capacity=open_cap,
              warnings=sorted(set(warnings)), provenance=provenance(inputs, cal_summary))
    m.model_hash = mcfg.model_hash(inputs)
    return m


def provenance(inputs: dict, cal_summary: list) -> list[dict]:
    """What each input is: historical (source trust), published, derived,
    calibrated, illustrative (synthetic), or a simulated output."""
    f = mcfg.fixture()
    rows = [
        {"item": "Adult attendances per day", "value": inputs["cohort"]["adult_attendances_per_day"],
         "kind": "derived", "source": f["cohort"]["adult_attendances_per_day"]["provenance"]},
        {"item": "All-ages attendances (source trust)", "value": 400.5, "kind": "published",
         "source": f["cohort"]["all_ages_attendances_per_day"]["provenance"]},
        {"item": "Paediatric share removed", "value": 0.1335, "kind": "historical",
         "source": f["cohort"]["paediatric_share_excluded"]["provenance"]},
    ]
    for line in cal_summary:
        rows.append({"item": "Calibration (source trust aggregates)", "value": None,
                     "kind": "historical / calibrated", "source": line})
    for k, v in inputs["capacity"].items():
        src = f["capacity"]["provenance"].get(k, "Scenario input")
        kind = "illustrative" if src.upper().startswith("ILLUSTRATIVE") else (
            "template estimate" if src.lower().startswith("template") else "historical")
        if v != f["capacity"]["values"].get(k):
            kind, src = "scenario change", f"Changed in this scenario (baseline {f['capacity']['values'].get(k)})."
        rows.append({"item": f"Physical capacity: {k}", "value": v, "kind": kind, "source": src})
    rows += [
        {"item": "Rota", "value": f"{len(inputs['rota'])} rows", "kind": "illustrative",
         "source": f["rota"]["provenance"]},
        {"item": "Staff costs", "value": None, "kind": "illustrative", "source": f["cost_table"]["status"]},
        {"item": "Estates unit costs", "value": None, "kind": "illustrative", "source": f["estates"]["status"]},
        {"item": "Space-staffing ratios", "value": None, "kind": "illustrative",
         "source": f["space_staffing"]["note"]},
        {"item": "SDEC routing, hours, size and stay split", "value": None, "kind": "illustrative",
         "source": f["sdec"]["routing_note"] + " " + f["sdec"]["service_note"]},
        {"item": "SDEC admission rate", "value": inputs["sdec"]["admission_rate"], "kind": "historical",
         "source": f["sdec"]["admission_provenance"]},
        {"item": "Mental-health admission rate", "value": inputs["mental_health"]["admission_rate"],
         "kind": "historical", "source": f["mental_health"]["provenance"]},
        {"item": "Hospital bed model", "value": inputs["downstream"]["inpatient_beds"],
         "kind": "published / template", "source": f["downstream"]["provenance"]},
        {"item": "Everything on the Overview and Patient flow screens", "value": None,
         "kind": "simulated output", "source": "The discrete-event + system-dynamics simulation of these inputs."},
    ]
    for a in f["cohort"]["assumptions"]:
        rows.append({"item": "Cohort assumption", "value": None, "kind": "assumption", "source": a})
    return rows
