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
]

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
    "ed_nurse": "ED nursing (majors / resus)",
    "minors_enp": "Minor injury (ENPs)",
    "hca_pool": "Healthcare assistants",
    "porter_pool": "Porters / patient transport",
    "reception": "Reception / registration",
}


def roles_for(resource: str) -> list[str]:
    return [r for r, m in ROLES.items() if m["staffs"] == resource]
