"""
Normalisation engine — the ONE function, index chosen by data.

The engine is identical for every category. What differs is which escalation
series it reads (US PPI-FG for pipeline, a steel index for carbon steel, a
tech index for laptops...). That selection is a lookup on the category
ontology, never an `if category == ...` ladder — so a new category with its
own index is a DATA change.

Reproduces the existing 440-observation factors exactly:
  • USD 2017 → ×(257.70/199.91) = 1.28908
  • NGN 2023 → /645.16 × (257.70/254.60) = 0.001569  (Seplat anchor $20.26/m)
"""
from sqlmodel import Session, select
from .models import EscalationIndex

# Special key: NGN→USD FX (currency-level, stored as data like everything else)
FX_KEY = "CBN_NGN_USD"

# ─── Seed series (loaded once into EscalationIndex) ──────────────────────
_SEED = {
    "US_PPI_FG": {
        "name": "US PPI — Finished Goods",
        "source": "US BLS WPUFD49207 (FERC oil-pipeline escalation)",
        "ref_year": 2024,
        "series": {2015: 195.30, 2016: 195.36, 2017: 199.91, 2018: 204.50,
                   2019: 206.10, 2020: 206.50, 2021: 221.00, 2022: 250.90,
                   2023: 254.60, 2024: 257.70, 2025: 263.00},
    },
    FX_KEY: {
        "name": "CBN official NGN per USD (annual avg)",
        "source": "CBN / World Bank annual average",
        "ref_year": 2024,
        "series": {2015: 192.44, 2016: 253.49, 2017: 305.79, 2018: 306.08,
                   2019: 306.92, 2020: 358.81, 2021: 401.15, 2022: 425.98,
                   2023: 645.16, 2024: 1486.57, 2025: 1554.62},
    },
    # ── Example indices proving multi-category escalation (illustrative) ──
    "STEEL": {
        "name": "Steel mill products PPI",
        "source": "US BLS WPU101 (illustrative)",
        "ref_year": 2024,
        "series": {2017: 180.0, 2020: 190.0, 2021: 250.0, 2022: 275.0,
                   2023: 245.0, 2024: 250.0, 2025: 252.0},
    },
    "IT_HARDWARE": {
        "name": "IT hardware price index (deflationary)",
        "source": "BLS computer hardware PPI (illustrative)",
        "ref_year": 2024,
        "series": {2017: 118.0, 2020: 108.0, 2021: 105.0, 2022: 102.0,
                   2023: 100.5, 2024: 100.0, 2025: 99.0},
    },
    "FUEL": {
        "name": "Diesel / fuel index",
        "source": "Energy price index (illustrative)",
        "ref_year": 2024,
        "series": {2017: 70.0, 2020: 60.0, 2021: 85.0, 2022: 130.0,
                   2023: 110.0, 2024: 100.0, 2025: 98.0},
    },
}


def seed_escalation_indices(session: Session):
    """Idempotent — insert any missing indices."""
    for key, cfg in _SEED.items():
        if session.get(EscalationIndex, key) is None:
            session.add(EscalationIndex(
                key=key, name=cfg["name"], description=cfg.get("description", ""),
                source=cfg["source"], ref_year=cfg["ref_year"],
                # JSON keys must be strings
                series={str(k): v for k, v in cfg["series"].items()},
            ))
    session.commit()


def _series(session: Session, key: str) -> tuple[dict, int]:
    idx = session.get(EscalationIndex, key)
    if not idx:
        raise ValueError(f"Escalation index '{key}' not found")
    return idx.series, idx.ref_year


def _nearest(series: dict, year: int) -> float:
    if str(year) in series:
        return series[str(year)]
    yrs = [int(y) for y in series.keys()]
    return series[str(min(yrs, key=lambda y: abs(y - year)))]


def normalise(session: Session, *, orig_rate: float, currency: str, year: int,
              index_key: str = "US_PPI_FG") -> tuple[float, dict]:
    """Convert a rate to reference-year real terms in USD.

    NGN → divide by that year's CBN FX → escalate by the category's index.
    USD → escalate by the category's index only.
    """
    series, ref_year = _series(session, index_key)
    esc = _nearest(series, ref_year) / _nearest(series, year)
    cur = (currency or "USD").upper()

    if cur == "NGN":
        fx_series, _ = _series(session, FX_KEY)
        fx = _nearest(fx_series, year)
        usd_at_time = orig_rate / fx
        value = usd_at_time * esc
        prov = {"method": "NGN→USD(FX)→ref(index)", "index": index_key,
                "cbn_fx": fx, "usd_at_time": round(usd_at_time, 4),
                "escalation": round(esc, 6), "ref_year": ref_year,
                "combined_factor": round(value / orig_rate, 8) if orig_rate else None}
    else:
        value = orig_rate * esc
        prov = {"method": "USD→ref(index)", "index": index_key,
                "escalation": round(esc, 6), "ref_year": ref_year,
                "combined_factor": round(esc, 8)}
    return round(value, 6), prov
