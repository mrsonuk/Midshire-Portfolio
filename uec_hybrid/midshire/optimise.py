"""
Target-driven package search: "what workforce and space changes would get X%
of adult attendances through within N minutes, and what would it cost?"

What it does, in order (all of it reported back with the result):

1. Simulates the baseline on the SELECTION seeds. If the target is already met,
   it says so and stops.
2. Screens every lever in the bounded catalogue on its own (full re-run, same
   seeds as the baseline).
3. Builds packages step by step along two paths, re-running the FULL model for
   every candidate package (effects are never added up arithmetically):
     * "largest effect" - add whichever lever lifts the measure most;
     * "best value"     - add whichever lever gives the most improvement per £
                          of annualised comparison cost.
   A lever that did nothing on its own is still tried in combination - an
   extra cubicle may only help once the nurses to open it are there.
4. Prunes each target-meeting package: a lever is dropped if the package still
   meets the target without it.
5. Ranks packages that meet the target AND keep the guardrails (walk-outs and
   unfinished patients not materially worse) by annualised comparison cost.
   Partially costed packages are listed but never ranked as cheapest.
6. Re-runs the shortlist and the baseline on a SEPARATE validation seed set,
   so selection is not mistaken for confirmation, and reports matched
   differences with their simulation-noise intervals.

It cannot prove a target is impossible in the real hospital, nor that a
package is the cheapest possible: the result is the "lowest-cost package found
within the tested options".
"""
from __future__ import annotations

import copy
from decimal import Decimal, ROUND_HALF_UP
import time

from . import config as mcfg
from . import metrics as M
from . import runner
from .packages import apply_package, move_source, package_finance


class SearchCancelled(Exception):
    pass


MODES = {
    # nothing added: move existing shifts (paid hours unchanged) and two process
    # changes whose size is an assumption (faster ward discharge, quicker decisions)
    "no_extra": {"label": "No extra resources: move existing staff and change how we work",
                 "kinds": {"move", "process"}, "also": {"discharge_10"}},
    "workforce": {"label": "Staffing only", "kinds": {"shift"}},
    "estate": {"label": "Space and beds, with the staff they need",
               "kinds": {"estate", "hours", "downstream"}},
    "combined": {"label": "Staffing, space and beds",
                 "kinds": {"shift", "estate", "hours", "downstream"}},
}


def levers_for(inputs: dict, bounds: dict | None = None, mode: str = "combined") -> list[dict]:
    """The bounded lever catalogue for a comparison mode, filtered to levers
    that can apply to this scenario (e.g. no SDEC lever if SDEC is off)."""
    cat = copy.deepcopy((bounds or mcfg.fixture()["search"])["levers"])
    enabled = set(inputs["areas"]["enabled"])
    kinds, also = MODES[mode]["kinds"], MODES[mode].get("also", set())
    out = []
    for lv in cat:
        if lv["kind"] not in kinds and lv["id"] not in also:
            continue
        if lv["kind"] == "move" and move_source(inputs["rota"], lv["move"]) is None:
            continue                                   # this rota has no such shift to move
        if lv["kind"] == "estate" and lv["space"] not in inputs["capacity"]:
            continue
        if lv["kind"] == "hours" and lv["area"] not in enabled:
            continue
        if lv["kind"] == "shift" and lv["shift"]["role"].startswith("sdec") and "sdec" not in enabled:
            continue
        out.append(lv)
    return out


class Search:
    def __init__(self, base_inputs: dict, target: dict, bounds: dict | None = None,
                 progress=None, cancel=None, workers: int | None = None, mode: str = "combined"):
        if mode not in MODES:
            raise ValueError(f"unknown search mode {mode!r}")
        self.mode = mode
        self.base = copy.deepcopy(base_inputs)
        self.target = {"pct": float(target["pct"]), "minutes": int(target["minutes"])}
        fx = mcfg.fixture()["search"]
        self.bounds = copy.deepcopy(bounds or fx)
        self.bounds.setdefault("guardrails", fx["guardrails"])
        self.levers = levers_for(self.base, self.bounds, mode)
        self.by_id = {lv["id"]: lv for lv in self.levers}
        reps = int(self.bounds.get("reps", fx["reps"]))
        self.seeds = list(self.base["engine"]["selection_seeds"])[:reps]
        self.validation_seeds = list(self.base["engine"]["validation_seeds"])
        self.max_steps = int(self.bounds.get("max_steps", fx["max_steps"]))
        self.progress, self.cancel = progress, cancel
        self.workers = workers
        self.cache = {}
        self.runs = 0
        self.log = []

    # -- evaluation ------------------------------------------------------- #
    def _check(self):
        if self.cancel and self.cancel():
            raise SearchCancelled()

    def _say(self, msg, frac=None):
        self.log.append(msg)
        if self.progress:
            self.progress(msg, frac)

    def evaluate(self, ids: tuple, seeds=None, keep_run=False) -> dict:
        key = (tuple(sorted(ids)), tuple(seeds or self.seeds))
        if key in self.cache and not keep_run:
            return self.cache[key]
        self._check()
        levers = [self.by_id[i] for i in sorted(ids)]
        inputs, recs = apply_package(self.base, levers)
        res = runner.run(inputs, seeds=list(seeds or self.seeds), replay=keep_run,
                         pool=self.pool, cancel=self.cancel,
                         seed_set="selection" if seeds is None else "validation")
        self.runs += len(seeds or self.seeds)
        within = runner.within_at(res, self.target["minutes"])
        fin = package_finance(self.base, inputs, recs)
        out = {"ids": list(sorted(ids)), "titles": [lv["title"] for lv in levers],
               "within": within, "measure": M.summarise(within),
               "lwbs": [r.get("lwbs") for r in res["reps"]],
               "wip": [r.get("wip_end") for r in res["reps"]],
               "twelve": [r.get("twelve_hour") for r in res["reps"]],
               "duration": [r.get("duration_median") for r in res["reps"]],
               "finance": fin, "records": recs, "model_hash": res["model_hash"]}
        if keep_run:
            out["run"] = res
            out["inputs"] = inputs
        self.cache[key] = {k: v for k, v in out.items() if k not in ("run", "inputs")}
        return out

    def _mean(self, ev):
        return ev["measure"]["mean"] if ev["measure"] else float("-inf")

    def _guard_ok(self, ev, base) -> dict:
        g = self.bounds["guardrails"]
        d_lwbs = M.paired_delta(base["lwbs"], ev["lwbs"]) or {"mean": 0.0}
        d_wip = M.paired_delta(base["wip"], ev["wip"]) or {"mean": 0.0}
        bw = max(1e-9, sum(x or 0 for x in base["wip"]) / max(1, len(base["wip"])))
        ok_l = d_lwbs["mean"] <= float(g["max_lwbs_increase_pts"])
        ok_w = (100.0 * d_wip["mean"] / bw) <= float(g["max_wip_increase_pct"]) or d_wip["mean"] <= 2
        return {"ok": bool(ok_l and ok_w), "lwbs_delta_pts": d_lwbs["mean"],
                "wip_delta": d_wip["mean"]}

    # -- the search ------------------------------------------------------- #
    def run(self) -> dict:
        t0 = time.time()
        self.pool = runner.get_pool() if (self.workers or 2) > 1 else None
        return self._run(t0)

    def _met(self, ev):
        return self._mean(ev) >= self.target["pct"]

    def _run(self, t0) -> dict:
        tgt = self.target
        self._say("Running the current position", 0.02)
        base = self.evaluate(())
        bmean = self._mean(base)
        result = {"target": tgt, "baseline": self._public(base, base),
                  "bounds": self._bounds_public()}
        if self._met(base):
            result["outcome"] = "already_met"
            return self._finish(result, base, [], t0)

        # 2. screen singles
        singles = []
        for i, lv in enumerate(self.levers):
            self._say(f"Testing: {_name(lv['id'])}", 0.05 + 0.25 * i / max(1, len(self.levers)))
            singles.append(self.evaluate((lv["id"],)))

        # 3. two greedy paths
        paths = {}
        for pi, path in enumerate(("effect", "value")):
            cur, cur_ev, steps = (), base, []
            for step in range(self.max_steps):
                cands = [lv["id"] for lv in self.levers if lv["id"] not in cur]
                if not cands:
                    break
                evs = []
                for j, c in enumerate(cands):
                    frac = 0.30 + 0.30 * pi + 0.30 * (step + j / len(cands)) / self.max_steps
                    self._say(f"Building a package. Testing: {_name(c)}", frac)
                    evs.append(self.evaluate(cur + (c,)))
                gain = [(self._mean(e) - self._mean(cur_ev), e) for e in evs]
                floor = float(self.bounds.get("min_step_gain_pts", 0.5))
                gain = [(g, e) for g, e in gain if g >= floor]          # must actually help
                if not gain:
                    break
                if path == "effect":
                    g, best = max(gain, key=lambda x: x[0])
                else:
                    def per_pound(x):
                        g, e = x
                        cost = e["finance"]["annualised_comparison_cost"] - \
                            cur_ev["finance"]["annualised_comparison_cost"]
                        if not e["finance"]["fully_costed"]:
                            return (-1, g)                             # rank uncosted last
                        return (1, g / max(1.0, cost))
                    g, best = max(gain, key=per_pound)
                cur = tuple(best["ids"])
                cur_ev = best
                steps.append(self._public(best, base))
                if self._met(best):
                    break
            paths[path] = {"steps": steps, "final": tuple(cur)}

        # 4. prune target-meeting packages
        finals = {p["final"] for p in paths.values() if p["final"]}
        pruned = set()
        for ids in finals:
            ev = self.evaluate(ids)
            if not self._met(ev):
                continue
            cur = list(ids)
            changed = True
            while changed and len(cur) > 1:
                changed = False
                for drop in list(cur):
                    trial = tuple(x for x in cur if x != drop)
                    self._say("Checking every change is needed", frac)
                    if self._met(self.evaluate(trial)):
                        cur = list(trial)
                        changed = True
                        break
            pruned.add(tuple(sorted(cur)))

        # 5. rank everything evaluated (on the selection seeds)
        evaluated = [v for (ids, seeds), v in self.cache.items()
                     if seeds == tuple(self.seeds) and ids]
        feasible, partial, best_perf = [], [], None
        for ev in evaluated:
            pub = self._public(ev, base)
            if best_perf is None or self._mean(ev) > best_perf["measure"]["mean"]:
                best_perf = pub
            if self._met(ev) and pub["guardrails"]["ok"]:
                (feasible if ev["finance"]["fully_costed"] else partial).append(pub)
        feasible.sort(key=lambda p: p["finance"]["annualised_comparison_cost"])
        partial.sort(key=lambda p: -p["measure"]["mean"])
        result.update({"singles": [self._public(s, base) for s in singles],
                       "paths": {k: {"steps": v["steps"]} for k, v in paths.items()},
                       "feasible": feasible[:10], "partially_costed_feasible": partial[:5],
                       "best_tested": best_perf})

        # 6. validation on independent seeds
        shortlist = [p["ids"] for p in feasible[:3]] or ([best_perf["ids"]] if best_perf else [])
        self._say("Re-testing the best packages on different weeks", 0.95)
        vbase = self.evaluate((), seeds=self.validation_seeds)
        validated = []
        for ids in shortlist:
            ev = self.evaluate(tuple(ids), seeds=self.validation_seeds)
            pub = self._public(ev, vbase)
            pub["seed_set"] = "validation"
            validated.append(pub)
        result["validation"] = {"seeds": self.validation_seeds, "baseline": self._public(vbase, vbase),
                                "packages": validated}
        if feasible:
            best = feasible[0]
            result["outcome"] = "met"
            result["recommended"] = best
        else:
            result["outcome"] = "not_reached"
            result["recommended"] = best_perf
        return self._finish(result, base, shortlist, t0)

    def _finish(self, result, base, shortlist, t0):
        # evidence about what limits the best package found: full run with replay
        rec_ids = tuple((result.get("recommended") or {}).get("ids") or ())
        self._say("Finding what still holds performance back", 0.98)
        full = self.evaluate(rec_ids, keep_run=True)
        run = full["run"]
        util = run["stages"]["utilisation"]
        hot = sorted([{"resource": r, "utilisation": u["utilisation"]} for r, u in util.items()
                      if u.get("utilisation") is not None and u["utilisation"] >= 80],
                     key=lambda x: -x["utilisation"])
        result["limits"] = {
            "top_waiting_states": run["pressure"][:5],
            "busy_resources": hot,
            "fixed_in_this_model": [
                ("Quicker results and decisions were tested only as an assumed 10% improvement, not a "
                 "measured one." if any(lv["kind"] == "process" and lv.get("param") == "decision_time_scale"
                                        for lv in self.levers) else
                 "None of the tested changes shortens the time patients spend waiting for results, "
                 "review or a decision."),
                "Bed waits depend on how full the hospital is; extra beds and faster discharges help "
                "only through that.",
                "Demand, treatment times and how patients are routed stay as they are."]}
        result["package_run"] = run
        result["package_inputs"] = full["inputs"]
        result["base_inputs"] = self.base
        result["evaluations"] = {"packages": len([k for k in self.cache if k[1] == tuple(self.seeds)]),
                                 "replications": self.runs,
                                 "seconds": round(time.time() - t0, 1)}
        result["method"] = __doc__.strip()
        result["headline"] = describe(result)
        return result

    def _bounds_public(self):
        return {"mode": self.mode, "mode_label": MODES[self.mode]["label"],
                "target": self.target, "levers": [{"id": lv["id"], "title": lv["title"], "kind": lv["kind"]} for lv in self.levers],
                "max_steps": self.max_steps, "selection_seeds": self.seeds,
                "min_step_gain_pts": float(self.bounds.get("min_step_gain_pts", 0.5)),
                "validation_seeds": self.validation_seeds, "replications_per_package": len(self.seeds),
                "guardrails": self.bounds["guardrails"], "note": mcfg.fixture()["search"]["note"]}

    def _public(self, ev, base) -> dict:
        d = M.paired_delta(base["within"], ev["within"])
        return {"ids": ev["ids"], "titles": ev["titles"], "measure": ev["measure"],
                "delta_vs_baseline_pts": d, "guardrails": self._guard_ok(ev, base),
                "twelve_hour": M.summarise(ev["twelve"]), "lwbs": M.summarise(ev["lwbs"]),
                "wip_end": M.summarise(ev["wip"]), "duration_median": M.summarise(ev["duration"]),
                "meets_target": self._met(ev), "finance": ev["finance"], "records": ev["records"],
                "model_hash": ev["model_hash"]}


def _name(lever_id: str) -> str:
    from .packages import lever_text
    return lever_text(lever_id)["name"]


def wait_phrase(label: str) -> str:
    """'Waiting for an inpatient bed' -> 'the wait for an inpatient bed'."""
    l = (label or "").strip()
    low = l[:1].lower() + l[1:]
    if low.startswith("waiting for "):
        return "the wait for " + low[len("waiting for "):]
    if low.startswith("awaiting "):
        return "waiting for " + low[len("awaiting "):].replace(" or decision", " or a decision")
    return low


def _time_words(minutes) -> str:
    m = int(minutes)
    return f"{m // 60} hours" if m % 60 == 0 else f"{m} minutes"


def num(x, dp: int = 0, sign: bool = False, comma: bool = False) -> str:
    """A number exactly as the page shows it. The page rounds halves away from
    zero (JavaScript's toFixed); Python's format rounds them to even, so 444.5
    hours would read 444 here and 445 on screen. Every figure in a sentence
    goes through this."""
    q = Decimal(x).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
    out = f"{q:,}" if comma else f"{q}"
    return ("+" + out) if sign and q > 0 else out


def perf_words(minutes) -> str:
    """'4-hour performance' (or '90-minute performance'): the one way the tool
    names the target measure in sentences."""
    m = int(minutes)
    return f"{m // 60}-hour performance" if m % 60 == 0 else f"{m}-minute performance"


def describe(result: dict) -> str:
    """The verdict in plain words, built from the structured fields (so a
    re-priced result never carries a stale sentence)."""
    tgt, bmean = result["target"], result["baseline"]["measure"]["mean"]
    out = result.get("outcome")
    rec = result.get("recommended")
    within = _time_words(tgt["minutes"])
    if out == "already_met":
        return (f"The department already meets this target: {num(bmean, 1)}% of patients leave within "
                f"{within}, against {tgt['pct']:g}%.")
    top = ((result.get("limits") or {}).get("top_waiting_states") or [{}])[0].get("label")
    if out == "met" and rec:
        f = rec["finance"]
        cost = f"£{num(f['recurring_annual_total'], comma=True)} a year"
        if f.get("capital"):
            cost += f" plus £{num(f['capital'], comma=True)} one-off"
        costs = f"It is the lowest-cost option the model found and costs about {cost}."
        if not f.get("capital") and abs(f.get("recurring_annual_total") or 0) < 0.5:
            costs = "It needs no extra staff, space or beds" + (
                "; the process changes in it are not costed." if f.get("not_costed") else ".")
        v = next((x for x in (result.get("validation") or {}).get("packages", [])
                  if x["ids"] == rec["ids"]), None)
        held = ""
        if v and v.get("measure"):
            held = (f" It held up when re-tested on different weeks ({num(v['measure']['mean'], 1)}%)."
                    if v["measure"]["mean"] >= tgt["pct"] else
                    f" Re-tested on different weeks it reached {num(v['measure']['mean'], 1)}%, so treat it as borderline.")
        return (f"This package takes {perf_words(tgt['minutes'])} from {num(bmean, 1)}% to "
                f"{num(rec['measure']['mean'], 1)}% on a typical day, meeting the {tgt['pct']:g}% target. "
                f"{costs}{held}")
    best = rec["measure"]["mean"] if rec and rec.get("measure") else bmean
    txt = (f"None of the tested packages reaches {tgt['pct']:g}%. The best one takes {perf_words(tgt['minutes'])} "
           f"from {num(bmean, 1)}% to {num(best, 1)}% on a typical day, still {num(tgt['pct'] - best, 1)} points short.")
    if top:
        txt += f" The main remaining constraint is {wait_phrase(top)}."
    return txt


def search(base_inputs, target, bounds=None, progress=None, cancel=None, workers=None,
           mode="combined") -> dict:
    return Search(base_inputs, target, bounds, progress, cancel, workers, mode).run()


def search_key(inputs: dict, target: dict, mode: str, bounds: dict | None = None) -> str:
    """Cache key for a search: the model inputs, the target, the mode and the
    bounds. Cost tables are NOT in it - prices are re-applied on read (rerank),
    so a cost edit re-ranks instantly and never re-simulates."""
    # only the changes this mode may use are part of the key, so adding a change
    # for one mode leaves every other mode's stored results valid
    b = copy.deepcopy(bounds or mcfg.fixture()["search"])
    b.pop("note", None)
    b["levers"] = levers_for(inputs, b, mode)
    return "search:" + mcfg.stable_hash({"model": mcfg.model_hash(inputs),
                                         "target": {"pct": float(target["pct"]),
                                                    "minutes": int(target["minutes"])},
                                         "mode": mode, "bounds": b})


def rerank(result: dict, cost_table: dict, estates: dict) -> dict:
    """Cost-table edits change every financial figure and the ranking - but
    never the simulated performance. Re-price the evaluated packages with the
    new tables and re-rank, WITHOUT re-simulating."""
    out = copy.deepcopy(result)
    base = {**out["base_inputs"], "cost_table": cost_table, "estates": estates}
    fx_levers = {lv["id"]: lv for lv in mcfg.fixture()["search"]["levers"]}

    def reprice(pub):
        if not pub:
            return pub
        levers = [fx_levers[i] for i in pub["ids"] if i in fx_levers]
        pkg, recs = apply_package(base, levers)
        pub["finance"] = package_finance(base, pkg, recs)
        return pub
    for key in ("feasible", "partially_costed_feasible", "singles"):
        out[key] = [reprice(p) for p in out.get(key) or []]
    for key in ("recommended", "best_tested", "baseline"):
        out[key] = reprice(out.get(key))
    for path in (out.get("paths") or {}).values():
        path["steps"] = [reprice(p) for p in path.get("steps") or []]
    for v in (out.get("validation") or {}).get("packages") or []:
        reprice(v)
    pool = (out.get("feasible") or []) + (out.get("partially_costed_feasible") or [])
    feas = sorted([p for p in pool if p["finance"]["fully_costed"]],
                  key=lambda p: p["finance"]["annualised_comparison_cost"])
    out["feasible"] = feas
    out["partially_costed_feasible"] = [p for p in pool if not p["finance"]["fully_costed"]]
    if out.get("outcome") == "met" and feas:
        out["recommended"] = feas[0]
    if out.get("package_inputs") is not None:
        out["package_inputs"] = {**out["package_inputs"], "cost_table": cost_table, "estates": estates}
    out["base_inputs"] = base
    out["repriced"] = True
    out["headline"] = describe(out)
    return out
