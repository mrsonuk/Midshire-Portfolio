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

import logging
import os
import threading
import time
import traceback
import uuid

from .public import current_owner, enabled

log = logging.getLogger(__name__)
FAILED_MESSAGE = "This run couldn't be completed. Please try again. If it keeps happening, restart the tool."

_jobs: dict[str, dict] = {}
_by_key: dict[str, str] = {}
_lock = threading.RLock()
MAX_KEEP = 50
MAX_RUNNING = max(1, int(os.environ.get("MIDSHIRE_MAX_RUNNING_JOBS", "1" if enabled() else "2")))
MAX_QUEUED = max(0, int(os.environ.get("MIDSHIRE_MAX_QUEUED_JOBS", "3")))
_slots = threading.BoundedSemaphore(MAX_RUNNING)


class CapacityError(Exception):
    """The public demonstration has reached its compute quota."""


def _visible(j: dict | None) -> bool:
    if j is None:
        return False
    owner = current_owner()
    return owner is None or j.get("owner") == owner



def _public(j: dict) -> dict:
    return {k: v for k, v in j.items() if k not in ("thread", "cancel_flag", "fn", "owner")}


def start(kind: str, key: str, fn, meta: dict | None = None) -> dict:
    """Start ``fn(progress, cancelled)`` in a thread unless a job with the same
    key is already queued or running (then return that one)."""
    owner = current_owner()
    # No cross-visitor attachment to someone else's in-flight what-if job.
    owned_key = f"{owner}:{key}" if owner else key
    with _lock:
        jid = _by_key.get(owned_key)
        if jid and _jobs.get(jid, {}).get("status") in ("queued", "running"):
            return _public(_jobs[jid])
        live = [j for j in _jobs.values() if j["status"] in ("queued", "running")]
        if owner is not None and any(j.get("owner") == owner for j in live):
            raise CapacityError("Finish your current simulation before starting another.")
        if len(live) >= MAX_RUNNING + MAX_QUEUED:
            raise CapacityError("All simulation slots are busy. Please try again later.")
        jid = uuid.uuid4().hex[:12]
        job = {"id": jid, "kind": kind, "key": owned_key, "owner": owner,
               "status": "queued", "progress": 0.0,
               "message": "Starting", "started": time.time(), "finished": None,
               "result_ref": None, "error": None, "meta": meta or {},
               "cancel_flag": threading.Event()}
        _jobs[jid] = job
        _by_key[owned_key] = jid
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
        with _slots:
            with _lock:
                if cancelled():
                    job["status"] = "cancelled"
                else:
                    job["status"] = "running"
            try:
                if not cancelled():
                    ref = fn(progress, cancelled)
                    with _lock:
                        if cancelled():
                            job["status"], job["message"] = "cancelled", "Cancelled. Nothing was saved."
                        else:
                            job["status"], job["result_ref"] = "done", ref
                            job["progress"], job["message"] = 1.0, "Done"
                else:
                    with _lock:
                        job["message"] = "Cancelled. Nothing was saved."
            except Exception as e:
                name = type(e).__name__
                with _lock:
                    if name in ("Cancelled", "SearchCancelled") or cancelled():
                        job["status"], job["message"] = "cancelled", "Cancelled. Nothing was saved."
                    else:
                        job["status"] = "failed"
                        details = getattr(e, "details", None)
                        if name == "BuildError" and details:
                            job["message"] = "These changes can't be modelled. Please check the highlighted inputs."
                            job["details"] = details
                        else:
                            job["message"] = FAILED_MESSAGE
                            job["details"] = None
                        job["error"] = None
                        log.error("Midshire %s job %s failed: %s: %s\n%s", kind, jid, name, e,
                                  traceback.format_exc())
            finally:
                with _lock:
                    job["finished"] = time.time()
                    _trim()

    t = threading.Thread(target=body, name=f"midshire-{kind}-{jid}", daemon=True)
    job["thread"] = t
    t.start()
    return _public(job)


def get(jid: str) -> dict | None:
    with _lock:
        j = _jobs.get(jid)
        return _public(j) if _visible(j) else None


def get_raw(jid: str) -> dict | None:
    """Internal read for supported what-if results, with the same ownership check."""
    with _lock:
        j = _jobs.get(jid)
        return j if _visible(j) else None


def update_meta(jid: str, values: dict):
    with _lock:
        j = _jobs.get(jid)
        if not _visible(j):
            return False
        j["meta"].update(values)
        return True


def cancel(jid: str) -> bool:
    with _lock:
        j = _jobs.get(jid)
        if not _visible(j) or j["status"] not in ("queued", "running"):
            return False
        j["cancel_flag"].set()
        j["message"] = "Stopping..."
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
            if _by_key.get(j["key"]) == j["id"]:
                _by_key.pop(j["key"], None)
