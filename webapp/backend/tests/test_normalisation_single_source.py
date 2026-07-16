"""
Priority 2 guard: there must be exactly ONE FX / inflation table in the codebase.

History: the legacy engine's `normalizer_fx.py` carried its own hardcoded copy of
US_PPI_FG and CBN_OFFICIAL_FX, byte-identical to the seed tables in
`app/core/escalation.py`. Two literals for one truth is a silent-divergence bug
waiting to happen: add a 2026 data point to one and not the other and the two
engines quietly compute different dollar values for the same raw observation.

`normalizer_fx` was reachable only from `project_modeller.add_observation()`,
which was itself orphaned when the legacy unauthenticated write route
`POST /api/observations/add` was deleted. Dead table in a dead function — so the
fix was deletion, not a wrapper.

These tests fail if anyone reintroduces a second table.
"""
import ast
import pathlib

import pytest
from sqlmodel import Session

from app.core.db import engine
from app.core.escalation import normalise

APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "app"

# The single file permitted to hold the raw series literals.
SOLE_SOURCE = APP_DIR / "core" / "escalation.py"

# Sentinel values unique to the FX / PPI-FG series. If these floats appear as
# live code constants anywhere else, someone has cloned the table again.
SENTINELS = {
    645.16,     # CBN NGN/USD 2023  — the Seplat anchor
    1486.57,    # CBN NGN/USD 2024
    401.15,     # CBN NGN/USD 2021
    199.91,     # US PPI-FG 2017    — the SPDC anchor
    257.70,     # US PPI-FG 2024    — the reference year
}


def test_normalizer_fx_module_is_gone():
    """The legacy duplicate-table module must stay deleted."""
    with pytest.raises(ModuleNotFoundError):
        import app.engine.normalizer_fx  # noqa: F401


def test_dead_write_path_stays_deleted():
    """`add_observation` and its private helpers were the only consumers of the
    duplicate table. If they come back, the table tends to come back with them.
    """
    import app.engine.project_modeller as pm

    for name in ("add_observation", "observations_summary",
                 "_rebuild_catalogue_cell", "_next_obs_id"):
        assert not hasattr(pm, name), (
            f"REGRESSION: project_modeller.{name}() is back. This was dead code "
            "orphaned by the removal of POST /api/observations/add. The secured "
            "path is app/core/service.py -> escalation.normalise()."
        )


def test_exactly_one_fx_table_in_the_codebase():
    """Parse every module's AST and look for the series values as *live* float
    constants.

    Walking the AST rather than grepping the text is deliberate: it ignores
    comments and docstrings, so the illustrative `{"2017": 199.91, ...}` in the
    models.py docstring is correctly not counted as a second table, while an
    actual dict literal anywhere would be.
    """
    offenders = {}

    for path in sorted(APP_DIR.rglob("*.py")):
        if path == SOLE_SOURCE:
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:  # pragma: no cover
            continue

        hits = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, float)
            and node.value in SENTINELS
        }
        if hits:
            offenders[path.relative_to(APP_DIR.parent)] = sorted(hits)

    assert not offenders, (
        "REGRESSION: FX / PPI-FG series values found as live constants outside "
        f"{SOLE_SOURCE.name}: {offenders}. There must be exactly one escalation "
        "table, seeded into the EscalationIndex table and read through "
        "escalation.normalise(). Do not clone it back into the engine."
    )


def test_sole_source_still_reproduces_the_documented_anchors(app_client):
    """The one surviving table must still produce the two published factors the
    440-observation dataset was normalised with. If these move, every benchmark
    in the platform silently moves with them.
    """
    with Session(engine) as s:
        # SPDC 2017 anchor: USD 2017 -> USD 2024 = 257.70 / 199.91 = 1.28908
        usd, prov = normalise(s, orig_rate=20.70, currency="USD", year=2017)
        assert round(prov["escalation"], 5) == 1.28908
        assert round(usd, 2) == 26.68, "SPDC 2017 6in swamp lay/weld anchor moved"

        # Seplat 2023 anchor: NGN 12,911.50/m -> /645.16 -> x(257.70/254.60)
        ngn, prov_ngn = normalise(s, orig_rate=12911.50, currency="NGN", year=2023)
        assert prov_ngn["cbn_fx"] == 645.16
        assert round(prov_ngn["combined_factor"], 6) == 0.001569
        assert round(ngn, 2) == 20.26, "Seplat 2023 6in swamp lay/weld anchor moved"
