import os, sys, unittest, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gridmind import core, store

class S(unittest.TestCase):
    def setUp(self): self.con = store.connect(":memory:"); self.df = core.generate_data(30, 5)
    def test_recs_persist_status(self):
        recs = store.generate_recommendations(self.df, core.detect_anomalies(self.df))
        store.upsert_recommendations(self.con, recs); r = store.list_recommendations(self.con); self.assertTrue(r)
        store.set_status(self.con, r[0]["id"], "Resolved"); store.upsert_recommendations(self.con, recs)  # regenerate
        self.assertEqual(store.list_recommendations(self.con)[0]["status"], "Resolved")
        with self.assertRaises(ValueError): store.set_status(self.con, r[0]["id"], "Done")
        with self.assertRaises(KeyError): store.set_status(self.con, 999, "Open")
        self.assertTrue(all("guarantee" not in x["title"].lower() for x in r))
    def test_savings_math_and_labels(self):
        i = store.add_savings(self.con, "LED", 1000, 10000, 900, 8000); row = store.list_savings(self.con)[0]
        self.assertAlmostEqual(row["calculated_savings"], 2000); self.assertTrue(row["classification"].startswith("Estimated"))
        store.add_savings(self.con, "HVAC", 1000, 10000, 900, 9000, 100, 200)  # 2x hours: baseline scaled to 20000
        self.assertAlmostEqual(store.list_savings(self.con)[1]["calculated_savings"], 11000)
        store.add_savings(self.con, "X", 1000, 10000, 900, 8000, 100, 100, confounders_controlled=True)
        self.assertTrue(store.list_savings(self.con)[2]["classification"].startswith("Verified"))
        store.add_savings(self.con, "Y", 1000, 10000, 900, 12000); self.assertEqual(store.list_savings(self.con)[3]["classification"], "No measurable saving")
    def test_savings_validation(self):
        for bad in [("", 1, 1, 1, 1), ("a", 0, 1, 1, 1), ("a", 1, -1, 1, 1)]:
            with self.assertRaises(ValueError): store.add_savings(self.con, *bad)
        with self.assertRaises(ValueError): store.add_savings(self.con, "a", 1, 1, 1, 1, 0, 5)
        with self.assertRaises(sqlite3.IntegrityError): self.con.execute("INSERT INTO recommendations(key,title,status) VALUES('k','t','bogus')")
if __name__ == "__main__": unittest.main()
