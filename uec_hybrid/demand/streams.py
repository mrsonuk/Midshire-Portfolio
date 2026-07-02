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
    relative case-mix character."""
    old = arrivals.get("acuity_mix") or {}
    for s in arrivals.get("streams") or []:
        m = s.get("acuity_mix")
        if not m:
            continue
        for k in list(m):
            if old.get(k):
                m[k] = m[k] * (new_mix.get(k, 0.0) / old[k])
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
