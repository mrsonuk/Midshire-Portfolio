# -*- coding: utf-8 -*-
"""Lay the narration onto the recording at the offsets the take actually hit.

Sync comes from measurement, not from hope: record.py logs the wall-clock offset
at which each caption appeared, and each wav is delayed to exactly that offset.
If the app took longer on the day than the narration allowed, the words still
land on the right screen.
"""
import json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
TL = json.loads((HERE / "timeline.json").read_text())
segs = TL["segments"]
vids = sorted((HERE / "video").glob("*.webm"))
if not vids:
    sys.exit("no recording found")
video = vids[-1]
out = HERE / "CUH_ED_Control_Tower_demo.mp4"

cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-stats", "-i", str(video)]
for s in segs:
    cmd += ["-i", s["wav"]]

parts, labels = [], []
for n, s in enumerate(segs, start=1):
    ms = int(round(s["offset"] * 1000))
    parts.append(f"[{n}:a]adelay={ms}|{ms}[a{n}]")
    labels.append(f"[a{n}]")
parts.append("".join(labels) + f"amix=inputs={len(segs)}:normalize=0:"
                               f"dropout_transition=0[mix]")
# a touch of headroom so the peaks of two overlapping tails never clip
parts.append("[mix]alimiter=limit=0.95,aresample=48000[aout]")

cmd += ["-filter_complex", ";".join(parts),
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "libx264", "-crf", "21", "-preset", "medium",
        "-pix_fmt", "yuv420p", "-r", "25",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart", "-shortest", str(out)]

print(f"muxing {len(segs)} narration segments onto {video.name} ...")
subprocess.run(cmd, check=True)
print(f"\nwrote {out}  ({out.stat().st_size/1e6:.1f} MB)")
