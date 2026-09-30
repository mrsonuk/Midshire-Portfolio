"""Synthesize one wav per narration segment and record its exact duration."""
import json, sys, wave
from pathlib import Path
from piper import PiperVoice
from piper.config import SynthesisConfig
sys.path.insert(0, str(Path(__file__).parent))
from narration import SEGMENTS

OUT = Path(__file__).parent / "audio"; OUT.mkdir(exist_ok=True)
voice = PiperVoice.load("/tmp/voices/en_GB-alan-medium.onnx")
# a shade slower than default: this is a clinical audience reading figures
cfg = SynthesisConfig(length_scale=1.06, volume=1.0)

meta = []
for i, (act, action, text) in enumerate(SEGMENTS):
    f = OUT / f"seg{i:03d}.wav"
    with wave.open(str(f), "wb") as w:
        voice.synthesize_wav(text, w, syn_config=cfg)
    with wave.open(str(f)) as w:
        dur = w.getnframes() / float(w.getframerate())
    meta.append({"i": i, "act": act, "action": action, "text": text,
                 "wav": str(f), "dur": round(dur, 3)})
    print(f"{i:3d} {dur:6.2f}s  {act[:28]:<28} {text[:50]}")

(Path(__file__).parent / "segments.json").write_text(json.dumps(meta, indent=1))
print(f"\n{len(meta)} segments, speech total {sum(m['dur'] for m in meta)/60:.1f} min")
