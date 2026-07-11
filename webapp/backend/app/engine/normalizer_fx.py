"""
FX + Inflation Normalisation — USD 2024 real terms.

Every raw observation is normalised to USD 2024 so that rates from different
operators, years and currencies are directly comparable. This module is the
single source of truth for that normalisation and is used by the Data Entry
front door (`POST /api/observations/add`) so new observations enter the
catalogue on exactly the same basis as the existing 440.

METHOD (documented, verifiable — sourced from FX_Inflation_Lookup_Table.xlsx):

  USD-denominated rate, year Y:
      usd_2024 = rate_usd × (US_PPI_FG[2024] / US_PPI_FG[Y])

  NGN-denominated rate, year Y:
      usd_at_time = rate_ngn / CBN_OFFICIAL_FX[Y]      # contemporaneous FX
      usd_2024    = usd_at_time × (US_PPI_FG[2024] / US_PPI_FG[Y])

This reproduces the existing dataset exactly, e.g.:
  • Seplat 2023 6" swamp lay/weld  ₦12,911.50/m
        → /645.16 × (257.7/254.6) = $20.26/m   (factor 0.001569)
  • SPDC 2017 6" swamp lay/weld    $20.70/m
        → ×(257.7/199.91)           = $26.68/m   (factor 1.28908)
  • Seplat 2021 USD rate            ×(257.7/221.0) = ×1.16606

Sources: US PPI-FG = BLS WPUFD49207 (FERC oil-pipeline escalation index).
         CBN official FX = World Bank/IMF annual average, CBN monthly rates.
"""
from typing import Optional, Tuple

REF_YEAR = 2024

# US PPI Finished Goods index (BLS via FERC notices). 2024 = 257.70.
US_PPI_FG = {
    2015: 195.30, 2016: 195.36, 2017: 199.91, 2018: 204.50, 2019: 206.10,
    2020: 206.50, 2021: 221.00, 2022: 250.90, 2023: 254.60, 2024: 257.70,
    2025: 263.00,
}

# CBN / World Bank official NGN-per-USD annual average.
CBN_OFFICIAL_FX = {
    2015: 192.44, 2016: 253.49, 2017: 305.79, 2018: 306.08, 2019: 306.92,
    2020: 358.81, 2021: 401.15, 2022: 425.98, 2023: 645.16, 2024: 1486.57,
    2025: 1554.62,
}

# Parallel-market estimate (context only — NOT used in the default chain).
CBN_PARALLEL_FX = {
    2017: 360, 2021: 570, 2023: 1000, 2024: 1650, 2025: 1600,
}

SUPPORTED_YEARS = sorted(US_PPI_FG.keys())


def _ppi_escalation(year: int) -> float:
    """US_PPI_FG[2024] / US_PPI_FG[year]. Falls back to nearest known year."""
    if year not in US_PPI_FG:
        year = min(US_PPI_FG, key=lambda y: abs(y - year))
    return US_PPI_FG[REF_YEAR] / US_PPI_FG[year]


def _cbn_fx(year: int) -> float:
    if year not in CBN_OFFICIAL_FX:
        year = min(CBN_OFFICIAL_FX, key=lambda y: abs(y - year))
    return CBN_OFFICIAL_FX[year]


def normalise_to_usd2024(orig_rate: float, orig_currency: str, year: int) -> Tuple[float, dict]:
    """
    Normalise a single rate to USD 2024 real terms.

    Returns (usd_2024, provenance) where provenance documents every factor
    applied — the UI surfaces this so the number is never a black box.
    """
    cur = (orig_currency or 'USD').upper()
    ppi = _ppi_escalation(year)

    if cur == 'NGN':
        fx = _cbn_fx(year)
        usd_at_time = orig_rate / fx
        usd_2024 = usd_at_time * ppi
        prov = {
            'method': 'NGN→USD(FX)→USD2024(PPI-FG)',
            'orig_currency': 'NGN',
            'orig_rate': orig_rate,
            'cbn_official_fx': fx,
            'usd_at_time': round(usd_at_time, 4),
            'ppi_escalation': round(ppi, 6),
            'us_ppi_year': US_PPI_FG.get(year),
            'us_ppi_2024': US_PPI_FG[REF_YEAR],
            'combined_factor': round(usd_2024 / orig_rate, 8) if orig_rate else None,
            'usd_2024': round(usd_2024, 4),
        }
    else:  # USD (default)
        usd_2024 = orig_rate * ppi
        prov = {
            'method': 'USD→USD2024(PPI-FG)',
            'orig_currency': 'USD',
            'orig_rate': orig_rate,
            'ppi_escalation': round(ppi, 6),
            'us_ppi_year': US_PPI_FG.get(year),
            'us_ppi_2024': US_PPI_FG[REF_YEAR],
            'combined_factor': round(ppi, 8),
            'usd_2024': round(usd_2024, 4),
        }
    return round(usd_2024, 6), prov


def normalise_method_label(orig_currency: str) -> str:
    cur = (orig_currency or 'USD').upper()
    return ('NGN→USD2024 via CBN FX + US PPI-FG'
            if cur == 'NGN' else 'USD→USD2024 via US PPI-FG')
