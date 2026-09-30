# -*- coding: utf-8 -*-
"""Drive the REAL product through the demo and record it, captions burned in.

Nothing here fakes a screen: every figure the narration quotes is read off the
same endpoints the browser calls. The script writes timeline.json - the measured
wall-clock offset of each narration segment - so the audio can be laid onto the
video afterwards and stay in sync even when the app takes longer than expected.
"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import overlay, panels

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
URL = "http://127.0.0.1:5000/"
WB = "/home/user/Simulation_model/uec_hybrid/data/seeds/rgt_cuh_workbook.xlsx"
W, H = 1600, 900
TAIL = 0.55          # breath between segments
ACT_TAIL = 1.25      # longer breath when the act changes

SEGS = json.loads((HERE / "segments.json").read_text())
import os
if os.environ.get("DEMO_ONLY"):                 # dry-run a subset before a full take
    want = {int(x) for x in os.environ["DEMO_ONLY"].split(",")}
    SEGS = [s for s in SEGS if s["i"] in want]


class Demo:
    def __init__(self, page):
        self.p = page

    # ---- overlay -------------------------------------------------------
    def cap(self, text):
        self.p.evaluate("t => window.__cap(t)", text)

    def act(self, text):
        self.p.evaluate("t => window.__act(t)", text)

    def hi(self, sel):
        self.p.evaluate("s => window.__hi(s)", sel)

    def panel(self, html):
        self.p.evaluate("h => window.__panel(h)", html)

    def card(self, h1, h2=None, foot=None):
        self.p.evaluate("a => window.__card(a[0], a[1], a[2])", [h1, h2, foot])

    # ---- helpers -------------------------------------------------------
    def scroll_to(self, sel, block="center"):
        self.p.evaluate(
            "a => {const e=document.querySelector(a[0]);"
            "if(e)e.scrollIntoView({behavior:'smooth',block:a[1]});}", [sel, block])
        self.p.wait_for_timeout(700)

    def click(self, sel, timeout=15000):
        """Click, falling back to a DOM click if anything intercepts it."""
        try:
            self.p.click(sel, timeout=timeout)
        except Exception:
            self.p.eval_on_selector(sel, "e => e.click()")

    def tab(self, name):
        self.click(f'#nav a[data-tab="{name}"]')
        self.p.wait_for_timeout(500)

    # ---- actions -------------------------------------------------------
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
                  "A hybrid simulation built on CUH's own data · September 2026")

    def do_hi(self, sel):
        self.card(None)
        self.panel(None)
        self.scroll_to(sel)
        self.hi(sel)

    def do_scroll_to(self, sel):
        self.hi(None)
        self.scroll_to(sel, "start")

    def do_goto_setup(self):
        self.card(None)
        self.hi(None)
        self.tab("setup")
        self.scroll_to("#trustPick", "center")

    def do_upload_workbook(self):
        self.hi(None)
        self.p.set_input_files("#trustFile", WB)
        self.p.wait_for_timeout(600)
        self.hi("#trustFile")
        self.p.wait_for_timeout(500)
        self.click("#importTrust")
        self.p.wait_for_function(
            "() => {const t=document.querySelector('#importStatus');"
            "return t && t.textContent.trim() && !t.querySelector('.spin');}",
            timeout=120000)
        self.hi("#importStatus")

    def do_status_overlay(self):
        self.hi(None)
        self.panel(panels.status_panel())

    def do_goto_tower(self):
        self.panel(None)
        self.hi(None)
        self.tab("tower")
        self.p.wait_for_selector("#flow", timeout=180000)
        self.p.wait_for_timeout(800)
        self.p.evaluate("window.scrollTo({top:0,behavior:'smooth'})")

    def do_slider(self, hour):
        self.hi(None)
        self.scroll_to("#flow", "start")
        self._set_hour(int(hour))

    def do_slider_sweep(self, hour):
        target = int(hour)
        cur = int(self.p.eval_on_selector("#hour", "e => +e.value"))
        step = 1 if target >= cur else -1
        for h in range(cur + step, target + step, step):
            self._set_hour(h)
            self.p.wait_for_timeout(260)

    def _set_hour(self, h):
        self.p.eval_on_selector(
            "#hour",
            "(e,h) => {e.value=h; e.dispatchEvent(new Event('input',{bubbles:true}));}", h)
        self.p.wait_for_timeout(180)

    def do_click_area(self, label):
        self.hi(None)
        sel = f'.fmnode[data-label="{label}"]'
        self.p.wait_for_selector(sel, timeout=30000)
        self.click(sel)
        self.p.wait_for_timeout(700)
        self.scroll_to("#drill", "center")

    def do_close_drill(self):
        if self.p.query_selector("#drillClose"):
            self.click("#drillClose")
        self.p.wait_for_timeout(400)
        if self.p.query_selector("#towerBody .pinch"):
            self.scroll_to("#towerBody .pinch", "center")
            self.hi("#towerBody .pinch")

    def do_recommend(self):
        self.hi(None)
        self.scroll_to("#recBtn", "center")
        self.p.wait_for_timeout(400)
        self.click("#recBtn")
        self.p.wait_for_timeout(600)
        self.hi("#recStatus")

    def do_wait_rec(self):
        self.p.wait_for_function(
            "() => {const o=document.querySelector('#recOut');"
            "return o && o.textContent.trim().length > 40;}", timeout=180000)
        self.p.wait_for_timeout(500)
        self.hi(None)
        self.scroll_to("#recOut", "start")

    def do_whatif(self, text):
        self.hi(None)
        self.scroll_to("#askQ", "center")
        self.p.fill("#askQ", "")
        self.p.type("#askQ", text, delay=32)
        self.p.wait_for_timeout(300)
        self.click("#askBtn")
        self.p.wait_for_function(
            "() => {const o=document.querySelector('#askOut');"
            "return o && o.style.display !== 'none' && o.textContent.trim().length > 30;}",
            timeout=180000)
        self.p.wait_for_timeout(400)
        self.scroll_to("#askOut", "center")
        self.hi("#askOut")

    def do_chat(self, text):
        self.hi(None)
        if not self.p.eval_on_selector("#chatPanel", "e => e.classList.contains('open')"):
            self.click("#chatFab")
            self.p.wait_for_timeout(600)
        before = self.p.eval_on_selector("#chatMsgs", "e => e.children.length")
        self.p.fill("#chatIn", "")
        self.p.type("#chatIn", text, delay=34)
        self.p.wait_for_timeout(250)
        self.click("#chatSend")
        self.p.wait_for_function(
            "n => document.querySelector('#chatMsgs').children.length > n + 1",
            arg=before, timeout=180000)
        self.p.wait_for_timeout(500)

    def do_close_chat(self):
        self.p.wait_for_timeout(1500)

    def do_validation_overlay(self):
        self.hi(None)
        if self.p.eval_on_selector("#chatPanel", "e => e.classList.contains('open')"):
            self.click("#chatClose")
        self.panel(panels.validation_panel())

    def do_limits_overlay(self):
        self.panel(panels.limits_panel())

    def do_closing(self):
        self.panel(None)
        self.hi(None)
        self.tab("tower")
        self.p.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        self.p.wait_for_timeout(900)


def main():
    outdir = HERE / "video"; outdir.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME,
                                args=["--no-sandbox", "--force-device-scale-factor=1",
                                      "--hide-scrollbars"])
        ctx = br.new_context(viewport={"width": W, "height": H},
                             record_video_dir=str(outdir),
                             record_video_size={"width": W, "height": H},
                             reduced_motion="no-preference")
        page = ctx.new_page()
        page.goto(URL, wait_until="load")
        page.wait_for_selector("#flow", timeout=240000)
        page.add_style_tag(content=overlay.CSS)
        page.evaluate(overlay.JS)
        page.wait_for_timeout(400)

        d = Demo(page)
        d.card("Cambridge University Hospitals",
               "Emergency Department Control Tower",
               "A hybrid simulation built on CUH's own data · September 2026")
        page.wait_for_timeout(1200)

        t0 = time.monotonic()
        timeline, last_act = [], None
        for n, s in enumerate(SEGS):
            start_abs = time.monotonic()
            offset = start_abs - t0
            if s["act"] != last_act:
                d.act(s["act"]); last_act = s["act"]
            d.cap(s["text"])
            try:
                d.run(s["action"])
            except Exception as e:                       # never abandon the take
                print(f"    !! {s['action']}: {str(e)[:120]}")
            nxt = SEGS[n + 1]["act"] if n + 1 < len(SEGS) else None
            tail = TAIL if nxt == s["act"] else ACT_TAIL   # breathe between acts
            rest = s["dur"] + tail - (time.monotonic() - start_abs)
            if rest > 0:
                page.wait_for_timeout(rest * 1000)
            timeline.append({**s, "offset": round(offset, 3)})
            print(f"  {s['i']:3d} @{offset:7.2f}s  {s['dur']:5.2f}s  "
                  f"{s['action'][:22]:<22} {s['text'][:44]}")

        # hold a closing card so the film does not cut on a caption
        d.cap("")
        d.card("Cambridge University Hospitals",
               "Emergency Department Control Tower",
               "Validation: python3 -m uec_hybrid.validation.against_trust RGT")
        page.wait_for_timeout(3200)
        total = time.monotonic() - t0
        ctx.close(); br.close()

    (HERE / "timeline.json").write_text(json.dumps(
        {"total": round(total, 3), "segments": timeline}, indent=1))
    vids = sorted(outdir.glob("*.webm"))
    print(f"\nrecorded {total/60:.1f} min -> {vids[-1] if vids else 'NO VIDEO'}")


if __name__ == "__main__":
    main()
