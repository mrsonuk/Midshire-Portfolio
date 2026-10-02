"""
The Midshire metric contract: ONE aggregation layer for every number the cards,
flow diagram, charts, scenario comparisons, exports and Ask Qbo ED show.

Everything is computed from patient-level STATE INTERVALS (the engine's trace):
for each patient, the time they entered and left each (node, phase) - "queue"
(waiting for that step's space or clinician) or "service" (in it). A patient is
in exactly one state at any instant, so:

* occupancy at time t   = unique patients whose interval contains t
                          (intervals are [start, end); a zero-length interval -
                          a milestone such as a decision to admit - holds nobody)
* group occupancy       = the sum of its states (they never overlap)
* census                = unique patients arrived and not yet departed
* waiting               = patients in a state classed "waiting" in the central
                          group table (a queue anywhere, or waiting for a bed /
                          results); in service = the rest
* total ED duration     = departure boundary - arrival, per patient
* total waiting time    = the union of a patient's waiting intervals
                          (never a sum of stage averages)

Nothing is averaged across replications into a "snapshot": the replay comes from
ONE replication. Whole-run KPIs are per replication first, then summarised
across replications. Every metric has a written definition in ``DEFINITIONS``.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats as _st

from . import config as mcfg

STEP = 15                    # replay resolution, minutes

DEFINITIONS = {
    "census": {
        "label": "Patients in the department",
        "population": "Every simulated adult attendance, including patients who arrived before the day started (carry-in).",
        "units": "patients (whole numbers)", "window": "an instant (the viewing time)",
        "aggregation": "count of unique patients", "start": "arrival", "end": "ED departure boundary",
        "in_progress": "counted while present"},
    "waiting": {
        "label": "Patients waiting",
        "population": "Patients present at the viewing time whose current state is a waiting state (waiting for streaming, a handover bay, RAT, a treatment space or clinician, diagnostics, results or a decision, a bed, or a porter).",
        "units": "patients", "window": "an instant", "aggregation": "count of unique patients",
        "start": "entering the waiting state", "end": "leaving it", "in_progress": "counted while waiting"},
    "in_service": {
        "label": "Patients being seen or treated",
        "population": "Patients present whose current state is receiving a service (streaming, handover, RAT, treatment, SDEC care, imaging, transfer, discharge preparation).",
        "units": "patients", "window": "an instant", "aggregation": "count", "start": "service start",
        "end": "service end", "in_progress": "counted while in service"},
    "arrivals_interval": {
        "label": "Arrivals in the interval",
        "population": "Adult arrivals at the front door", "units": "patients",
        "window": "the named interval (for example the hour before the viewing time)",
        "aggregation": "count of arrival events", "start": "-", "end": "-",
        "in_progress": "not applicable - a flow, not a queue size"},
    "departures_interval": {
        "label": "Departures in the interval",
        "population": "Patients reaching an outcome (admitted after ward transfer, discharged from the ED or SDEC, left without being seen)",
        "units": "patients", "window": "the named interval", "aggregation": "count of departure events",
        "start": "-", "end": "-", "in_progress": "not applicable"},
    "elapsed_wait": {
        "label": "Current elapsed wait",
        "population": "Patients waiting at the viewing time",
        "units": "minutes", "window": "an instant", "aggregation": "median and longest across those waiting",
        "start": "entering their current waiting state", "end": "the viewing time",
        "in_progress": "these are all in progress by definition"},
    "four_hour": {
        "label": "Completed within the target time",
        "population": "Eligible adult ED attendances: everyone ARRIVING in the observed days of each replication. No exclusions. Patients who left without being seen are included with the time they left.",
        "units": "% of attendances", "window": "the observed days of each replication",
        "aggregation": "per replication, then the mean (and range) across replications",
        "start": "arrival", "end": "ED departure: after ward transfer for admitted patients, at discharge from the ED or from SDEC, or on leaving unseen. SDEC time counts inside the ED attendance (the clock does not stop at transfer to SDEC).",
        "in_progress": "Each replication runs a 12-hour drain after the cohort window. A patient still in the department at the end has already been there longer than the target, so they count as NOT met; they are also reported as work in progress."},
    "twelve_hour": {
        "label": "Over 12 hours in the department (from arrival)",
        "population": "Same cohort as the target measure", "units": "% of attendances",
        "window": "observed days", "aggregation": "per replication, then across replications",
        "start": "arrival", "end": "ED departure", "in_progress": "unfinished at the end of the drain = over 12 hours"},
    "duration_median": {
        "label": "Time in the department (median)",
        "population": "Same cohort", "units": "minutes", "window": "observed days",
        "aggregation": "median of each patient's own arrival-to-departure time, per replication, then the mean of the replication medians",
        "start": "arrival", "end": "ED departure",
        "in_progress": "unfinished patients are ranked as longer than everyone who finished; the median is 'not available' if more than half are unfinished"},
    "total_wait_median": {
        "label": "Total time waiting (median)",
        "population": "Same cohort", "units": "minutes", "window": "observed days",
        "aggregation": "median of each patient's total waiting time (the union of their waiting intervals)",
        "start": "-", "end": "-", "in_progress": "unfinished patients counted at their waiting time so far, ranked as longest"},
    "waiting_patient_hours": {
        "label": "Waiting patient-hours per day",
        "population": "All patients present during the observed days", "units": "patient-hours per day",
        "window": "observed days", "aggregation": "time-integral of waiting occupancy, divided by the number of days",
        "start": "-", "end": "-", "in_progress": "included for the part inside the window"},
    "lwbs": {
        "label": "Left without being seen", "population": "Same cohort", "units": "% of attendances",
        "window": "observed days", "aggregation": "per replication, then across replications",
        "start": "-", "end": "-", "in_progress": "-"},
    "wip_end": {
        "label": "Unfinished at the end of the run",
        "population": "Cohort patients still in the department when the drain ends", "units": "patients per replication",
        "window": "end of each replication", "aggregation": "mean across replications",
        "start": "-", "end": "-", "in_progress": "this IS the in-progress count (a guardrail: a package must not win by leaving patients unfinished)"},
    "handover_45": {
        "label": "Ambulance handover within 45 minutes",
        "population": "Cohort patients arriving by ambulance", "units": "%", "window": "observed days",
        "aggregation": "per replication", "start": "arrival",
        "end": "start of the handover (a handover bay and crew handover begins)",
        "in_progress": "still waiting at the end = not met"},
    "dta_to_departure": {
        "label": "Decision to admit to departure (median)",
        "population": "Cohort patients with a decision to admit", "units": "minutes", "window": "observed days",
        "aggregation": "median per replication", "start": "decision to admit (a milestone event)",
        "end": "departure after ward transfer", "in_progress": "unfinished ranked as longest"},
    "utilisation": {
        "label": "Resource utilisation",
        "population": "Each modelled space or staff group", "units": "% of rostered / open capacity",
        "window": "observed days", "aggregation": "busy unit-minutes / available unit-minutes",
        "start": "-", "end": "-",
        "in_progress": "holds still open when the run ends are not counted (a small under-count near the end)"},
}


# --------------------------------------------------------------------------- #
# patient-level frames from a traced run
# --------------------------------------------------------------------------- #
def states_frame(trace: dict, table: dict | None = None) -> pd.DataFrame:
    """State intervals with group / kind attached. Open intervals end at +inf
    (censored) and carry ``open=True``."""
    table = table or mcfg.state_table()
    st = trace["states"].copy()
    st["open"] = st["end"].isna()
    st["end"] = st["end"].fillna(np.inf)
    keys = list(zip(st["node"], st["phase"]))
    st["group"] = [table.get(k, {}).get("group") for k in keys]
    st["kind"] = [table.get(k, {}).get("kind") for k in keys]
    st["state_label"] = [table.get(k, {}).get("label") for k in keys]
    return st


def patients_frame(trace: dict, sdec_boundary: str = "inside_ed", states=None) -> pd.DataFrame:
    """One row per patient (all, not only the cohort): arrival, departure
    boundary (NaN if still present at the end) and outcome."""
    arr = trace["arrivals"].set_index("pid")
    dep = trace["departures"].set_index("pid")
    p = arr.join(dep, how="left")
    p = p.rename(columns={"time": "departure", "sink": "outcome"})
    p["ed_end"] = p["departure"]
    if sdec_boundary == "transfer_ends_ed" and states is not None:
        sd = states[states["node"] == "sdec"].groupby("pid")["start"].min()
        p.loc[sd.index, "ed_end"] = sd
    p["ambulance"] = p["attrs"].fillna("").str.contains("ambulance")
    return p.reset_index()


def _cohort(p, window):
    s, e = window
    return p[(p["arrival"] >= s) & (p["arrival"] < e)]


def _quantile_censored(values: np.ndarray, q: float):
    """Quantile where censored values are +inf (longer than every finished
    one). None when the quantile falls among the censored."""
    if len(values) == 0:
        return None
    v = float(np.quantile(values, q, method="higher"))
    return None if math.isinf(v) else v


# --------------------------------------------------------------------------- #
# per-replication KPIs
# --------------------------------------------------------------------------- #
def replication_kpis(trace: dict, raw: dict, target_minutes: float) -> dict:
    uec = raw.get("uec") or {}
    window = uec.get("cohort_window") or [raw["warmup_minutes"], raw["sim_duration_minutes"]]
    end = float(trace["end"])
    st = states_frame(trace)
    p = patients_frame(trace, uec.get("sdec_boundary", "inside_ed"), st)
    c = _cohort(p, window).copy()
    n = len(c)
    days = (window[1] - window[0]) / 1440.0
    out = {"n_cohort": int(n), "per_day": n / days if days else None}
    if n == 0:
        return out
    fin = c["ed_end"].notna()
    dur = np.where(fin, c["ed_end"] - c["arrival"], np.inf)
    elapsed_at_end = end - c["arrival"].to_numpy()
    tm = float(target_minutes)
    met = fin.to_numpy() & (dur <= tm)
    unknown = (~fin.to_numpy()) & (elapsed_at_end <= tm)        # cannot happen with a 12 h drain
    out["four_hour"] = 100.0 * met.sum() / n
    out["four_hour_unknown"] = int(unknown.sum())
    over12 = np.where(fin, dur > 720, elapsed_at_end > 720)
    out["twelve_hour"] = 100.0 * over12.sum() / n
    out["n_twelve_hour"] = int(over12.sum())
    out["duration_median"] = _quantile_censored(dur, 0.5)
    out["duration_p90"] = _quantile_censored(dur, 0.9)
    out["wip_end"] = int((~fin).sum())
    out["lwbs"] = 100.0 * (c["outcome"] == "lwbs").sum() / n
    adm = c["outcome"].isin(["admitted", "admitted_mh"])
    out["admitted_pct"] = 100.0 * adm.sum() / n
    out["outcomes_per_day"] = {str(k): v / days for k, v in c["outcome"].fillna("in_department")
                               .value_counts().to_dict().items()}
    pids = set(c["pid"])
    sc = st[st["pid"].isin(pids)]
    visited_sdec = set(sc.loc[sc["node"] == "sdec", "pid"])
    out["sdec_pct"] = 100.0 * len(visited_sdec) / n
    # total waiting time per patient = union of waiting intervals (they never
    # overlap for one patient, so the union is the sum - asserted in tests)
    w = sc[sc["kind"] == "waiting"]
    w_end = np.minimum(w["end"].to_numpy(), end)
    wt = pd.Series(w_end - w["start"].to_numpy(), index=w["pid"].to_numpy()).groupby(level=0).sum()
    tw = c["pid"].map(wt).fillna(0.0).to_numpy()
    tw_rank = np.where(fin, tw, np.inf)
    out["total_wait_median"] = _quantile_censored(tw_rank, 0.5)
    out["total_wait_p90"] = _quantile_censored(tw_rank, 0.9)
    # ambulance handover: arrival -> start of handover service
    amb = c[c["ambulance"]]
    if len(amb):
        hs = sc[(sc["node"] == "ambulance_handover") & (sc["phase"] == "service")]
        first = hs.groupby("pid")["start"].min()
        t0 = amb.set_index("pid")["arrival"]
        h = (first.reindex(t0.index) - t0)
        ok = (h <= 45).fillna(False)
        out["handover_45"] = 100.0 * ok.sum() / len(amb)
        out["handover_median"] = float(h.dropna().median()) if h.notna().any() else None
    # initial assessment (streaming or RAT service start) within 15 minutes
    ia = sc[sc["node"].isin(["streaming", "rat"]) & (sc["phase"] == "service")].groupby("pid")["start"].min()
    t0 = c.set_index("pid")["arrival"]
    ttia = ia.reindex(t0.index) - t0
    out["initial_assessment_15"] = 100.0 * (ttia <= 15).fillna(False).sum() / n
    # decision to admit -> departure
    dta = sc[sc["node"].isin(["decision_to_admit", "decision_to_admit_mh"])].groupby("pid")["start"].min()
    if len(dta):
        dd = c.set_index("pid").loc[dta.index]
        dv = np.where(dd["ed_end"].notna(), dd["ed_end"] - dta, np.inf)
        out["dta_to_departure_median"] = _quantile_censored(dv, 0.5)
        out["dta_over_12h"] = int((np.where(dd["ed_end"].notna(), dv, end - dta) > 720).sum())
        out["dta_per_day"] = len(dta) / days
    else:
        out["dta_to_departure_median"] = None
        out["dta_per_day"] = 0.0
    return out


# --------------------------------------------------------------------------- #
# stage / group pressure and utilisation (time-integrals over the window)
# --------------------------------------------------------------------------- #
def _overlap(start, end, a, b):
    return np.clip(np.minimum(end, b) - np.maximum(start, a), 0, None)


def stage_metrics(trace: dict, raw: dict) -> dict:
    uec = raw.get("uec") or {}
    window = uec.get("cohort_window") or [raw["warmup_minutes"], raw["sim_duration_minutes"]]
    a, b = window
    days = (b - a) / 1440.0
    st = states_frame(trace)
    st = st[st["group"].notna()]
    ov = _overlap(st["start"].to_numpy(), st["end"].to_numpy(), a, b)
    st = st.assign(ov=ov)
    per_state = {}
    for (node, phase), g in st.groupby(["node", "phase"]):
        done = g[~g["open"] & (g["start"] >= a) & (g["start"] < b)]
        durs = (done["end"] - done["start"]).to_numpy()
        per_state[f"{node}|{phase}"] = {
            "node": node, "phase": phase, "group": g["group"].iloc[0], "kind": g["kind"].iloc[0],
            "label": g["state_label"].iloc[0],
            "mean_occupancy": float(g["ov"].sum() / (b - a)),
            "patient_hours_per_day": float(g["ov"].sum() / 60.0 / days),
            "entries_per_day": float(((g["start"] >= a) & (g["start"] < b)).sum() / days),
            "completed_median": float(np.median(durs)) if len(durs) else None,
            "completed_p90": float(np.quantile(durs, 0.9)) if len(durs) else None,
            "n_completed": int(len(durs))}
    # entries INTO a group = moving in from another group (or arriving): the
    # same definition the replay uses, so the two views cannot disagree
    srt = st.sort_values(["pid", "start", "end"])
    prev = srt.groupby("pid")["group"].shift(1)
    entry = srt[(srt["group"] != prev) & (srt["start"] >= a) & (srt["start"] < b)]
    entries = entry.groupby("group").size()
    per_group = {}
    for gid, g in st.groupby("group"):
        wg = g[g["kind"] == "waiting"]
        per_group[gid] = {
            "mean_occupancy": float(g["ov"].sum() / (b - a)),
            "mean_waiting": float(wg["ov"].sum() / (b - a)),
            "waiting_patient_hours_per_day": float(wg["ov"].sum() / 60.0 / days),
            "entries_per_day": float(entries.get(gid, 0) / days)}
    # milestone event counts (zero-length service intervals)
    ms = {}
    allst = trace["states"]
    for m in mcfg.fixture()["milestones"]:
        sel = allst[(allst["node"] == m["node"]) & (allst["phase"] == "service")
                    & (allst["start"] >= a) & (allst["start"] < b)]
        ms[m["node"]] = float(len(sel) / days)
    return {"states": per_state, "groups": per_group, "milestones_per_day": ms,
            "utilisation": utilisation(trace, raw, a, b)}


def utilisation(trace, raw, a, b) -> dict:
    holds = trace.get("holds")
    out = {}
    if holds is None or len(holds) == 0:
        return out
    for r, cap in raw.get("resources", {}).items():
        sub = holds[holds["resource"] == r]
        busy = float(_overlap(sub["start"].to_numpy(), sub["end"].to_numpy(), a, b).sum())
        if isinstance(cap, list):
            per = len(cap)
            mins = np.arange(a, b, 60)
            avail = float(sum(cap[int(t // 60) % per] for t in mins) * 60)
        else:
            avail = float(cap) * (b - a)
        out[r] = {"utilisation": (100.0 * busy / avail) if avail > 0 else None,
                  "busy_hours_per_day": busy / 60.0 / ((b - a) / 1440.0),
                  "available_hours_per_day": avail / 60.0 / ((b - a) / 1440.0)}
    return out


# --------------------------------------------------------------------------- #
# the replay (ONE replication) - snapshot series at STEP-minute resolution
# --------------------------------------------------------------------------- #
def _count_at(starts_sorted, ends_sorted, t):
    return np.searchsorted(starts_sorted, t, side="right") - np.searchsorted(ends_sorted, t, side="right")


def replay_series(trace: dict, raw: dict) -> dict:
    """Integer counts for every STEP minutes of every observed day of ONE
    replication: census, waiting, in service, per group and per state, the
    median and longest current elapsed wait, arrivals and departures in each
    STEP interval, patients present longer than the target, and a
    conservation check. Day 0 = the first observed day."""
    uec = raw.get("uec") or {}
    a, b = uec.get("cohort_window") or [raw["warmup_minutes"], raw["sim_duration_minutes"]]
    tgt = float(raw.get("target_minutes", 240))
    st = states_frame(trace)
    st = st[st["group"].notna()]
    p = patients_frame(trace, uec.get("sdec_boundary", "inside_ed"), st)
    arr_t = np.sort(p["arrival"].to_numpy())
    dep_t = np.sort(p["departure"].fillna(np.inf).to_numpy())
    times = np.arange(a, b + 1e-9, STEP)
    # per state counts
    state_counts = {}
    for (node, phase), g in st.groupby(["node", "phase"]):
        s_ = np.sort(g["start"].to_numpy()); e_ = np.sort(g["end"].to_numpy())
        state_counts[f"{node}|{phase}"] = _count_at(s_, e_, times).astype(int)
    kinds = {f"{n}|{ph}": k for (n, ph), k in
             st.groupby(["node", "phase"])["kind"].first().items()}
    groups = {f"{n}|{ph}": g for (n, ph), g in
              st.groupby(["node", "phase"])["group"].first().items()}
    gids = [g["id"] for g in mcfg.fixture()["groups"]]
    present = {g: np.zeros(len(times), int) for g in gids}
    waiting = {g: np.zeros(len(times), int) for g in gids}
    for k, v in state_counts.items():
        present[groups[k]] += v
        if kinds[k] == "waiting":
            waiting[groups[k]] += v
    census = (np.searchsorted(arr_t, times, side="right")
              - np.searchsorted(dep_t, times, side="right")).astype(int)
    # elapsed waits of those waiting now, by group (median / longest)
    w = st[st["kind"] == "waiting"]
    ws, we, wg = w["start"].to_numpy(), w["end"].to_numpy(), w["group"].to_numpy()
    med = {g: [] for g in gids}
    mx = {g: [] for g in gids}
    over_target = []
    pa = p["arrival"].to_numpy(); pd_ = p["departure"].fillna(np.inf).to_numpy()
    for t in times:
        live = (ws <= t) & (we > t)
        el = t - ws[live]
        gl = wg[live]
        for g in gids:
            e = el[gl == g]
            med[g].append(int(round(float(np.median(e)))) if len(e) else None)
            mx[g].append(int(round(float(e.max()))) if len(e) else None)
        here = (pa <= t) & (pd_ > t)
        over_target.append(int(((t - pa[here]) > tgt).sum()))
    # arrivals / departures in each STEP interval ending at t: (t-STEP, t]
    arr_in = np.diff(np.searchsorted(arr_t, np.concatenate([[times[0] - STEP], times]), side="right"))
    dep_in = np.diff(np.searchsorted(dep_t, np.concatenate([[times[0] - STEP], times]), side="right"))
    edges = np.concatenate([[times[0] - STEP], times])

    def per_interval(ts):
        ts = np.sort(np.asarray(ts, float))
        return np.diff(np.searchsorted(ts, edges, side="right")).astype(int).tolist()
    # entries INTO a group: a patient moving from a state in another group (or
    # arriving) - moving between steps inside the same group is not an entry
    srt = st[st["phase"].notna()].sort_values(["pid", "start", "end"])
    prev = srt.groupby("pid")["group"].shift(1)
    entry = srt[srt["group"] != prev]
    entries = {g: per_interval(entry.loc[entry["group"] == g, "start"]) for g in gids}
    # milestone EVENTS (zero-duration decisions) per interval - counts, not occupancy
    allst = trace["states"]
    milestones = {}
    for m in mcfg.fixture()["milestones"]:
        ev = allst[(allst["node"] == m["node"]) & (allst["phase"] == "service")]
        if len(ev):
            milestones[m["node"]] = per_interval(ev["start"])
    dep = trace["departures"]
    dep_by_outcome = {str(k): per_interval(g["time"]) for k, g in dep.groupby("sink")}
    in_service = sum(present.values()) - sum(waiting.values())
    # conservation: census(t0) + arrivals(t0, t] - departures(t0, t] == census(t)
    cons = census[0] + np.cumsum(arr_in)[0:] - arr_in[0] - (np.cumsum(dep_in) - dep_in[0])
    conserved = bool(np.array_equal(cons, census))
    groups_ok = bool(np.array_equal(sum(present.values()), census))
    return {
        "step_minutes": STEP, "t0": float(a), "times": [float(x) for x in times],
        "census": census.tolist(), "waiting": sum(waiting.values()).tolist(),
        "in_service": np.asarray(in_service).tolist(),
        "over_target": over_target,
        "arrivals": arr_in.astype(int).tolist(), "departures": dep_in.astype(int).tolist(),
        "groups": {g: {"present": present[g].tolist(), "waiting": waiting[g].tolist(),
                       "elapsed_median": med[g], "elapsed_max": mx[g],
                       "entries": entries[g]} for g in gids},
        "milestones": milestones, "departures_by_outcome": dep_by_outcome,
        "states": {k: v.tolist() for k, v in state_counts.items()},
        "checks": {"conservation": conserved, "groups_sum_to_census": groups_ok},
    }


def hour_profile(trace: dict, raw: dict) -> dict:
    """SECONDARY 'typical day' view for one replication: AVERAGE simulated
    patients by hour of day (census and waiting sampled every STEP minutes and
    averaged), and arrivals / departures per hour normalised by the number of
    observed days (the same exposure for every hour)."""
    rs = replay_series(trace, raw)
    times = np.array(rs["times"][:-1])
    hod = ((times // 60) % 24).astype(int)
    days = (times[-1] + STEP - times[0]) / 1440.0
    def avg(series):
        s = np.array(series[:-1], float)
        return [float(s[hod == h].mean()) for h in range(24)]
    arr = np.array(rs["arrivals"][1:], float); dep = np.array(rs["departures"][1:], float)
    # intervals (t-STEP, t] attributed to the hour containing t-STEP
    hod_i = (((np.array(rs["times"][1:]) - STEP) // 60) % 24).astype(int)
    return {"census_avg": avg(rs["census"]), "waiting_avg": avg(rs["waiting"]),
            "arrivals_per_hour": [float(arr[hod_i == h].sum() / days) for h in range(24)],
            "departures_per_hour": [float(dep[hod_i == h].sum() / days) for h in range(24)],
            "days": days}


# --------------------------------------------------------------------------- #
# summaries across replications
# --------------------------------------------------------------------------- #
SUMMARY_KEYS = ["four_hour", "twelve_hour", "duration_median", "duration_p90",
                "total_wait_median", "total_wait_p90", "lwbs", "wip_end", "admitted_pct",
                "sdec_pct", "handover_45", "initial_assessment_15", "dta_to_departure_median",
                "per_day", "n_cohort", "dta_per_day"]


def summarise(values: list) -> dict | None:
    """Mean, range and the t-interval of the MEAN across replications. The
    interval describes simulation noise in the mean only - not real-world
    uncertainty, and not a range of weeks."""
    v = np.array([x for x in values if x is not None], float)
    if len(v) == 0:
        return None
    out = {"mean": float(v.mean()), "min": float(v.min()), "max": float(v.max()),
           "n": int(len(v)), "missing": int(len(values) - len(v))}
    if len(v) > 1:
        se = float(v.std(ddof=1) / math.sqrt(len(v)))
        t = float(_st.t.ppf(0.975, len(v) - 1))
        out.update({"sd": float(v.std(ddof=1)), "ci_low": out["mean"] - t * se,
                    "ci_high": out["mean"] + t * se})
    return out


def paired_delta(base: list, scen: list) -> dict | None:
    """Matched-seed difference (scenario - baseline), its mean and 95%
    t-interval. Percentage POINTS for % metrics."""
    pairs = [(b, s) for b, s in zip(base, scen) if b is not None and s is not None]
    if not pairs:
        return None
    d = np.array([s - b for b, s in pairs], float)
    out = {"mean": float(d.mean()), "n": int(len(d))}
    if len(d) > 1:
        se = float(d.std(ddof=1) / math.sqrt(len(d)))
        t = float(_st.t.ppf(0.975, len(d) - 1))
        out.update({"ci_low": out["mean"] - t * se, "ci_high": out["mean"] + t * se})
    return out


def summarise_reps(reps: list[dict]) -> dict:
    return {k: summarise([r.get(k) for r in reps]) for k in SUMMARY_KEYS}


def summarise_stage_metrics(items: list[dict]) -> dict:
    """Average the per-replication stage/group metrics (these are rates and
    time-averages, so averaging across replications is the right aggregate)."""
    def avg(dicts):
        keys = set().union(*[d.keys() for d in dicts]) if dicts else set()
        out = {}
        for k in keys:
            vals = [d.get(k) for d in dicts]
            if any(isinstance(v, str) for v in vals):
                out[k] = next((v for v in vals if v is not None), None)
                continue
            nums = [float(v) for v in vals if isinstance(v, (int, float))]
            out[k] = float(np.mean(nums)) if nums else None
        return out
    states = {}
    for key in set().union(*[i["states"].keys() for i in items]):
        states[key] = avg([i["states"][key] for i in items if key in i["states"]])
    groups = {}
    for key in set().union(*[i["groups"].keys() for i in items]):
        groups[key] = avg([i["groups"][key] for i in items if key in i["groups"]])
    ms = avg([i["milestones_per_day"] for i in items])
    util = {}
    for key in set().union(*[i["utilisation"].keys() for i in items]):
        util[key] = avg([i["utilisation"][key] for i in items if key in i["utilisation"]])
    return {"states": states, "groups": groups, "milestones_per_day": ms, "utilisation": util}


def pressure_ranking(stage_summary: dict) -> list[dict]:
    """Where waits accumulate, by a NAMED measure: waiting patient-hours per
    day (the time-integral of the number waiting). Volume, or an area's own
    daily peak, is not used."""
    rows = []
    for key, s in stage_summary["states"].items():
        if s.get("kind") != "waiting":
            continue
        rows.append({"state": key, "node": s["node"], "label": s["label"], "group": s["group"],
                     "patient_hours_per_day": s["patient_hours_per_day"],
                     "mean_waiting": s["mean_occupancy"], "completed_median": s["completed_median"],
                     "entries_per_day": s["entries_per_day"]})
    rows.sort(key=lambda r: -(r["patient_hours_per_day"] or 0))
    return rows
