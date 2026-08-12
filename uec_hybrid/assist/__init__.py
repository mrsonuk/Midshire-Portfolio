"""
AI assist: the two places AI genuinely earns its keep in this product.

* **Ask a what-if** (``nl``) - a plain-English question ("add 2 doctors",
  "10% more attendances") is parsed into a scenario, run through the real
  engine (paired Monte-Carlo vs baseline), and answered in plain language.
  Every number in the answer comes from the engine - never from a language
  model. A rule-based parser keeps it fully offline; if the ``anthropic``
  package is installed and ``ANTHROPIC_API_KEY`` is set,  upgrades the
  parsing (free-form phrasing) and the narration. No key -> offline mode,
  same numbers.

* **Auto-calibration** (``autocal``) - an automated search that tunes the
  model's service-time scale until the modelled 4-hour performance matches
  the trust's real observed figure. One click closes the "inputs are real,
  internals need tuning" gap, honestly and reproducibly.
"""
from .nl import parse_question, run_what_if
from .autocal import auto_calibrate

__all__ = ["parse_question", "run_what_if", "auto_calibrate"]
