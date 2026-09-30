# -*- coding: utf-8 -*-
"""Drive the real product through the demo and record it.

Nothing is staged: every figure the narration quotes is read off the same
endpoints the browser calls. What the recorder adds is the things a viewer
needs in order to follow along - a step chip and subtitle, a visible cursor
that travels to a control before it clicks it, a yellow outline on whatever the
voice is describing, and scrolling that eases instead of jumping.

Sync is measured, not assumed. say() logs the wall-clock offset at which each
clip's subtitle appeared and sets a deadline of the clip length plus 0.45s;
actions run while the clip plays and the next say() waits for the deadline. If
the app is slow on the day, the audio still lands on the right screen because
mux.py delays each wav to the offset that was actually observed.
"""
import json, os, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import overlay, panels
from narration import STEPS

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
URL = "http://127.0.0.1:5000/"
WB = "/home/user/Simulation_model/uec_hybrid/data/seeds/rgt_cuh_workbook.xlsx"
W, H = 1280, 720
TAIL = 0.45          # the spec's breath between clips
STEP_TAIL = 0.9      # a slightly longer one when the step changes
N_STEPS = max(STEPS)

SEGS = json.loads((HERE / "segments.json").read_text())
if os.environ.get("DEMO_ONLY"):
    want = {int(x) for x in os.environ["DEMO_ONLY"].split(",")}
    SEGS = [s for s in SEGS if s["i"] in want]


class Demo:
    def __init__(self, page):
        self.p = page
        self.mx, self.my = W * 0.5, H * 0.45

    # ---- overlay ------------------------------------------------------
    def step(self, n):
        self.p.evaluate("a => window.__step(a[0], a[1])",
                        [f"Step {n} of {N_STEPS}", STEPS.get(n, "")] if n else ["", ""])

    def say(self, text):
        self.p.evaluate("t => window.__say(t)", text)

    def hi(self, sel):
        self.p.evaluate("s => { window.__hlsel = s; window.__hi(s); }", sel)

    def panel(self, html):
        self.p.evaluate("h => window.__panel(h)", html)

    def card(self, h1, h2=None, foot=None):
        self.p.evaluate("a => window.__card(a[0], a[1], a[2])", [h1, h2, foot])

    # ---- pointer ------------------------------------------------------
    def move_to(self, x, y, ms=340):
        """Travel the real mouse, so the drawn cursor travels with it."""
        steps = max(8, int(ms / 16))
        x0, y0 = self.mx, self.my
        for i in range(1, steps + 1):
            t = i / steps
            e = 4 * t ** 3 if t < .5 else 1 - pow(-2 * t + 2, 3) / 2
            self.p.mouse.move(x0 + (x - x0) * e, y0 + (y - y0) * e)
            self.p.wait_for_timeout(ms / steps)
        self.mx, self.my = x, y

    def point_at(self, sel):
        box = self.p.query_selector(sel).bounding_box() if self.p.query_selector(sel) else None
        if not box:
            return None
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        cy = min(cy, H - 150)                       # never behind the caption bar
        self.move_to(cx, cy)
        return cx, cy

    def click(self, sel):
        """Move to the control, pause, then really click it - so the ring fires."""
        try:
            at = self.point_at(sel)
            self.p.wait_for_timeout(170)
            if at:
                self.p.mouse.click(*at)
                return
        except Exception:
            pass
        try:
            self.p.click(sel, timeout=8000)
        except Exception:
            self.p.eval_on_selector(sel, "e => e.click()")

    def type_into(self, sel, text, delay=58):
        self.click(sel)
        self.p.eval_on_selector(sel, "e => { e.value=''; e.focus(); }")
        self.p.keyboard.type(text, delay=delay)

    # ---- page ---------------------------------------------------------
    def scroll_to(self, sel, block="center", ms=2200):
        try:
            self.p.evaluate("a => window.__scroll(a[0], a[1], a[2])", [sel, block, ms])
            self.p.wait_for_timeout(120)      # evaluate already awaited the ease
        except Exception:
            pass

    def tab(self, name):
        self.click(f'#nav a[data-tab="{name}"]')
        self.p.wait_for_timeout(450)

    # ---- actions ------------------------------------------------------
    def run(self, action):
        if action in ("none", ""):
            return
        kind, _, arg = action.partition(":")
        fn = getattr(self, "do_" + kind, None)
        if fn is None:
            print(f"    !! no handler for {action!r}")
            return
        fn(arg) if arg else fn()

    def do_titlecard(self):
        self.card("Cambridge University Hospitals",
                  "Emergency Department Control Tower",
                  "A hybrid simulation built on CUH's own data")

    def do_hi(self, sel):
        self.card(None); self.panel(None)
        self.scroll_to(sel)
        self.point_at(sel)
        self.hi(sel)

    def do_scroll_to(self, sel):
        self.hi(None)
        self.scroll_to(sel, "start")

    def do_goto_setup(self):
        self.card(None); self.hi(None)
        self.tab("setup")
        self.scroll_to("#trustPick", "center")

    def do_upload_workbook(self):
        self.hi(None)
        self.p.set_input_files("#trustFile", WB)
        self.p.wait_for_timeout(500)
        self.hi("#trustFile")
        self.p.wait_for_timeout(450)
        self.click("#importTrust")
        self.p.wait_for_function(
            "() => {const t=document.querySelector('#importStatus');"
            "return t && t.textContent.trim() && !t.querySelector('.spin');}", timeout=120000)
        self.hi("#importStatus")

    def do_status_overlay(self):
        self.hi(None); self.panel(panels.status_panel())

    def do_goto_tower(self):
        self.panel(None); self.hi(None)
        self.tab("tower")
        self.p.wait_for_selector("#flow", timeout=180000)
        self.p.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        self.p.wait_for_timeout(700)

    def do_slider(self, hour):
        self.hi(None)
        self.scroll_to("#flow", "start")
        self.point_at("#hour")
        self._set_hour(int(hour))

    def do_slider_sweep(self, hour):
        target = int(hour)
        cur = int(self.p.eval_on_selector("#hour", "e => +e.value"))
        box = self.p.query_selector("#hour").bounding_box()
        step = 1 if target >= cur else -1
        for h in range(cur + step, target + step, step):
            self._set_hour(h)
            if box:                                  # drag the cursor along the slider
                frac = h / 23.0
                self.p.mouse.move(box["x"] + box["width"] * frac, box["y"] + box["height"] / 2)
                self.mx = box["x"] + box["width"] * frac; self.my = box["y"] + box["height"] / 2
            self.p.wait_for_timeout(230)

    def _set_hour(self, h):
        self.p.eval_on_selector(
            "#hour", "(e,h) => {e.value=h; e.dispatchEvent(new Event('input',{bubbles:true}));}", h)
        self.p.wait_for_timeout(150)

    def do_click_area(self, label):
        self.hi(None)
        sel = f'.fmnode[data-label="{label}"]'
        self.p.wait_for_selector(sel, timeout=30000)
        self.click(sel)
        self.p.wait_for_timeout(600)
        self.scroll_to("#drill", "center")

    def do_close_drill(self):
        if self.p.query_selector("#drillClose"):
            self.click("#drillClose")
        self.p.wait_for_timeout(350)
        if self.p.query_selector("#towerBody .pinch"):
            self.scroll_to("#towerBody .pinch", "center")
            self.hi("#towerBody .pinch")

    def do_recommend(self):
        self.hi(None)
        self.scroll_to("#recBtn", "center")
        self.click("#recBtn")
        self.p.wait_for_timeout(450)
        self.hi("#recStatus")

    def do_wait_rec(self):
        self.p.wait_for_function(
            "() => {const o=document.querySelector('#recOut');"
            "return o && o.textContent.trim().length > 40;}", timeout=180000)
        self.hi(None)
        self.scroll_to("#recOut", "start")

    def do_whatif(self, text):
        self.hi(None)
        self.type_into("#askQ", text)
        self.p.wait_for_timeout(220)
        self.click("#askBtn")
        self.p.wait_for_function(
            "() => {const o=document.querySelector('#askOut');"
            "return o && o.style.display !== 'none' && o.textContent.trim().length > 30;}",
            timeout=180000)
        self.p.wait_for_timeout(250)
        self.scroll_to("#askOut", "center", ms=1100)
        self.hi("#askOut")

    def do_chat(self, text):
        self.hi(None)
        if not self.p.eval_on_selector("#chatPanel", "e => e.classList.contains('open')"):
            self.click("#chatFab")
            self.p.wait_for_timeout(550)
        before = self.p.eval_on_selector("#chatMsgs", "e => e.children.length")
        self.type_into("#chatIn", text, delay=46)
        self.p.wait_for_timeout(200)
        self.click("#chatSend")
        self.p.wait_for_function("n => document.querySelector('#chatMsgs').children.length > n + 1",
                                 arg=before, timeout=180000)
        self.p.wait_for_timeout(400)

    def do_close_chat(self):
        self.p.wait_for_timeout(800)

    def do_validation_overlay(self):
        self.hi(None)
        if self.p.eval_on_selector("#chatPanel", "e => e.classList.contains('open')"):
            self.click("#chatClose")
        self.panel(panels.validation_panel())

    def do_limits_overlay(self):
        self.panel(panels.limits_panel())

    def do_closing(self):
        self.panel(None); self.hi(None)
        self.tab("tower")
        self.p.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        self.p.wait_for_timeout(800)


def main():
    outdir = HERE / "video"; outdir.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME,
                                args=["--no-sandbox", "--force-device-scale-factor=1",
                                      "--hide-scrollbars"])
        ctx = br.new_context(viewport={"width": W, "height": H},
                             record_video_dir=str(outdir),
                             record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        page.goto(URL, wait_until="load")
        page.wait_for_selector("#flow", timeout=240000)
        page.add_style_tag(content=overlay.CSS)
        page.evaluate(overlay.JS)
        page.wait_for_timeout(350)

        d = Demo(page)
        d.do_titlecard()
        page.wait_for_timeout(1100)

        t0 = time.monotonic()
        timeline, last_step, longest_gap = [], None, 0.0
        for n, s in enumerate(SEGS):
            start = time.monotonic()
            offset = start - t0
            if s["step"] != last_step:
                d.step(s["step"]); last_step = s["step"]
            d.say(s["text"])
            try:
                d.run(s["action"])
            except Exception as e:                       # never abandon a take
                print(f"    !! {s['action']}: {str(e)[:110]}")
            spoke_until = offset + s["dur"]
            nxt = SEGS[n + 1]["step"] if n + 1 < len(SEGS) else None
            rest = s["dur"] + (TAIL if nxt == s["step"] else STEP_TAIL) \
                   - (time.monotonic() - start)
            if rest > 0:
                page.wait_for_timeout(rest * 1000)
            gap = (time.monotonic() - t0) - spoke_until
            longest_gap = max(longest_gap, gap)
            timeline.append({**s, "offset": round(offset, 3), "silence_after": round(gap, 2)})
            print(f"  {s['i']:3d} @{offset:7.2f}s {s['dur']:5.2f}s gap{gap:5.2f}s  "
                  f"{s['action'][:20]:<20} {s['text'][:40]}")

        d.say(""); d.step(None)
        d.card("Cambridge University Hospitals", "Emergency Department Control Tower",
               "Validation: python3 -m uec_hybrid.validation.against_trust RGT")
        page.wait_for_timeout(3000)
        total = time.monotonic() - t0
        ctx.close(); br.close()

    (HERE / "timeline.json").write_text(json.dumps(
        {"total": round(total, 3), "longest_silence": round(longest_gap, 2),
         "segments": timeline}, indent=1))
    v = sorted(outdir.glob("*.webm"))
    print(f"\nrecorded {total/60:.1f} min, longest silent gap {longest_gap:.1f}s "
          f"-> {v[-1] if v else 'NO VIDEO'}")


if __name__ == "__main__":
    main()
