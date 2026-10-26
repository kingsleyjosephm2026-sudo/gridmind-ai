"""SQLite persistence (stdlib) + rule-based recommendations + savings tracking. All outputs are estimates."""
import os, sqlite3
from datetime import datetime, timezone
import numpy as np, pandas as pd

STATUSES = ("Open", "In progress", "Resolved", "Dismissed")
SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations(id INTEGER PRIMARY KEY, key TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
 evidence TEXT, metric TEXT, severity TEXT, action TEXT, expected_benefit_inr REAL, method TEXT, assumptions TEXT,
 confidence TEXT, status TEXT NOT NULL DEFAULT 'Open' CHECK(status IN ('Open','In progress','Resolved','Dismissed')),
 updated_at TEXT);
CREATE TABLE IF NOT EXISTS savings(id INTEGER PRIMARY KEY, name TEXT NOT NULL, baseline_kwh REAL NOT NULL CHECK(baseline_kwh>0),
 baseline_cost REAL NOT NULL CHECK(baseline_cost>=0), post_kwh REAL NOT NULL CHECK(post_kwh>=0), post_cost REAL NOT NULL CHECK(post_cost>=0),
 baseline_hours REAL, post_hours REAL, expected_savings REAL, calculated_savings REAL, confounders_controlled INTEGER NOT NULL DEFAULT 0,
 classification TEXT, method TEXT, notes TEXT, created_at TEXT);
"""

def connect(path=None):
    c = sqlite3.connect(path or os.environ.get("GRIDMIND_DB", "gridmind.db"), check_same_thread=False)
    c.row_factory = sqlite3.Row; c.executescript(SCHEMA); return c

def _now(): return datetime.now(timezone.utc).isoformat()

def generate_recommendations(df, anomalies, shift_fraction=0.10):
    """Rules over the data. Benefits are scenario estimates under stated assumptions, never guarantees."""
    h = pd.to_datetime(df["timestamp"]).dt.hour; days = max(len(df) / 24, 1)
    peak = (h >= 18) & (h < 22); recs = []
    pk_kwh = float(df.loc[peak, "demand_kwh"].sum()); off = float(df.loc[h < 6, "tariff_inr_kwh"].mean()); pt = float(df.loc[peak, "tariff_inr_kwh"].mean())
    if pk_kwh > 0 and pt > off:
        recs.append(dict(key="shift-peak", title="Shift flexible load out of the 18:00-22:00 peak tariff", severity="medium",
            evidence=f"{pk_kwh:,.0f} kWh consumed in peak hours over {days:.0f} days at ~{pt:.1f} INR/kWh vs ~{off:.1f} overnight.",
            metric="peak-period cost", action="Identify processes that can run overnight or midday.",
            expected_benefit_inr=pk_kwh * shift_fraction * (pt - off), method="peak_kWh x shift_fraction x (peak - overnight tariff)",
            assumptions=f"{shift_fraction:.0%} of peak energy is movable; tariff difference holds; no process cost.", confidence="Low (assumption-driven)"))
    if len(anomalies):
        night = anomalies[pd.to_datetime(anomalies["timestamp"]).dt.hour < 6]
        recs.append(dict(key="investigate-anomalies", title=f"Investigate {len(anomalies)} unusual demand intervals", severity="high" if (anomalies.severity == "high").any() else "medium",
            evidence=f"{len(anomalies)} intervals deviate strongly from weekday-hour norms ({len(night)} overnight).", metric="demand_kw",
            action="Check schedules, start-ups and meter data for the listed timestamps; these are candidates, not confirmed faults.",
            expected_benefit_inr=None, method="robust z-score vs weekday-hour median/MAD", assumptions="History is representative.", confidence="Medium"))
    pk = df.loc[df.demand_kw.idxmax()] if len(df) else None
    if pk is not None:
        recs.append(dict(key="review-peak", title="Review peak demand", severity="low", evidence=f"Peak {pk.demand_kw:.0f} kW at {pk.timestamp}.",
            metric="peak_kw", action="Evaluate simulated battery dispatch on the Battery page.", expected_benefit_inr=None,
            method="max(demand_kw)", assumptions="Peak is not a metering artefact.", confidence="Medium"))
    return recs

def upsert_recommendations(con, recs):
    for r in recs:  # INSERT OR IGNORE keeps user-set status
        con.execute("INSERT OR IGNORE INTO recommendations(key,title,evidence,metric,severity,action,expected_benefit_inr,method,assumptions,confidence,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (r["key"], r["title"], r["evidence"], r["metric"], r["severity"], r["action"], r["expected_benefit_inr"], r["method"], r["assumptions"], r["confidence"], _now()))
    con.commit()

def list_recommendations(con): return [dict(r) for r in con.execute("SELECT * FROM recommendations ORDER BY id")]

def set_status(con, rec_id, status):
    if status not in STATUSES: raise ValueError(f"status must be one of {STATUSES}")
    if con.execute("UPDATE recommendations SET status=?, updated_at=? WHERE id=?", (status, _now(), rec_id)).rowcount == 0:
        raise KeyError(rec_id)
    con.commit()

def add_savings(con, name, baseline_kwh, baseline_cost, post_kwh, post_cost, baseline_hours=None, post_hours=None,
                expected_savings=None, confounders_controlled=False, notes=""):
    """Operating-hours normalisation when both hour counts are given. 'Verified' is never automatic."""
    if not name.strip() or baseline_kwh <= 0 or min(baseline_cost, post_kwh, post_cost) < 0: raise ValueError("invalid savings inputs")
    scale, method = 1.0, "baseline_cost - post_cost (no normalisation)"
    if (baseline_hours is None) != (post_hours is None): raise ValueError("provide both operating-hour values or neither")
    if baseline_hours is not None:
        if baseline_hours <= 0 or post_hours <= 0: raise ValueError("operating hours must be positive")
        scale, method = post_hours / baseline_hours, "baseline_cost x (post_hours/baseline_hours) - post_cost"
    saved = baseline_cost * scale - post_cost
    cls = "Estimated post-intervention savings"
    if confounders_controlled and baseline_hours is not None and saved > 0: cls = "Verified savings (user-attested confounder control)"
    elif saved <= 0: cls = "No measurable saving"
    cur = con.execute("INSERT INTO savings(name,baseline_kwh,baseline_cost,post_kwh,post_cost,baseline_hours,post_hours,expected_savings,calculated_savings,confounders_controlled,classification,method,notes,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (name, baseline_kwh, baseline_cost, post_kwh, post_cost, baseline_hours, post_hours, expected_savings, saved, int(confounders_controlled), cls, method, notes, _now()))
    con.commit(); return cur.lastrowid

def list_savings(con): return [dict(r) for r in con.execute("SELECT * FROM savings ORDER BY id")]
