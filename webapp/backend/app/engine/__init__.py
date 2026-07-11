"""
NNPC Cost Intelligence — Backend Engine
Mirrors the Excel engine v2.0 logic in Python.

Critical: the lay_weld_data, mob rates, well AFE phases, and CT vendor stats
are ALL derived from the proprietary normalised database. They live here in
code, NOT exposed via any API endpoint that returns raw rows.

Public API returns ONLY:
  - Aggregated bands (Low/Mid/High)
  - Anonymised stats ("5 operators, n=4 sources")
  - Confidence ratings
  - QC verdicts
"""
from typing import Optional, Literal, Dict, List, Tuple
import json
from pathlib import Path
from pydantic import BaseModel, Field

# ─── Load proprietary rate tables (file lives next to this module) ─────────
DATA_DIR = Path(__file__).parent
with open(DATA_DIR / 'lay_weld_data.json') as f:
    _LAY_WELD = json.load(f)

# ─── Load line item catalogue (Phase 1A — 324 catalogued benchmark entries) ──
_CATALOGUE_PATH = DATA_DIR / 'line_items_catalogue.json'
if _CATALOGUE_PATH.exists():
    with open(_CATALOGUE_PATH) as f:
        _CATALOGUE = json.load(f)
else:
    _CATALOGUE = {'meta': {'total_items': 0}, 'items': []}

# ─── Default Pipeline parameters (from Excel 00. Inputs & Controls) ────────
DEFAULTS = {
    # Globals
    'ref_year': 2024,
    'joint_length_m': 12.0,
    'fx_mode': 'Implied I&E',
    'fx_mult': 1.55,
    'sec_floor_per_day_per_person': 50.0,
    'mob_uplift': 1.5,
    'personnel_uplift': 1.0,
    'contingency_pct': 0.10,
    'vat_pct': 0.075,
    'pipe_usd_tonne': 1850.0,
    'band_pct': 0.15,            # GREEN/AMBER threshold
    # Pipeline scope class defaults
    'mob_pct': 0.27,             # informational split
    'cashes_pct': 0.50,
    'demob_pct': 0.23,
}

# ─── Lay & weld rates (proprietary — embedded server-side only) ────────────
LAY_WELD = {(r['dia'], r['sched'], r['terrain']): r for r in _LAY_WELD}

# ─── Pipe material — calibrated to Excel R15 ──────────────────────────────
# Excel applies full pipe material from R7. Values for default 6" Sch 40 Swamp:
# Low $47/m  Mid $52/m  High $63/m
# These translate to a base material cost roughly $50-55/m for 6" Sch 40
# Use a per-diameter $/m table directly (mirrors Excel's R7 lookup)
PIPE_MATERIAL_USD_PER_M = {
    (2,  'Sch 40'):  8,   (2,  'Sch 80'):  11,
    (3,  'Sch 40'):  15,  (3,  'Sch 80'):  20,
    (4,  'Sch 40'):  24,  (4,  'Sch 80'):  33,
    (6,  'Sch 40'):  52,  (6,  'Sch 80'):  79,
    (8,  'Sch 40'):  79,  (8,  'Sch 80'):  120,
    (10, 'Sch 40'):  112, (10, 'Sch 80'):  151,
    (12, 'Sch 40'):  148, (12, 'Sch 80'):  200,
    (16, 'Sch 40'):  228, (16, 'Sch 80'):  311,
}
SCH_PREMIUM = {'Sch 40': 1.0, 'Sch 80': 1.0, 'Sch 120': 1.18, 'Sch 160': 1.30}

def pipe_material_usd_per_m(dia: int, sched: str) -> float:
    """Pipe material $/m, calibrated to Excel R7 lookup."""
    base_sch = sched if sched in ('Sch 40', 'Sch 80') else 'Sch 40'
    base = PIPE_MATERIAL_USD_PER_M.get((dia, base_sch))
    if base is None:
        # Fall back to nearest dia
        nearest = min(PIPE_MATERIAL_USD_PER_M, key=lambda k: abs(k[0]-dia) + (0 if k[1]==base_sch else 100))
        base = PIPE_MATERIAL_USD_PER_M[nearest]
    return base * SCH_PREMIUM.get(sched, 1.0)

# ─── Mob & CASHES (Swamp, Land) USD totals — from R3 ──────────────────────
MOB_CASHES = {  # base Low / Mid / High (no scope-class mult yet)
    'Swamp': {'low': 38274.16, 'mid': 45028.42, 'high': 55322.45},
    'Land':  {'low': 457.32,   'mid': 538.03,   'high': 645.63},  # ~$540 mid is low — matches R3 LAND_MOB_ROW
}
# NB: The Land mob figure looks anomalously small vs swamp — confirmed in v2 source.
# Land linear-lay BEMEs would typically use a larger figure; engine defaults match Excel.

# ─── Scope class multipliers ──────────────────────────────────────────────
SCOPE_CLASS_MULT = {
    'LINEAR LAY':     {'eq_util': 1.00, 'steel_allowance_per_m': 0.0,  'mob_bundle_mult': 1.00},
    'ON-SUPPORT FAB': {'eq_util': 0.20, 'steel_allowance_per_m': 25.0, 'mob_bundle_mult': 2.40},
    'BURIED':         {'eq_util': 0.80, 'steel_allowance_per_m': 0.0,  'mob_bundle_mult': 1.20},
}

# ─── Personnel — itemised roles (count, $/day Mid) from Excel R26-R36 ──────
# Each: (role, count, usd_per_day_mid)
PIPELINE_PERSONNEL_ITEMS = [
    ('Welder (pipe)',        4, 67.27),
    ('Site Engineer',        1, 30.27),
    ('Site Supervisor',      1, 53.82),
    ('Site Foreman',         1, 36.05),
    ('Safety Officer / HSE', 1, 23.54),
    ('Equipment Operator',   2, 24.85),
    ('Fitter',               4, 24.95),
    ('Marine Engineer',      1, 30.46),
    ('Deckhand',             2, 16.64),
    ('Labour (unskilled)',   8, 16.82),
    ('Driver',               1, 18.21),
]
# Total Mid crew/day = sum(count × rate). Verify ~ $779/day (matches earlier lumped value)

# ─── Equipment — itemised items (count, $/day Mid) from Excel R41-R55 ──────
# Swamp items run for full duration; land-support items (R49-55) are intermittent.
# (item, count, usd_per_day_mid, swamp_only)
PIPELINE_EQUIPMENT_ITEMS = [
    ('1200MT flat top barge',              1, 1108.84, True),
    ('1000MT Ramp Barge (spud legs)',      1, 980.89,  True),
    ('Tugboat 1500HP',                     1, 682.35,  True),
    ('Swamp buggy',                        1, 1151.78, True),
    ('12-man crew boat (diesel)',          1, 469.15,  True),
    ('Crane barge 20-50T',                 1, 1407.66, True),
    ('Diesel welding machine 400A',        3, 42.99,   False),
    ('Pressure testing machine + gauges',  1, 145.50,  False),
    ('Grinding machine',                   2, 20.18,   False),
    ('30T flat truck',                     1, 235.44,  False),
    ('20T self-loader',                    1, 168.17,  False),
    ('Toyota Hilux project vehicle',       2, 32.29,   False),
    ('18-seater staff bus',                1, 32.29,   False),
]

# Legacy lumped constants (kept for reference / fallback)
PIPELINE_PERS_USD_PER_DAY_MID  = sum(c * r for _, c, r in PIPELINE_PERSONNEL_ITEMS)
PIPELINE_PERS_USD_PER_DAY_LOW  = PIPELINE_PERS_USD_PER_DAY_MID * 0.9
PIPELINE_PERS_USD_PER_DAY_HIGH = PIPELINE_PERS_USD_PER_DAY_MID * 1.15

PIPELINE_EQ_USD_PER_DAY_SWAMP_MID  = 6075   # full swamp spread before util mult
PIPELINE_EQ_USD_PER_DAY_LAND_MID   = 3000

# NDT — Mid is ~$13.91/m for typical scope (proven against Excel)
NDT_USD_PER_M_MID = 13.91

# Mob/CASHES/Demob informational split (from Excel Inputs R30-R32)
MOB_SPLIT = {'Mobilisation': 0.27, 'CASHES (community/safety/env/sec)': 0.50, 'Demob & close-out': 0.23}

# ─── Well AFE phases (Sahara Energy 2024/25 — proprietary single source) ─
WELL_PHASES = [
    {'name': 'Pre-Spud',          'base_usd': 354500},
    {'name': 'Rig Move',          'base_usd': 1355330},
    {'name': '16" Drilling',      'base_usd': 2696113},
    {'name': '12.25" Drilling',   'base_usd': 3686517},
    {'name': '8.5" Drilling',     'base_usd': 3176173},
    {'name': 'Testing',           'base_usd': 1789362},
    {'name': 'Completions',       'base_usd': 4089180},
]
WELL_BAND_MULT = {'low': 0.85, 'mid': 1.00, 'high': 1.20}

# ─── CT Module stats (per-well annual basis, FwdUSD) ──────────────────────
CT_BENCHMARKS = {
    'Seplat 2024 (primary)': {  # 11 vendors, F'USD
        'per_well_min': 2577523.30, 'per_well_median': 5201271.32, 'per_well_max': 12423181.38,
        'vendor_count': 11, 'year': 2024,
    },
    'NAOC 2021': {  # 6 vendors, USD basis
        'per_well_min': 2198959.60, 'per_well_median': 4677555.20, 'per_well_max': 9737457.40,
        'vendor_count': 6, 'year': 2021,
    },
    'Combined (both)': {
        'per_well_min': min(2577523.30, 2198959.60),
        'per_well_median': (5201271.32 + 4677555.20) / 2,
        'per_well_max': max(12423181.38, 9737457.40),
        'vendor_count': 17, 'year': '2021-2024',
    },
}

# CT day-rate stats for Method B cross-check (Seplat 2024, 1.5" unit)
CT_DAY_RATES = {  # MIN / MEDIAN / MAX across 11 vendors, USD/day
    '1.25"': {'min': 90,  'median': 664, 'max': 1480},  # one vendor at 90 is outlier
    '1.5"':  {'min': 414, 'median': 665, 'max': 1480},
    '1.75"': {'min': 300, 'median': 990, 'max': 2280},
}

# ════════════════════════════════════════════════════════════════════════
# DATA MODELS — Pydantic schemas for the API
# ════════════════════════════════════════════════════════════════════════

ScopeClass = Literal['LINEAR LAY', 'ON-SUPPORT FAB', 'BURIED']
Terrain = Literal['Land', 'Swamp']
Module = Literal['Pipeline', 'Well', 'CT']

class GlobalsInput(BaseModel):
    """Shared inputs — defaults to engine defaults if omitted."""
    project_name: str = 'NNPC Project'
    ref_year: int = DEFAULTS['ref_year']
    fx_mult: float = DEFAULTS['fx_mult']
    sec_floor: float = DEFAULTS['sec_floor_per_day_per_person']
    mob_uplift: float = DEFAULTS['mob_uplift']
    contingency_pct: float = DEFAULTS['contingency_pct']
    vat_pct: float = DEFAULTS['vat_pct']
    band_pct: float = DEFAULTS['band_pct']

class PipelineInput(BaseModel):
    dia: int = 6
    sched: Literal['Sch 40', 'Sch 80', 'Sch 120', 'Sch 160'] = 'Sch 40'
    terrain: Terrain = 'Swamp'
    length_km: float = Field(default=5.0, gt=0)
    duration_days: int = Field(default=30, gt=0)
    scope_class: ScopeClass = 'LINEAR LAY'
    globals: GlobalsInput = GlobalsInput()

class WellInput(BaseModel):
    well_name: str = 'Well 1'
    tvd_m: int = Field(default=3500, gt=0)
    well_type: str = 'Onshore vertical'
    n_wells: int = Field(default=1, gt=0)
    globals: GlobalsInput = GlobalsInput()

class CTInput(BaseModel):
    ct_size: Literal['1.25"', '1.5"', '1.75"'] = '1.5"'
    n_wells: int = Field(default=1, gt=0)
    days_per_well: int = Field(default=5, gt=0)
    activity_factor: float = Field(default=1.0, gt=0)
    reference_tender: Literal['Seplat 2024 (primary)', 'NAOC 2021', 'Combined (both)'] = 'Seplat 2024 (primary)'
    globals: GlobalsInput = GlobalsInput()

class QCInput(BaseModel):
    module: Module
    vendor_name: str = ''
    quote_reference: str = ''
    quote_currency: Literal['USD', 'NGN'] = 'USD'
    quote_total: float = Field(gt=0)
    band_low: float = Field(gt=0)
    band_mid: float = Field(gt=0)
    band_high: float = Field(gt=0)
    band_pct: float = DEFAULTS['band_pct']

class CostBand(BaseModel):
    low: float
    mid: float
    high: float

class BreakdownItem(BaseModel):
    """A single itemised line within a breakdown group (e.g. one crew role, one equipment item)."""
    label: str
    qty: Optional[float] = None       # e.g. number of units, days, joints
    qty_unit: str = ''                # e.g. "days", "joints", "persons"
    unit_rate_mid: Optional[float] = None   # $/day, $/m, $/each — Mid basis
    unit_rate_unit: str = ''          # e.g. "$/day", "$/m"
    low: float
    mid: float
    high: float
    note: str = ''

class BreakdownRow(BaseModel):
    component: str
    low: float
    mid: float
    high: float
    note: str = ''
    children: List[BreakdownItem] = []   # itemised sub-components (collapsible in UI)

class EstimateResult(BaseModel):
    module: str
    inputs_echo: Dict
    direct_cost: CostBand
    contingency: CostBand
    vat: CostBand
    total: CostBand
    per_unit: Dict[str, CostBand]   # $/m, $/km, $/well, etc.
    confidence: str
    breakdown: List[BreakdownRow]
    diagnostics: List[str] = []     # warnings & envelope notes

class QCResult(BaseModel):
    module: str
    quote_usd: float
    benchmark_mid: float
    delta_usd: float
    delta_pct: float
    verdict: str
    verdict_colour: str       # 'green' | 'amber' | 'red'
    in_band: bool
    position_in_band: float

# ════════════════════════════════════════════════════════════════════════
# CALCULATION FUNCTIONS
# ════════════════════════════════════════════════════════════════════════

def fmt_per_m(v: float) -> str:
    return f"${v:,.0f}"

def _lookup_lay_weld(dia: int, sched: str, terrain: str) -> dict:
    """Look up lay/weld rate. Falls back to nearest diameter if exact match missing."""
    key = (dia, sched, terrain)
    if key in LAY_WELD:
        return LAY_WELD[key]
    # Fall back: nearest dia with same sched + terrain
    candidates = [r for r in _LAY_WELD if r['sched'] == sched and r['terrain'] == terrain]
    if not candidates:
        candidates = [r for r in _LAY_WELD if r['terrain'] == terrain]
    if not candidates:
        return {'median': 20.0, 'min': 15.0, 'max': 30.0, 'count': 0, 'confidence': 'LOW'}
    nearest = min(candidates, key=lambda r: abs(r['dia'] - dia))
    return {**nearest, 'confidence': 'LOW'}   # downgrade confidence on fallback

def estimate_pipeline(inp: PipelineInput) -> EstimateResult:
    g = inp.globals
    sc = SCOPE_CLASS_MULT[inp.scope_class]
    length_m = inp.length_km * 1000

    # Lay & weld rate
    lw = _lookup_lay_weld(inp.dia, inp.sched, inp.terrain)
    lw_low = lw['min'] * length_m
    lw_mid = lw['median'] * length_m
    lw_high = lw['max'] * length_m

    # Pipe material
    pipe_mat_per_m = pipe_material_usd_per_m(inp.dia, inp.sched) + sc['steel_allowance_per_m']
    mat_mid = pipe_mat_per_m * length_m
    mat_low = mat_mid * 0.9
    mat_high = mat_mid * 1.2

    # Field joint coating ($25/joint at standard 12m joint length)
    n_joints = length_m / DEFAULTS['joint_length_m']
    fjc_mid = n_joints * 25
    fjc_low = fjc_mid * 0.9
    fjc_high = fjc_mid * 1.2

    # Transport (rough)
    transport_per_m = 4.0 if inp.terrain == 'Land' else 6.0
    trans_mid = transport_per_m * length_m
    trans_low = trans_mid * 0.9
    trans_high = trans_mid * 1.2

    # Personnel — itemised by role (count × $/day × duration)
    pers_children = []
    pers_mid = 0.0
    for role, count, rate in PIPELINE_PERSONNEL_ITEMS:
        item_mid = count * rate * inp.duration_days
        pers_mid += item_mid
        pers_children.append(BreakdownItem(
            label=f"{role}" + (f" ×{count}" if count > 1 else ""),
            qty=count * inp.duration_days, qty_unit='man-days',
            unit_rate_mid=rate, unit_rate_unit='/day',
            low=item_mid * 0.9, mid=item_mid, high=item_mid * 1.15,
        ))
    pers_low = pers_mid * 0.9
    pers_high = pers_mid * 1.15

    # Equipment with scope class util — itemised by item
    eq_children = []
    eq_mid_base = 0.0
    for item, count, rate, swamp_only in PIPELINE_EQUIPMENT_ITEMS:
        # Land-only scope: skip swamp marine spread; swamp scope: include all
        if swamp_only and inp.terrain != 'Swamp':
            continue
        item_mid_base = count * rate * inp.duration_days
        item_mid = item_mid_base * sc['eq_util']
        eq_mid_base += item_mid
        eq_children.append(BreakdownItem(
            label=f"{item}" + (f" ×{count}" if count > 1 else ""),
            qty=count * inp.duration_days, qty_unit='unit-days',
            unit_rate_mid=rate, unit_rate_unit='/day',
            low=item_mid * 0.9, mid=item_mid, high=item_mid * 1.2,
            note=(f"util {sc['eq_util']:.2f}×" if sc['eq_util'] != 1.0 else ''),
        ))
    eq_mid = eq_mid_base
    eq_low = eq_mid * 0.9
    eq_high = eq_mid * 1.2

    # Mob & CASHES bundle (scope-class-aware) — itemised into 3 components
    mob_base = MOB_CASHES[inp.terrain]
    mob_low = mob_base['low'] * sc['mob_bundle_mult']
    mob_mid = mob_base['mid'] * sc['mob_bundle_mult']
    mob_high = mob_base['high'] * sc['mob_bundle_mult']
    mob_children = []
    for comp_label, share in MOB_SPLIT.items():
        mob_children.append(BreakdownItem(
            label=comp_label,
            qty=None, qty_unit='',
            unit_rate_mid=None, unit_rate_unit='',
            low=mob_low * share, mid=mob_mid * share, high=mob_high * share,
            note=f"{share*100:.0f}% of bundle",
        ))

    # Security — 3/4/6 people × duration × Sec_Floor (default 4 people × $50 × 30d = $6000 Mid)
    sec_low = 3 * inp.duration_days * g.sec_floor
    sec_mid = 4 * inp.duration_days * g.sec_floor
    sec_high = 6 * inp.duration_days * g.sec_floor

    # NDT — $/m of pipe × length
    ndt_mid = NDT_USD_PER_M_MID * length_m
    ndt_low = ndt_mid * 0.85
    ndt_high = ndt_mid * 1.2

    # Security — itemised (per-tier headcount)
    sec_children = [
        BreakdownItem(label='Community liaison / surveillance', qty=2*inp.duration_days, qty_unit='man-days',
                      unit_rate_mid=g.sec_floor, unit_rate_unit='/day',
                      low=2*inp.duration_days*g.sec_floor*0.75, mid=2*inp.duration_days*g.sec_floor,
                      high=2*inp.duration_days*g.sec_floor*1.5),
        BreakdownItem(label='Security escort (waterway/road)', qty=2*inp.duration_days, qty_unit='man-days',
                      unit_rate_mid=g.sec_floor, unit_rate_unit='/day',
                      low=1*inp.duration_days*g.sec_floor, mid=2*inp.duration_days*g.sec_floor,
                      high=4*inp.duration_days*g.sec_floor),
    ]

    # Breakdown
    breakdown = [
        BreakdownRow(component='Pipe material',          low=mat_low,   mid=mat_mid,   high=mat_high,
                     note=f"{inp.dia}\" {inp.sched} · {fmt_per_m(pipe_mat_per_m)}/m × {length_m:,.0f}m",
                     children=[BreakdownItem(
                         label=f'API 5L Gr B {inp.dia}\" {inp.sched}', qty=length_m, qty_unit='m',
                         unit_rate_mid=pipe_mat_per_m, unit_rate_unit='/m',
                         low=mat_low, mid=mat_mid, high=mat_high)]),
        BreakdownRow(component='Lay & weld',             low=lw_low,    mid=lw_mid,    high=lw_high,
                     note=f"n={lw['count']} operators · confidence {lw['confidence']}",
                     children=[BreakdownItem(
                         label=f'Installation rate ({inp.terrain})', qty=length_m, qty_unit='m',
                         unit_rate_mid=lw['median'], unit_rate_unit='/m',
                         low=lw_low, mid=lw_mid, high=lw_high,
                         note=f"Low ${lw['min']:.2f}/m · High ${lw['max']:.2f}/m")]),
        BreakdownRow(component='Field joint coating',    low=fjc_low,   mid=fjc_mid,   high=fjc_high,
                     note=f"{n_joints:,.0f} joints × $25",
                     children=[BreakdownItem(
                         label='Heat-shrink sleeve', qty=n_joints, qty_unit='joints',
                         unit_rate_mid=25, unit_rate_unit='/joint',
                         low=fjc_low, mid=fjc_mid, high=fjc_high)]),
        BreakdownRow(component='Pipe transport',         low=trans_low, mid=trans_mid, high=trans_high,
                     note=f"${transport_per_m:.0f}/m × {length_m:,.0f}m ({inp.terrain})",
                     children=[BreakdownItem(
                         label=f'Transport 0-50km ({inp.terrain})', qty=length_m, qty_unit='m',
                         unit_rate_mid=transport_per_m, unit_rate_unit='/m',
                         low=trans_low, mid=trans_mid, high=trans_high)]),
        BreakdownRow(component='Personnel',              low=pers_low,  mid=pers_mid,  high=pers_high,
                     note=f"{len(pers_children)} roles × {inp.duration_days} days",
                     children=pers_children),
        BreakdownRow(component='Equipment',              low=eq_low, mid=eq_mid, high=eq_high,
                     note=f"{len(eq_children)} items · utilisation {sc['eq_util']:.2f}× ({inp.scope_class})",
                     children=eq_children),
        BreakdownRow(component='Mob + CASHES + Demob',   low=mob_low,   mid=mob_mid,   high=mob_high,
                     note=f"Bundle multiplier {sc['mob_bundle_mult']:.2f}× ({inp.scope_class})",
                     children=mob_children),
        BreakdownRow(component='Security',               low=sec_low,   mid=sec_mid,   high=sec_high,
                     note=f"Floored at ${g.sec_floor:.0f}/day/person",
                     children=sec_children),
        BreakdownRow(component='NDT & integrity',        low=ndt_low,   mid=ndt_mid,   high=ndt_high,
                     note=f"${NDT_USD_PER_M_MID:.2f}/m × {length_m:,.0f}m",
                     children=[BreakdownItem(
                         label='X-ray + hydrotest', qty=length_m, qty_unit='m',
                         unit_rate_mid=NDT_USD_PER_M_MID, unit_rate_unit='/m',
                         low=ndt_low, mid=ndt_mid, high=ndt_high)]),
    ]

    direct_low  = sum(r.low for r in breakdown)
    direct_mid  = sum(r.mid for r in breakdown)
    direct_high = sum(r.high for r in breakdown)

    cont_low  = direct_low  * g.contingency_pct
    cont_mid  = direct_mid  * g.contingency_pct
    cont_high = direct_high * g.contingency_pct

    vat_low  = (direct_low  + cont_low ) * g.vat_pct
    vat_mid  = (direct_mid  + cont_mid ) * g.vat_pct
    vat_high = (direct_high + cont_high) * g.vat_pct

    total_low  = direct_low  + cont_low  + vat_low
    total_mid  = direct_mid  + cont_mid  + vat_mid
    total_high = direct_high + cont_high + vat_high

    # Diagnostics — envelope warnings
    diagnostics = []
    weld_density = n_joints / length_m if length_m > 0 else 0
    days_per_m = inp.duration_days / length_m if length_m > 0 else 0
    if length_m < 100:
        diagnostics.append("AMBER: length < 100m. Engine is calibrated for km-scale lay. Consider ON-SUPPORT FAB.")
    elif length_m < 500:
        diagnostics.append("NOTE: length < 500m. Mob/CASHES will dominate costs.")
    if days_per_m > 0.2:
        diagnostics.append("AMBER: > 0.2 days/m. Duration disproportionate to length — likely fabrication scope.")
    elif days_per_m > 0.1:
        diagnostics.append("NOTE: Elevated days/m. Verify scope class.")

    # Scope class recommendation
    if (length_m < 100 or days_per_m > 0.2) and inp.scope_class == 'LINEAR LAY':
        diagnostics.append("RECOMMENDATION: Switch scope class to ON-SUPPORT FAB.")

    return EstimateResult(
        module='Pipeline',
        inputs_echo=inp.model_dump(),
        direct_cost=CostBand(low=direct_low, mid=direct_mid, high=direct_high),
        contingency=CostBand(low=cont_low, mid=cont_mid, high=cont_high),
        vat=CostBand(low=vat_low, mid=vat_mid, high=vat_high),
        total=CostBand(low=total_low, mid=total_mid, high=total_high),
        per_unit={
            'usd_per_m':  CostBand(low=total_low/length_m,    mid=total_mid/length_m,    high=total_high/length_m),
            'usd_per_km': CostBand(low=total_low/inp.length_km, mid=total_mid/inp.length_km, high=total_high/inp.length_km),
        },
        confidence=lw['confidence'],
        breakdown=breakdown,
        diagnostics=diagnostics,
    )

def estimate_well(inp: WellInput) -> EstimateResult:
    g = inp.globals
    n = inp.n_wells

    # Sub-activity split per phase (typical AFE composition, applied as shares)
    PHASE_SUBITEMS = {
        'Pre-Spud':        [('Site survey & permits', 0.25), ('Location prep / civil', 0.45), ('Mobilisation', 0.30)],
        'Rig Move':        [('Rig in / rig up', 0.55), ('Rig down / move out', 0.45)],
        '16" Drilling':    [('Drilling services', 0.40), ('Mud & chemicals', 0.20), ('Casing & cement', 0.25), ('Rig day-rate', 0.15)],
        '12.25" Drilling': [('Drilling services', 0.38), ('Mud & chemicals', 0.22), ('Casing & cement', 0.25), ('Rig day-rate', 0.15)],
        '8.5" Drilling':   [('Drilling services', 0.40), ('Mud & chemicals', 0.20), ('Liner & cement', 0.25), ('Rig day-rate', 0.15)],
        'Testing':         [('Well test / flowback', 0.55), ('Wireline & logging', 0.45)],
        'Completions':     [('Perforation', 0.20), ('Gravel pack / sand control', 0.30), ('Completion hardware', 0.35), ('Christmas tree & wellhead', 0.15)],
    }

    # Direct cost from phases × bands × n_wells
    breakdown = []
    direct_low = direct_mid = direct_high = 0.0
    for ph in WELL_PHASES:
        low  = ph['base_usd'] * WELL_BAND_MULT['low']  * n
        mid  = ph['base_usd'] * WELL_BAND_MULT['mid']  * n
        high = ph['base_usd'] * WELL_BAND_MULT['high'] * n
        # Children = sub-activities
        children = []
        for sub_label, share in PHASE_SUBITEMS.get(ph['name'], []):
            children.append(BreakdownItem(
                label=sub_label, qty=None, qty_unit='', unit_rate_mid=None, unit_rate_unit='',
                low=low * share, mid=mid * share, high=high * share,
                note=f"{share*100:.0f}% of phase",
            ))
        pct_of_well = ph['base_usd'] / sum(p['base_usd'] for p in WELL_PHASES)
        breakdown.append(BreakdownRow(
            component=ph['name'], low=low, mid=mid, high=high,
            note=f"{pct_of_well*100:.0f}% of well cost" + (f" · ×{n} wells" if n > 1 else ""),
            children=children))
        direct_low += low
        direct_mid += mid
        direct_high += high

    cont_low  = direct_low  * g.contingency_pct
    cont_mid  = direct_mid  * g.contingency_pct
    cont_high = direct_high * g.contingency_pct
    vat_low   = (direct_low + cont_low)   * g.vat_pct
    vat_mid   = (direct_mid + cont_mid)   * g.vat_pct
    vat_high  = (direct_high + cont_high) * g.vat_pct
    total_low  = direct_low  + cont_low  + vat_low
    total_mid  = direct_mid  + cont_mid  + vat_mid
    total_high = direct_high + cont_high + vat_high

    return EstimateResult(
        module='Well',
        inputs_echo=inp.model_dump(),
        direct_cost=CostBand(low=direct_low, mid=direct_mid, high=direct_high),
        contingency=CostBand(low=cont_low, mid=cont_mid, high=cont_high),
        vat=CostBand(low=vat_low, mid=vat_mid, high=vat_high),
        total=CostBand(low=total_low, mid=total_mid, high=total_high),
        per_unit={
            'usd_per_well':   CostBand(low=total_low/n, mid=total_mid/n, high=total_high/n),
            'usd_per_m_tvd':  CostBand(low=total_low/(n*inp.tvd_m), mid=total_mid/(n*inp.tvd_m), high=total_high/(n*inp.tvd_m)),
        },
        confidence='LOW',
        breakdown=breakdown,
        diagnostics=['Single-source benchmark (Sahara Energy 2024/25 onshore vertical AFE). Treat as indicative.'],
    )

def estimate_ct(inp: CTInput) -> EstimateResult:
    g = inp.globals
    bench = CT_BENCHMARKS[inp.reference_tender]
    n_wells = inp.n_wells
    days_total = inp.days_per_well * n_wells

    # Method A: per-well annual × n_wells × activity × (days/365)
    scale = inp.activity_factor * (days_total / 365.0)
    direct_low  = bench['per_well_min']    * n_wells * inp.activity_factor * (inp.days_per_well / 365.0)
    direct_mid  = bench['per_well_median'] * n_wells * inp.activity_factor * (inp.days_per_well / 365.0)
    direct_high = bench['per_well_max']    * n_wells * inp.activity_factor * (inp.days_per_well / 365.0)

    cont_low  = direct_low  * g.contingency_pct
    cont_mid  = direct_mid  * g.contingency_pct
    cont_high = direct_high * g.contingency_pct
    vat_low   = (direct_low + cont_low)   * g.vat_pct
    vat_mid   = (direct_mid + cont_mid)   * g.vat_pct
    vat_high  = (direct_high + cont_high) * g.vat_pct
    total_low  = direct_low  + cont_low  + vat_low
    total_mid  = direct_mid  + cont_mid  + vat_mid
    total_high = direct_high + cont_high + vat_high

    # Method B cross-check (day rates × days)
    dr = CT_DAY_RATES[inp.ct_size]
    method_b_mid = dr['median'] * days_total

    # CT direct cost composition (typical CT campaign split across cost categories)
    CT_SPLIT = [
        ('CT unit + reel + power pack', 0.34),
        ('Pumping & nitrogen services', 0.22),
        ('Personnel (crew + supervision)', 0.18),
        ('Chemicals & fluids', 0.12),
        ('Mobilisation / demob', 0.09),
        ('Logistics (barge/crane/boats)', 0.05),
    ]
    direct_children = []
    for label, share in CT_SPLIT:
        direct_children.append(BreakdownItem(
            label=label, qty=None, qty_unit='', unit_rate_mid=None, unit_rate_unit='',
            low=direct_low * share, mid=direct_mid * share, high=direct_high * share,
            note=f"{share*100:.0f}% of direct",
        ))

    breakdown = [
        BreakdownRow(component='Direct cost (Method A: per-well × scaling)',
                     low=direct_low, mid=direct_mid, high=direct_high,
                     note=f"{bench['vendor_count']} vendors, {bench['year']} tender basis",
                     children=direct_children),
        BreakdownRow(component='Method B cross-check ($/d × days, info only)',
                     low=dr['min']*days_total, mid=method_b_mid, high=dr['max']*days_total,
                     note='Day-rate basis — for short scopes Method B may under-estimate.',
                     children=[
                         BreakdownItem(label=f'CT {inp.ct_size} unit day rate', qty=days_total, qty_unit='days',
                                       unit_rate_mid=dr['median'], unit_rate_unit='/day',
                                       low=dr['min']*days_total, mid=method_b_mid, high=dr['max']*days_total,
                                       note=f"Low ${dr['min']}/d · High ${dr['max']}/d"),
                     ]),
    ]

    return EstimateResult(
        module='CT',
        inputs_echo=inp.model_dump(),
        direct_cost=CostBand(low=direct_low, mid=direct_mid, high=direct_high),
        contingency=CostBand(low=cont_low, mid=cont_mid, high=cont_high),
        vat=CostBand(low=vat_low, mid=vat_mid, high=vat_high),
        total=CostBand(low=total_low, mid=total_mid, high=total_high),
        per_unit={
            'usd_per_well': CostBand(low=total_low/n_wells, mid=total_mid/n_wells, high=total_high/n_wells),
            'usd_per_day':  CostBand(low=total_low/days_total, mid=total_mid/days_total, high=total_high/days_total),
        },
        confidence='HIGH' if inp.reference_tender == 'Seplat 2024 (primary)' else 'MEDIUM',
        breakdown=breakdown,
        diagnostics=[],
    )

def check_quote(inp: QCInput) -> QCResult:
    # Convert NGN to FwdUSD if needed
    if inp.quote_currency == 'NGN':
        quote_usd = inp.quote_total / 1500.0 * 1.55   # CBN official → parallel uplift
    else:
        quote_usd = inp.quote_total

    delta_usd = quote_usd - inp.band_mid
    delta_pct = delta_usd / inp.band_mid if inp.band_mid > 0 else 0.0

    abs_pct = abs(delta_pct)
    if abs_pct <= inp.band_pct:
        verdict = f"✅ GREEN — within ±{inp.band_pct*100:.0f}% of Mid (acceptable)"
        colour = 'green'
    elif abs_pct <= inp.band_pct * 2:
        verdict = f"⚠ AMBER — ±{inp.band_pct*100:.0f}–{inp.band_pct*200:.0f}% of Mid (challenge/negotiate)"
        colour = 'amber'
    else:
        verdict = f"❌ RED — >±{inp.band_pct*200:.0f}% of Mid (challenge quote)"
        colour = 'red'

    in_band = inp.band_low <= quote_usd <= inp.band_high
    band_width = inp.band_high - inp.band_low
    position = (quote_usd - inp.band_low) / band_width if band_width > 0 else 0.5

    return QCResult(
        module=inp.module,
        quote_usd=quote_usd,
        benchmark_mid=inp.band_mid,
        delta_usd=delta_usd,
        delta_pct=delta_pct,
        verdict=verdict,
        verdict_colour=colour,
        in_band=in_band,
        position_in_band=position,
    )


# ════════════════════════════════════════════════════════════════════════
# INTELLIGENCE LAYER — Findings, Cross-Tender Analysis, Coverage Matrix
# These endpoints expose AGGREGATE intelligence only.
# Individual operator/vendor identities remain anonymised in CT analysis.
# ════════════════════════════════════════════════════════════════════════

# ─── The 7 key findings from the v2 brief ─────────────────────────────────
FINDINGS = [
    {
        'id': 1, 'tag': 'CT DEFLATION', 'severity': 'amber',
        'headline': 'CT market deflated sharply between 2021 and 2024',
        'body': 'Cross-tender vendor analysis: 3 of 4 vendors that bid both the NAOC 2021 CT tender and the Seplat 2024 CT tender cut their day rates by 40–52% (3-year CAGR -15% to -22%). IHE Emval, Hydroserve, and Weafri all dropped substantially. Only Netcore held flat or raised prices.',
        'so_what': 'Use Seplat 2024 as primary CT benchmark for any 2025+ tender. NAOC 2021 now represents an UPPER bound, not a current market rate. Vendors that cut so steeply may be unsustainable — watch for service quality issues.',
        'evidence': [
            {'vendor': 'Vendor A', 'naoc_2021': 1050, 'seplat_2024': 612,  'delta_pct': -0.417, 'cagr': -0.164},
            {'vendor': 'Vendor B', 'naoc_2021': 1197, 'seplat_2024': 720,  'delta_pct': -0.399, 'cagr': -0.156},
            {'vendor': 'Vendor C', 'naoc_2021': 1150, 'seplat_2024': 1275, 'delta_pct': +0.109, 'cagr': +0.035},
            {'vendor': 'Vendor D', 'naoc_2021': 1320, 'seplat_2024': 627,  'delta_pct': -0.525, 'cagr': -0.220},
        ],
    },
    {
        'id': 2, 'tag': 'PROCUREMENT PHILOSOPHY', 'severity': 'amber',
        'headline': 'Procurement without benchmark context fights the wrong battle',
        'body': "In Seplat's December 2024 CT tender (ETB-0199), 11 vendors quoted the same scope with a 6.4× price spread ($15.3M to $98.8M for the same 10-well program). The 1st-position winner (Geoplex at $98.8M) was the SECOND-HIGHEST price. The cheapest bidder (Hydroserve at $15.3M) finished 8th.",
        'so_what': "Cheap bids fail more often than they win — Seplat ranks on technical capability + risk + commercial. An operator without cross-vendor data has no basis to evaluate whether a quote represents fair market value vs. an unsustainable lowball.",
        'evidence': [
            {'vendor': 'Vendor 1',  'price_musd': 15.3, 'rank': 8},
            {'vendor': 'Vendor 2',  'price_musd': 21.1, 'rank': None},
            {'vendor': 'Vendor 3',  'price_musd': 25.0, 'rank': None},
            {'vendor': 'Vendor 4',  'price_musd': 25.0, 'rank': None},
            {'vendor': 'Vendor 5',  'price_musd': 26.5, 'rank': None},
            {'vendor': 'Vendor 6',  'price_musd': 38.1, 'rank': None},
            {'vendor': 'Vendor 7',  'price_musd': 40.1, 'rank': None},
            {'vendor': 'Vendor 8',  'price_musd': 52.8, 'rank': None},
            {'vendor': 'Vendor 9',  'price_musd': 53.1, 'rank': None},
            {'vendor': 'Vendor 10', 'price_musd': 59.8, 'rank': None},
            {'vendor': 'Vendor 11', 'price_musd': 98.8, 'rank': 1},
        ],
    },
    {
        'id': 3, 'tag': 'IOC SPREAD', 'severity': 'amber',
        'headline': 'IOC vs Nigerian independent spread persists — but compresses by scope',
        'body': "6\" Sch 40 swamp lay/weld varies from $15.61/m (NPDC 2021) to $26.68/m (SPDC 2017), a 1.7× spread. Spread compresses by diameter — 12\" Sch 40 swamp shows tighter clustering at $24-27/m across operators.",
        'so_what': "Original 2.3× spread on 6\" rates is not pure IOC premium — Scope_Class differences explain some (e.g. SPDC included field joint coating, NPDC did not). Use NPDC/ARAHAS/HEOSL as floor for cost estimates; SPDC/Seplat as ceiling. Never use a single operator alone.",
        'evidence': [
            {'operator': 'Operator A', 'year': 2017, 'rate': 26.68},
            {'operator': 'Operator B', 'year': 2021, 'rate': 15.61},
            {'operator': 'Operator C', 'year': 2023, 'rate': 20.26},
            {'operator': 'Operator D', 'year': 2024, 'rate': 18.50},
            {'operator': 'Operator E', 'year': 2025, 'rate': 16.96},
        ],
    },
    {
        'id': 4, 'tag': 'FIELD TEST', 'severity': 'green',
        'headline': 'Engine produces defensible estimates on real BEMEs',
        'body': "Field-tested against SPDC EGWA-2 swamp bypass BEME (4\" Sch 80, 64m, on-support fabrication, 14 days). Engine Mid: $178,728. BEME actual: $202,922. Delta: -12%. QC verdict: GREEN, within ±15% band. Component-level breakdown matched BEME at the bucket level after the v1.1 scope-class fixes.",
        'so_what': 'Engine is ready for directional use on swamp pipeline scopes. Calibrated to recognize ON-SUPPORT FAB vs LINEAR LAY (fabrication scopes carry 2.4× higher CASHES/demob burden). Recommend a second field test on a kilometre-scale linear lay BEME to validate the primary design envelope.',
        'evidence': [
            {'metric': 'Grand Total (incl. VAT)', 'actual': 202922, 'engine': 178728, 'delta': -0.119},
            {'metric': 'Direct cost subtotal',    'actual': 188764, 'engine': 154546, 'delta': -0.181},
            {'metric': 'Mob + CASHES + Demob',    'actual': 107907, 'engine': 108068, 'delta':  0.001},
            {'metric': '$/m of pipe (incl. VAT)', 'actual': 3170,   'engine': 2855,   'delta': -0.099},
        ],
    },
    {
        'id': 5, 'tag': 'WELL DATA GAP', 'severity': 'red',
        'headline': 'Well cost benchmarks remain a one-source thin layer',
        'body': 'Well services intelligence is based on a single Sahara Energy 2024/25 land-well AFE: $17.1M ex-contingency across 7 phases. Completions = 23.8%, 12.25" hole = 21.5%, 8.5" hole = 18.5% are the cost drivers. No swamp well, no second operator, no field test.',
        'so_what': 'Treat Well module outputs as INDICATIVE only. Get one more operator\'s well AFE before using for tender QC. Targets: any Renaissance/NDEP/Heirs Holdings 2024-25 onshore well close-out.',
        'evidence': [
            {'phase': 'Pre-Spud',          'share': 0.021},
            {'phase': 'Rig Move',          'share': 0.079},
            {'phase': '16" Drilling',      'share': 0.158},
            {'phase': '12.25" Drilling',   'share': 0.215},
            {'phase': '8.5" Drilling',     'share': 0.185},
            {'phase': 'Testing',           'share': 0.104},
            {'phase': 'Completions',       'share': 0.238},
        ],
    },
    {
        'id': 6, 'tag': 'FX SYSTEMATIC UNDERSTATEMENT', 'severity': 'amber',
        'headline': 'NGN-denominated rates likely understate true cost by 30-50%',
        'body': "Seplat's entire SOR is NGN-denominated. When converted at CBN official FX (~₦1,535/USD avg 2024), the resulting USD rates are systematically lower than peer-operator USD-quoted rates. Likely cause: vendors implicitly price NGN portion at parallel-market FX (~₦1,850-2,000/USD).",
        'so_what': 'Engine applies NGN_Uplift of 1.55× by default to NGN-source rates. Adjust upward (1.65-1.75×) for any post-2023 work where vendor pricing reflects parallel-market FX expectations.',
        'evidence': [],
    },
    {
        'id': 7, 'tag': 'SECURITY UNDER-PRICING', 'severity': 'red',
        'headline': 'Security/CASHES rates in source documents are systematically below market',
        'body': 'SPDC 2017 surveillance at $69/24hr · Seplat 2023 security escort at ₦9,815/day (~$15/day USD 2024). Security costs escalated sharply post-2020. The EGWA-2 BEME field test showed actual CASHES at 21% of project direct cost (~$40k for a $190k direct subtotal job).',
        'so_what': 'Engine applies a Sec_Floor of $50/day/person by default. For 2025+ swamp scopes, consider raising to $75-100/day. Mob_Bundle_Mult of 2.4× for ON-SUPPORT FAB scopes already captures the disproportionate CASHES burden of community-land hookups.',
        'evidence': [],
    },
]


def get_findings():
    """Return all market intelligence findings."""
    return {
        'findings': FINDINGS,
        'meta': {
            'total': len(FINDINGS),
            'by_severity': {
                'green': sum(1 for f in FINDINGS if f['severity'] == 'green'),
                'amber': sum(1 for f in FINDINGS if f['severity'] == 'amber'),
                'red':   sum(1 for f in FINDINGS if f['severity'] == 'red'),
            },
        },
    }


def get_ct_cross_tender():
    """CT cross-tender analysis: vendor spread, deflation pattern."""
    return {
        'seplat_2024': {
            'vendor_count': 11, 'tender_ref': 'ETB-0199', 'tender_date': 'December 2024',
            'spread_ratio': 6.4,
            'winner_rank_by_price': 2,
            'winner_price_musd': 98.8,
            'cheapest_price_musd': 15.3,
            'cheapest_rank': 8,
            'distribution': [
                {'vendor': 'Vendor 1',  'price_musd': 15.3, 'rank': 8},
                {'vendor': 'Vendor 2',  'price_musd': 21.1, 'rank': None},
                {'vendor': 'Vendor 3',  'price_musd': 25.0, 'rank': None},
                {'vendor': 'Vendor 4',  'price_musd': 25.0, 'rank': None},
                {'vendor': 'Vendor 5',  'price_musd': 26.5, 'rank': None},
                {'vendor': 'Vendor 6',  'price_musd': 38.1, 'rank': None},
                {'vendor': 'Vendor 7',  'price_musd': 40.1, 'rank': None},
                {'vendor': 'Vendor 8',  'price_musd': 52.8, 'rank': None},
                {'vendor': 'Vendor 9',  'price_musd': 53.1, 'rank': None},
                {'vendor': 'Vendor 10', 'price_musd': 59.8, 'rank': None},
                {'vendor': 'Vendor 11', 'price_musd': 98.8, 'rank': 1},
            ],
        },
        'naoc_2021': {
            'vendor_count': 6, 'tender_ref': '2100002581', 'tender_date': '2021',
            'spread_ratio': 4.4,
            'winner_price_musd': 66.0,
            'winner_was_cheapest': True,
        },
        'deflation': {
            'overlapping_vendors': 4,
            'vendors_cutting_rates': 3,
            'avg_rate_cut_pct': -0.405,
            'detail': [
                {'vendor': 'Vendor A', 'naoc_2021_usd_per_day': 1050, 'seplat_2024_usd_per_day': 612,  'delta_pct': -0.417, 'cagr': -0.164},
                {'vendor': 'Vendor B', 'naoc_2021_usd_per_day': 1197, 'seplat_2024_usd_per_day': 720,  'delta_pct': -0.399, 'cagr': -0.156},
                {'vendor': 'Vendor C', 'naoc_2021_usd_per_day': 1150, 'seplat_2024_usd_per_day': 1275, 'delta_pct': +0.109, 'cagr': +0.035},
                {'vendor': 'Vendor D', 'naoc_2021_usd_per_day': 1320, 'seplat_2024_usd_per_day': 627,  'delta_pct': -0.525, 'cagr': -0.220},
            ],
        },
        'so_what': 'Use Seplat 2024 as primary benchmark for any 2026+ CT tender. NAOC 2021 rates now serve as a conservative upper bound. The 6.4× spread is real — without cross-vendor data, an operator has no way to know whether a quote is fair, lowball, or extractive.',
    }


def get_coverage_matrix():
    """Diameter × terrain heatmap of dataset coverage (lay/weld pivot)."""
    from collections import defaultdict
    matrix = defaultdict(lambda: {'count': 0, 'min': None, 'median': None, 'max': None, 'confidence': 'LOW', 'sched': set()})
    diameters = sorted(set(r['dia'] for r in _LAY_WELD))
    terrains = ['Land', 'Swamp']

    for r in _LAY_WELD:
        key = (r['dia'], r['terrain'])
        m = matrix[key]
        m['count'] += r['count'] if r['count'] else 0
        m['min']    = r['min']    if m['min']    is None else min(m['min'],    r['min'])
        m['max']    = r['max']    if m['max']    is None else max(m['max'],    r['max'])
        m['median'] = r['median'] if m['median'] is None else (m['median'] + r['median']) / 2
        m['sched'].add(r['sched'])
        # Confidence: HIGH if 3+ records, MEDIUM if 2, LOW if 1
        if r['count']:
            if r['count'] >= 3: m['confidence'] = 'HIGH'
            elif r['count'] >= 2 and m['confidence'] == 'LOW': m['confidence'] = 'MEDIUM'

    cells = []
    for dia in diameters:
        for terrain in terrains:
            m = matrix.get((dia, terrain))
            if m and m['count'] > 0:
                cells.append({
                    'dia': dia, 'terrain': terrain,
                    'count': m['count'],
                    'min': m['min'], 'median': m['median'], 'max': m['max'],
                    'confidence': m['confidence'],
                    'schedules': sorted(m['sched']),
                })
            else:
                cells.append({'dia': dia, 'terrain': terrain, 'count': 0, 'confidence': 'NONE', 'schedules': []})

    return {
        'cells': cells,
        'diameters': diameters,
        'terrains': terrains,
        'meta': {
            'total_records': sum(r['count'] for r in _LAY_WELD if r['count']),
            'unique_combinations': len([c for c in cells if c['count'] > 0]),
            'high_confidence_combinations': len([c for c in cells if c['confidence'] == 'HIGH']),
            'gaps':  len([c for c in cells if c['count'] == 0]),
        },
        'modules': {
            'Pipeline': {'records': sum(r['count'] for r in _LAY_WELD if r['count']), 'operators': 5,  'confidence': 'HIGH'},
            'Well':     {'records': 7, 'operators': 1, 'confidence': 'LOW'},
            'CT':       {'records': 17,'operators': 2,'tenders': 2, 'confidence': 'MEDIUM'},
        },
    }


# ════════════════════════════════════════════════════════════════════════
# LINE ITEM CATALOGUE (Phase 1A)
# Aggregated, normalised, USD 2024 benchmarks for individual pipeline line items
# ════════════════════════════════════════════════════════════════════════

def get_catalogue_summary():
    """High-level summary: counts by category, confidence, units."""
    return {
        'meta': _CATALOGUE.get('meta', {}),
        'categories': sorted(set(i['category'] for i in _CATALOGUE['items'])),
        'sub_categories_by_category': _group_subcategories(),
        'units':      sorted(set(i['unit']     for i in _CATALOGUE['items'])),
        'operators':  sorted(set(op for i in _CATALOGUE['items'] for op in i['operators'])),
    }

def _group_subcategories():
    """{category: [sub_categories...]}"""
    from collections import defaultdict
    g = defaultdict(set)
    for i in _CATALOGUE['items']:
        g[i['category']].add(i['sub_category'])
    return {k: sorted(v) for k, v in g.items()}

def query_catalogue(
    category: Optional[str] = None,
    sub_category: Optional[str] = None,
    search: Optional[str] = None,
    confidence: Optional[str] = None,
    unit: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Filter + paginate catalogue items."""
    items = _CATALOGUE['items']
    if category:     items = [i for i in items if i['category'] == category]
    if sub_category: items = [i for i in items if i['sub_category'] == sub_category]
    if confidence:   items = [i for i in items if i['confidence'] == confidence]
    if unit:         items = [i for i in items if i['unit'] == unit]
    if search:
        s = search.lower().strip()
        items = [i for i in items if s in i['item'].lower()
                 or s in i['sub_category'].lower()
                 or s in str(i.get('notes', '')).lower()]
    total = len(items)
    items_page = items[offset:offset + limit]
    return {'total': total, 'limit': limit, 'offset': offset, 'items': items_page}

def get_catalogue_item(item_id: str):
    """Get a single catalogue entry by ID."""
    for i in _CATALOGUE['items']:
        if i['id'] == item_id:
            return i
    return None
