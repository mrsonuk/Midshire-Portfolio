# Working on this repository

A hybrid DES + SD model of an emergency department, currently configured for
Cambridge University Hospitals (RGT). `docs/CUH_DATA_LOG.md` is the record of
what data exists, what it feeds, and what is still assumed.

## Before you finish any change, run this

```bash
python3 -m uec_hybrid.tests.run                       # must be green
python3 -m uec_hybrid.validation.against_trust RGT    # and read the per-area block
```

The test suite passing does **not** mean the model is right. Every defect found
in this build was found by the second command, and none by the first: the model
was internally consistent and green throughout while resus ran at 1.77x and
majors trolleys at 0.35x of the volumes and stays the trust actually sees. The
headline KPIs agreed the whole time, through compensating errors.

## Mistakes that have actually been made here

These are not hypothetical. Each one cost a round trip.

**Check the value the engine RESOLVES, not the one you set.** `ed_cubicles` and
`paeds_assessment` carry a `service_by_class`, and the engine prefers it over
`service` — so calibrating `service` was a silent no-op and the "calibration"
was tuning nothing. Likewise `resources` (plural, held during service),
`resource` (singular) and `acquire` (held until a later `release`) are three
different things; reading the wrong key produced a confident wrong diagnosis.
Print the built node and check.

**Check the measurement basis before calling something a defect.** Two reported
"defects" were comparison errors. `twelve_hour` is `los > 720`, measured *from
arrival*, and was being compared against a decision-to-admit figure — the model
was 1.08x of the right target while being reported as 3x too bad. The
15-minute tile compares the model's triage event against a CUH figure that, for
minors, is a clinician assessment 37 minutes into the visit.

**Check which function computes it.** `kpis()` and `uec_metrics()` return
different measures. A metric missing from one is not a broken metric.

**Fix the mechanism, not the number.** Reproducing a 725-minute trolley stay by
lengthening treatment tied up a doctor for the whole 12 hours, saturating the
pool and sending LWBS to 25%. Real patients occupy a *trolley*, not a
clinician — the time belonged on `disposition`, which holds no resource.
If a parameter has to go somewhere implausible to fit, the mechanism is wrong.

**Re-validate the WHOLE model after a change, not the thing you changed.**
Fixing the RAT queue moved it downstream into cubicles; that was only noticed
later. Run the per-area comparison every time.

**Give a calibration objective guards.** Optimising per-area length of stay
alone drove LWBS to 25% and collapsed two areas' volumes. Constrain LWBS and
volumes, not just the thing being fitted.

**Assert that operations succeeded.** A `float()` on a dict made
`/api/trust/select` return 500; the script carried on against a stale saved
department and the calibration looked applied when it was not. Check status
codes and that the value you wrote is the value now in force.

## Data rules

* Nothing is invented. Every model input traces to a CUH extract under
  `data/cuh/`, an NHS England publication under `data/`, or is labelled an
  assumption in the seed workbook's `Status` tab.
* An explicit `0` in a capacity means "we don't have this" and is kept; blank
  means "keep the template estimate". They are different claims.
* Trust-specific facts belong in `uec_hybrid/data/<ods>_published.json` and
  reach the model as a calibration patch — **not** as edits to
  `pathways/model_ed.json`, which is the shared template for every trust.
* Before asking the trust for data, check whether a national publication has
  it. Ambulance handover was closed from the NHSE UEC SitRep without going back
  to CUH.

## Reporting

State what matches and what does not, with the numbers. If something is still
wrong, say so plainly and say what it would take to close it — this build is
shown to the trust, and an overstated figure is worse than a missing one.
