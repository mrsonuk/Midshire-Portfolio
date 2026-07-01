"""A sensible default rota for the ~320/day template ED, with a daytime peak and
overnight dip — the starting point a department then edits."""

DEFAULT_ROTA = [
    # majors / cubicles / resus doctors (consultant + registrar + SHO)
    {"role": "ed_consultant", "start": 8,  "end": 20, "count": 3},
    {"role": "ed_consultant", "start": 20, "end": 8,  "count": 1},
    {"role": "em_registrar",  "start": 8,  "end": 22, "count": 5},
    {"role": "em_registrar",  "start": 22, "end": 8,  "count": 3},
    {"role": "em_sho",        "start": 10, "end": 23, "count": 6},
    {"role": "em_sho",        "start": 22, "end": 10, "count": 3},
    # front-door streaming
    {"role": "streaming_nurse", "start": 0,  "end": 24, "count": 1},
    {"role": "streaming_nurse", "start": 8,  "end": 22, "count": 2},
    # rapid assessment (senior decision-makers)
    {"role": "rat_consultant", "start": 8,  "end": 22, "count": 2},
    {"role": "rat_consultant", "start": 22, "end": 8,  "count": 1},
    # children's area
    {"role": "paeds_doctor", "start": 9,  "end": 22, "count": 3},
    {"role": "paeds_doctor", "start": 22, "end": 9,  "count": 1},
    # SDEC / specialty (daytime)
    {"role": "sdec_doctor", "start": 8,  "end": 20, "count": 5},
    {"role": "sdec_doctor", "start": 20, "end": 23, "count": 1},
    # frailty (daytime)
    {"role": "frailty_pract", "start": 8,  "end": 18, "count": 4},
    {"role": "frailty_pract", "start": 18, "end": 8,  "count": 1},
    # mental-health liaison (24/7 cover, daytime uplift)
    {"role": "mh_liaison", "start": 0,  "end": 24, "count": 1},
    {"role": "mh_liaison", "start": 9,  "end": 21, "count": 2},
    # ED nursing — the biggest staff group (Bands 5/6, day-heavy)
    {"role": "band6_nurse", "start": 8,  "end": 20, "count": 4},
    {"role": "band6_nurse", "start": 20, "end": 8,  "count": 2},
    {"role": "band5_nurse", "start": 8,  "end": 20, "count": 8},
    {"role": "band5_nurse", "start": 20, "end": 8,  "count": 5},
    # nurse practitioners on minors (daytime into evening)
    {"role": "enp", "start": 10, "end": 22, "count": 2},
    # support team
    {"role": "hca", "start": 8,  "end": 20, "count": 4},
    {"role": "hca", "start": 20, "end": 8,  "count": 2},
    {"role": "porter", "start": 0, "end": 24, "count": 2},
    {"role": "receptionist", "start": 8,  "end": 22, "count": 3},
    {"role": "receptionist", "start": 22, "end": 8,  "count": 1},
]
