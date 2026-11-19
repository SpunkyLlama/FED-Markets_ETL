"""Metric -> source mapping.

Every metric key matches the existing CSV schema. Metrics not listed here
(fomc_hike_odds_pct, supercore, Hormuz status, Fed speaker remarks, real AHE)
stay manual: they are judgment calls or have no free daily feed.

kind:
  level   - take the series value as-is
  yoy     - 12-month % change of a monthly index (needs the index 12 months back)
  mom     - 1-month % change of a monthly index
  diff    - month-over-month change of a level (payrolls: PAYEMS is in thousands)
  changes - emit an event row only on dates where the value changes (policy rates)
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Spec:
    metric: str
    provider: str          # "fred" or "yf"
    series: str            # FRED series id or yfinance ticker
    kind: str              # level | yoy | mom | diff | changes
    freq: str              # D | M | event
    unit: str
    source: str            # goes into the CSV `source` column
    note: str = ""


SPECS = [
    # ---- Daily markets (yfinance) ----
    Spec("spx_close", "yf", "^GSPC", "level", "D", "index", "Yahoo Finance"),
    Spec("nasdaq_close", "yf", "^IXIC", "level", "D", "index", "Yahoo Finance"),
    Spec("dow_close", "yf", "^DJI", "level", "D", "index", "Yahoo Finance"),
    Spec("rut_close", "yf", "^RUT", "level", "D", "index", "Yahoo Finance"),
    Spec("gold_usd", "yf", "GC=F", "level", "D", "usd_oz", "Yahoo Finance",
         "front-month COMEX futures settle, not London spot"),

    # ---- Daily rates / FX / vol / oil (FRED) ----
    Spec("ust10y_pct", "fred", "DGS10", "level", "D", "pct", "FRED (Treasury H.15)"),
    Spec("vix_close", "fred", "VIXCLS", "level", "D", "index", "FRED (Cboe)"),
    Spec("usdjpy", "fred", "DEXJPUS", "level", "D", "jpy", "FRED (Fed H.10)",
         "H.10 noon NY rate; differs from intraday quotes"),
    Spec("brent_usd", "fred", "DCOILBRENTEU", "level", "D", "usd_bbl", "FRED (EIA)"),
    Spec("wti_usd", "fred", "DCOILWTICO", "level", "D", "usd_bbl", "FRED (EIA)"),
    Spec("gasoline_usd_gal", "fred", "GASREGW", "level", "D", "usd_gal", "FRED (EIA)",
         "weekly national regular average, dated to the Monday"),

    # ---- Policy rates (event rows on change dates only) ----
    Spec("fed_funds_lower_pct", "fred", "DFEDTARL", "changes", "event", "pct", "FRED (Federal Reserve)"),
    Spec("fed_funds_upper_pct", "fred", "DFEDTARU", "changes", "event", "pct", "FRED (Federal Reserve)"),

    # ---- Monthly macro (FRED mirrors BLS / BEA) ----
    # Headline YoY uses the NSA index (that is what BLS publishes); MoM uses SA.
    Spec("cpi_yoy_pct", "fred", "CPIAUCNS", "yoy", "M", "pct", "BLS via FRED"),
    Spec("core_cpi_yoy_pct", "fred", "CPILFENS", "yoy", "M", "pct", "BLS via FRED"),
    Spec("cpi_mom_pct", "fred", "CPIAUCSL", "mom", "M", "pct", "BLS via FRED"),
    Spec("core_cpi_mom_pct", "fred", "CPILFESL", "mom", "M", "pct", "BLS via FRED"),
    Spec("core_pce_yoy_pct", "fred", "PCEPILFE", "yoy", "M", "pct", "BEA via FRED"),
    Spec("pce_yoy_pct", "fred", "PCEPI", "yoy", "M", "pct", "BEA via FRED"),
    Spec("payrolls_k", "fred", "PAYEMS", "diff", "M", "thousands", "BLS via FRED"),
    Spec("unemployment_pct", "fred", "UNRATE", "level", "M", "pct", "BLS via FRED"),
    Spec("participation_pct", "fred", "CIVPART", "level", "M", "pct", "BLS via FRED"),
    Spec("ahe_yoy_pct", "fred", "CES0500000003", "yoy", "M", "pct", "BLS via FRED"),
]

# Series that need extra history to compute (months of lookback beyond the window).
EXTRA_MONTHS = {"yoy": 13, "mom": 2, "diff": 2}
