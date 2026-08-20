"""
Arrival streams: ambulance, walk-in, GP referral and NHS 111 as per-hour SHARE
partitions of the single total hourly profile.

Because streams are shares (not absolute rates), every existing demand seam -
department sizing, winter scaling, population determinants, ECDS calibration -
keeps operating on the one ``hourly_profile`` knob and the streams follow.
"""
from __future__ import annotations


def stream_shares_at(arrivals: dict, hour: int) -> dict:
    """{stream name: share} at an hour (empty when the pathway has no streams)."""
    out = {}
    for s in arrivals.get("streams") or []:
        w = s["share_by_hour"][hour] if "share_by_hour" in s else s.get("share", 0)
        out[s["name"]] = float(w)
    tot = sum(out.values())
    return {k: v / tot for k, v in out.items()} if tot > 0 else out


def daily_stream_split(arrivals: dict) -> dict:
    """Whole-day {stream: share of attendances}, demand-weighted by the profile."""
    profile = arrivals.get("hourly_profile") or [1] * 24
    tot = sum(profile) or 1
    out = {}
    for h in range(24):
        for name, w in stream_shares_at(arrivals, h).items():
            out[name] = out.get(name, 0.0) + profile[h] * w / tot
    return out


def skew_stream_mixes(arrivals: dict, new_mix: dict):
    """Move every stream's acuity mix in step with a change to the global mix
    (population determinants, ECDS calibration), preserving each stream's
    relative case-mix character.

    Two constraints have to hold at once, and scaling alone satisfies neither:

    * each STREAM's mix must sum to 100 (it is a percentage split), and
    * the SHARE-WEIGHTED mix across streams must equal the calibrated target.

    A plain per-class multiply broke both - it left Cambridge's streams summing
    to 145 / 71 / 136 / 84, and because the engine renormalises each stream on
    the way in, the department actually ran at Acuity 1 1.3% / Acuity 4 51%
    against a calibrated 2.5% / 36%. Resus then saw half the patients CUH sees.

    Iterative proportional fitting satisfies both: alternately normalise each
    stream to 100 (rows) and rescale each class so the weighted mix hits the
    target (columns). Both margins are positive, so it converges - and each
    stream keeps its character (ambulance stays sicker than walk-in).
    """
    old = arrivals.get("acuity_mix") or {}
    streams = [s for s in (arrivals.get("streams") or []) if s.get("acuity_mix")]
    if not streams:
        arrivals["acuity_mix"] = dict(new_mix)
        return
    total = sum(new_mix.values()) or 100.0

    for s in streams:                      # seed: keep each stream's character
        m = s["acuity_mix"]
        for k in list(m):
            if old.get(k):
                m[k] = m[k] * (new_mix.get(k, 0.0) / old[k])

    shares = daily_stream_split(arrivals)
    wsum = sum(shares.get(s["name"], 0.0) for s in streams) or 1.0
    for _ in range(200):
        for s in streams:                                  # rows -> sum to 100
            m = s["acuity_mix"]; t = sum(m.values())
            if t > 0:
                for k in m:
                    m[k] = m[k] / t * total
        overall = {}                                       # columns -> target
        for s in streams:
            w = shares.get(s["name"], 0.0) / wsum
            for k, v in s["acuity_mix"].items():
                overall[k] = overall.get(k, 0.0) + w * v
        err = 0.0
        for k, tgt in new_mix.items():
            cur = overall.get(k, 0.0)
            if tgt <= 0:
                for s in streams:
                    s["acuity_mix"][k] = 0.0
            elif cur > 0:
                f = tgt / cur
                err = max(err, abs(f - 1.0))
                for s in streams:
                    if k in s["acuity_mix"]:
                        s["acuity_mix"][k] *= f
        if err < 1e-9:
            break
    for s in streams:
        m = s["acuity_mix"]; t = sum(m.values())
        if t > 0:
            for k in m:
                m[k] = round(m[k] / t * total, 4)
    arrivals["acuity_mix"] = dict(new_mix)


def scale_stream_share(arrivals: dict, name: str, factor: float,
                       absorber: str = "walk_in"):
    """Scale one stream's share (e.g. deprivation lifts ambulance conveyance);
    the absorber stream takes up the slack so shares still sum to 1."""
    streams = {s["name"]: s for s in arrivals.get("streams") or []}
    target, absorb = streams.get(name), streams.get(absorber)
    if not target or not absorb or "share_by_hour" not in target:
        return
    for h in range(24):
        old = target["share_by_hour"][h]
        new = min(0.95, max(0.0, old * factor))
        target["share_by_hour"][h] = round(new, 4)
        if "share_by_hour" in absorb:
            absorb["share_by_hour"][h] = round(
                max(0.0, absorb["share_by_hour"][h] - (new - old)), 4)
