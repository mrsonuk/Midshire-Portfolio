"""
Background jobs for the slow work (simulation runs and package searches), so
the browser never waits on a long request and can show progress, cancel, and
an explicit failed state - never an endless spinner or old numbers dressed up
as a new run.

Jobs are de-duplicated by key: asking for the same run twice attaches to the
job already going. Results are written to the Midshire store by the job itself,
keyed by model hash, so a finished job's numbers can only ever be shown against
the inputs that produced them.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid

_jobs: dict[str, dict] = {}
_by_key: dict[str, str] = {}
_lock = threading.RLock()
MAX_KEEP = 50


def _public(j: dict) -> dict:
    return {k: v for k, v in j.items() if k not in ("thread", "cancel_flag", "fn")}


def start(kind: str, key: str, fn, meta: dict | None = None) -> dict:
    """Start ``fn(progress, cancelled)`` in a thread unless a job with the same
    key is already queued or running (then return that one)."""
    with _lock:
        jid = _by_key.get(key)
        if jid and _jobs.get(jid, {}).get("status") in ("queued", "running"):
            return _public(_jobs[jid])
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": kind, "key": key, "status": "queued", "progress": 0.0,
               "message": "Queued", "started": time.time(), "finished": None,
               "result_ref": None, "error": None, "meta": meta or {},
               "cancel_flag": threading.Event()}
        _jobs[jid] = job
        _by_key[key] = jid
        _trim()

    def progress(msg=None, frac=None):
        with _lock:
            if msg:
                job["message"] = str(msg)[:300]
            if frac is not None:
                job["progress"] = float(max(0.0, min(1.0, frac)))

    def cancelled():
        return job["cancel_flag"].is_set()

    def body():
        job["status"] = "running"
        try:
            ref = fn(progress, cancelled)
            with _lock:
                if cancelled():
                    job["status"], job["message"] = "cancelled", "Cancelled - nothing was saved."
                else:
                    job["status"], job["result_ref"] = "done", ref
                    job["progress"], job["message"] = 1.0, "Finished"
        except Exception as e:                                   # explicit failed state
            name = type(e).__name__
            with _lock:
                if name in ("Cancelled", "SearchCancelled") or cancelled():
                    job["status"], job["message"] = "cancelled", "Cancelled - nothing was saved."
                else:
                    job["status"] = "failed"
                    job["error"] = f"{name}: {e}"
                    job["details"] = getattr(e, "details", None)
                    job["trace"] = traceback.format_exc()[-2000:]
                    job["message"] = "The run failed - no new results were produced."
        finally:
            job["finished"] = time.time()

    t = threading.Thread(target=body, name=f"midshire-{kind}-{jid}", daemon=True)
    job["thread"] = t
    t.start()
    return _public(job)


def get(jid: str) -> dict | None:
    with _lock:
        j = _jobs.get(jid)
        return _public(j) if j else None


def cancel(jid: str) -> bool:
    with _lock:
        j = _jobs.get(jid)
        if not j or j["status"] not in ("queued", "running"):
            return False
        j["cancel_flag"].set()
        j["message"] = "Cancelling..."
        return True


def wait(jid: str, timeout: float = 600) -> dict | None:
    """Block until a job finishes (tests and the CLI)."""
    j = _jobs.get(jid)
    if j and j.get("thread"):
        j["thread"].join(timeout)
    return get(jid)


def _trim():
    done = [j for j in _jobs.values() if j["status"] not in ("queued", "running")]
    if len(_jobs) > MAX_KEEP:
        for j in sorted(done, key=lambda x: x["started"])[: len(_jobs) - MAX_KEEP]:
            _jobs.pop(j["id"], None)
