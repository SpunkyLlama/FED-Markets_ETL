"""Offline tests: python -m unittest discover -s etl -t . -v"""
import datetime as dt
import unittest

from etl import core, fetch


def row(date, metric, value, quality="verified", freq="D", source="x", note=""):
    return dict(obs_date=date, freq=freq, metric=metric, value=str(value), unit="u",
                quality=quality, source=source, edition="2026-10-23", note=note)


def obs(date, metric, value, freq="D", source="API"):
    return core.Obs(date, freq, metric, value, "u", source)


class Transforms(unittest.TestCase):
    def test_yoy_and_mom(self):
        pts = {"2025-09-01": 100.0, "2025-10-01": 101.0, "2026-09-01": 103.7, "2026-10-01": 104.1}
        self.assertEqual(core.transform_monthly(pts, "yoy")["2026-09-01"], 3.7)
        self.assertEqual(core.transform_monthly(pts, "mom")["2026-10-01"], 0.4)

    def test_missing_base_month_yields_nothing(self):
        # Oct 2025 was never collected (shutdown): Oct 2026 YoY must be absent, not guessed.
        pts = {"2025-09-01": 100.0, "2026-09-01": 103.7, "2026-10-01": 104.1}
        out = core.transform_monthly(pts, "yoy")
        self.assertIn("2026-09-01", out)
        self.assertNotIn("2026-10-01", out)

    def test_payrolls_diff(self):
        pts = {"2026-09-01": 159000.0, "2026-10-01": 159165.0}
        self.assertEqual(core.transform_monthly(pts, "diff")["2026-10-01"], 165.0)

    def test_change_points(self):
        d = {"2026-09-15": 3.5, "2026-09-16": 3.75, "2026-09-17": 3.75, "2026-10-28": 3.75}
        self.assertEqual(core.change_points(d), {"2026-09-15": 3.5, "2026-09-16": 3.75})


class Reconcile(unittest.TestCase):
    def test_new_row_appended_verified(self):
        rows, rep = core.reconcile([], [obs("2026-11-12", "ust10y_pct", 4.9)], "2026-11-14")
        self.assertEqual(rows[0]["quality"], "verified")
        self.assertEqual(rows[0]["edition"], "2026-11-14")
        self.assertEqual(len(rep.added), 1)

    def test_unverified_same_value_upgraded(self):
        rows = [row("2026-11-10", "vix_close", 19.63, quality="unverified")]
        rows, rep = core.reconcile(rows, [obs("2026-11-10", "vix_close", 19.63)], "2026-11-14")
        self.assertEqual(rows[0]["quality"], "verified")
        self.assertEqual(len(rep.upgraded), 1)

    def test_estimate_replaced_by_official(self):
        rows = [row("2026-09-01", "core_pce_yoy_pct", 3.1, quality="estimate", freq="M")]
        rows, rep = core.reconcile(rows, [obs("2026-09-01", "core_pce_yoy_pct", 3.1, "M")], "2026-11-14")
        self.assertEqual(rows[0]["quality"], "verified")

    def test_monthly_revision_replaces_and_keeps_old_in_note(self):
        rows = [row("2026-09-01", "payrolls_k", 29, freq="M")]
        rows, rep = core.reconcile(rows, [obs("2026-09-01", "payrolls_k", 60, "M")], "2026-11-14")
        self.assertEqual(rows[0]["value"], "60")
        self.assertIn("revised from 29", rows[0]["note"])
        self.assertEqual(len(rep.revised), 1)

    def test_verified_daily_disagreement_is_conflict_not_overwrite(self):
        rows = [row("2026-10-15", "gold_usd", 4198)]
        rows, rep = core.reconcile(rows, [obs("2026-10-15", "gold_usd", 4210.3, source="Yahoo")], "2026-11-14")
        self.assertEqual(rows[0]["value"], "4198")
        self.assertEqual(len(rep.conflicts), 1)

    def test_unverified_daily_wrong_value_corrected(self):
        rows = [row("2026-08-11", "vix_close", 15.28, quality="unverified")]
        rows, rep = core.reconcile(rows, [obs("2026-08-11", "vix_close", 16.1)], "2026-11-14")
        self.assertEqual(rows[0]["value"], "16.1")
        self.assertIn("corrected from 15.28", rows[0]["note"])
        self.assertEqual(len(rep.corrected), 1)

    def test_rounding_noise_is_not_a_change(self):
        rows = [row("2026-10-20", "spx_close", 7712.57)]
        rows, rep = core.reconcile(rows, [obs("2026-10-20", "spx_close", 7712.5712)], "2026-11-14")
        self.assertEqual(rep.summary(), dict(added=0, upgraded=0, revised=0, corrected=0, conflicts=0))

    def test_never_deletes_and_untouched_metrics_survive(self):
        rows = [row("2026-10-18", "fomc_hike_odds_pct", 74, note="Dec 8-9 meeting")]
        rows, rep = core.reconcile(rows, [obs("2026-11-12", "ust10y_pct", 4.9)], "2026-11-14")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["value"], "74")

    def test_idempotent(self):
        rows, _ = core.reconcile([], [obs("2026-11-12", "ust10y_pct", 4.9)], "2026-11-14")
        rows, rep = core.reconcile(rows, [obs("2026-11-12", "ust10y_pct", 4.9)], "2026-11-15")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rep.summary()["added"], 0)


class Collect(unittest.TestCase):
    """Drive collect() with fake fetchers: no network."""

    def test_end_to_end_with_fakes(self):
        today = dt.date(2026, 11, 14)

        def fake_fred(series, key, start):
            if series == "CPIAUCNS":
                return {"2025-09-01": 100.0, "2026-09-01": 103.7}
            if series == "DGS10":
                return {"2026-11-10": 4.98, "2026-11-11": 4.95}
            if series == "DFEDTARL":
                return {"2026-09-15": 3.5, "2026-09-16": 3.75, "2026-09-17": 3.75}
            raise RuntimeError("no fixture for " + series)

        def fake_yf(ticker, start):
            if ticker == "^GSPC":
                return {"2025-12-31": 6800.0, "2026-11-10": 7520.93, "2026-11-11": 7619.38}
            return {}

        # Fed lower-bound already stored through 2026-09-16 -> no new change event.
        obs_, errors = fetch.collect(today, 10, "k", {"fed_funds_lower_pct": "2026-09-16"},
                                     fred=fake_fred, yf=fake_yf)
        by = {(o.metric, o.obs_date): o.value for o in obs_}
        self.assertEqual(by[("ust10y_pct", "2026-11-10")], 4.98)
        self.assertEqual(by[("spx_close", "2026-11-11")], 7619.38)
        self.assertEqual(by[("spx_ytd_pct", "2026-11-11")], 12.0)       # 7619.38/6800 - 1
        self.assertEqual(by[("cpi_yoy_pct", "2026-09-01")], 3.7)
        self.assertFalse(any(m == "fed_funds_lower_pct" for m, _ in by))
        self.assertTrue(errors)  # series without fixtures were reported, not fatal


if __name__ == "__main__":
    unittest.main()
