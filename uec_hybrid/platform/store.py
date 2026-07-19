"""
Persistence for the platform - the saved department (versioned), ECDS
calibrations, and a run cache keyed by configuration hash.

Everything a surface shows is traceable: a cached result is only reused when
the *exact* configuration (department, calibration, parameters and engine
version) hashes the same, so the control tower, planner and analyst can never
silently show numbers from different set-ups.

SQLite by default (zero-setup single file next to the repo); set DATABASE_URL
(or UEC_DATABASE_URL) for Postgres in a shared deployment.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

ENGINE_VERSION = "0.4.0"

_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "uec_platform.sqlite3"

Base = declarative_base()
_engine = None
_Session = None


class DepartmentRow(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    key = Column(String(64), index=True, nullable=False, default="default")
    version = Column(Integer, nullable=False, default=1)
    config = Column(Text, nullable=False)          # Department.to_dict() JSON
    updated_at = Column(DateTime, nullable=False)


class CalibrationRow(Base):
    __tablename__ = "calibrations"
    id = Column(Integer, primary_key=True)
    scope = Column(String(128), unique=True, index=True, nullable=False)
    patch = Column(Text, nullable=False)           # derived-parameter patch JSON
    summary = Column(Text, nullable=False)         # list[str] JSON
    created_at = Column(DateTime, nullable=False)


class RunRow(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True)
    config_hash = Column(String(64), unique=True, index=True, nullable=False)
    kind = Column(String(32), nullable=False)
    engine_version = Column(String(32), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False)


class SettingRow(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class AuditRow(Base):
    """Append-only trail of every configuration change (settings, department,
    calibration) - who-did-what governance for a shared deployment."""
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True)
    at = Column(DateTime, nullable=False, index=True)
    kind = Column(String(32), nullable=False)      # setting | department | calibration
    key = Column(String(128), nullable=False)
    detail = Column(Text, nullable=False)          # JSON summary of the change


class ActionRow(Base):
    """Append-only operational decision log: what the team decided and why,
    stamped with the model state it was decided against. Never edited."""
    __tablename__ = "actions"
    id = Column(Integer, primary_key=True)
    at = Column(DateTime, nullable=False, index=True)
    author = Column(String(128), nullable=False, default="")
    note = Column(Text, nullable=False)
    context = Column(Text, nullable=False)         # JSON snapshot (dept version, source)


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def to_jsonable(obj):
    """Round-trip through JSON so cached and fresh responses are identical."""
    return json.loads(json.dumps(obj, default=_json_default))


def init_db(url: str | None = None, force: bool = False):
    """Create tables (idempotent). Call with a sqlite URL in tests to isolate."""
    global _engine, _Session
    if _engine is not None and not force:
        return _engine
    url = (url or os.environ.get("UEC_DATABASE_URL")
           or os.environ.get("DATABASE_URL") or f"sqlite:///{_DEFAULT_PATH}")
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    _engine = create_engine(url, **kwargs)
    _Session = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)
    return _engine


def _session():
    if _Session is None:
        init_db()
    return _Session()


def _now():
    return datetime.now(timezone.utc)


# --- department ------------------------------------------------------------ #
def load_department(key: str = "default") -> dict | None:
    with _session() as s:
        row = (s.query(DepartmentRow).filter_by(key=key)
               .order_by(DepartmentRow.version.desc()).first())
        return json.loads(row.config) if row else None


def save_department(config: dict, key: str = "default") -> int:
    """Append a new version (departments are never edited in place)."""
    with _session() as s:
        last = (s.query(DepartmentRow).filter_by(key=key)
                .order_by(DepartmentRow.version.desc()).first())
        version = (last.version + 1) if last else 1
        s.add(DepartmentRow(key=key, version=version, updated_at=_now(),
                            config=json.dumps(config, default=_json_default)))
        s.add(AuditRow(at=_now(), kind="department", key=key,
                       detail=json.dumps({"version": version,
                                          "name": config.get("name")})))
        s.commit()
        return version


def department_meta(key: str = "default") -> dict | None:
    """Version and last-updated timestamp of the saved department."""
    with _session() as s:
        row = (s.query(DepartmentRow).filter_by(key=key)
               .order_by(DepartmentRow.version.desc()).first())
        if not row:
            return None
        return {"version": row.version, "updated_at": row.updated_at.isoformat()}


# --- calibration ------------------------------------------------------------ #
def get_calibration(scope: str) -> dict | None:
    with _session() as s:
        row = s.query(CalibrationRow).filter_by(scope=scope).first()
        if not row:
            return None
        return {"patch": json.loads(row.patch), "summary": json.loads(row.summary),
                "created_at": row.created_at.isoformat()}


def save_calibration(scope: str, patch: dict, summary: list):
    with _session() as s:
        s.query(CalibrationRow).filter_by(scope=scope).delete()
        s.add(CalibrationRow(scope=scope, created_at=_now(),
                             patch=json.dumps(patch, default=_json_default),
                             summary=json.dumps(summary, default=_json_default)))
        s.commit()


def clear_calibration(scope: str):
    with _session() as s:
        s.query(CalibrationRow).filter_by(scope=scope).delete()
        s.commit()


# --- settings (e.g. the trust-editable cost book) ---------------------------- #
def get_setting(key: str) -> dict | None:
    with _session() as s:
        row = s.query(SettingRow).filter_by(key=key).first()
        return json.loads(row.value) if row else None


def save_setting(key: str, value):
    with _session() as s:
        s.query(SettingRow).filter_by(key=key).delete()
        s.add(SettingRow(key=key, updated_at=_now(),
                         value=json.dumps(value, default=_json_default)))
        detail = json.dumps(value, default=_json_default)
        s.add(AuditRow(at=_now(), kind="setting", key=key,
                       detail=detail[:2000]))     # summary, not a full dump
        s.commit()


def setting_meta(key: str) -> dict | None:
    """When a setting was last changed (None if never set)."""
    with _session() as s:
        row = s.query(SettingRow).filter_by(key=key).first()
        return {"updated_at": row.updated_at.isoformat()} if row else None


# --- governance: audit trail + operational decision log ----------------------- #
def audit_trail(limit: int = 100) -> list[dict]:
    """Most-recent-first log of configuration changes (append-only)."""
    with _session() as s:
        rows = s.query(AuditRow).order_by(AuditRow.at.desc(), AuditRow.id.desc()).limit(limit)
        return [{"at": r.at.isoformat(), "kind": r.kind, "key": r.key,
                 "detail": json.loads(r.detail) if r.detail.startswith(("{", "[")) else r.detail}
                for r in rows]


def log_action(note: str, author: str = "", context: dict | None = None) -> dict:
    """Record an operational decision (append-only; there is no delete)."""
    with _session() as s:
        row = ActionRow(at=_now(), author=(author or "")[:128], note=note,
                        context=json.dumps(context or {}, default=_json_default))
        s.add(row)
        s.commit()
        return {"id": row.id, "at": row.at.isoformat(), "author": row.author,
                "note": row.note, "context": context or {}}


def list_actions(limit: int = 100) -> list[dict]:
    """Most-recent-first operational decision log."""
    with _session() as s:
        rows = s.query(ActionRow).order_by(ActionRow.at.desc(), ActionRow.id.desc()).limit(limit)
        return [{"id": r.id, "at": r.at.isoformat(), "author": r.author,
                 "note": r.note, "context": json.loads(r.context)} for r in rows]


# --- run cache --------------------------------------------------------------- #
def config_hash(kind: str, key_obj) -> str:
    blob = json.dumps({"kind": kind, "engine": ENGINE_VERSION, "key": key_obj},
                      sort_keys=True, default=_json_default)
    return hashlib.sha256(blob.encode()).hexdigest()


def cached(kind: str, key_obj) -> dict | None:
    with _session() as s:
        row = s.query(RunRow).filter_by(config_hash=config_hash(kind, key_obj)).first()
        return json.loads(row.payload) if row else None


def remember(kind: str, key_obj, payload) -> dict:
    """Store a result under its configuration hash and return the JSON-clean copy."""
    clean = to_jsonable(payload)
    h = config_hash(kind, key_obj)
    with _session() as s:
        row = s.query(RunRow).filter_by(config_hash=h).first()
        if row:
            row.payload = json.dumps(clean)
            row.engine_version = ENGINE_VERSION
            row.created_at = _now()
        else:
            s.add(RunRow(config_hash=h, kind=kind, engine_version=ENGINE_VERSION,
                         payload=json.dumps(clean), created_at=_now()))
        s.commit()
    return clean


def cached_or_compute(kind: str, key_obj, compute) -> dict:
    hit = cached(kind, key_obj)
    if hit is not None:
        return hit
    return remember(kind, key_obj, compute())
