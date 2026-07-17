"""
Guard against the positional line-matrix bug found 7 days before the pitch
final: the original build_bid_comparison() zipped vendors' line_items lists
together by raw index, assuming every vendor itemizes their BOQ in the same
order. Two vendors bidding the identical 3-item scope but listing "pipe
transport" before "line pipe" produced a row labelled "Line pipe" that
silently compared one vendor's pipe rate against the other vendor's
transport rate.

Fix: rows are grouped by catalogue_id (the shared benchmark item each line
matched to), not by position. This test constructs exactly that
out-of-order scenario and asserts every row compares the correct rates.
"""
from app.engine.bid_comparator import build_bid_comparison


def _line(desc, cat_id, rate, bm_mid, unit='m'):
    return {
        'description': desc, 'unit': unit, 'vendor_rate': rate,
        'vendor_amount': rate * 100, 'verdict': 'GREEN',
        'variance': {'delta_pct': round((rate - bm_mid) / bm_mid, 3),
                     'benchmark_mid': bm_mid, 'catalogue_id': cat_id,
                     'catalogue_item': desc},
    }


def _vendor(label, lines, matched=None):
    matched = matched if matched is not None else len(lines)
    return {'vendor_label': label, 'filename': f'{label}.xlsx', 'report': {
        'executive_summary': {'total_vendor_value_usd': 0, 'total_benchmark_value_usd': 0,
                               'total_savings_opportunity_usd': 0},
        'procurement_summary': {'items_matched': matched, 'items_unmatched': len(lines) - matched,
                                 'benchmark_coverage_pct': 100, 'verdict_counts': {'GREEN': matched}},
        'line_items': lines,
    }}


def test_rows_align_by_catalogue_item_not_row_position():
    """The exact repro: same 3-item scope, different submission order."""
    vendor_a = _vendor('VendorA', [
        _line('Line pipe', 'PIPE', 50, 50),
        _line('Pipe transport', 'TRANSPORT', 5, 5),
        _line('Lay & weld', 'WELD', 25, 25),
    ])
    vendor_b = _vendor('VendorB', [
        _line('Pipe transport (site delivery)', 'TRANSPORT', 6, 5),
        _line('Line pipe API 5L', 'PIPE', 48, 50),
        _line('Lay & weld', 'WELD', 26, 25),
    ])

    result = build_bid_comparison([vendor_a, vendor_b])
    by_cat = {row['catalogue_id']: row for row in result['line_matrix']}

    assert by_cat['PIPE']['vendors']['VendorA']['rate'] == 50
    assert by_cat['PIPE']['vendors']['VendorB']['rate'] == 48, (
        "REGRESSION: PIPE row is comparing the wrong vendor rate — "
        "positional (row-index) matching is back."
    )
    assert by_cat['TRANSPORT']['vendors']['VendorA']['rate'] == 5
    assert by_cat['TRANSPORT']['vendors']['VendorB']['rate'] == 6
    assert by_cat['WELD']['vendors']['VendorA']['rate'] == 25
    assert by_cat['WELD']['vendors']['VendorB']['rate'] == 26


def test_bench_mid_is_populated_at_row_level():
    """The UI's single 'Bench Mid' column reads row.bench_mid directly —
    it must never render blank when a catalogue match exists."""
    vendor_a = _vendor('VendorA', [_line('Line pipe', 'PIPE', 50, 50)])
    result = build_bid_comparison([vendor_a, vendor_a])
    row = result['line_matrix'][0]
    assert row['bench_mid'] == 50, "REGRESSION: bench_mid missing from row — UI will show '—'"


def test_different_line_counts_do_not_corrupt_shorter_vendor_rows():
    """A vendor who priced fewer scope items must not have an unrelated
    vendor's extra line bleed into their column."""
    vendor_a = _vendor('VendorA', [
        _line('Line pipe', 'PIPE', 50, 50),
        _line('Lay & weld', 'WELD', 25, 25),
        _line('Radiographic testing', 'NDT', 12, 12),
    ])
    vendor_b = _vendor('VendorB', [
        _line('Line pipe', 'PIPE', 52, 50),
        _line('Lay & weld', 'WELD', 24, 25),
    ])  # VendorB simply didn't price NDT — a real, common scenario

    result = build_bid_comparison([vendor_a, vendor_b])
    by_cat = {row['catalogue_id']: row for row in result['line_matrix']}
    assert by_cat['NDT']['vendors']['VendorA']['rate'] == 12
    assert by_cat['NDT']['vendors']['VendorB'] is None, (
        "VendorB never priced NDT — must show as absent, not inherit "
        "another vendor's row by position."
    )


def test_unmatched_vendor_lines_are_surfaced_not_dropped():
    """A line with no catalogue match must appear in unmatched_lines,
    never silently vanish or get force-merged into an unrelated row."""
    vendor_a = _vendor('VendorA', [
        _line('Line pipe', 'PIPE', 50, 50),
        {'description': 'Custom scaffolding rental', 'unit': 'day',
         'vendor_rate': 300, 'vendor_amount': 3000, 'verdict': 'UNMATCHED',
         'variance': None},
    ], matched=1)

    result = build_bid_comparison([vendor_a, vendor_a])
    unmatched_descs = [u['description'] for u in result['unmatched_lines']]
    assert 'Custom scaffolding rental' in unmatched_descs
    assert len(result['line_matrix']) == 1  # only PIPE, the one real match
