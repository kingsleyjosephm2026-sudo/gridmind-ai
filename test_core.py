import os, sys, unittest, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gridmind.core import *

class T(unittest.TestCase):
    def test_reproducible(self):
        a, b = generate_data(10, 1), generate_data(10, 1)
        pd.testing.assert_frame_equal(a, b); self.assertTrue((a.source == "SIMULATED").all())
    def test_cost_and_zero_demand(self):
        self.assertAlmostEqual(energy_cost([100, 0], [10, 5], 1.0), 1000)
        self.assertEqual(energy_cost([0, 0], [10, 5]), 0.0)
        self.assertAlmostEqual(energy_cost([100], [10], 0.5), 500)
    def test_metrics(self):
        m = metrics([2, 0, 4], [1, 1, 2]); self.assertAlmostEqual(m["mae"], 4 / 3)
        self.assertAlmostEqual(m["mape"], 50.0); self.assertIsNone(metrics([0], [1])["mape"])
        self.assertIsNone(metrics([], [])["mae"])
    def test_chrono_split(self):
        a, b, c = chrono_split(100); self.assertEqual((a.stop, b.start, b.stop, c.start), (70, 70, 85, 85))
    def _opt(self, **kw):
        L = np.array([100.0] * 6 + [400.0] * 4 + [100.0] * 6 + [500.0] * 4 + [100.0] * 4)
        p = tariff_for(pd.date_range("2026-01-01", periods=24, freq="h"))
        args = dict(capacity_kwh=800, soc0_kwh=100, max_charge_kw=200, max_discharge_kw=200); args.update(kw)
        return L, p, args, optimize_battery(L, p, **args)
    def test_optimizer_constraints(self):
        L, p, a, r = self._opt(); self.assertEqual(r["status"], "optimal")
        c, d, s = r["charge_kw"], r["discharge_kw"], r["soc_kwh"]
        self.assertTrue((c <= 200 + 1e-6).all() and (d <= 200 + 1e-6).all() and (c >= -1e-9).all())
        self.assertTrue((s >= 80 - 1e-6).all() and (s <= 720 + 1e-6).all())
        self.assertGreaterEqual(s[-1], a["soc0_kwh"] - 1e-6)
        for t in range(24):
            self.assertAlmostEqual(s[t + 1], s[t] + 0.95 * c[t] - d[t] / 0.95, places=5)
        self.assertEqual(r["simultaneous_intervals"], 0)
        self.assertLessEqual(r["optimized_cost"], r["baseline_cost"] + 1e-6); self.assertGreater(r["savings"], 0)
        self.assertGreaterEqual(r["battery_losses_kwh"], -1e-6)
    def test_efficiency_losses_reduce_savings(self):
        s1 = self._opt(eff_c=1.0, eff_d=1.0)[3]["savings"]; s2 = self._opt(eff_c=0.8, eff_d=0.8)[3]["savings"]
        self.assertGreater(s1, s2)
    def test_zero_capacity_and_invalid(self):
        r = self._opt(capacity_kwh=0, soc0_kwh=0)[3]; self.assertAlmostEqual(r["savings"], 0.0, places=6)
        with self.assertRaises(ValueError): self._opt(soc0_kwh=-5)
        with self.assertRaises(ValueError): self._opt(capacity_kwh=-1)
        with self.assertRaises(ValueError): optimize_battery([], [], 10, 0, 1, 1)
    def test_reserve_respected(self):
        r = self._opt(reserve_frac=0.5, soc0_kwh=400)[3]
        self.assertTrue((r["soc_kwh"] >= 400 - 1e-6).all())
    def test_validation(self):
        df = pd.DataFrame({"timestamp": ["2026-01-01 00:00", "2026-01-01 00:00", "bad", "2026-01-01 03:00", "2026-01-01 04:00"],
            "demand_kw": [1, 2, 3, -4, "x"], "solar_kw": [0] * 5, "tariff_inr_kwh": [5] * 5})
        r = validate_readings(df); self.assertEqual(len(r["valid"]), 1); self.assertEqual(len(r["rejected"]), 4)
        self.assertTrue(validate_readings(df.drop(columns=["solar_kw"]))["errors"])
        self.assertEqual(len(validate_readings(df.iloc[0:0])["valid"]), 0)
    def test_forecast_and_fallback(self):
        df = generate_data(60, 3)
        f = forecast_demand(df); self.assertEqual(len(f["forecast"]), 24); self.assertIn("metrics_test", f)
        self.assertFalse(np.isnan(f["forecast"]).any())
        short = forecast_demand(df.iloc[:200]); self.assertEqual(short["method"], "baseline_same_hour_previous_day")
        self.assertIn("insufficient", short["reason"])
    def test_anomalies_found(self):
        df = generate_data(90, 42); a = detect_anomalies(df)
        inj = set(df.timestamp[df.injected_anomaly == 1]); found = set(a.timestamp)
        self.assertGreaterEqual(len(inj & found), 3); self.assertLess(len(found), 40)

if __name__ == "__main__": unittest.main()
