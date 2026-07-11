"""
Fuzzy Matching Engine — Priority 4

Takes a normalized BOQ line (output from boq_normalizer) and finds the best
catalogue match with a confidence score.

Matching strategy: weighted feature similarity
  - category match: 30% weight
  - sub_category match: 25% weight
  - diameter match: 20% weight (exact or close)
  - schedule match: 10% weight
  - terrain match: 10% weight
  - unit match: 5% weight

Returns top N matches sorted by score with thresholds:
  >= 0.85 → HIGH match (auto-accept)
  >= 0.60 → MEDIUM match (review recommended)
  >= 0.40 → LOW match (likely needs manual correction)
  <  0.40 → unmatched
"""
from typing import List, Optional


def _dia_proximity(target, candidate):
    """0–1 score. 1.0 = exact match, 0.0 = unrelated."""
    if target is None or candidate is None:
        return 0.0
    try:
        t = float(str(target).strip().rstrip('"').rstrip('″'))
        c = float(str(candidate).strip().rstrip('"').rstrip('″'))
    except (ValueError, TypeError):
        return 0.0
    if t == c:
        return 1.0
    # Within 1 inch → 0.7, within 2 inches → 0.4, beyond → 0.0
    diff = abs(t - c)
    if diff <= 1: return 0.7
    if diff <= 2: return 0.4
    return 0.0


def _terrain_match(target, candidate):
    if not target or not candidate:
        return 0.5  # neutral when missing
    if target == candidate:
        return 1.0
    # Land+Swamp catalogue items match either
    if 'Land+Swamp' in (str(target), str(candidate)):
        return 1.0
    return 0.0


def _schedule_match(target, candidate):
    if not target or not candidate:
        return 0.5
    if target == candidate:
        return 1.0
    # Same family (e.g. Sch 40 vs Sch 80) → partial credit
    if 'Sch' in str(target) and 'Sch' in str(candidate):
        return 0.3
    return 0.0


def _unit_match(target, candidate):
    if not target or not candidate:
        return 0.5
    t = str(target).strip().lower()
    c = str(candidate).strip().lower()
    if t == c: return 1.0
    # Common equivalents
    equiv_groups = [
        {'m', 'meter', 'metre', 'lm', 'lineal m'},
        {'each', 'ea', 'no', 'nr', 'pc', 'item'},
        {'joint', 'per joint', 'jt'},
        {'per weld', 'weld', 'wld'},
        {'m2', 'sqm'},
        {'m3', 'cum'},
        {'ls', 'lump sum'},
    ]
    for g in equiv_groups:
        if t in g and c in g:
            return 0.9
    return 0.0


def match_line_to_catalogue(
    normalized_line: dict,
    catalogue_items: List[dict],
    top_n: int = 5,
):
    """Score every catalogue item against the normalized line, return top matches.

    Args:
        normalized_line: output from normalize_boq_line()
        catalogue_items: list of catalogue entries from line_items_catalogue.json
        top_n: how many candidates to return

    Returns:
        list of dicts:
            { 'catalogue_id': 'C027', 'item': '...', 'score': 0.91,
              'verdict': 'HIGH'|'MEDIUM'|'LOW'|'UNMATCHED', 'reasons': [...], 'entry': {...} }
    """
    if not normalized_line:
        return []

    cat   = normalized_line.get('category_hint')
    sub   = normalized_line.get('sub_category_hint')
    spec  = normalized_line.get('spec', {})
    unit  = normalized_line.get('unit_extracted')

    scored = []
    for entry in catalogue_items:
        e_spec = entry.get('spec', {})

        # Hard filter: if both have categories, they must match exactly for the
        # match to be meaningful. Cross-category fuzz is too risky.
        if cat and entry.get('category') and cat != entry['category']:
            continue

        # ─── HARD SUB-CATEGORY GATE (v5 fix) ──────────────────────────────
        # The v4.1 demo-killer: flanges/gaskets fuzzy-matched HDD crossings
        # because both sit in 'Materials' and the diameter/unit features
        # accumulated enough score to pass. A different sub_category is a
        # categorically different line item — there is no such thing as a
        # "pity match" across sub-categories. If the normalized line declares
        # a sub_category_hint and the candidate's sub_category is genuinely
        # different (not an exact match and not a containment near-match),
        # drop the candidate entirely. No fuzzy score can rescue it.
        e_sub = entry.get('sub_category')
        if sub and e_sub:
            sl, el = sub.strip().lower(), e_sub.strip().lower()
            if sl != el and sl not in el and el not in sl:
                continue

        # Compute weighted score
        s_cat   = 1.0 if cat and cat == entry.get('category') else 0.0
        s_sub   = 1.0 if sub and sub == entry.get('sub_category') else (0.5 if sub and sub.lower() in (entry.get('sub_category') or '').lower() else 0.0)
        s_dia   = _dia_proximity(spec.get('dia'), e_spec.get('dia'))
        s_sched = _schedule_match(spec.get('sched'), e_spec.get('sched'))
        s_terr  = _terrain_match(spec.get('terrain'), e_spec.get('terrain'))
        s_unit  = _unit_match(unit, entry.get('unit'))

        score = (
            0.30 * s_cat +
            0.25 * s_sub +
            0.20 * s_dia +
            0.10 * s_sched +
            0.10 * s_terr +
            0.05 * s_unit
        )

        reasons = []
        if s_cat == 1.0:   reasons.append(f"category={entry['category']}")
        if s_sub == 1.0:   reasons.append(f"sub-cat={entry['sub_category']}")
        if s_dia >= 0.9:   reasons.append(f"dia exact {e_spec.get('dia')}")
        elif s_dia >= 0.4: reasons.append(f"dia close ({e_spec.get('dia')} vs {spec.get('dia')})")
        if s_sched == 1.0: reasons.append(f"sched={e_spec.get('sched')}")
        if s_terr == 1.0:  reasons.append(f"terrain={e_spec.get('terrain')}")
        if s_unit >= 0.9:  reasons.append(f"unit={entry.get('unit')}")

        scored.append({
            'catalogue_id': entry['id'],
            'item': entry['item'],
            'score': round(score, 3),
            'reasons': reasons,
            'entry': entry,
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    top = scored[:top_n]
    for m in top:
        if m['score'] >= 0.85:    m['verdict'] = 'HIGH'
        elif m['score'] >= 0.60:  m['verdict'] = 'MEDIUM'
        elif m['score'] >= 0.40:  m['verdict'] = 'LOW'
        else:                     m['verdict'] = 'UNMATCHED'
    return top


def best_match(normalized_line: dict, catalogue_items: List[dict]) -> Optional[dict]:
    """Convenience: return only the top match, or None if no candidate scored above 0.40."""
    matches = match_line_to_catalogue(normalized_line, catalogue_items, top_n=1)
    if not matches or matches[0]['score'] < 0.40:
        return None
    return matches[0]
