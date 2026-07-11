"""
The one invariant that must never silently drift: the legacy estimating
engine's calibration against the EGWA-2 field test. This has been manually
re-verified by hand across many sessions — it deserves a real test."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_pipeline_default_calibration_unchanged():
    from app.engine import estimate_pipeline, PipelineInput
    result = estimate_pipeline(PipelineInput())
    assert round(result.total.mid) == 870175, (
        f"REGRESSION: pipeline default calibration is {round(result.total.mid)}, "
        "expected 870175 (the EGWA-2 field-test anchor)."
    )
