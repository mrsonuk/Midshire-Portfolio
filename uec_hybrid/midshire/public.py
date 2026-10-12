"""Public-demo visitor isolation and lightweight abuse controls.

This is for a ONE-INSTANCE demonstration. AWS WAF is still required for
source-IP rate limiting: anonymous visitors can clear cookies.
"""
from __future__ import annotations

from collections import deque
import hmac
import os
import secrets
import threading
import time

from flask import g, has_request_context, jsonify, request, session

_lock = threading.RLock()
_events = {}
_MAX_BUCKETS = 10000


def enabled() -> bool:
    return os.environ.get("MIDSHIRE_PUBLIC_MODE", "").lower() in ("1", "true", "yes")


def current_owner() -> str | None:
    """Return the authenticated-by-signed-cookie anonymous visitor ID.

    No value outside a public HTTP request: precompute, CLI and existing
    local development remain able to manage shared demonstration fixtures.
    """
    if not has_request_context():
        return None
    return getattr(g, "midshire_owner", None)


def csrf_token() -> str:
    return session.get("_midshire_csrf", "")


def _allow(bucket: str, visitor: str, window: float, maximum: int) -> bool:
    now = time.monotonic()
    key = (bucket, visitor)
    with _lock:
        q = _events.setdefault(key, deque())
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= maximum:
            return False
        q.append(now)
        if len(_events) > _MAX_BUCKETS:
            # Bounded memory even when visitors repeatedly clear cookies.
            for old in list(_events)[:len(_events) - _MAX_BUCKETS]:
                _events.pop(old, None)
        return True


def guard_request():
    """Call as Flask before_request only when MIDSHIRE_PUBLIC_MODE is enabled."""
    if request.path == "/healthz":
        return None  # load-balancer probes never create visitor sessions
    visitor = session.get("_midshire_visitor")
    if not isinstance(visitor, str) or len(visitor) != 32 or any(c not in "0123456789abcdef" for c in visitor):
        visitor = secrets.token_hex(16)
        session["_midshire_visitor"] = visitor
        session["_midshire_csrf"] = secrets.token_hex(24)
    elif not session.get("_midshire_csrf"):
        session["_midshire_csrf"] = secrets.token_hex(24)
    session.permanent = True
    g.midshire_owner = visitor

    if not _allow("all", visitor, 60, 240):
        return jsonify(error="Too many requests. Please try again shortly.", details=[]), 429, {"Retry-After": "60"}

    # All state-changing API methods require a secret from the SAME page.
    # Cross-origin forms and scripts cannot read the token in the HTML.
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/m/"):
        candidate = request.headers.get("X-Midshire-CSRF", "")
        if not hmac.compare_digest(candidate, session["_midshire_csrf"]):
            return jsonify(error="Your session needs refreshing. Reload the page and try again.", details=[]), 403

    limits = {
        ("/api/m/run", "POST"): ("run", 3600, 12),
        ("/api/m/search", "POST"): ("search", 3600, 6),
        ("/api/m/ask", "POST"): ("assistant", 3600, 40),
    }
    rule = limits.get((request.path, request.method))
    if rule and not _allow(rule[0], visitor, rule[1], rule[2]):
        return jsonify(error="Demo usage limit reached. Please return later.", details=[]), 429, {"Retry-After": "3600"}
    return None
