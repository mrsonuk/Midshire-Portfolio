"""
Staff roles for the ED - the workforce a department rosters.

Each role has an indicative cost per hour and the ED area (engine resource) it
staffs. Several roles can staff the same area (e.g. consultant + registrar + SHO
all fill the 'ed_doctor' pool); the rota sums them by hour. Costs are indicative
planning figures (mid-points incl. on-costs) so a department can weigh options -
they are editable.
"""
from __future__ import annotations

# resources that represent STAFF (rostered) vs physical space/equipment (fixed).
# ENPs staff minor injury and porters staff ward transfers as engine resources;
# ED nurses limit flow through the nurse-to-cubicle ratio applied in the builder.
STAFF_RESOURCES = [
    "streaming_nurse", "rat_clinician", "ed_doctor", "paeds_doctor",
    "specialty_doctor", "frailty_team", "mh_clinician",
    "ed_nurse", "minors_enp", "porter_pool",
    "resus_nurse", "utc_clinician", "sdec_nurse",
]

# staff areas that limit flow through a builder RATIO (spaces open = staff on
# shift x spaces per member of staff, never more than the physical spaces)
# rather than as engine resources. They never appear in a built pathway's
# resource list. ed_nurse -> majors cubicles is the template's ratio; the other
# three are used only where a department's space-staffing table names them
# (the Midshire demonstrator does; the Cambridge build does not).
RATIO_RESOURCES = {"ed_nurse", "resus_nurse", "utc_clinician", "sdec_nurse"}

# rostered-and-costed workforce that does not yet limit flow in the engine -
# it appears in the rota, the pay-bill and the staffing-vs-demand view.
SUPPORT_RESOURCES = ["hca_pool", "reception"]

ROLES = {
    "streaming_nurse": {"label": "Streaming / triage nurse", "staffs": "streaming_nurse", "cost": 34},
    "rat_consultant":  {"label": "RAT senior decision-maker", "staffs": "rat_clinician", "cost": 95},
    "ed_consultant":   {"label": "EM consultant", "staffs": "ed_doctor", "cost": 95},
    "em_registrar":    {"label": "EM registrar", "staffs": "ed_doctor", "cost": 55},
    "em_sho":          {"label": "EM junior doctor (SHO)", "staffs": "ed_doctor", "cost": 40},
    "paeds_doctor":    {"label": "Paediatric EM doctor", "staffs": "paeds_doctor", "cost": 58},
    "sdec_doctor":     {"label": "Acute / specialty doctor (SDEC)", "staffs": "specialty_doctor", "cost": 60},
    "frailty_pract":   {"label": "Frailty practitioner", "staffs": "frailty_team", "cost": 46},
    "mh_liaison":      {"label": "Mental-health liaison clinician", "staffs": "mh_clinician", "cost": 42},
    # nursing and support team (rostered + costed; flow constraints in pathway v2)
    "band6_nurse":     {"label": "ED nurse - Band 6", "staffs": "ed_nurse", "cost": 34},
    "band5_nurse":     {"label": "ED nurse - Band 5", "staffs": "ed_nurse", "cost": 28},
    "enp":             {"label": "Emergency nurse practitioner (minors)", "staffs": "minors_enp", "cost": 41},
    "hca":             {"label": "Healthcare assistant", "staffs": "hca_pool", "cost": 20},
    "porter":          {"label": "Porter / patient transport", "staffs": "porter_pool", "cost": 18},
    "receptionist":    {"label": "Receptionist", "staffs": "reception", "cost": 18},
    # ratio-staffed spaces (only limit flow where a space-staffing table uses them)
    "resus_nurse":     {"label": "Resus nurse - Band 6", "staffs": "resus_nurse", "cost": 36},
    "utc_practitioner": {"label": "UTC practitioner (ENP / GP)", "staffs": "utc_clinician", "cost": 48},
    "sdec_nurse":      {"label": "SDEC nurse - Band 5", "staffs": "sdec_nurse", "cost": 30},
}

# Indicative contracted hours per week by role, used ONLY to express extra
# hours as whole-time equivalents (WTE). Professions work different standard
# weeks, so there is deliberately no single figure. Editable per scenario.
CONTRACTED_HOURS = {
    "ed_consultant": 40.0, "rat_consultant": 40.0, "em_registrar": 40.0,
    "em_sho": 40.0, "paeds_doctor": 40.0, "sdec_doctor": 40.0,
    "streaming_nurse": 37.5, "band6_nurse": 37.5, "band5_nurse": 37.5,
    "resus_nurse": 37.5, "sdec_nurse": 37.5, "enp": 37.5,
    "utc_practitioner": 37.5, "frailty_pract": 37.5, "mh_liaison": 37.5,
    "hca": 37.5, "porter": 37.5, "receptionist": 37.5,
}

# nice plain labels for the staff areas, for the workforce view
AREA_LABEL = {
    "streaming_nurse": "Front door (streaming)",
    "rat_clinician": "Rapid assessment (RAT)",
    "ed_doctor": "Majors / cubicles / resus doctors",
    "paeds_doctor": "Children's area doctors",
    "specialty_doctor": "SDEC / specialty doctors",
    "frailty_team": "Frailty team",
    "mh_clinician": "Mental-health liaison",
    "ed_nurse": "ED nursing (majors cubicles)",
    "minors_enp": "Minor injury (ENPs)",
    "hca_pool": "Healthcare assistants",
    "porter_pool": "Porters / patient transport",
    "reception": "Reception / registration",
    "resus_nurse": "Resus nursing",
    "utc_clinician": "UTC practitioners",
    "sdec_nurse": "SDEC nursing",
}


def roles_for(resource: str) -> list[str]:
    return [r for r, m in ROLES.items() if m["staffs"] == resource]


# --------------------------------------------------------------------------- #
# Editable hourly rates: defaults live above; a trust can override them (from the
# cost workbook or the cost book) without touching code. Overrides are stored as
# a setting and merged over the defaults, so unedited roles keep their default.
# --------------------------------------------------------------------------- #
_RATES_KEY = "role_rates"


def default_rates() -> dict:
    return {k: v["cost"] for k, v in ROLES.items()}


def role_rates() -> dict:
    """Hourly rate per role = defaults merged with any stored override."""
    from ..platform import store
    saved = store.get_setting(_RATES_KEY) or {}
    return {**default_rates(), **{k: float(v) for k, v in saved.items() if k in ROLES}}


def save_role_rates(values: dict) -> dict:
    """Persist trust edits to role hourly rates (known roles only)."""
    from ..platform import store
    clean = {k: float(v) for k, v in (values or {}).items()
             if k in ROLES and v is not None}
    store.save_setting(_RATES_KEY, clean)
    return role_rates()
