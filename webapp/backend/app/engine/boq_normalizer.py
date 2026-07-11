"""
BOQ Normalization Engine — Priority 2

Takes free-text vendor BOQ line items and extracts structured attributes:
diameter, schedule, grade, unit, terrain, category hints.

Example:
  "6 inch CS Pipe Sch40 Swamp Lay & Weld - 5000m @ $120/m"
  →
  {
    "raw_description": "6 inch CS Pipe Sch40 Swamp Lay & Weld - 5000m @ $120/m",
    "normalized_description": "Carbon Steel Pipe — Lay & Weld",
    "category_hint": "Construction",
    "sub_category_hint": "Lay & Weld",
    "discipline": "Pipeline",
    "spec": {"dia": 6, "sched": "Sch 40", "terrain": "Swamp", "grade": "Carbon Steel"},
    "unit_extracted": "m",
    "qty_extracted": 5000,
    "rate_extracted": 120.0,
    "confidence": 0.85,
    "tokens_matched": ["6 inch", "CS", "Sch40", "Swamp", "Lay & Weld", "m"],
    "tokens_unmatched": [],
  }
"""
import re
from typing import Optional


# ─── Token dictionaries ─────────────────────────────────────────────────
DIAMETER_PATTERNS = [
    re.compile(r'(\d+(?:\.\d+)?)\s*(?:inch|in|"|″|\bnb|nominal)', re.IGNORECASE),
    re.compile(r'\bDN\s*(\d+)', re.IGNORECASE),  # DN150 → 6"
    re.compile(r'(\d+(?:\.\d+)?)\s*(?=\s+(?:sch|schedule))', re.IGNORECASE),  # "6 Sch40"
]

DN_TO_INCH = {15: 0.5, 20: 0.75, 25: 1, 32: 1.25, 40: 1.5, 50: 2, 65: 2.5, 80: 3,
              100: 4, 125: 5, 150: 6, 200: 8, 250: 10, 300: 12, 350: 14, 400: 16,
              450: 18, 500: 20, 550: 22, 600: 24, 650: 26, 700: 28}

SCHEDULE_PATTERNS = [
    (re.compile(r'\bsch(?:edule)?\.?\s*(\d+|XXS|XS|STD)\b', re.IGNORECASE),
     lambda m: f'Sch {m.group(1).upper()}'),
    (re.compile(r'\b(STD|XS|XXS)\b'),
     lambda m: f'Sch {m.group(1)}'),
]

GRADE_PATTERNS = [
    (re.compile(r'\bAPI\s*5L\s*(X\d{2,3})\b', re.IGNORECASE), 'API 5L {0}'),
    (re.compile(r'\b(X\d{2,3})\b'),                            'API 5L {0}'),
    (re.compile(r'\bA53\s*Gr\.?\s*([AB])\b', re.IGNORECASE),   'A53 Gr.{0}'),
    (re.compile(r'\bA106\s*Gr\.?\s*([AB])\b', re.IGNORECASE),  'A106 Gr.{0}'),
    (re.compile(r'\bA105\b', re.IGNORECASE),                   'A105'),
    (re.compile(r'\b(CS|carbon steel)\b', re.IGNORECASE),      'Carbon Steel'),
    (re.compile(r'\b(SS|stainless steel)\b', re.IGNORECASE),   'Stainless Steel'),
    (re.compile(r'\bHDPE\b', re.IGNORECASE),                   'HDPE'),
    (re.compile(r'\bPE\s*100\b', re.IGNORECASE),               'PE 100'),
]

TERRAIN_PATTERNS = [
    (re.compile(r'\bswamp\b', re.IGNORECASE),   'Swamp'),
    (re.compile(r'\bmarsh\b', re.IGNORECASE),   'Swamp'),
    (re.compile(r'\bonshore\b', re.IGNORECASE), 'Land'),
    (re.compile(r'\bland\b', re.IGNORECASE),    'Land'),
    (re.compile(r'\bdry\s*land\b', re.IGNORECASE), 'Land'),
]

UNIT_PATTERNS = [
    (re.compile(r'\b(?:per\s+)?(?:linear\s+)?(?:m(?:eter|etre)?|m)\b\.?', re.IGNORECASE), 'm'),
    (re.compile(r'\bkm\b', re.IGNORECASE),                'km'),
    (re.compile(r'\b(?:per\s+)?joint\b\.?', re.IGNORECASE), 'joint'),
    (re.compile(r'\b(?:per\s+)?weld\b\.?', re.IGNORECASE),  'per weld'),
    (re.compile(r'\b(?:each|ea|no\.?|nr|item|pcs?)\b\.?', re.IGNORECASE), 'each'),
    (re.compile(r'\b(?:LS|lump\s*sum)\b', re.IGNORECASE),  'LS'),
    (re.compile(r'\b(?:per\s+)?day\b', re.IGNORECASE),     'day'),
    (re.compile(r'\bm2|sqm|sq\.?\s*m\b', re.IGNORECASE),   'm2'),
    (re.compile(r'\bm3|cum|cu\.?\s*m\b', re.IGNORECASE),   'm3'),
    (re.compile(r'\bton(?:ne)?s?\b', re.IGNORECASE),       'ton'),
]

# Category/sub-category keyword matchers → ordered by specificity
CATEGORY_RULES = [
    # Materials
    (re.compile(r'\bcarbon\s+steel\s+pipe|cs\s+pipe|API\s*5L|api5l\b', re.IGNORECASE),
     ('Materials', 'Carbon Steel Pipe')),
    # CS without explicit "pipe" — only matches when a diameter/schedule is also implied nearby
    (re.compile(r'\b(carbon\s+steel|CS)\b(?=.*(?:\d+\s*(?:inch|in|")|Sch|sch))', re.IGNORECASE),
     ('Materials', 'Carbon Steel Pipe')),
    (re.compile(r'\bHDPE\s+pipe|polyethylene', re.IGNORECASE),
     ('Materials', 'HDPE Pipe')),
    (re.compile(r'\b(flange|spade|spectacle\s+blind|blind)\b', re.IGNORECASE),
     ('Materials', 'Flanges')),
    (re.compile(r'\b(gasket|spiral\s+wound)\b', re.IGNORECASE),
     ('Materials', 'Gaskets')),
    (re.compile(r'\b(bolt|stud|nut)\b', re.IGNORECASE),
     ('Materials', 'Bolts & studs')),
    (re.compile(r'\b(valve|gate\s+valve|ball\s+valve|check\s+valve)\b', re.IGNORECASE),
     ('Materials', 'Valves')),
    (re.compile(r'\b(reducer|concentric|eccentric)\b', re.IGNORECASE),
     ('Materials', 'Reducers')),
    (re.compile(r'\b(elbow|bend\s+90|bend\s+45)\b', re.IGNORECASE),
     ('Materials', 'Elbows')),
    (re.compile(r'\b(tee|equal\s+tee|reducing\s+tee)\b', re.IGNORECASE),
     ('Materials', 'Tees')),
    (re.compile(r'\b(weldolet|threadolet|sockolet|olet)\b', re.IGNORECASE),
     ('Materials', 'Olets')),
    (re.compile(r'\b(split\s+sleeve|clamp|repair\s+clamp)\b', re.IGNORECASE),
     ('Materials', 'Split sleeves (clamps)')),
    (re.compile(r'\b(pipe\s+coating|external\s+coating|3lpe|fbe|painting)\b', re.IGNORECASE),
     ('Materials', 'Pipe coating & painting')),
    (re.compile(r'\b(HDD|horizontal\s+directional\s+drill|creek\s+crossing|canal\s+crossing)\b', re.IGNORECASE),
     ('Materials', 'HDD creek/canal crossings')),
    (re.compile(r'\bline\s+crossing\b', re.IGNORECASE),
     ('Materials', 'Line crossings')),
    # Construction
    (re.compile(r'\blay\s*&\s*weld|lay\s+and\s+weld\b', re.IGNORECASE),
     ('Construction', 'Lay & Weld')),
    (re.compile(r'\b(field\s+joint\s+coating|fjc|joint\s+coating|heat\s+shrink|shrink\s+sleeve)\b', re.IGNORECASE),
     ('Construction', 'Field joint coating')),
    (re.compile(r'\b(welding|weld(?!ing\s+machine))\b', re.IGNORECASE),
     ('Construction', 'Welding')),
    (re.compile(r'\b(tie.?in|hook.?up|tie\s+ins)\b', re.IGNORECASE),
     ('Construction', 'Tie-ins')),
    (re.compile(r'\bpost.?weld\s+heat\b', re.IGNORECASE),
     ('Construction', 'Post-weld heat treatment')),
    (re.compile(r'\bpipe\s+support\b', re.IGNORECASE),
     ('Construction', 'Pipe supports')),
    # NDT & Integrity
    (re.compile(r'\bradiograph(?:y|ic)|x.?ray|RT\b', re.IGNORECASE),
     ('NDT & Integrity', 'Radiography')),
    (re.compile(r'\b(dye\s+penetrant|DPT|liquid\s+penetrant|PT)\b', re.IGNORECASE),
     ('NDT & Integrity', 'Dye penetrant test')),
    (re.compile(r'\b(magnetic\s+particle|MPI|MT)\b', re.IGNORECASE),
     ('NDT & Integrity', 'Magnetic particle inspection')),
    (re.compile(r'\b(ultrasonic|UT\b|automated\s+ultrasonic)\b', re.IGNORECASE),
     ('NDT & Integrity', 'Ultrasonic testing')),
    (re.compile(r'\b(holiday\s+test|holiday\s+detection)\b', re.IGNORECASE),
     ('NDT & Integrity', 'Holiday testing')),
    # Mechanical Completion
    (re.compile(r'\b(hydrotest|hydraulic\s+test|pressure\s+test|hydro\s+test)\b', re.IGNORECASE),
     ('Mechanical Completion', 'Hydrotesting')),
    (re.compile(r'\b(pigging|pig\s+launching|pig\s+receiving|gauge\s+pig|gauging\s+pig)\b', re.IGNORECASE),
     ('Mechanical Completion', 'Pigging')),
    (re.compile(r'\b(flushing|line\s+flushing)\b', re.IGNORECASE),
     ('Mechanical Completion', 'Flushing')),
    (re.compile(r'\b(dewatering|de.?watering)\b', re.IGNORECASE),
     ('Mechanical Completion', 'Dewatering')),
    (re.compile(r'\b(drying|air\s+drying|nitrogen\s+drying)\b', re.IGNORECASE),
     ('Mechanical Completion', 'Drying')),
    (re.compile(r'\b(pre.?commission|commissioning)\b', re.IGNORECASE),
     ('Mechanical Completion', 'Pre-commissioning')),
    # Civil
    (re.compile(r'\b(excavat\w*|trench(?!\s+coat)\w*|dig|ditch)\b', re.IGNORECASE),
     ('Civil', 'Excavation')),
    (re.compile(r'\b(backfill|back.?filling)\w*', re.IGNORECASE),
     ('Civil', 'Backfilling')),
    (re.compile(r'\b(ROW|right.?of.?way|clear(?:ing)?|grub)\b', re.IGNORECASE),
     ('Civil', 'ROW clearing')),
    (re.compile(r'\b(concrete|pcc|rcc)\b', re.IGNORECASE),
     ('Civil', 'Concrete works')),
    # Logistics
    (re.compile(r'\b(transport|haul|truck(?:ing)?|barg(?:e|ing))\b', re.IGNORECASE),
     ('Logistics', 'Pipe transport')),
    # Mobilisation
    (re.compile(r'\b(mob(?:ilis)?ation|mobilization|demob)\b', re.IGNORECASE),
     ('Mobilisation', 'Mob / demob')),
    (re.compile(r'\b(CASHES|community|security\s+(?:guard|escort|spread))\b', re.IGNORECASE),
     ('Mobilisation', 'Security / CASHES')),
    (re.compile(r'\b(camp|accommodation|catering)\b', re.IGNORECASE),
     ('Mobilisation', 'Camp / accommodation')),
]


def _extract_diameter(text: str):
    """Return diameter in inches (int/float) or None."""
    for pat in DIAMETER_PATTERNS:
        m = pat.search(text)
        if m:
            val = float(m.group(1))
            # If pattern was DN-based, convert
            if 'DN' in pat.pattern:
                return DN_TO_INCH.get(int(val), val)
            return int(val) if val.is_integer() else val
    return None


def _extract_schedule(text: str):
    for pat, fmt_fn in SCHEDULE_PATTERNS:
        m = pat.search(text)
        if m:
            return fmt_fn(m)
    return None


def _extract_grade(text: str):
    for pat, fmt in GRADE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return fmt.format(m.group(1))
            except IndexError:
                return fmt
    return None


def _extract_terrain(text: str):
    for pat, val in TERRAIN_PATTERNS:
        if pat.search(text):
            return val
    return None


def _extract_unit(text: str):
    for pat, val in UNIT_PATTERNS:
        if pat.search(text):
            return val
    return None


def _extract_category(text: str):
    """Return (category, sub_category) — first matching rule wins."""
    for pat, (cat, sub) in CATEGORY_RULES:
        if pat.search(text):
            return cat, sub
    return None, None


def normalize_boq_line(
    description: str,
    qty: Optional[float] = None,
    unit_hint: Optional[str] = None,
    rate: Optional[float] = None,
):
    """Parse a single BOQ line description into a normalized record.

    Returns a dict with extracted attributes and a confidence score.
    """
    if not description:
        return None
    desc = str(description).strip()

    dia      = _extract_diameter(desc)
    sched    = _extract_schedule(desc)
    grade    = _extract_grade(desc)
    terrain  = _extract_terrain(desc)
    unit_x   = _extract_unit(desc) or (unit_hint.lower() if unit_hint else None)
    cat, sub = _extract_category(desc)

    # Confidence: each successful field adds to the score
    score = 0
    max_score = 6  # category, sub_cat, dia, sched, grade, unit
    if cat:     score += 1
    if sub:     score += 1
    if dia:     score += 1
    if sched:   score += 1
    if grade:   score += 1
    if unit_x:  score += 1
    confidence = score / max_score

    return {
        'raw_description': desc,
        'normalized_description': sub or cat or desc,
        'category_hint': cat,
        'sub_category_hint': sub,
        'discipline': 'Pipeline',  # default — could be inferred from context
        'spec': {
            'dia': dia,
            'sched': sched,
            'terrain': terrain,
            'grade': grade,
        },
        'unit_extracted': unit_x,
        'qty_extracted': qty,
        'rate_extracted': rate,
        'confidence': round(confidence, 2),
        'tokens_extracted': {
            k: v for k, v in [
                ('dia', dia), ('sched', sched), ('grade', grade),
                ('terrain', terrain), ('unit', unit_x),
                ('category', cat), ('sub_category', sub),
            ] if v is not None
        },
    }
