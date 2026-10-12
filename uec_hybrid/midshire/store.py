"""
Midshire persistence - a SEPARATE database from the Cambridge build.

The Cambridge product keeps its saved department, calibration, cost book and
settings in ``uec_platform.sqlite3``. A Git branch does not isolate a database,
so Midshire never touches that file: it uses its own (``uec_midshire.sqlite3``
by default, or ``MIDSHIRE_DATABASE_URL``). Loading or resetting Midshire cannot
overwrite anything Cambridge has saved.

Stored here:
* scenarios - named, versioned input sets (the demo baseline is fixed and can
  only be RESET from the committed fixture, never overwritten by an edit or a
  speculative assistant request);
* runs - results keyed by (model hash, seed set), with run id, seeds, engine
  version, source commit, timestamp and metric definitions;
* settings - e.g. which scenario is applied (being viewed).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import threading
import uuid
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine, or_
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config as mcfg
from .public import current_owner

_DEFAULT = Path(__file__).resolve().parent.parent.parent / "uec_midshire.sqlite3"
BASELINE_ID = "baseline"

Base = declarative_base()
_engine = None
_Session = None
_lock = threading.RLock()


class ScenarioRow(Base):
    __tablename__ = "midshire_scenarios"
    id = Column(String(40), primary_key=True)
    name = Column(String(200), nullable=False)
    owner_id = Column(String(64), nullable=True, index=True)  # NULL only for shared baseline/library
    kind = Column(String(20), nullable=False)          # baseline | scenario | precomputed
    parent_id = Column(String(40), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    inputs = Column(Text, nullable=False)
    note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class RunRow(Base):
    __tablename__ = "midshire_runs"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), unique=True, index=True, nullable=False)   # model hash + seeds
    model_hash = Column(String(40), index=True, nullable=False)
    source = Column(String(20), nullable=False, default="computed")     # computed | precomputed
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)


class SettingRow(Base):
    __tablename__ = "midshire_settings"
    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)


def _now():
    return _dt.datetime.now(_dt.timezone.utc)


def init(url: str | None = None, force: bool = False):
    global _engine, _Session
    with _lock:
        if _engine is not None and not force:
            return _engine
        url = url or os.environ.get("MIDSHIRE_DATABASE_URL") or f"sqlite:///{_DEFAULT}"
        if "uec_platform" in url:
            raise RuntimeError("Midshire must not share the Cambridge database")
        kw = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
        _engine = create_engine(url, **kw)
        _Session = sessionmaker(bind=_engine)
        Base.metadata.create_all(_engine)
        ensure_baseline()
        return _engine


def url() -> str:
    init()
    return str(_engine.url)


def _s():
    if _Session is None:
        init()
    return _Session()


# --------------------------------------------------------------------------- #
# scenarios
# --------------------------------------------------------------------------- #
def _row(r: ScenarioRow) -> dict:
    inputs = json.loads(r.inputs)
    return {"id": r.id, "name": r.name, "kind": r.kind, "parent_id": r.parent_id,
            "version": r.version, "note": r.note, "inputs": inputs,
            "model_hash": mcfg.model_hash(inputs), "finance_hash": mcfg.finance_hash(inputs),
            "created_at": r.created_at.isoformat(timespec="seconds"),
            "updated_at": r.updated_at.isoformat(timespec="seconds")}


def ensure_baseline(reset: bool = False) -> dict:
    """The demo baseline from the committed fixture. ``reset`` restores it
    (and clears which scenario is applied) - it never touches other saves."""
    with _lock, _s() as s:
        row = s.get(ScenarioRow, BASELINE_ID)
        inputs = mcfg.baseline_inputs()
        name = mcfg.fixture().get("baseline_name", "Baseline")
        note = json.dumps({"why": "How the department runs today, with the current staffing, space and beds.",
                           "look_for": "Use it as the starting point every other scenario is compared with."})
        if row is None:
            row = ScenarioRow(id=BASELINE_ID, name=name, kind="baseline",
                              inputs=json.dumps(inputs), version=1, note=note,
                              created_at=_now(), updated_at=_now())
            s.add(row)
        elif reset or json.loads(row.inputs).get("fixture_version") != inputs["fixture_version"]:
            row.inputs = json.dumps(inputs)
            row.version += 1
            row.updated_at = _now()
        if row.name != name or row.note != note:      # older databases: plain name and description
            row.name, row.note = name, note
        s.commit()
        if reset:
            s.query(SettingRow).filter(SettingRow.key.in_(["applied", "shown"])).delete(synchronize_session=False)
            s.commit()
        return _row(row)


def shown_ids() -> list[str]:
    """Scenarios the user has opened, run or saved: the scenario picker lists
    these after the baseline. Library scenarios stay out of it until used."""
    return list(get_setting("shown") or [])


def mark_shown(sid: str):
    if not sid or sid == BASELINE_ID:
        return
    if current_owner() is not None and get_scenario(sid) is None:
        return
    ids = shown_ids()
    if sid not in ids:
        save_setting("shown", ids + [sid])


def get_scenario(sid: str) -> dict | None:
    owner = current_owner()
    with _s() as s:
        r = s.get(ScenarioRow, sid)
        if owner is not None and r is not None:
            if r.kind not in ("baseline", "precomputed") and r.owner_id != owner:
                return None
        return _row(r) if r else None


def list_scenarios() -> list[dict]:
    owner = current_owner()
    with _s() as s:
        query = s.query(ScenarioRow)
        if owner is not None:
            query = query.filter(or_(ScenarioRow.kind.in_(("baseline", "precomputed")),
                                     ScenarioRow.owner_id == owner))
        rows = query.order_by(ScenarioRow.kind, ScenarioRow.created_at).all()
        out = []
        for r in rows:
            d = _row(r)
            d.pop("inputs")
            out.append(d)
        return out


def save_scenario(name: str, inputs: dict, kind: str = "scenario", note: str = "",
                  sid: str | None = None, parent_id: str = BASELINE_ID) -> dict:
    """Create (or update a non-baseline) named scenario. The baseline id is
    refused - it can only be reset from the fixture."""
    if sid == BASELINE_ID or kind == "baseline":
        raise PermissionError("The baseline can't be changed. Save your changes as a new scenario.")
    owner = current_owner()
    if owner is not None and kind != "scenario":
        raise PermissionError("Shared example scenarios can't be changed.")
    with _lock, _s() as s:
        row = s.get(ScenarioRow, sid) if sid else None
        if owner is not None and sid and row is None:
            raise LookupError("That scenario couldn't be found.")
        if row is None:
            row = ScenarioRow(id=sid or uuid.uuid4().hex[:12], name=name[:200], kind=kind,
                              owner_id=owner, parent_id=parent_id, inputs=json.dumps(inputs),
                              note=note[:2000], version=1, created_at=_now(), updated_at=_now())
            s.add(row)
        else:
            if row.kind == "baseline" or (owner is not None and
                                         (row.owner_id != owner or row.kind != "scenario")):
                raise PermissionError("That scenario can't be changed.")
            row.name, row.inputs, row.note = name[:200], json.dumps(inputs), note[:2000]
            row.version += 1
            row.updated_at = _now()
        s.commit()
        return _row(row)


def delete_scenario(sid: str) -> bool:
    if sid == BASELINE_ID:
        raise PermissionError("The baseline can't be deleted.")
    owner = current_owner()
    with _lock, _s() as s:
        q = s.query(ScenarioRow).filter_by(id=sid)
        if owner is not None:
            q = q.filter_by(owner_id=owner, kind="scenario")
        n = q.delete()
        s.commit()
        return bool(n)


# --------------------------------------------------------------------------- #
# runs (cache keyed by model hash + seed list)
# --------------------------------------------------------------------------- #
def run_key(model_hash: str, seeds) -> str:
    return f"{model_hash}:{mcfg.stable_hash(list(seeds))[:12]}"


def get_run(model_hash: str, seeds) -> dict | None:
    with _s() as s:
        r = s.query(RunRow).filter_by(key=run_key(model_hash, seeds)).first()
        if not r:
            return None
        out = json.loads(r.payload)
        out["result_source"] = r.source
        return out


def put_run(payload: dict, source: str = "computed") -> dict:
    key = run_key(payload["model_hash"], payload["seeds"])
    with _lock, _s() as s:
        row = s.query(RunRow).filter_by(key=key).first()
        blob = json.dumps(payload)
        if row:
            row.payload, row.source, row.created_at = blob, source, _now()
        else:
            s.add(RunRow(key=key, model_hash=payload["model_hash"], source=source,
                         payload=blob, created_at=_now()))
        s.commit()
    out = dict(payload)
    out["result_source"] = source
    return out


def _setting_key(key: str) -> str:
    owner = current_owner()
    if owner is not None and key in ("applied", "shown"):
        return f"{key}:{owner}"
    return key


def get_setting(key: str):
    with _s() as s:
        r = s.get(SettingRow, _setting_key(key))
        return json.loads(r.value) if r else None


def save_setting(key: str, value):
    with _lock, _s() as s:
        scoped_key = _setting_key(key)
        r = s.get(SettingRow, scoped_key)
        if r:
            r.value = json.dumps(value)
        else:
            s.add(SettingRow(key=scoped_key, value=json.dumps(value)))
        s.commit()


# --------------------------------------------------------------------------- #
# keyed blobs (package-search results) - same table, their own key space
# --------------------------------------------------------------------------- #
def get_blob(key: str) -> dict | None:
    with _s() as s:
        r = s.query(RunRow).filter_by(key=key).first()
        if not r:
            return None
        out = json.loads(r.payload)
        out["result_source"] = r.source
        return out


def put_blob(key: str, model_hash: str, payload: dict, source: str = "computed") -> dict:
    with _lock, _s() as s:
        row = s.query(RunRow).filter_by(key=key).first()
        blob = json.dumps(payload)
        if row:
            row.payload, row.source, row.model_hash, row.created_at = blob, source, model_hash, _now()
        else:
            s.add(RunRow(key=key, model_hash=model_hash, source=source, payload=blob,
                         created_at=_now()))
        s.commit()
    out = dict(payload)
    out["result_source"] = source
    return out
