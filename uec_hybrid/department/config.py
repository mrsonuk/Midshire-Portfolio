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
            "why": "Senior decision-makers at the front for early decisions on the sickest."},
    "utc": {"label": "Co-located Urgent Treatment Centre", "nodes": ["utc_minor_illness"],
            "resources": ["utc_room"], "fallback": "ed_minor_injury", "mode": "reroute",
            "why": "Streams minor illness out of the ED so it can prioritise emergencies."},
    "fit_to_sit": {"label": "Ambulatory ‘fit to sit’ area", "nodes": ["ed_ambulatory"],
                   "resources": ["fit_to_sit_chair"], "fallback": "ed_cubicles", "mode": "reroute",
                   "why": "Seated care for ambulatory patients, freeing cubicles/trolleys."},
    "paeds": {"label": "Children’s area / PAU", "nodes": ["paeds_assessment"],
              "resources": ["paeds_cubicle", "paeds_doctor"], "fallback": "ed_cubicles", "mode": "reroute",
              "why": "Dedicated children’s space and paediatric-competent decision-makers."},
    # Same-day / ambulatory / assessment areas AVOID admission. Without them those
    # patients are admitted (occupying scarce beds → exit-block), so the fallback
    # is the inpatient-bed wait — which is why having them improves flow.
    "eemac": {"label": "EEMAC (extended emergency ambulatory care)", "nodes": ["eemac", "eemac_outcome"],
              "resources": ["eemac_space"], "fallback": "await_inpatient_bed", "mode": "reroute",
              "why": "Up to 12h emergency-medicine care for patients who would otherwise be admitted."},
    "sdec": {"label": "Specialty Same-Day Emergency Care (SDEC)", "nodes": ["sdec", "sdec_outcome"],
             "resources": ["sdec_chair", "specialty_doctor"], "fallback": "await_inpatient_bed", "mode": "reroute",
             "why": "Same-day specialty pathway that avoids an overnight admission."},
    "cdu": {"label": "Clinical Decision Unit (CDU)", "nodes": ["cdu"],
            "resources": ["cdu_bed"], "fallback": "await_inpatient_bed", "mode": "reroute",
            "why": "Short-stay observation that avoids admitting to a ward bed."},
    "frailty": {"label": "Frailty unit (FAU)", "nodes": ["fau"],
                "resources": ["fau_bed", "frailty_team"], "fallback": "await_inpatient_bed", "mode": "attribute",
                "why": "Early frailty assessment that prevents unnecessary admission."},
    "mh": {"label": "Mental-health liaison / MHED", "nodes": ["mh_liaison"],
           "resources": ["mh_clinician", "mh_assessment_room"], "fallback": "await_mh_bed", "mode": "attribute",
           "why": "1-hour mental-health assessment that speeds the right onward care."},
}

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

    @classmethod
    def default(cls):
        # A realistic mid-maturity Type 1 ED: has rapid assessment, SDEC,
        # children's area and MH liaison, but is MISSING several Model ED
        # elements (co-located UTC, fit-to-sit, EEMAC, CDU, frailty unit) — so the
        # gap view has something to show.
        from ..workforce.defaults import DEFAULT_ROTA
        return cls(enabled=["rat", "sdec", "paeds", "mh"], rota=list(DEFAULT_ROTA))

    def to_dict(self):
        return {"name": self.name, "attendances_per_day": self.attendances_per_day,
                "enabled": self.enabled, "rota": self.rota,
                "inpatient_beds": self.inpatient_beds, "community_capacity": self.community_capacity}

    @classmethod
    def from_dict(cls, d):
        base = cls.default()
        return cls(name=d.get("name", base.name),
                   attendances_per_day=float(d.get("attendances_per_day", base.attendances_per_day)),
                   enabled=d.get("enabled", base.enabled),
                   rota=d.get("rota", base.rota),
                   inpatient_beds=int(d.get("inpatient_beds", base.inpatient_beds)),
                   community_capacity=int(d.get("community_capacity", base.community_capacity)))
