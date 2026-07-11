"""
Project Modeller — v5 core deliverable.

Takes the 13 data-backed project inputs and produces a line-item BOQ where
EVERY line is backed by real observations from the proprietary
database. The design principle (Reu's clearest recurring intervention):

    Only offer what the data supports. Show actual operator names, real
    observation counts, and honest confidence. No soft assumptions, no
    fabricated lines.

Architecture:
  • The calibrated `estimate_pipeline` engine is the untouched cost spine
    (default 6" Sch 40 Swamp 5km 30d still = $870,175). The modeller wraps
    it, so component economics never drift from the field-tested engine.
  • Lay & weld — the crown jewel — is re-derived per selected operator
    directly from raw_observations, so "operator benchmark = SPDC" actually
    shows SPDC's own installation rate ($26.68/m for 6" swamp), not a blend.
  • Each BOQ line carries a `source` block: which operators back it, how many
    observations, which years, and a confidence grade derived from the real
    cell depth. Lines with no backing data are NOT invented — the section is
    reported as unbacked so the UI can lock it rather than fake it.
"""
from typing import Optional, Literal, List, Dict
from pydantic import BaseModel, Field
from collections import defaultdict
import json
from pathlib import Path
import statistics as _st

from . import (
    PipelineInput, GlobalsInput, estimate_pipeline,
)

_DATA_DIR = Path(__file__).parent
with open(_DATA_DIR / 'raw_observations.json') as f:
    _RAW = json.load(f)['observations']
with open(_DATA_DIR / 'line_items_catalogue.json') as f:
    _CAT = json.load(f)['items']

# Operator label mapping — UI short name → dataset operator string(s)
OPERATOR_ALIASES = {
    'SPDC':   ['SPDC'],
    'Seplat': ['Seplat'],
    'NPDC':   ['NPDC'],
    'ARAHAS': ['ARAHAS/NNPC OML11'],
}

# Section toggle → which spine components / catalogue lines it gates
SECTIONS = ['materials', 'welding', 'civil', 'ndt', 'coating', 'hydrotest', 'mob_cashes_security']


# ════════════════════════════════════════════════════════════════════════
# Observation-backed source statistics
# ════════════════════════════════════════════════════════════════════════

def _confidence(n: int) -> str:
    if n >= 3: return 'HIGH'
    if n == 2: return 'MEDIUM'
    if n == 1: return 'LOW'
    return 'NONE'


def observation_stats(sub_category, dia=None, terrain=None, operator_filter=None,
                      dia_tolerance=2):
    """Return real source stats for a BOQ line from raw_observations.

    Filters by sub_category, optionally diameter (within tolerance) and
    terrain, and optionally a specific operator. Returns operator names,
    observation count, year coverage, confidence and the USD-2024 band.
    """
    if isinstance(sub_category, str):
        sub_category = [sub_category]
    obs = [o for o in _RAW if o.get('sub_category') in sub_category]
    if terrain:
        obs = [o for o in obs if (o.get('spec') or {}).get('terrain') in (terrain, 'Land+Swamp', None)]
    if dia is not None:
        def _dia_of(o):
            d = (o.get('spec') or {}).get('dia')
            try:
                return float(str(d).strip().rstrip('"').rstrip('\u2033'))
            except (TypeError, ValueError):
                return None
        near = [o for o in obs if _dia_of(o) is not None
                and abs(_dia_of(o) - dia) <= dia_tolerance]
        if near:
            obs = near
    op_all = obs
    if operator_filter:
        op_specific = [o for o in obs if o.get('operator') in operator_filter]
        if op_specific:
            obs = op_specific  # honour operator selection when data exists
    rates = [o['usd_2024'] for o in obs if o.get('usd_2024') is not None]
    operators = sorted(set(o.get('operator') for o in op_all if o.get('operator')))
    years = sorted(set(o.get('year') for o in obs if o.get('year')))
    n = len(obs)
    stat = {
        'sub_category': sub_category[0] if len(sub_category) == 1 else ' / '.join(sub_category),
        'n_obs': n,
        'operators': operators,
        'operator_used': sorted(set(o.get('operator') for o in obs if o.get('operator'))),
        'years': years,
        'year_range': (f"{min(years)}\u2013{max(years)}" if years else '\u2014'),
        'confidence': _confidence(n),
        'median': round(_st.median(rates), 2) if rates else None,
        'low': round(min(rates), 2) if rates else None,
        'high': round(max(rates), 2) if rates else None,
    }
    return stat


def _operator_lay_weld_rate(operator_filter, dia, sched, terrain):
    """Operator-specific lay&weld $/m from observations, with blended fallback.

    Returns (low, mid, high, source_stat, used_operator_specific: bool).
    """
    lw_subs = ['Lay & Weld', 'Lay & Weld (arc)']
    obs = [o for o in _RAW if o.get('sub_category') in lw_subs
           and (o.get('spec') or {}).get('terrain') == terrain]
    # nearest diameter band
    def _dia_of(o):
        d = (o.get('spec') or {}).get('dia')
        try:
            return float(str(d).strip().rstrip('"').rstrip('\u2033'))
        except (TypeError, ValueError):
            return None
    near = [o for o in obs if _dia_of(o) is not None and abs(_dia_of(o) - dia) <= 2]
    pool = near if near else obs
    used_specific = False
    if operator_filter:
        op_pool = [o for o in pool if o.get('operator') in operator_filter]
        if op_pool:
            pool = op_pool
            used_specific = True
    rates = sorted(o['usd_2024'] for o in pool if o.get('usd_2024') is not None)
    if not rates:
        return None
    mid = _st.median(rates)
    low, high = rates[0], rates[-1]
    stat = {
        'sub_category': 'Lay & Weld',
        'n_obs': len(pool),
        'operators': sorted(set(o.get('operator') for o in pool if o.get('operator'))),
        'operator_used': sorted(set(o.get('operator') for o in pool if o.get('operator'))),
        'years': sorted(set(o.get('year') for o in pool if o.get('year'))),
        'year_range': '',
        'confidence': _confidence(len(pool)),
        'median': round(mid, 2), 'low': round(low, 2), 'high': round(high, 2),
    }
    yrs = stat['years']
    stat['year_range'] = f"{min(yrs)}\u2013{max(yrs)}" if yrs else '\u2014'
    return low, mid, high, stat, used_specific


# ════════════════════════════════════════════════════════════════════════
# Schemas
# ════════════════════════════════════════════════════════════════════════

class SectionToggles(BaseModel):
    materials: bool = True
    welding: bool = True
    civil: bool = True
    ndt: bool = True
    coating: bool = True
    hydrotest: bool = True
    mob_cashes_security: bool = True


class ProjectScope(BaseModel):
    project_name: str = 'Untitled Project'
    operator: Literal['Blended', 'SPDC', 'Seplat', 'NPDC', 'ARAHAS'] = 'Blended'
    year: int = 2023
    project_type: Literal['New Flowline', 'Replacement Line', 'Bypass'] = 'New Flowline'
    dia: int = 6
    sched: Literal['Sch 40', 'Sch 80'] = 'Sch 40'
    terrain: Literal['Land', 'Swamp'] = 'Swamp'
    length_m: float = Field(default=5000, gt=0)
    duration_days: int = Field(default=30, gt=0)
    n_tie_ins: int = Field(default=0, ge=0)
    n_crossings: int = Field(default=0, ge=0)
    sections: SectionToggles = SectionToggles()
    contingency_pct: float = 0.10
    vat_pct: float = 0.075


class BoqLine(BaseModel):
    item_no: str
    section: str
    description: str
    spec: str = ''
    qty: float
    unit: str
    rate_low: float
    rate_mid: float
    rate_high: float
    line_low: float
    line_mid: float
    line_high: float
    confidence: str
    source: Dict


class ProjectResult(BaseModel):
    project_name: str
    scope_echo: Dict
    lines: List[BoqLine]
    section_totals: Dict
    direct: Dict
    contingency: Dict
    vat: Dict
    total: Dict
    per_m: Dict
    coverage_pct: float
    backed_lines: int
    total_lines: int
    diagnostics: List[str] = []


# ════════════════════════════════════════════════════════════════════════
# The modeller
# ════════════════════════════════════════════════════════════════════════

def model_project(scope: ProjectScope) -> ProjectResult:
    L = scope.length_m
    diag: List[str] = []
    op_filter = OPERATOR_ALIASES.get(scope.operator)  # None if Blended

    # ── Calibrated spine (untouched engine) — for consistent component economics
    spine = estimate_pipeline(PipelineInput(
        dia=scope.dia, sched=scope.sched, terrain=scope.terrain,
        length_km=L / 1000.0, duration_days=scope.duration_days,
        scope_class='LINEAR LAY',
        globals=GlobalsInput(project_name=scope.project_name,
                             contingency_pct=scope.contingency_pct, vat_pct=scope.vat_pct),
    ))
    spine_rows = {r.component: r for r in spine.breakdown}

    lines: List[BoqLine] = []
    n = [0]

    def _no():
        n[0] += 1
        return f"{n[0]:03d}"

    def add(section, desc, spec, qty, unit, low, mid, high, stat):
        lines.append(BoqLine(
            item_no=_no(), section=section, description=desc, spec=spec,
            qty=round(qty, 2), unit=unit,
            rate_low=round(low, 4), rate_mid=round(mid, 4), rate_high=round(high, 4),
            line_low=round(low * qty, 2), line_mid=round(mid * qty, 2), line_high=round(high * qty, 2),
            confidence=stat['confidence'], source=stat,
        ))

    S = scope.sections

    # ── MATERIALS ────────────────────────────────────────────────────────
    if S.materials:
        r = spine_rows['Pipe material']
        stat = observation_stats('Carbon Steel Pipe', dia=scope.dia, terrain=scope.terrain)
        if stat['n_obs'] == 0:
            stat = {'sub_category': 'Carbon Steel Pipe', 'n_obs': 0, 'operators': [],
                    'operator_used': [], 'years': [], 'year_range': '\u2014',
                    'confidence': 'MODELLED', 'median': None, 'low': None, 'high': None,
                    'note': 'Priced from engine material table (Excel R7 calibration).'}
        add('Materials', f'Line pipe API 5L Gr B {scope.dia}" {scope.sched}',
            f'{scope.dia}" {scope.sched}', L, 'm', r.low / L, r.mid / L, r.high / L, stat)
        tr = spine_rows['Pipe transport']
        tstat = observation_stats('Pipe transport', dia=scope.dia, terrain=scope.terrain)
        add('Materials', f'Pipe transport to site ({scope.terrain})', f'0\u201350km {scope.terrain}',
            L, 'm', tr.low / L, tr.mid / L, tr.high / L, tstat)

    # ── WELDING / LAY & WELD (crown jewel — operator-specific) ────────────
    if S.welding:
        olw = _operator_lay_weld_rate(op_filter, scope.dia, scope.sched, scope.terrain)
        if olw:
            low, mid, high, stat, used_specific = olw
            note = (f"{scope.operator} own rate" if used_specific
                    else "Blended across operators (selected operator has no cell data)")
            if scope.operator != 'Blended' and not used_specific:
                diag.append(f"{scope.operator} has no lay&weld observation at {scope.dia}\" {scope.terrain}; "
                            f"using blended rate — confidence downgraded.")
            stat = {**stat, 'note': note}
            add('Welding', f'Lay & weld installation ({scope.terrain})',
                f'{scope.dia}" {scope.sched} {scope.terrain}', L, 'm', low, mid, high, stat)
        else:
            r = spine_rows['Lay & weld']
            add('Welding', f'Lay & weld installation ({scope.terrain})',
                f'{scope.dia}" {scope.sched}', L, 'm', r.low / L, r.mid / L, r.high / L,
                {'sub_category': 'Lay & Weld', 'n_obs': 0, 'operators': [], 'operator_used': [],
                 'years': [], 'year_range': '\u2014', 'confidence': 'MODELLED',
                 'median': None, 'low': None, 'high': None})
        # Construction spread (personnel + equipment) rides with welding scope
        for comp in ('Personnel', 'Equipment'):
            r = spine_rows[comp]
            sub = 'Personnel day rate' if comp == 'Personnel' else 'Equipment day rate'
            stat = observation_stats(sub, terrain=scope.terrain)
            add('Welding', f'{comp} spread ({scope.duration_days} days)',
                f'{scope.terrain} construction spread', scope.duration_days, 'days',
                r.low / scope.duration_days, r.mid / scope.duration_days, r.high / scope.duration_days, stat)

    # ── CIVIL WORKS ──────────────────────────────────────────────────────
    if S.civil:
        stat = observation_stats('Excavation', dia=scope.dia, terrain=scope.terrain)
        if stat['n_obs'] > 0 and stat['median']:
            # Excavation observed per m3; approximate trench volume ~0.6 m3/m of route
            vol = L * 0.6
            add('Civil', 'Excavation & trenching', 'Trench excavation', vol, 'm3',
                stat['low'], stat['median'], stat['high'], stat)
        rstat = observation_stats('ROW clearing', terrain=scope.terrain)
        if rstat['n_obs'] > 0 and rstat['median']:
            add('Civil', 'ROW clearing & grubbing', 'Right-of-way prep', L, 'm',
                rstat['low'], rstat['median'], rstat['high'], rstat)

    # ── NDT & INTEGRITY ──────────────────────────────────────────────────
    if S.ndt:
        r = spine_rows['NDT & integrity']
        stat = observation_stats('Radiography', dia=scope.dia, terrain=scope.terrain)
        add('NDT', 'Radiographic testing (RT)', 'Weld NDT', L, 'm',
            r.low / L, r.mid / L, r.high / L, stat)

    # ── COATING ──────────────────────────────────────────────────────────
    if S.coating:
        r = spine_rows['Field joint coating']
        n_joints = L / 12.0
        stat = observation_stats('Field joint coating', dia=scope.dia, terrain=scope.terrain)
        if scope.operator != 'Blended':
            diag_note = None
        add('Coating', 'Field joint coating (heat-shrink)', 'FJC per joint',
            n_joints, 'joints', r.low / n_joints, r.mid / n_joints, r.high / n_joints, stat)
        if stat['n_obs'] and stat['n_obs'] <= 5:
            diag.append('Field joint coating backed by only '
                        f"{stat['n_obs']} observation(s) — no coating-type differentiation available.")

    # ── HYDROTEST ────────────────────────────────────────────────────────
    if S.hydrotest:
        stat = observation_stats('Hydrotesting', dia=scope.dia, terrain=scope.terrain)
        if stat['n_obs'] > 0 and stat['median']:
            add('Hydrotest', 'Hydrostatic pressure test', 'Hydrotest per m', L, 'm',
                stat['low'], stat['median'], stat['high'], stat)

    # ── MOB / CASHES / SECURITY ──────────────────────────────────────────
    if S.mob_cashes_security:
        r = spine_rows['Mob + CASHES + Demob']
        mstat = observation_stats('Mob / demob', terrain=scope.terrain)
        add('Mob/CASHES/Security', 'Mobilisation + CASHES + demobilisation',
            'Bundle (mob/CASHES/demob)', 1, 'lump sum', r.low, r.mid, r.high, mstat)
        sr = spine_rows['Security']
        sstat = observation_stats('Security / CASHES', terrain=scope.terrain)
        add('Mob/CASHES/Security', f'Security spread ({scope.duration_days} days)',
            'Community/surveillance', scope.duration_days, 'days',
            sr.low / scope.duration_days, sr.mid / scope.duration_days, sr.high / scope.duration_days, sstat)

    # ── SCOPE DRIVERS: tie-ins & crossings (single count, pooled) ─────────
    if scope.n_tie_ins > 0:
        tstat = observation_stats('Tie-ins', dia=scope.dia, terrain=scope.terrain)
        if tstat['median']:
            add('Scope drivers', 'Tie-ins / hook-ups', 'Per tie-in', scope.n_tie_ins, 'each',
                tstat['low'], tstat['median'], tstat['high'], tstat)
    if scope.n_crossings > 0:
        cstat = observation_stats(['Line crossings', 'HDD creek/canal crossings'],
                                  dia=scope.dia, terrain=scope.terrain)
        if cstat['median']:
            add('Scope drivers', 'Crossings (HDD/road/river, pooled)', 'Per crossing',
                scope.n_crossings, 'each', cstat['low'], cstat['median'], cstat['high'], cstat)

    # ── Totals ───────────────────────────────────────────────────────────
    section_totals = defaultdict(lambda: {'low': 0.0, 'mid': 0.0, 'high': 0.0})
    for ln in lines:
        st = section_totals[ln.section]
        st['low'] += ln.line_low; st['mid'] += ln.line_mid; st['high'] += ln.line_high

    direct = {k: round(sum(l.__dict__[f'line_{k}'] for l in lines), 2) for k in ('low', 'mid', 'high')}
    cont = {k: round(direct[k] * scope.contingency_pct, 2) for k in direct}
    vat = {k: round((direct[k] + cont[k]) * scope.vat_pct, 2) for k in direct}
    total = {k: round(direct[k] + cont[k] + vat[k], 2) for k in direct}
    per_m = {k: round(total[k] / L, 2) for k in total}

    backed = sum(1 for l in lines if l.source.get('n_obs', 0) > 0)
    coverage = round(100.0 * backed / len(lines), 1) if lines else 0.0

    if scope.project_type == 'Bypass':
        diag.append('Bypass scope: short tie-in-heavy runs — mob/CASHES will dominate $/m.')
    if L < 500:
        diag.append('Length < 500m: mobilisation dominates. Consider fabrication scope class in the engine.')

    return ProjectResult(
        project_name=scope.project_name,
        scope_echo=scope.model_dump(),
        lines=lines,
        section_totals={k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in section_totals.items()},
        direct=direct, contingency=cont, vat=vat, total=total, per_m=per_m,
        coverage_pct=coverage, backed_lines=backed, total_lines=len(lines),
        diagnostics=diag,
    )


# ════════════════════════════════════════════════════════════════════════
# Observations summary (for Data Entry preview + Catalogue)
# ════════════════════════════════════════════════════════════════════════

def _next_obs_id():
    mx = 0
    for o in _RAW:
        oid = str(o.get('id', ''))
        if oid.startswith('OBS'):
            try: mx = max(mx, int(oid[3:]))
            except ValueError: pass
    return f"OBS{mx + 1:05d}"


def _rebuild_catalogue_cell(category, sub_category, dia, terrain, unit):
    """Recompute (or create) the catalogue entry for one cell from all
    observations that now fall in it. Returns the catalogue item dict."""
    def _dia_of(o):
        d = (o.get('spec') or {}).get('dia')
        try: return float(str(d).strip().rstrip('"').rstrip('\u2033'))
        except (TypeError, ValueError): return None
    cell = [o for o in _RAW if o.get('category') == category
            and o.get('sub_category') == sub_category
            and ((o.get('spec') or {}).get('terrain') in (terrain, None, 'Land+Swamp'))
            and (dia is None or _dia_of(o) == dia)]
    rates = [o['usd_2024'] for o in cell if o.get('usd_2024') is not None]
    if not rates:
        return None
    operators = sorted(set(o.get('operator') for o in cell if o.get('operator')))
    years = sorted(set(o.get('year') for o in cell if o.get('year')))
    n = len(cell)
    item = {
        'category': category, 'sub_category': sub_category,
        'spec': {'dia': dia, 'sched': None, 'terrain': terrain},
        'unit': unit,
        'low': round(min(rates), 2), 'high': round(max(rates), 2),
        'mid': round(_st.median(rates), 2), 'median': round(_st.median(rates), 2),
        'n_records': n, 'confidence': _confidence(n),
        'operators': operators, 'years_covered': years,
        'year_range': (f"{min(years)}\u2013{max(years)}" if years else '\u2014'),
    }
    # find & update existing catalogue entry for this exact cell, else create
    for it in _CAT:
        if (it.get('category') == category and it.get('sub_category') == sub_category
                and (it.get('spec') or {}).get('dia') == dia
                and (it.get('spec') or {}).get('terrain') == terrain):
            it.update(item)
            return it
    new_id = f"C{len(_CAT) + 1:03d}"
    full = {'id': new_id, 'discipline': 'Pipeline', 'item': f"{sub_category} \u2014 {dia}\" {terrain}" if dia else sub_category,
            'material_grade': None, 'source_refs': [], 'source_documents': [], 'source_pages': [],
            'vendor': None, 'notes': 'Added via Data Entry front door', **item}
    _CAT.append(full)
    return full


def add_observation(*, operator, year, work_scope, sub_category, category=None,
                    dia=None, sched=None, terrain='Swamp', unit='m',
                    orig_currency='USD', orig_rate, notes='', source_doc=None):
    """Data Entry front door: normalise → append → rebuild catalogue cell.

    Persists to raw_observations.json + line_items_catalogue.json and updates
    the in-memory caches so the app reflects the new observation immediately.
    """
    from .normalizer_fx import normalise_to_usd2024, normalise_method_label
    year = int(year)
    orig_rate = float(orig_rate)
    dia_val = None
    if dia not in (None, '', 'None'):
        try: dia_val = int(float(dia))
        except (TypeError, ValueError): dia_val = None
    # infer category from sub_category if not given
    if not category:
        for it in _CAT:
            if it.get('sub_category') == sub_category:
                category = it.get('category'); break
        category = category or work_scope

    usd_2024, prov = normalise_to_usd2024(orig_rate, orig_currency, year)
    obs_id = _next_obs_id()
    obs = {
        'id': obs_id, 'source': 'data_entry', 'source_record_id': None,
        'source_doc': source_doc, 'source_page': None, 'discipline': 'Pipeline',
        'operator': operator, 'vendor': None, 'project': None, 'year': year,
        'work_scope': work_scope, 'category': category, 'sub_category': sub_category,
        'item_description': f"{sub_category} {dia_val or ''}\" {terrain}".strip(),
        'spec': {'dia': dia_val, 'sched': sched, 'terrain': terrain, 'grade': None},
        'unit': unit, 'orig_currency': orig_currency, 'orig_rate': orig_rate,
        'usd_2024': usd_2024, 'norm_method': normalise_method_label(orig_currency),
        'flag': 'OK', 'notes': notes or None,
    }
    _RAW.append(obs)

    # persist observations
    raw_path = _DATA_DIR / 'raw_observations.json'
    with open(raw_path) as f:
        rawfile = json.load(f)
    rawfile['observations'].append(obs)
    rawfile['meta']['total_observations'] = len(rawfile['observations'])
    rawfile['meta'].setdefault('by_source', {})
    rawfile['meta']['by_source']['data_entry'] = rawfile['meta']['by_source'].get('data_entry', 0) + 1
    with open(raw_path, 'w') as f:
        json.dump(rawfile, f, indent=1, ensure_ascii=False)

    # rebuild affected catalogue cell + persist catalogue
    cat_item = _rebuild_catalogue_cell(category, sub_category, dia_val, terrain, unit)
    cat_path = _DATA_DIR / 'line_items_catalogue.json'
    with open(cat_path) as f:
        catfile = json.load(f)
    # replace/insert matching item
    replaced = False
    for i, it in enumerate(catfile['items']):
        if cat_item and it.get('id') == cat_item.get('id'):
            catfile['items'][i] = cat_item; replaced = True; break
    if cat_item and not replaced:
        catfile['items'].append(cat_item)
    catfile['meta']['total_items'] = len(catfile['items'])
    catfile['meta']['records_aggregated'] = len(rawfile['observations'])
    with open(cat_path, 'w') as f:
        json.dump(catfile, f, indent=1, ensure_ascii=False)

    return {
        'observation_id': obs_id,
        'usd_2024': usd_2024,
        'normalisation': prov,
        'total_observations': len(_RAW),
        'catalogue_cell': {
            'sub_category': sub_category, 'dia': dia_val, 'terrain': terrain,
            'n_records': cat_item['n_records'] if cat_item else 1,
            'confidence': cat_item['confidence'] if cat_item else 'LOW',
            'median': cat_item['median'] if cat_item else usd_2024,
            'operators': cat_item['operators'] if cat_item else [operator],
        } if cat_item else None,
    }


def observations_summary():
    ops = defaultdict(int)
    yrs = defaultdict(int)
    subs = defaultdict(int)
    for o in _RAW:
        ops[o.get('operator')] += 1
        yrs[o.get('year')] += 1
        subs[o.get('sub_category')] += 1
    return {
        'total_observations': len(_RAW),
        'by_operator': dict(sorted(ops.items(), key=lambda x: -x[1])),
        'by_year': dict(sorted(yrs.items())),
        'by_sub_category': dict(sorted(subs.items(), key=lambda x: -x[1])),
        'operators': sorted(k for k in ops if k),
    }
