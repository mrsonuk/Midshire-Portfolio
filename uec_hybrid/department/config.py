"""
A Department is a trust's own ED: which Model ED areas they actually have, its
size, and its workforce rota. It serialises to/from JSON (the v1 "save"), and is
turned into a runnable model by department/builder.py.

The AREAS catalogue lists the toggleable Model ED elements. Each names the model
nodes it owns, the resources it uses, and a safe fallback for when it is switched
off (so no patient is left without a route). 'reroute' areas sit in the main path
(their patients divert to the fallback node); 'option' areas are downstream choices
(their edge is dropped and the remaining choices renormalised).
"""
from __future__ import annotations

from dataclasses import dataclass, field

# key -> {label, nodes, resources, fallback, mode, model_ed (is it a Model ED ask?)}
AREAS = {
    "rat": {"label": "Rapid Assessment & Treatment (RAT)", "nodes": ["rat"],
            "resources": ["rat_clinician"], "fallback": "ed_cubicles", "mode": "reroute",
            "hours": [0, 24],
            "why": "Senior decision-makers at the front for early decisions on the sickest."},
    "utc": {"label": "Co-located Urgent Treatment Centre", "nodes": ["utc_minor_illness"],
            "resources": ["utc_room"], "fallback": "ed_minor_injury", "mode": "reroute",
            "hours": [8, 24],
            "why": "Streams minor illness out of the ED so it can prioritise emergencies."},
    "fit_to_sit": {"label": "Ambulatory ‘fit to sit’ area", "nodes": ["ed_ambulatory"],
                   "resources": ["fit_to_sit_chair"], "fallback": "ed_cubicles", "mode": "reroute",
                   "hours": [8, 22],
                   "why": "Seated care for ambulatory patients, freeing cubicles/trolleys."},
    "paeds": {"label": "Children’s area / PAU", "nodes": ["paeds_assessment"],
              "resources": ["paeds_cubicle", "paeds_doctor"], "fallback": "ed_cubicles", "mode": "reroute",
              "hours": [8, 22],
              "why": "Dedicated children’s space and paediatric-competent decision-makers."},
    # Same-day / ambulatory / assessment areas AVOID admission. Without them those
    # patients are admitted (occupying scarce beds → exit-block), so the fallback
    # is the inpatient-bed wait - which is why having them improves flow.
    "eemac": {"label": "EEMAC (extended emergency ambulatory care)", "nodes": ["eemac", "eemac_outcome"],
              "resources": ["eemac_space"], "fallback": "await_inpatient_bed", "mode": "reroute",
              "hours": [8, 22],
              "why": "Up to 12h emergency-medicine care for patients who would otherwise be admitted."},
    "sdec": {"label": "Specialty Same-Day Emergency Care (SDEC)", "nodes": ["sdec", "sdec_outcome"],
             "resources": ["sdec_chair", "specialty_doctor"], "fallback": "await_inpatient_bed", "mode": "reroute",
             "hours": [8, 20],
             "why": "Same-day specialty pathway that avoids an overnight admission."},
    "cdu": {"label": "Clinical Decision Unit (CDU)", "nodes": ["cdu"],
            "resources": ["cdu_bed"], "fallback": "await_inpatient_bed", "mode": "reroute",
            "hours": [0, 24],
            "why": "Short-stay observation that avoids admitting to a ward bed."},
    "frailty": {"label": "Frailty unit (FAU)", "nodes": ["fau"],
                "resources": ["fau_bed", "frailty_team"], "fallback": "await_inpatient_bed", "mode": "attribute",
                "hours": [8, 18],
                "why": "Early frailty assessment that prevents unnecessary admission."},
    "mh": {"label": "Mental-health liaison / MHED", "nodes": ["mh_liaison"],
           "resources": ["mh_clinician", "mh_assessment_room"], "fallback": "await_mh_bed", "mode": "attribute",
           "hours": [0, 24],
           "why": "1-hour mental-health assessment that speeds the right onward care."},
}

# Core nodes a trust can declare OUT OF EXISTENCE by giving their physical
# resource an explicit capacity of 0 (distinct from the AREAS toggles, which
# cover optional areas - these are template nodes some trusts simply don't
# have). ``fallback`` inherits the node's patients; ``closed_substitute`` is
# tried in order when an enabled part-time area's closed-hours fallback pointed
# at the removed node (e.g. the UTC's overnight fallback IS ed_minor_injury -
# at CUH minors are seen in the UTC, so overnight minors divert to the 24/7
# fit-to-sit area instead: a labelled assumption until the trust says where
# overnight minors actually go).
ZERO_CAPACITY_NODES = {
    "minor_injury_space": {"node": "ed_minor_injury", "fallback": "utc_minor_illness",
                           "closed_substitute": ["ed_ambulatory", "ed_cubicles"]},
}

# default opening hours [open, close] per area; [0, 24] == always open (24/7)
DEFAULT_HOURS = {k: list(a.get("hours", [0, 24])) for k, a in AREAS.items()}

# Always-present core (front door, cubicles, resus, imaging, decision, admission)
CORE_NOTE = "Front door, cubicles, resus, imaging, the clinical decision and admission are always present."


@dataclass
class Department:
    name: str = "Your Emergency Department"
    attendances_per_day: float = 320.0
    enabled: list = field(default_factory=lambda: list(AREAS.keys()))
    rota: list = field(default_factory=list)
    inpatient_beds: int = 320
    community_capacity: int = 60
    # opening hours [open, close] per area; defaults to DEFAULT_HOURS, [0,24] == 24/7
    hours: dict = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_HOURS.items()})
    # observed whole-hospital bed occupancy (0-1). None = use the pathway's SD
    # default; set it (e.g. from a trust's bed-availability return) so exit-block
    # feedback reflects how full THIS hospital actually runs.
    baseline_bed_occupancy: float | None = None
    # REAL physical capacity by resource key (e.g. {"cdu_bed": 6, "cubicle": 28}).
    # Empty = the Model ED template scaled by attendances; a trust's own counts
    # replace the scaled figure exactly (no open dataset publishes these, so they
    # can only come from the trust). Staff resources are rota-driven, not set here.
    capacity: dict = field(default_factory=dict)

    @classmethod
    def default(cls):
        # A realistic mid-maturity Type 1 ED: has rapid assessment, SDEC,
        # children's area and MH liaison, but is MISSING several Model ED
        # elements (co-located UTC, fit-to-sit, EEMAC, CDU, frailty unit) - so the
        # gap view has something to show.
        from ..workforce.defaults import DEFAULT_ROTA
        return cls(enabled=["rat", "sdec", "paeds", "mh"], rota=list(DEFAULT_ROTA))

    def hours_for(self, area: str) -> list:
        """Opening hours for an area, falling back to the catalogue default."""
        return list((self.hours or {}).get(area, DEFAULT_HOURS.get(area, [0, 24])))

    def to_dict(self):
        return {"name": self.name, "attendances_per_day": self.attendances_per_day,
                "enabled": self.enabled, "rota": self.rota,
                "inpatient_beds": self.inpatient_beds, "community_capacity": self.community_capacity,
                "hours": {k: list(v) for k, v in (self.hours or {}).items()},
                "baseline_bed_occupancy": self.baseline_bed_occupancy,
                "capacity": {k: int(v) for k, v in (self.capacity or {}).items()}}

    @classmethod
    def from_dict(cls, d):
        base = cls.default()
        hours = {k: list(v) for k, v in DEFAULT_HOURS.items()}
        for k, v in (d.get("hours") or {}).items():
            if k in hours and isinstance(v, (list, tuple)) and len(v) == 2:
                hours[k] = [int(v[0]), int(v[1])]
        occ = d.get("baseline_bed_occupancy", base.baseline_bed_occupancy)
        capacity = {}
        for k, v in (d.get("capacity") or {}).items():
            try:
                n = int(v)
            except (TypeError, ValueError):
                continue
            if n >= 0:                     # 0 is meaningful ("we don't have this"); drop only negatives
                capacity[str(k)] = n
        return cls(name=d.get("name", base.name),
                   attendances_per_day=float(d.get("attendances_per_day", base.attendances_per_day)),
                   enabled=d.get("enabled", base.enabled),
                   rota=d.get("rota", base.rota),
                   inpatient_beds=int(d.get("inpatient_beds", base.inpatient_beds)),
                   community_capacity=int(d.get("community_capacity", base.community_capacity)),
                   hours=hours,
                   baseline_bed_occupancy=(float(occ) if occ is not None else None),
                   capacity=capacity)
