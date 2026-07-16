"""
Optional Claude integration for the assist layer.

Design rules (why NHS deployments stay safe and offline):
- Entirely optional: used only when the ``anthropic`` package is installed AND
  ``ANTHROPIC_API_KEY`` is set. Neither ships in requirements.txt, so a
  locked-down NHS install never makes an outbound call - the rule-based
  parser and templated narration take over with identical numbers.
- The model never computes: it translates a question into a scenario (which
  we validate against the department's real resources) and phrases a summary
  of numbers the engine already computed. Only aggregate simulation results
  are ever sent - no patient-level data exists in this product at all.
- Every call is wrapped: any failure returns None and the offline path runs.
"""
from __future__ import annotations

import json
import os

MODEL = "claude-opus-4-8"


def available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def _client():
    import anthropic
    return anthropic.Anthropic()


# --- fallback parser: free-form question -> validated scenario ---------------- #
def _schema(resource_names: list[str]) -> dict:
    num_or_null = {"anyOf": [{"type": "number"}, {"type": "null"}]}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["resources", "demand_change_pct", "extra_ward_beds",
                     "extra_community", "divert_minors_pct", "understood"],
        "properties": {
            "resources": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["name", "delta"],
                "properties": {"name": {"type": "string", "enum": resource_names},
                               "delta": {"type": "integer"}}}},
            "demand_change_pct": num_or_null,
            "extra_ward_beds": num_or_null,
            "extra_community": num_or_null,
            "divert_minors_pct": num_or_null,
            "understood": {"type": "string"},
        },
    }


def parse_with_llm(question: str, raw: dict):
    """Ask Claude to translate a free-form what-if into our scenario shape.
    Returns (scenario, notes) or None. Output is schema-constrained and then
    validated: only real resources, bounded numbers."""
    try:
        names = sorted(raw.get("resources", {}).keys())
        resp = _client().messages.create(
            model=MODEL,
            max_tokens=2048,
            system=("You translate a plain-English NHS emergency-department what-if "
                    "question into a structured change set for a simulation. Only "
                    "capture changes the question actually asks for; use null for "
                    "anything not mentioned. 'understood' restates the change in "
                    "one short plain sentence."),
            messages=[{"role": "user", "content": question}],
            output_config={"format": {"type": "json_schema", "schema": _schema(names)}},
        )
        if resp.stop_reason == "refusal":
            return None
        data = json.loads(next(b.text for b in resp.content if b.type == "text"))
        scenario, notes = {}, []
        for r in data.get("resources") or []:
            if r["name"] in raw.get("resources", {}) and r["delta"]:
                delta = max(-50, min(50, int(r["delta"])))
                scenario.setdefault("resources", {})[r["name"]] = f"{delta:+d}"
                notes.append(f"{r['name'].replace('_', ' ')}: {delta:+d}")
        if data.get("demand_change_pct"):
            pct = max(-90, min(100, float(data["demand_change_pct"])))
            scenario["arrivals_scale"] = round(1 + pct / 100, 3)
            notes.append(f"demand x{scenario['arrivals_scale']}")
        sd_now = raw.get("sd", {})
        if data.get("extra_ward_beds"):
            beds = max(1, int(sd_now.get("inpatient_beds", 320)) + int(data["extra_ward_beds"]))
            scenario.setdefault("sd", {})["inpatient_beds"] = beds
            notes.append(f"ward beds -> {beds}")
        if data.get("extra_community"):
            comm = max(0, int(sd_now.get("community_capacity", 60)) + int(data["extra_community"]))
            scenario.setdefault("sd", {})["community_capacity"] = comm
            notes.append(f"community capacity -> {comm}")
        if data.get("divert_minors_pct"):
            frac = max(0.0, min(0.9, float(data["divert_minors_pct"]) / 100))
            scenario["divert"] = {"classes": ["Acuity 4", "Acuity 5"], "fraction": frac}
            notes.append(f"redirect {frac * 100:.0f}% of low-acuity patients")
        if not scenario:
            return None
        if data.get("understood"):
            notes.insert(0, data["understood"])
        return scenario, notes
    except Exception:
        return None


# --- narration: computed results -> plain-language answer --------------------- #
def narrate(payload: dict):
    """Phrase the engine's computed deltas in plain language. The prompt forbids
    inventing numbers; the computed table is displayed regardless, so a bad
    narration can never smuggle in a figure the user can't check."""
    try:
        resp = _client().messages.create(
            model=MODEL,
            max_tokens=1024,
            system=("You narrate results from an NHS emergency-department simulation "
                    "for a non-technical operations audience. Write 2-4 plain "
                    "sentences. Use ONLY the numbers present in the JSON you are "
                    "given (you may round to one decimal). Never invent, extrapolate "
                    "or compute new figures. Mention that differences under about one "
                    "percentage point may be simulation noise. British English."),
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
        if resp.stop_reason == "refusal":
            return None
        text = next((b.text for b in resp.content if b.type == "text"), "").strip()
        return text or None
    except Exception:
        return None
