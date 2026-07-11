"""
Tender Variance Reporting — Priority 5

Combines the parser + normalizer + matcher into the full procurement workflow:

  BOQ file → parse → normalize each line → fuzzy-match to catalogue → compute variance
  → return line-by-line report + executive summary + procurement summary

This is the headline procurement-engineer-ready output.
"""
from typing import Optional
from .boq_parser import parse_xlsx
from .boq_normalizer import normalize_boq_line
from .fuzzy_matcher import match_line_to_catalogue


# Verdict thresholds — applied to (vendor_rate - benchmark_mid) / benchmark_mid
VARIANCE_THRESHOLDS = {
    'green': 0.15,   # ±15% of Mid
    'amber': 0.30,   # ±15% to ±30%
    # beyond ±30% → RED
}


def _verdict(delta_pct: Optional[float], in_band: Optional[bool]) -> str:
    """Apply traffic-light verdict to a variance."""
    if delta_pct is None:
        return 'UNMATCHED'
    abs_d = abs(delta_pct)
    if abs_d <= VARIANCE_THRESHOLDS['green']:
        return 'GREEN'
    if abs_d <= VARIANCE_THRESHOLDS['amber']:
        return 'AMBER'
    return 'RED'


def analyze_tender(
    parsed_boq: dict,
    catalogue_items: list,
    project_name: str = '',
    vendor_name: str = '',
):
    """Run the full benchmark workflow on a parsed BOQ.

    Args:
        parsed_boq: output from parse_xlsx() / parse_csv()
        catalogue_items: list of catalogue entries (from line_items_catalogue.json items)
        project_name: optional tag
        vendor_name: optional tag

    Returns:
        {
          'header': {project_name, vendor_name, sheet, total_lines},
          'executive_summary': {...},
          'procurement_summary': {...},
          'line_items': [...]    # one entry per BOQ line with normalized + match + variance
        }
    """
    if not parsed_boq or not parsed_boq.get('rows'):
        return None

    line_results = []
    total_vendor_value = 0.0
    total_benchmark_value = 0.0   # what the catalogue Mid would have cost
    n_matched = 0
    n_unmatched = 0
    n_above = 0
    n_below = 0
    n_in_band = 0
    biggest_savings = []     # negative deltas (vendor below benchmark — savings opportunity if their rate prevails... but we want overpriced)
    biggest_overpriced = []  # positive deltas (vendor above benchmark — savings opportunity by negotiating down)

    for idx, line in enumerate(parsed_boq['rows']):
        desc = line['description']
        qty = line.get('qty')
        unit = line.get('unit')
        rate = line.get('rate')
        amount = line.get('amount')

        # Step 1: normalize
        norm = normalize_boq_line(desc, qty=qty, unit_hint=unit, rate=rate)

        # Step 2: fuzzy-match
        matches = match_line_to_catalogue(norm, catalogue_items, top_n=3) if norm else []
        # Only treat as "matched" if score >= 0.50 (LOW threshold raised from 0.40)
        best = None
        if matches and matches[0]['score'] >= 0.50:
            best = matches[0]

        # Step 3: compute variance vs best match's Mid
        variance = None
        if best and rate is not None and rate > 0:
            entry = best['entry']
            bm_low, bm_mid, bm_high = entry['low'], entry['mid'], entry['high']
            delta_pct = (rate - bm_mid) / bm_mid if bm_mid else None
            in_band   = bm_low <= rate <= bm_high if bm_mid else None
            verdict   = _verdict(delta_pct, in_band)
            variance = {
                'benchmark_low':   bm_low,
                'benchmark_mid':   bm_mid,
                'benchmark_high':  bm_high,
                'delta_pct':       round(delta_pct, 3) if delta_pct is not None else None,
                'delta_abs':       round(rate - bm_mid, 2) if delta_pct is not None else None,
                'in_band':         in_band,
                'verdict':         verdict,
                'match_score':     best['score'],
                'match_confidence': entry.get('confidence', 'LOW'),
                'catalogue_id':    entry['id'],
                'catalogue_item':  entry['item'],
            }
            # If this line has a qty, project the savings/overcharge across the whole line
            if qty:
                vendor_line_total = (rate * qty) if rate else (amount or 0)
                bench_line_total  = bm_mid * qty
                variance['line_savings_opportunity'] = round(vendor_line_total - bench_line_total, 2)

        # Track totals (only for matched items with qty + rate)
        line_amount = amount if amount else ((rate or 0) * (qty or 0))
        total_vendor_value += (line_amount or 0)
        if variance:
            n_matched += 1
            if variance['verdict'] == 'GREEN':
                n_in_band += 1
            if variance.get('delta_pct') is not None:
                if variance['delta_pct'] > 0.15:
                    n_above += 1
                    biggest_overpriced.append((idx, variance.get('line_savings_opportunity') or 0, desc, variance))
                elif variance['delta_pct'] < -0.15:
                    n_below += 1
                    biggest_savings.append((idx, abs(variance.get('line_savings_opportunity') or 0), desc, variance))
            if qty:
                total_benchmark_value += variance['benchmark_mid'] * qty
        else:
            n_unmatched += 1

        line_results.append({
            'line_index': idx + 1,
            'description': desc,
            'qty': qty,
            'unit': unit,
            'vendor_rate': rate,
            'vendor_amount': line_amount,
            'normalized': norm,
            'matches': matches,
            'variance': variance,
            'verdict': variance['verdict'] if variance else 'UNMATCHED',
        })

    # Build top-5 biggest variances (by absolute opportunity)
    biggest_overpriced.sort(key=lambda x: -x[1])
    biggest_savings.sort(key=lambda x: -x[1])
    top_overpriced = [{
        'line_index': i+1, 'description': d, 'overpriced_by_usd': round(v, 2),
        'delta_pct': var['delta_pct'], 'catalogue_id': var['catalogue_id'],
    } for (i, v, d, var) in biggest_overpriced[:5]]
    top_savings = [{
        'line_index': i+1, 'description': d, 'underpriced_by_usd': round(v, 2),
        'delta_pct': var['delta_pct'], 'catalogue_id': var['catalogue_id'],
    } for (i, v, d, var) in biggest_savings[:5]]

    total_lines = len(line_results)
    coverage_pct = (n_matched / total_lines) if total_lines > 0 else 0
    total_savings_opportunity = round(total_vendor_value - total_benchmark_value, 2) if n_matched > 0 else 0

    return {
        'header': {
            'project_name': project_name or '',
            'vendor_name':  vendor_name  or '',
            'sheet':        parsed_boq.get('sheet'),
            'header_row':   parsed_boq.get('header_row'),
            'columns':      parsed_boq.get('columns'),
            'total_lines':  total_lines,
        },
        'executive_summary': {
            'total_vendor_value_usd':    round(total_vendor_value, 2),
            'total_benchmark_value_usd': round(total_benchmark_value, 2),
            'total_savings_opportunity_usd': total_savings_opportunity,
            'savings_opportunity_pct':   round(total_savings_opportunity / total_vendor_value, 3) if total_vendor_value else 0,
            'top_overpriced_items':      top_overpriced,
            'top_savings_items':         top_savings,
        },
        'procurement_summary': {
            'items_total':           total_lines,
            'items_matched':         n_matched,
            'items_unmatched':       n_unmatched,
            'items_above_benchmark': n_above,
            'items_below_benchmark': n_below,
            'items_in_band':         n_in_band,
            'benchmark_coverage_pct': round(coverage_pct, 3),
            'verdict_counts': {
                'GREEN':     sum(1 for l in line_results if l['verdict'] == 'GREEN'),
                'AMBER':     sum(1 for l in line_results if l['verdict'] == 'AMBER'),
                'RED':       sum(1 for l in line_results if l['verdict'] == 'RED'),
                'UNMATCHED': sum(1 for l in line_results if l['verdict'] == 'UNMATCHED'),
            },
        },
        'line_items': line_results,
    }
