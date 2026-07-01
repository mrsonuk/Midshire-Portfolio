"""
The cost book: every pound the platform shows comes from here, and every figure
is trust-editable. The defaults are INDICATIVE planning values so a department
can weigh options on day one — they are deliberately conservative, clearly
flagged, and must be replaced with the trust's own finance figures before a
business case is submitted anywhere.

No figure here is presented as a national benchmark; they are editable
assumptions, and the assumptions used are printed on every business case.
"""
from __future__ import annotations

from ..platform import store

DEFAULT_COST_BOOK = {
    "currency": "GBP",
    # workforce (per-hour role rates live in workforce/roles.py and are editable there)
    "agency_premium": 1.6,          # cost of an agency-filled hour vs substantive
    "agency_share_pct": 12,         # share of ED staffing hours currently agency-filled
    # value of avoided harm/pressure — indicative planning values, trust-editable
    "admission_avoided": 1600,      # £ per non-elective admission avoided (bed-days released)
    "twelve_hour_breach": 400,      # £ per 12-hour breach avoided (corridor nursing, harm proxy)
    "four_hour_breach": 90,         # £ per 4-hour breach avoided (extra bed-hours, delayed care)
    # what an option's cost band means in £/year (recurring), midpoint used for ROI
    "option_cost_bands": {
        "Low": [25_000, 100_000],
        "Moderate": [100_000, 500_000],
        "High": [500_000, 2_000_000],
    },
    "note": ("Indicative planning defaults — replace with your trust's finance "
             "figures (Cost book) before submitting a business case."),
}

_SETTING_KEY = "cost_book"


def load_cost_book() -> dict:
    """The saved cost book merged over the defaults (missing keys fall back)."""
    saved = store.get_setting(_SETTING_KEY) or {}
    merged = {**DEFAULT_COST_BOOK, **saved}
    merged["option_cost_bands"] = {**DEFAULT_COST_BOOK["option_cost_bands"],
                                   **(saved.get("option_cost_bands") or {})}
    return merged


def save_cost_book(values: dict) -> dict:
    """Persist trust edits (only known keys) and return the merged book."""
    clean = {k: v for k, v in (values or {}).items() if k in DEFAULT_COST_BOOK}
    store.save_setting(_SETTING_KEY, clean)
    return load_cost_book()
