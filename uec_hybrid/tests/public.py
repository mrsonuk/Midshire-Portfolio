"""Public AWS demo regression: anonymous isolation, CSRF and job ownership.

Run: python -m uec_hybrid.tests.public
Does NOT require AWS credentials or a live Postgres database.
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path

from flask import g

from ..midshire import jobs, store
from ..midshire.server import create_app
from ..midshire import config as mcfg

HOST = "https://midshire.example.test"


def run():
    old_mode = os.environ.get("MIDSHIRE_PUBLIC_MODE")
    old_secret = os.environ.get("MIDSHIRE_SESSION_SECRET")
    os.environ["MIDSHIRE_PUBLIC_MODE"] = "1"
    os.environ["MIDSHIRE_SESSION_SECRET"] = "test-only-not-for-production-secret-key-123456789"
    try:
        db = f"sqlite:///{Path(tempfile.mkdtemp()) / 'public_test.sqlite3'}"
        app = create_app(db_url=db, load_fixtures=False)
        a, b = app.test_client(), app.test_client()

        def token(client):
            r = client.get("/", base_url=HOST)
            assert r.status_code == 200
            assert "Secure" in r.headers.get("Set-Cookie", "")
            assert "HttpOnly" in r.headers.get("Set-Cookie", "")
            html = r.get_data(as_text=True)
            match = re.search(r'<meta name="midshire-csrf" content="([^"]+)">', html)
            assert match, "A CSRF token must be on the page"
            return match.group(1)

        a_token, b_token = token(a), token(b)
        assert a_token != b_token

        def post(client, tk, path, body=None):
            return client.post(path, json=body or {}, base_url=HOST,
                               headers={"X-Midshire-CSRF": tk})

        def delete(client, tk, path):
            return client.delete(path, base_url=HOST,
                                 headers={"X-Midshire-CSRF": tk})

        original = mcfg.baseline_inputs()
        # Package search cache must not serve stale inputs when visitors change prices.
        from copy import deepcopy
        from ..midshire.server import _search_storage_key
        from ..midshire.optimise import search_key
        original_target = original["target"]
        default_key = search_key(original, original_target, "combined")
        assert _search_storage_key(original, original_target, "combined") == default_key
        with_new_price = deepcopy(original)
        with_new_price["estates"]["items"]["ct_scanner"]["capital"] += 1234
        priced_key = _search_storage_key(with_new_price, original_target, "combined")
        assert priced_key != default_key and priced_key.startswith("search:")
        assert _search_storage_key(with_new_price, original_target, "combined") == priced_key

        denied = a.post("/api/m/scenarios", json={"name": "No CSRF", "inputs": original}, base_url=HOST)
        assert denied.status_code == 403, denied.get_json()
        denied2 = post(a, b_token, "/api/m/scenarios", {"name": "Wrong token", "inputs": original})
        assert denied2.status_code == 403

        saved_a = post(a, a_token, "/api/m/scenarios", {"name": "Visitor A", "inputs": original})
        saved_b = post(b, b_token, "/api/m/scenarios", {"name": "Visitor B", "inputs": original})
        assert saved_a.status_code == saved_b.status_code == 200
        sid_a, sid_b = saved_a.get_json()["scenario"]["id"], saved_b.get_json()["scenario"]["id"]
        assert sid_a != sid_b
        assert a.get(f"/api/m/scenarios/{sid_b}", base_url=HOST).status_code == 404
        assert b.get(f"/api/m/scenarios/{sid_a}", base_url=HOST).status_code == 404

        cards_a = a.get("/api/m/scenarios", base_url=HOST).get_json()["scenarios"]
        cards_b = b.get("/api/m/scenarios", base_url=HOST).get_json()["scenarios"]
        assert sid_a in {x["id"] for x in cards_a} and sid_b not in {x["id"] for x in cards_a}
        assert sid_b in {x["id"] for x in cards_b} and sid_a not in {x["id"] for x in cards_b}

        unauthorized = post(a, a_token, "/api/m/scenarios",
                            {"id": sid_b, "name": "Attempt overwrite", "inputs": original})
        assert unauthorized.status_code == 403
        assert delete(a, a_token, f"/api/m/scenarios/{sid_b}").get_json()["ok"] is False
        assert post(a, a_token, "/api/m/apply", {"scenario_id": sid_b}).status_code == 404
        assert a.get(f"/api/m/export/inputs.json?scenario_id={sid_b}", base_url=HOST).status_code == 404
        assert post(a, a_token, "/api/m/result", {"scenario_id": sid_b}).status_code == 404
        assert post(a, a_token, "/api/m/compare", {"scenario_ids": [sid_b]}).get_json()["rows"] == []

        assert post(a, a_token, "/api/m/apply", {"scenario_id": sid_a}).status_code == 200
        assert post(b, b_token, "/api/m/apply", {"scenario_id": sid_b}).status_code == 200
        assert post(a, a_token, "/api/m/reset").status_code == 200
        assert a.get("/api/m/scenarios", base_url=HOST).get_json()["applied"] == "baseline"
        assert b.get("/api/m/scenarios", base_url=HOST).get_json()["applied"] == sid_b
        assert b.get(f"/api/m/scenarios/{sid_b}", base_url=HOST).status_code == 200
        assert store.get_scenario("baseline")["kind"] == "baseline"

        gate = threading.Event()
        def work(progress, cancelled):
            gate.wait(3)
            return {"ok": True}
        with app.test_request_context(HOST):
            g.midshire_owner = "a" * 32
            j = jobs.start("run", "owner-check", work)
            assert jobs.get(j["id"]) is not None
        with app.test_request_context(HOST):
            g.midshire_owner = "b" * 32
            assert jobs.get(j["id"]) is None
            assert jobs.get_raw(j["id"]) is None
            assert jobs.cancel(j["id"]) is False
        gate.set()
        assert jobs.wait(j["id"], 5)["status"] == "done"

        assert a.get("/healthz", base_url=HOST).get_json()["status"] == "ok"
        print("Public demo tests passed: CSRF, secure cookies, visitor-owned scenarios/settings,"
              " exports, comparison, jobs, and health check.")
    finally:
        if old_mode is None:
            os.environ.pop("MIDSHIRE_PUBLIC_MODE", None)
        else:
            os.environ["MIDSHIRE_PUBLIC_MODE"] = old_mode
        if old_secret is None:
            os.environ.pop("MIDSHIRE_SESSION_SECRET", None)
        else:
            os.environ["MIDSHIRE_SESSION_SECRET"] = old_secret


if __name__ == "__main__":
    run()
