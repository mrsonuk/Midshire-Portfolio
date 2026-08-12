"""
Offline retrieval (RAG) for the assistant.

The chatbot's intent router answers the live operational questions from engine
numbers. This module covers everything else - "how do I import my data?",
"what's the methodology?", "where do I change costs?" - by retrieving the most
relevant passage from a small knowledge base:

- the product glossary (chat.GLOSSARY),
- curated cards describing every part of the product (below), and
- the project docs (README + handover), chunked by heading.

The index is IDF-weighted keyword overlap - pure Python, no dependencies, no
network - built once per process and rebuilt if the doc files change. It is
used two ways: fully offline, the top passage IS the answer; with Claude
configured, the top passages are added to the model's context so free-form
answers are grounded in the docs (classic RAG). The numbers rule is unchanged
either way: figures only ever come from the engine, never from retrieved text.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_DOC_FILES = [_ROOT / "README.md", _ROOT / "docs" / "HANDOVER.md"]
_CHUNK_CHARS = 700                       # cap per doc chunk (keeps replies readable)

# what the product does and where - curated, kept in step with the UI
PRODUCT_CARDS = [
    ("Start from your trust",
     "On “Set up my ED” pick your trust from the registry and the whole model is "
     "pre-filled from its published NHS figures (attendances, beds, performance), "
     "with the source of every number shown. The registry lives in a CSV "
     "(uec_hybrid/data/nhs_trust_snapshot.csv) so new trusts are a data edit, not code."),
    ("Import your data from Excel",
     "On “Set up my ED”, download the Excel template, fill in the tabs (Overview, "
     "Areas, Rota, Arrivals, AcuityMix, Costs, ServiceTimes) and import it back - "
     "the entire department, rota, demand profile, costs and service times update "
     "in one go. CSV works too. Re-import any time to update."),
    ("How calibration works",
     "Calibration replaces the model's synthetic assumptions with your recorded "
     "activity. The set-up workbook's Arrivals and AcuityMix tabs calibrate the "
     "arrival profile and case mix; the published-aggregates file does the same "
     "from open NHS data; and auto-calibration tunes the service-time assumption "
     "until the modelled 4-hour position matches the figure you observed. Every "
     "calibrated value shows its source on the provenance banner."),
    ("Auto-calibrate to your 4-hour position",
     "Give the model the 4-hour performance you actually "
     "observe and auto-calibrate tunes the model's service-time scale until the "
     "modelled figure matches - so what-ifs start from your reality."),
    ("Control tower",
     "The home page: a live map of patient flow through your department. Each block "
     "is a pathway stage - click one to drill into its queue and timings; the tiles "
     "above show the standards from simulated weeks; the slider replays the day "
     "hour by hour."),
    ("Set up my ED",
     "Where the department is configured without code: attendances per day, "
     "inpatient beds, community capacity, which areas you run (SDEC, RAT, UTC, "
     "frailty, paediatrics, mental health, CDU) and their opening hours - plus the "
     "trust picker and Excel import."),
    ("Methodology",
     "The methodology - how the model works: a patient-level discrete-event "
     "simulation (every patient walks the pathway, queues and all) is coupled "
     "hourly to a whole-hospital system-dynamics model (beds, discharges, "
     "community capacity), so ward pressure feeds back into ED exit-block. "
     "Monte-Carlo replication turns one week into a realistic spread."),
    ("The Model ED blueprint",
     "The NHS “Model Emergency Department” describes the areas and standards a "
     "well-set-up ED runs. This build focuses on the flow view; a fuller edition adds a "
     "costed business case on each missing element."),
    ("Ask a what-if",
     "Type a change in plain English and the engine simulates it against your "
     "department: “add 2 doctors”, “add 3 nurses at 1pm”, “remove a doctor "
     "overnight”, “10% more attendances”, “40 more ward beds”, “divert 20% of "
     "minors to the UTC”, “a winter surge”. Time windows like “from 8pm to 8am” "
     "apply the change to just those hours."),
    ("Nurses and cubicles",
     "Cubicles only open when there are nurses to cover them - a 1:4 "
     "nurse-to-cubicle ratio by default - so cutting the nurse rota closes "
     "cubicles and adding nurses opens them, where physical spaces allow."),
    ("Numbers you can trust",
     "Every figure on every screen and in every chat answer comes from the "
     "product's own simulation of your department - the AI layer only translates "
     "questions and narrates computed results, and works fully offline. With a "
     "Claude key configured it phrases things better; it still never invents a number."),
    ("Editable costs, targets and service times",
     "Role hourly rates, scorecard targets (e.g. what counts as green on the "
     "4-hour standard) and clinical service times are all editable - via the Excel "
     "workbook's Costs and ServiceTimes tabs, the cost book, or the settings APIs - "
     "no code changes."),
    ("The chatbot",
     "The floating “Ask your ED” button answers from your model any time: where "
     "demand is, where to deploy staff, the pinch point, performance against the "
     "standards, what's missing from the Model ED, NHS jargon, and what-ifs, which "
     "run on the real engine."),
]

_STOPWORDS = frozenset(
    "the a an and or of to in for on with is are be as at by it its this that "
    "you your from we our i me my how what which do does can could should would "
    "will not no any all one more when where why who has have had was were been "
    "if then than so about into over under again there here they them he she".split())


def _stem(t: str) -> str:
    """Light plural/verb stemming so 'costs' matches 'cost', 'nurses' 'nurse'."""
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("es") and not t.endswith("ses"):
        return t[:-2] if t.endswith(("ches", "shes", "xes")) else t[:-1]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9']+", (text or "").lower())
            if len(t) > 1 and t not in _STOPWORDS]


def _doc_chunks():
    """README/handover split into (source, title, text) chunks by heading,
    code fences stripped, long sections capped."""
    for path in _DOC_FILES:
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        title, buf, fenced = path.stem, [], False
        def flush():
            text = re.sub(r"\s+", " ", " ".join(buf)).strip(" -|")
            if len(text) >= 60:
                yield (path.name, title, text[:_CHUNK_CHARS])
        for line in body.splitlines():
            if line.strip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            if line.startswith("#"):
                yield from flush()
                title, buf = line.lstrip("# ").strip(), []
            else:
                buf.append(line)
        yield from flush()


_INDEX = None
_SIG = None


def _signature():
    return tuple((str(p), p.stat().st_mtime if p.exists() else None) for p in _DOC_FILES)


def _index():
    """Build (or reuse) the keyword index over all knowledge chunks."""
    global _INDEX, _SIG
    sig = _signature()
    if _INDEX is not None and sig == _SIG:
        return _INDEX
    from .chat import GLOSSARY             # lazy: chat imports this module
    chunks = []
    for term, meaning in GLOSSARY.items():
        chunks.append({"source": "glossary", "title": term, "text": f"{term}: {meaning}"})
    for title, text in PRODUCT_CARDS:
        chunks.append({"source": "product guide", "title": title, "text": text})
    for source, title, text in _doc_chunks():
        chunks.append({"source": source, "title": title, "text": text})
    df: dict[str, int] = {}
    for ch in chunks:
        ch["toks"] = set(_tokens(ch["text"]))
        ch["title_toks"] = set(_tokens(ch["title"]))
        for t in ch["toks"] | ch["title_toks"]:
            df[t] = df.get(t, 0) + 1
    n = len(chunks)
    idf = {t: math.log((n + 1) / (d + 0.5)) for t, d in df.items()}
    _INDEX, _SIG = {"chunks": chunks, "idf": idf}, sig
    return _INDEX


def search(query: str, k: int = 3) -> list[dict]:
    """Top-k knowledge chunks for a query, scored by IDF-weighted keyword
    overlap (title hits count double). Empty list when nothing overlaps."""
    idx = _index()
    qt = set(_tokens(query))
    if not qt:
        return []
    hits = []
    for ch in idx["chunks"]:
        matched = qt & ch["toks"]
        title_hits = qt & ch["title_toks"]
        if not matched and not title_hits:
            continue
        score = (sum(idx["idf"].get(t, 0.0) for t in matched)
                 + sum(idx["idf"].get(t, 0.0) for t in title_hits))
        if ch["source"] == "product guide":
            score *= 1.25                  # curated cards outrank incidental doc matches
        hits.append({"source": ch["source"], "title": ch["title"], "text": ch["text"],
                     "score": round(score, 2), "matched": len(matched | title_hits),
                     "title_hit": bool(title_hits)})
    hits.sort(key=lambda h: -h["score"])
    return hits[:k]


def best(query: str, min_matched: int = 2, min_score: float = 3.5) -> dict | None:
    """The single best chunk, only if it's a confident match - used as the
    offline answer of last resort (never returns a weak guess). A single very
    strong title hit ("methodology") counts as confident too."""
    hits = search(query, k=1)
    if hits and hits[0]["score"] >= min_score and (
            hits[0]["matched"] >= min_matched or hits[0]["title_hit"]):
        return hits[0]
    return None
