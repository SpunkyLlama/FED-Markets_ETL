"""Refresh data/market-briefing-data.csv from FRED and Yahoo Finance.

    FRED_API_KEY=... python -m etl.fetch                  # normal run
    python -m etl.fetch --dry-run                          # print what would change
    python -m etl.fetch --lookback-days 400                # first-run backfill

Only the metrics in etl/series.py are touched. Everything else in the CSV
(hike odds, supercore, Hormuz notes, ...) stays manual.
"""
import argparse
import datetime as dt
import json
import os
import sys

from . import core
from .series import SPECS, EXTRA_MONTHS


# ---------- network fetchers (lazy imports so tests need no deps) ----------
def fetch_fred(series_id, api_key, start):
    import requests
    r = requests.get(
        "https://api.stlouisfed.org/fred/series/observations",
        params={"series_id": series_id, "api_key": api_key, "file_type": "json",
                "observation_start": start},
        timeout=30,
    )
    r.raise_for_status()
    return {o["date"]: float(o["value"]) for o in r.json()["observations"] if o["value"] != "."}


def fetch_yf(ticker, start):
    import yfinance as yf
    hist = yf.Ticker(ticker).history(start=start, auto_adjust=False)
    return {d.strftime("%Y-%m-%d"): float(v) for d, v in hist["Close"].dropna().items()}


# ---------- collection ----------
def _months_back(date, n):
    t = date.year * 12 + date.month - 1 - n
    return dt.date(t // 12, t % 12 + 1, 1)


def collect(today, lookback_days, fred_key, last_stored, fred=fetch_fred, yf=fetch_yf):
    """Return (observations, errors). `last_stored` = {metric: latest stored obs_date}."""
    start_daily = today - dt.timedelta(days=lookback_days)
    start_month = _months_back(today, 6 if lookback_days < 200 else lookback_days // 30 + 1)
    obs, errors = [], []
    spx_raw = {}

    for s in SPECS:
        try:
            if s.kind in ("yoy", "mom", "diff"):
                fetch_from = _months_back(start_month, EXTRA_MONTHS[s.kind]).isoformat()
            elif s.kind == "changes":
                fetch_from = (today - dt.timedelta(days=400)).isoformat()
            else:
                fetch_from = start_daily.isoformat()
            if s.series == "^GSPC":  # extra history for the YTD calculation
                fetch_from = min(fetch_from, dt.date(today.year - 1, 12, 15).isoformat())

            pts = fred(s.series, fred_key, fetch_from) if s.provider == "fred" else yf(s.series, fetch_from)
            if s.series == "^GSPC":
                spx_raw = pts

            if s.kind in ("yoy", "mom", "diff"):
                vals = core.transform_monthly(pts, s.kind)
                vals = {d: v for d, v in vals.items() if d >= start_month.isoformat()}
            elif s.kind == "changes":
                vals = core.change_points(pts)
                floor = last_stored.get(s.metric, "")
                vals = {d: v for d, v in vals.items() if d > floor}
            else:
                vals = {d: v for d, v in pts.items() if d >= start_daily.isoformat()}

            for d, v in sorted(vals.items()):
                obs.append(core.Obs(d, s.freq, s.metric, v, s.unit, s.source, s.note))
        except Exception as e:  # one bad series must not sink the run
            errors.append("%s (%s): %s: %s" % (s.metric, s.series, type(e).__name__, e))

    # S&P YTD % for the latest close only
    prior = sorted(d for d in spx_raw if d < "%d-01-01" % today.year)
    if prior and spx_raw:
        last = max(spx_raw)
        if last.startswith(str(today.year)):
            ytd = (spx_raw[last] / spx_raw[prior[-1]] - 1) * 100
            obs.append(core.Obs(last, "D", "spx_ytd_pct", round(ytd, 1), "pct", "Yahoo Finance",
                                "vs %s close" % prior[-1]))
    return obs, errors


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/market-briefing-data.csv")
    ap.add_argument("--report", default="data/last_run.json")
    ap.add_argument("--lookback-days", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    key = os.environ.get("FRED_API_KEY")
    if not key:
        print("FRED_API_KEY is not set", file=sys.stderr)
        return 2

    today = dt.date.today()
    rows = core.load_csv(a.csv)
    last_stored = {}
    for r in rows:
        last_stored[r["metric"]] = max(last_stored.get(r["metric"], ""), r["obs_date"])

    obs, errors = collect(today, a.lookback_days, key, last_stored)
    for e in errors:
        print("::warning::fetch failed: " + e)
    if not obs:
        print("::error::no observations fetched", file=sys.stderr)
        return 1

    rows, rep = core.reconcile(rows, obs, today.isoformat())
    detail = {"run_date": today.isoformat(), "counts": rep.summary(), "errors": errors,
              "revised": rep.revised, "corrected": rep.corrected, "conflicts": rep.conflicts}
    print(json.dumps(detail["counts"]))
    for c in rep.conflicts:
        print("::warning::conflict (not overwritten): %s stored=%s fetched=%s [%s]" % c)

    if not a.dry_run:
        core.save_csv(a.csv, rows)
        with open(a.report, "w") as f:
            json.dump(detail, f, indent=2, default=list)
    return 0


if __name__ == "__main__":
    sys.exit(main())
