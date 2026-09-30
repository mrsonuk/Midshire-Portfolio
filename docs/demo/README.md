# Recording the Cambridge demo

`docs/DEMO_SCRIPT.md` is the script a person reads. This directory is the
machine that records it: it drives the **real product** in a browser, burns the
narration in as subtitles, speaks it, and lays the audio onto the take.

Nothing here stages a screenshot. Every figure the narration quotes was read off
the same endpoints the browser calls, and the take fails loudly rather than
carrying on against a stale screen.

## Reproduce

```bash
pip install playwright kokoro-onnx soundfile
apt-get install -y ffmpeg                        # h264 + aac for the final mp4

mkdir -p /tmp/kokoro && cd /tmp/kokoro           # Kokoro, British voice bf_emma
H=https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main
curl -fsSL -o model.onnx $H/onnx/model.onnx
curl -fsSL -o bf_emma.bin $H/voices/bf_emma.bin
python3 -c "import numpy as np; np.savez('voices.npz', \
  bf_emma=np.fromfile('bf_emma.bin', dtype=np.float32).reshape(510,1,256))"

cd <repo>
python3 -m uec_hybrid.ingest.seed RGT --warm     # warm, or the take records spinners
python3 -m uec_hybrid.app.server &

cd docs/demo
python3 synth.py     # narration.py -> audio/seg###.wav + segments.json (durations)
python3 record.py    # drives the product, writes video/*.webm + timeline.json
python3 mux.py       # -> CUH_ED_Control_Tower_demo.mp4
```

`DEMO_ONLY=0,6,7,19` records just those clips - use it to check a change
without sitting through the whole take.

## How it stays in sync

`record.py` cannot know in advance how long the app will take to answer, so it
does not try. It holds each caption for at least its narration's length, and
logs the wall-clock offset at which the caption actually appeared. `mux.py` then
delays each wav to *that measured offset*. If a screen takes ten seconds longer
on the day, the words still land on the right screen instead of drifting.

## Files

| | |
|---|---|
| `narration.py` | the spoken lines and the action each one performs. The single source of truth - captions and speech are the same string, so what a viewer reads can never diverge from what they hear. |
| `synth.py` | speaks each line with Kokoro (`bf_emma`, speed 0.98) and records its exact duration. |
| `overlay.py` | the caption bar (step chip, section title, subtitle), the visible cursor and click ring, the yellow highlight, the eased scroll, the title card and the full-screen panels. All `pointer-events:none` - an overlay that swallows a click costs a whole take. |
| `panels.py` | the full-screen panels, built from the real files: the register is read out of the seed workbook's `Status` tab, the validation table is what `uec_hybrid.validation.against_trust` prints. |
| `record.py` | drives the product and records it: the cursor travels to a control before clicking it, text is typed a key at a time, scrolling eases over ~2.2s, and the silent gap after every clip is logged so nothing sits quiet for more than a few seconds. |
| `mux.py` | lays the narration onto the take at the measured offsets. |

## If you change a number in the narration

Re-check it against the running app first - `curl` the endpoint the screen
calls, do not trust an earlier note. Two claims in the first cut of the script
were wrong that way: the pinch banner names the **paediatric area** for the
working-day pinch and **ED ambulatory** for the largest total patient-hours
lost, and an earlier draft read only the second line while calling it the first.

Then re-run `synth.py` (it only re-speaks lines whose text changed) and record
again.
