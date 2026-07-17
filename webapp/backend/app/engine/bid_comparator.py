"""
Multi-vendor bid comparison logic.

Imported by both serve.py and main.py for the /api/bid-comparison endpoint.
"""


def build_bid_comparison(vendor_reports):
    """Compute side-by-side comparison + recommendation from N parsed vendor reports.

    Args:
        vendor_reports: list of {'vendor_label': str, 'filename': str, 'report': <analyze_tender output>}

    Returns:
        dict with vendor_summary, ranked, recommendation, line_matrix
    """
    # 1. Vendor totals
    vendor_summary = []
    for v in vendor_reports:
        es = v['report']['executive_summary']
        ps = v['report']['procurement_summary']
        deltas = []
        for line in v['report']['line_items']:
            if line['variance'] and line['variance'].get('delta_pct') is not None:
                deltas.append(line['variance']['delta_pct'])
        mean_delta = sum(deltas) / len(deltas) if deltas else 0
        abs_mean_delta = sum(abs(d) for d in deltas) / len(deltas) if deltas else 0
        vendor_summary.append({
            'vendor_label': v['vendor_label'],
            'filename': v['filename'],
            'total_vendor_value': es['total_vendor_value_usd'],
            'total_benchmark_value': es['total_benchmark_value_usd'],
            'savings_opportunity': es['total_savings_opportunity_usd'],
            'matched_items': ps['items_matched'],
            'unmatched_items': ps['items_unmatched'],
            'coverage_pct': ps['benchmark_coverage_pct'],
            'verdict_counts': ps['verdict_counts'],
            'mean_delta_pct': round(mean_delta, 3),
            'abs_mean_delta_pct': round(abs_mean_delta, 3),
        })

    # 2. Recommendation: lowest priced bid within acceptable deviation band
    candidates = []
    for v in vendor_summary:
        red = v['verdict_counts'].get('RED', 0)
        matched = max(v['matched_items'], 1)
        red_pct = red / matched
        accepted_avg = v['abs_mean_delta_pct'] <= 0.30
        accepted_red = red_pct <= 0.40
        accepted_below = v['mean_delta_pct'] >= -0.35
        unsustainable = v['mean_delta_pct'] < -0.35
        v['acceptable'] = bool(accepted_avg and accepted_red and accepted_below)
        v['unsustainable_risk'] = bool(unsustainable)
        v['red_line_pct'] = round(red_pct, 3)
        if v['acceptable']:
            candidates.append(v)

    candidates.sort(key=lambda x: x['total_vendor_value'])
    ranked = sorted(vendor_summary, key=lambda x: (
        0 if x['acceptable'] else 1,
        x['total_vendor_value']
    ))
    for i, v in enumerate(ranked):
        v['rank'] = i + 1
        v['recommended'] = (v == candidates[0]) if candidates else False
        v['lowest_overall'] = (v['total_vendor_value'] == min(s['total_vendor_value'] for s in vendor_summary))

    recommended = candidates[0] if candidates else None
    lowest = min(vendor_summary, key=lambda x: x['total_vendor_value'])

    # 3. Side-by-side line item matrix — grouped by the CANONICAL benchmark
    #    catalogue item each vendor line actually matched to, never by raw
    #    row position.
    #
    #    History: the original implementation zipped vendors' line_items
    #    lists together by index (row N = vendor['line_items'][N] for every
    #    vendor), on the unstated assumption that every vendor itemizes
    #    their BOQ in the same order. Two vendors bidding the identical
    #    scope but listing "pipe transport" before "line pipe" (a completely
    #    ordinary difference in how contractors format a BOQ) produced a row
    #    labelled "Line pipe" that silently compared one vendor's pipe rate
    #    against the other vendor's transport rate — same row, different
    #    physical items, no error, no warning. Confirmed live: two vendors
    #    bidding the same 3-item scope in different order returned exactly
    #    that mismatch (see tests/test_bid_comparator.py).
    #
    #    It also explains why "Bench Mid" rendered blank in the UI: the row
    #    dict never set a top-level bench_mid at all — only a per-vendor
    #    copy nested under row['vendors'][label]['bench_mid'], which the
    #    frontend's single Bench Mid column never reads.
    #
    #    Fix: key rows by catalogue_id (the actual matched benchmark item,
    #    identical for every vendor regardless of their own row order/count),
    #    with one authoritative bench_mid per row. Vendor lines that matched
    #    nothing are kept — never silently dropped or force-fit into an
    #    unrelated row — as unmatched_lines, per vendor, for the reviewer to
    #    see explicitly.
    rows_by_cat = {}
    row_order = []
    unmatched_lines = []

    for v in vendor_reports:
        for line in v['report']['line_items']:
            variance = line.get('variance')
            cat_id = variance.get('catalogue_id') if variance else None
            if not cat_id:
                unmatched_lines.append({
                    'vendor_label': v['vendor_label'],
                    'description': line.get('description', ''),
                    'unit': line.get('unit', ''),
                    'rate': line.get('vendor_rate'),
                    'amount': line.get('vendor_amount'),
                })
                continue
            if cat_id not in rows_by_cat:
                row_order.append(cat_id)
                rows_by_cat[cat_id] = {
                    'catalogue_id': cat_id,
                    'description': variance.get('catalogue_item') or line.get('description', ''),
                    'unit': line.get('unit', ''),
                    'bench_mid': variance.get('benchmark_mid'),
                    'vendors': {},
                }
            rows_by_cat[cat_id]['vendors'][v['vendor_label']] = {
                'rate':      line.get('vendor_rate'),
                'amount':    line.get('vendor_amount'),
                'verdict':   line.get('verdict'),
                'delta_pct': variance.get('delta_pct'),
                'bench_mid': variance.get('benchmark_mid'),
            }

    line_matrix = []
    for i, cat_id in enumerate(row_order):
        row = rows_by_cat[cat_id]
        for v in vendor_reports:
            row['vendors'].setdefault(v['vendor_label'], None)
        rates = [(label, vd['rate']) for label, vd in row['vendors'].items() if vd and vd.get('rate')]
        if rates:
            row['lowest_vendor'] = min(rates, key=lambda x: x[1])[0]
        row['line_index'] = i + 1
        line_matrix.append(row)

    return {
        'vendor_summary': vendor_summary,
        'ranked': ranked,
        'recommendation': {
            'recommended_vendor': recommended['vendor_label'] if recommended else None,
            'recommended_value':  recommended['total_vendor_value'] if recommended else None,
            'lowest_vendor':      lowest['vendor_label'],
            'lowest_value':       lowest['total_vendor_value'],
            'rationale':          _build_recommendation_rationale(recommended, lowest),
        },
        'line_matrix': line_matrix,
        'unmatched_lines': unmatched_lines,
    }


def _build_recommendation_rationale(recommended, lowest):
    if not recommended:
        return ("No vendor passes the deviation criteria (mean ≤30%, RED lines ≤40%, "
                "no deep lowball). Recommend re-tender or detailed scope clarification.")
    if recommended['vendor_label'] == lowest['vendor_label']:
        return (f"{recommended['vendor_label']} is both the lowest price and within acceptable deviation. "
                f"Mean Δ from benchmark: {recommended['abs_mean_delta_pct']*100:.1f}%. "
                f"RED-verdict lines: {recommended['red_line_pct']*100:.0f}%.")
    return (f"{lowest['vendor_label']} is the lowest at ${lowest['total_vendor_value']:,.0f} "
            f"but flagged unacceptable "
            f"(unsustainable risk: {lowest['unsustainable_risk']}, "
            f"mean Δ {lowest['abs_mean_delta_pct']*100:.1f}%, "
            f"RED lines {lowest['red_line_pct']*100:.0f}%). "
            f"Recommend {recommended['vendor_label']} at ${recommended['total_vendor_value']:,.0f} — "
            f"lowest priced bid within acceptable deviation band.")
