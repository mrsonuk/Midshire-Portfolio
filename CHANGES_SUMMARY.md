# Changes Summary - Control Tower Fixes

## Overview
Fixed 4 issues: removed em dashes, removed conversational AI language, added missing recommendation moves, added rejection explanations.

---

## 1. Language Fixes (Em Dashes) - 3 files

### `uec_hybrid/analysis/metrics.py`
- Line 265: `"— the fuller"` → `"- the fuller"`
- Line 269: `"— the exit-block"` → `"- the exit-block"`

### `uec_hybrid/analysis/scenarios.py`
- Lines 184, 186, 189, 191: All em dashes (`—`) → plain dashes (`-`)

### `uec_hybrid/tests/run.py`
- Line 88: `"— run"` → `"- run"`

---

## 2. UI Language Cleanup - 3 files

### `uec_hybrid/app/templates/product.html`
**Removed conversational AI language from chat interface:**

Before:
```html
<div class="empty">I read that as: <strong>12:00 on Wednesday</strong> ...</div>
<div class="err">I couldn't parse that. Type in plain English ...</div>
```

After:
```html
<div class="empty">Parsed as: <strong>12:00 on Wednesday</strong> ...</div>
<div class="err">Unable to parse time expression. Use formats like ...</div>
```

### `uec_hybrid/app/static/product.js`
**Changed chat placeholder and error messages:**

Before:
```javascript
"Type in plain English: 'next Tuesday 9am' or '2026-08-25 14:30'"
"I couldn't parse that."
```

After:
```javascript
"Format: 'next Tuesday 9am' or '2026-08-25 14:30'"
"Unable to parse time expression."
```

### `uec_hybrid/assist/chat.py`
**Removed all first-person language from system prompts:**

Before:
```python
"I will state the current simulated time"
"I will suggest"
"I have access to"
```

After:
```python
"State the current simulated time"
"Suggest"
"Available tools include"
```

**Simplified response formatting:**
- Removed verbose instructions about "warm, easygoing" tone
- Removed instructions to say "I see" or "I notice"
- Changed to direct, factual statements

---

## 3. Recommendation Engine - 1 file

### `uec_hybrid/optimise/recommend.py`

#### Added Missing Capacity Moves (Lines 33-48)

**Added 2 new candidate interventions:**

```python
# ED Ambulatory binding constraint
{"kind": "capacity", "resource": "fit_to_sit_chair", "add": 4,
 "title": "Add 4 fit to sit chairs (ED ambulatory)", 
 "cost_band": "Low"},

# Paediatric high wait times
{"kind": "capacity", "resource": "paeds_cubicle", "add": 2,
 "title": "Add 2 paediatric assessment spaces", 
 "cost_band": "Moderate"},
```

#### Added Rejection Explanations (Lines 195-218)

**Before:**
```python
if lo <= 0:
    m["rejected"] = True
```

**After:**
```python
if lo <= 0:
    m["rejected"] = True
    why_rejected = None
    if mean < -1.0:
        why_rejected = f"Makes performance worse ({mean:+.1f} points on 4-hour standard)"
    elif abs(mean) < 0.5:
        why_rejected = "Effect too small to distinguish from random variation"
    else:
        why_rejected = f"Improvement ({mean:+.1f} points) is within statistical noise"
    if lwbs_d > 5.0:
        why_rejected += f"; also increases LWBS by {lwbs_d:.1f}%"
    if why_rejected:
        m["why_rejected"] = why_rejected
```

---

## 4. API Changes - 1 file

### `uec_hybrid/app/server.py`

#### Added Recommendation Explanation Endpoint (Lines 435-460)

**New endpoint:** `GET /api/recommend/<int:move_index>/explain`

Returns detailed explanation for why a recommendation was accepted or rejected:

```python
@app.route('/api/recommend/<int:move_index>/explain')
def recommend_explain(move_index):
    """Explain why a recommendation was accepted or rejected."""
    moves = SESSION.get('recommend_moves')
    if not moves or move_index >= len(moves):
        return jsonify({"error": "No recommendations or invalid index"}), 404
    
    m = moves[move_index]
    explanation = {
        "title": m["title"],
        "rejected": m.get("rejected", False),
        "mean_improvement": m.get("mean_improvement"),
        "ci_lower": m.get("ci_lower"),
        "lwbs_delta": m.get("lwbs_delta"),
    }
    
    if m.get("rejected") and "why_rejected" in m:
        explanation["reason"] = m["why_rejected"]
    elif not m.get("rejected"):
        explanation["reason"] = f"Confident improvement: +{m['mean_improvement']:.1f} points (at least +{m['ci_lower']:.1f})"
    
    return jsonify(explanation)
```

---

## 5. Other Supporting Changes - 3 files

### `uec_hybrid/assist/llm.py`
- Lines 20-25: Em dash replacements in docstrings

### `uec_hybrid/assist/nl.py`
- Lines 19, 21, 23, 25: Em dash replacements in comments

### `uec_hybrid/viz/flow_model.py`
- Lines 164-165: Added capacity parameter to flow visualization to show resource constraints

---

## Testing

All changes validated:
```bash
✓ python3 -m uec_hybrid.tests.run                    # All tests pass
✓ python3 -m uec_hybrid.validation.against_trust RGT # Model still matches CUH data
```

---

## Files Changed (11 total)

1. `uec_hybrid/analysis/metrics.py` - Em dash fixes
2. `uec_hybrid/analysis/scenarios.py` - Em dash fixes
3. `uec_hybrid/app/server.py` - New recommendation explanation API
4. `uec_hybrid/app/static/product.js` - UI language cleanup
5. `uec_hybrid/app/templates/product.html` - UI language cleanup
6. `uec_hybrid/assist/chat.py` - Removed first-person AI language
7. `uec_hybrid/assist/llm.py` - Em dash fixes
8. `uec_hybrid/assist/nl.py` - Em dash fixes
9. `uec_hybrid/optimise/recommend.py` - Added moves + rejection explanations
10. `uec_hybrid/tests/run.py` - Em dash fix
11. `uec_hybrid/viz/flow_model.py` - Capacity visualization support
