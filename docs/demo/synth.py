# -*- coding: utf-8 -*-
"""Speak every narration clip and record its exact duration.

Kokoro (kokoro-onnx, onnx-community/Kokoro-82M-v1.0-ONNX), British voice
bf_emma at speed 0.98. Every clip is generated up front so record.py knows how
long each one runs before it starts driving the browser.
"""
import json, sys, wave
from pathlib import Path
import numpy as np
from kokoro_onnx import Kokoro
sys.path.insert(0, str(Path(__file__).parent))
from narration import SEGMENTS, STEPS

MODEL  = "/tmp/kokoro/model.onnx"
VOICES = "/tmp/kokoro/voices.npz"
VOICE, SPEED = "bf_emma", 0.98

OUT = Path(__file__).parent / "audio"; OUT.mkdir(exist_ok=True)
k = Kokoro(MODEL, VOICES)

meta = []
for i, (step, action, text) in enumerate(SEGMENTS):
    samples, sr = k.create(text, voice=VOICE, speed=SPEED, lang="en-gb")
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    f = OUT / f"clip{i:03d}.wav"
    with wave.open(str(f), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    dur = len(samples) / sr
    meta.append({"i": i, "step": step, "title": STEPS.get(step, ""),
                 "action": action, "text": text,
                 "wav": str(f), "dur": round(dur, 3)})
    print(f"{i:3d} {dur:5.2f}s  step {step}  {text[:56]}")

(Path(__file__).parent / "segments.json").write_text(json.dumps(meta, indent=1))
print(f"\n{len(meta)} clips, {sum(m['dur'] for m in meta)/60:.1f} min of speech")
