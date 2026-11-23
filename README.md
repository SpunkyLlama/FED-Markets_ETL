# FED-Markets_ETL

Keeps `data/market-briefing-data.csv` current for the recurring markets briefing.
Personal reference, not investment advice.

## How it works

`.github/workflows/refresh.yml` runs weekdays at 22:30 UTC (and on demand). It runs the
offline tests, then `python -m etl.fetch`, then commits the CSV if anything changed.

| Piece | Role |
|-------|------|
| `etl/series.py` | Which metric comes from which source |
| `etl/fetch.py` | Network fetch (FRED, Yahoo Finance) and the CLI |
| `etl/core.py` | CSV I/O, YoY/MoM transforms, reconciliation (no network) |
| `etl/test_etl.py` | Offline tests |
| `data/last_run.json` | Counts of rows added / revised / corrected, plus any conflicts |

## Reconciliation rules

- New (metric, date): appended as `verified`.
- Same value, previously `unverified`/`estimate`: upgraded to `verified`.
- Monthly value changed: treated as a revision; the old value goes in `note`.
- Daily value changed on an `unverified` row: corrected, old value in `note`.
- Daily value differs from a `verified` row: **not overwritten**. It shows up under
  `conflicts` in `last_run.json` and as a workflow warning, for you to decide.
- Rows are never deleted. A missing base month (Oct 2025 CPI) produces no YoY row, not a guess.

## Setup

1. Get a free FRED API key: <https://fred.stlouisfed.org/docs/api/api_key.html>
2. Repo Settings > Secrets and variables > Actions > new secret `FED_API_KEY` (the workflow maps it to the `FRED_API_KEY` variable the script reads).
3. Merge this branch, then run the workflow once manually with `lookback_days` = 400 to backfill.

Run locally:

```bash
pip install -r requirements.txt
python -m unittest discover -s etl -t . -v
FRED_API_KEY=... python -m etl.fetch --dry-run
```

## Not automated (stays in the manual "update report" flow)

Hike/cut odds, supercore services, share of CPI categories above 3%, real average hourly
earnings, Fed speaker remarks, Hormuz status, US-Japan 2-yr spread, BOJ policy rate, and the
JGB 10-yr (FRED only carries a monthly OECD series). Core CPI/PCE and payrolls come from FRED,
which mirrors BLS/BEA, so the first-print timing can lag the agency release by a day.
