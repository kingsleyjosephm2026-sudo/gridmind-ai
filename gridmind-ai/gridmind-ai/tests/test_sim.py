import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gridmind import core

class Sim(unittest.TestCase):
    def test_tick_updates_data_and_limits(self):
        s = core.Simulator(core.generate_data(30, 1)); n = len(s.df); t0 = s.df.timestamp.iloc[-1]
        for _ in range(200):
            e = s.tick(); self.assertGreaterEqual(s.soc, 0.1 * s.cap - 1e-6); self.assertLessEqual(s.soc, 0.9 * s.cap + 1e-6)
            self.assertGreaterEqual(e["grid_import_kw"], 0)
        self.assertEqual(len(s.df), n + 200); self.assertEqual((s.df.timestamp.iloc[-1] - t0).total_seconds(), 200 * 3600)
        self.assertEqual(len(s.events), 50); self.assertTrue((s.df.source == "SIMULATED").all())
    def test_retention_reset_determinism(self):
        a = core.Simulator(core.generate_data(10, 1), retention_rows=240); b = core.Simulator(core.generate_data(10, 1), retention_rows=240)
        for _ in range(30): a.tick(); b.tick()
        self.assertEqual(len(a.df), 240); self.assertEqual(a.events[-1]["demand_kw"], b.events[-1]["demand_kw"])
        a.reset(); self.assertEqual(len(a.df), 240); self.assertEqual(a.events, []); self.assertFalse(a.running)
if __name__ == "__main__": unittest.main()
