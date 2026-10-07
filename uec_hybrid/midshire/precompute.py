"""
Regenerate the committed, clearly labelled PRECOMPUTED results the demo opens
with, so a presentation never waits on a cold simulation:

    python3 -m uec_hybrid.midshire.precompute            # everything (~15-25 min)
    python3 -m uec_hybrid.midshire.precompute --quick    # baseline run only

Everything is written to uec_hybrid/data/midshire/precomputed/ as gzipped JSON
plus a manifest recording the model hash, engine version, seeds and the commit
it was generated from. The server loads a file only if its model hash still
matches the current inputs and engine; otherwise it is ignored as stale and the
page offers a fresh run. Rerunning is always possible from the page.

Nothing here writes to the Cambridge database.
"""
from __future__ import annotations

import argparse
import gzip
import json
import tempfile
import time

from . import config as mcfg
from .optimise import search, search_key
from .packages import apply_package, describe_package
from .runner import run, source_commit
from ..platform.store import ENGINE_VERSION

OUT = mcfg.PRECOMPUTED_DIR

# the named demo scenarios: (id, name, target, mode, note)
SEARCHES = [
    ("pkg_combined_90", {"pct": 90.0, "minutes": 240}, "combined"),
    ("pkg_workforce_90", {"pct": 90.0, "minutes": 240}, "workforce"),
    ("pkg_estate_90", {"pct": 90.0, "minutes": 240}, "estate"),
    ("pkg_combined_70", {"pct": 70.0, "minutes": 240}, "combined"),
    ("pkg_noextra_90", {"pct": 90.0, "minutes": 240}, "no_extra"),
]


def _write(name: str, obj) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    data = gzip.compress(json.dumps(obj, separators=(",", ":")).encode(), mtime=0)
    (OUT / name).write_bytes(data)
    return name


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="baseline run only")
    ap.add_argument("--extra-target", type=float, default=None,
                    help="also precompute a combined search at this target %% (a 'met' example)")
    a = ap.parse_args(argv)
    t0 = time.time()
    base = mcfg.baseline_inputs()
    manifest = {"generated_from_commit": source_commit(), "engine_version": ENGINE_VERSION,
                "fixture_version": base["fixture_version"],
                "label": "PRECOMPUTED demo results. Regenerate with "
                         "python3 -m uec_hybrid.midshire.precompute",
                "scenarios": [], "runs": [], "searches": []}
    _write("baseline_inputs.json.gz", base)
    print("baseline run ...", flush=True)
    res = run(base)
    manifest["runs"].append({"kind": "run", "file": _write("baseline_run.json.gz", res),
                             "inputs": "baseline_inputs.json.gz", "model_hash": res["model_hash"],
                             "seeds": res["seeds"], "scenario": "baseline"})
    if not a.quick:
        todo = list(SEARCHES)
        if a.extra_target:
            todo.append((f"pkg_combined_{int(a.extra_target)}",
                         {"pct": a.extra_target, "minutes": 240}, "combined"))
        for sid, target, mode in todo:
            print(f"search {sid} ...", flush=True)
            r = search(base, target, mode=mode,
                       progress=lambda m, f: print(f"   {int(100 * (f or 0)):3d}% {m}", flush=True))
            r["search_key"] = search_key(base, target, mode)
            fname = _write(f"{sid}_search.json.gz", r)
            manifest["searches"].append({"kind": "search", "file": fname,
                                         "inputs": "baseline_inputs.json.gz",
                                         "target": target, "mode": mode,
                                         "outcome": r["outcome"], "headline": r["headline"]})
            rec = r.get("recommended")
            seen = {tuple(x["ids"]) for x in manifest["scenarios"]}
            if rec and rec.get("ids") and tuple(sorted(rec["ids"])) in seen:
                continue                      # same package already saved as a scenario
            if rec and rec.get("ids"):
                fx = {l["id"]: l for l in mcfg.fixture()["search"]["levers"]}
                pkg, _ = apply_package(base, [fx[i] for i in sorted(rec["ids"])])
                iname = _write(f"{sid}_inputs.json.gz", pkg)
                d = describe_package(rec["ids"], mode, target, r["outcome"])
                manifest["scenarios"].append({
                    "id": sid, "inputs": iname, "ids": sorted(rec["ids"]),
                    "mode": mode, "target": target, "outcome": r["outcome"],
                    "name": d["name"][:200],
                    "note": json.dumps({"why": d["why"], "look_for": d["look_for"]})})
                prun = r["package_run"]
                manifest["runs"].append({"kind": "run", "file": _write(f"{sid}_run.json.gz", prun),
                                         "inputs": iname, "model_hash": prun["model_hash"],
                                         "seeds": prun["seeds"], "scenario": sid})
    manifest["seconds"] = round(time.time() - t0, 1)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {OUT} in {manifest['seconds']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
