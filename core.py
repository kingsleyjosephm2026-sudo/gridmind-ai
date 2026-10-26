"""GridMind AI core analytics. ALL DATA PRODUCED HERE IS SIMULATED. Units: kW (power), kWh (energy), INR/kWh."""
import numpy as np, pandas as pd
from scipy.optimize import linprog
from sklearn.ensemble import GradientBoostingRegressor

REQUIRED = ["timestamp", "demand_kw", "solar_kw", "tariff_inr_kwh"]

def tariff_for(ts):
    """Illustrative time-of-use tariff (INR/kWh): 6 overnight, 8 day, 12 evening peak 18-22h."""
    h = pd.DatetimeIndex(ts).hour.values
    return np.where((h >= 18) & (h < 22), 12.0, np.where(h < 6, 6.0, 8.0))

def generate_data(days=90, seed=42, start="2026-01-01"):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * 24, freq="h")
    h, dow = idx.hour.values, idx.dayofweek.values
    work = ((dow < 5) & (h >= 7) & (h < 19)).astype(int)
    temp = 26 + 5 * np.sin((h - 9) / 24 * 2 * np.pi) + rng.normal(0, 0.8, len(idx))
    demand = 300 + 250 * work + 4 * (temp - 26) + rng.normal(0, 12, len(idx))
    clear = np.clip(np.sin((h - 6) / 12 * np.pi), 0, None)
    solar = np.clip(250 * clear * rng.uniform(0.6, 1.0, days).repeat(24) + rng.normal(0, 4, len(idx)), 0, None)
    solar[clear == 0] = 0.0
    anomaly = np.zeros(len(idx), dtype=int)
    lo = min(24 * 14, len(idx) // 2)
    for k in rng.choice(np.arange(lo, len(idx)), min(4, len(idx) - lo), replace=False):  # injected, known events
        demand[k] *= 1.8; anomaly[k] = 1
    return pd.DataFrame({"timestamp": idx, "demand_kw": demand, "demand_kwh": demand * 1.0,
        "solar_kw": solar, "solar_kwh": solar * 1.0, "tariff_inr_kwh": tariff_for(idx),
        "temp_c": temp, "is_working_hour": work, "injected_anomaly": anomaly, "source": "SIMULATED"})

def validate_readings(df):
    """Returns dict(valid_rows, rejected_rows with reason, errors). Never silently accepts bad rows."""
    miss = [c for c in REQUIRED if c not in df.columns]
    if miss:
        return {"errors": [f"missing columns: {miss}"], "valid": df.iloc[0:0], "rejected": df.iloc[0:0]}
    d = df.copy()
    d["timestamp"] = pd.to_datetime(d["timestamp"], errors="coerce")
    for c in REQUIRED[1:]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    reason = pd.Series("", index=d.index, dtype=object)
    reason[d["timestamp"].isna()] = "invalid timestamp"
    reason[(reason == "") & d["timestamp"].duplicated()] = "duplicate timestamp"
    reason[(reason == "") & d[REQUIRED[1:]].isna().any(axis=1)] = "missing/non-numeric value"
    reason[(reason == "") & (d[REQUIRED[1:]] < 0).any(axis=1)] = "negative value"
    bad = reason != ""
    rej = d[bad].assign(reject_reason=reason[bad])
    return {"errors": [], "valid": d[~bad].reset_index(drop=True), "rejected": rej}

def energy_cost(import_kw, tariff, dt=1.0):
    return float(np.sum(np.clip(np.asarray(import_kw, float), 0, None) * dt * np.asarray(tariff, float)))

def metrics(actual, pred):
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    if len(a) == 0: return {"mae": None, "rmse": None, "mape": None}
    nz = a > 0  # MAPE only where denominator is valid
    return {"mae": float(np.mean(np.abs(a - p))), "rmse": float(np.sqrt(np.mean((a - p) ** 2))),
            "mape": float(np.mean(np.abs((a - p)[nz] / a[nz])) * 100) if nz.any() else None}

def chrono_split(n, train=0.7, val=0.15):
    i, j = int(n * train), int(n * (train + val))
    return slice(0, i), slice(i, j), slice(j, n)

def _features(ts, demand):
    s = pd.Series(demand, index=pd.DatetimeIndex(ts))
    f = pd.DataFrame({"hour": s.index.hour, "dow": s.index.dayofweek}, index=s.index)
    f["work"] = ((f.dow < 5) & (f.hour >= 7) & (f.hour < 19)).astype(int)
    f["lag24"], f["lag168"] = s.shift(24), s.shift(168)           # lags >= 24h: usable at decision time
    f["roll24"] = s.shift(24).rolling(24).mean()                  # only past values -> no leakage
    return f

def forecast_demand(df, horizon=24, min_rows=24 * 21):
    """Baseline = same hour previous day. Model = GradientBoosting on lag features; chosen only if it
    beats baseline on the VALIDATION split. Reported metrics are on the held-out chronological TEST split."""
    ts = pd.DatetimeIndex(df["timestamp"]); y = df["demand_kw"].to_numpy(float)
    fut = pd.date_range(ts[-1] + pd.Timedelta(hours=1), periods=horizon, freq="h")
    F = _features(ts.append(fut), np.concatenate([y, np.full(horizon, np.nan)]))
    base_future = F["lag24"].iloc[-horizon:].to_numpy()
    out = {"method": "baseline_same_hour_previous_day", "reason": "", "timestamps": fut, "forecast": base_future}
    H = F.iloc[:len(y)].dropna(); yy = pd.Series(y, index=ts).loc[H.index].to_numpy()
    if len(H) < min_rows:
        out["reason"] = f"insufficient history ({len(H)} usable rows < {min_rows}); using baseline"
        return out
    tr, va, te = chrono_split(len(H))
    mk = lambda: GradientBoostingRegressor(random_state=0, n_estimators=150, max_depth=3)
    cols = list(H.columns)
    m = mk().fit(H.iloc[tr][cols], yy[tr])
    bm = lambda sl: metrics(yy[sl], H["lag24"].iloc[sl])
    mm = lambda sl: metrics(yy[sl], m.predict(H.iloc[sl][cols]))
    out["metrics_test"] = {"baseline": bm(te), "model": mm(te)}
    if mm(va)["mae"] < bm(va)["mae"]:
        final = mk().fit(H[cols], yy)
        out.update(method="gradient_boosting", forecast=final.predict(F.iloc[-horizon:][cols]))
        out["reason"] = "model beat baseline on validation split"
    else:
        out["reason"] = "model did not beat baseline on validation; using baseline"
    return out

def optimize_battery(net_load_kw, tariff, capacity_kwh, soc0_kwh, max_charge_kw, max_discharge_kw,
                     soc_min_frac=0.1, soc_max_frac=0.9, reserve_frac=0.0, eff_c=0.95, eff_d=0.95,
                     deg_cost=0.05, dt=1.0):
    """LP: minimise sum(tariff*import*dt + deg*(c+d)*dt). net_load = demand - solar (kW). No export
    (surplus is curtailed). Terminal SOC >= initial SOC. Fallback to no-dispatch on solver failure."""
    L, p = np.asarray(net_load_kw, float), np.asarray(tariff, float); T = len(L)
    if T == 0 or len(p) != T: raise ValueError("net load and tariff must be non-empty and equal length")
    if capacity_kwh < 0 or not (0 < eff_c <= 1 and 0 < eff_d <= 1): raise ValueError("invalid battery parameters")
    smin, smax = capacity_kwh * max(soc_min_frac, reserve_frac), capacity_kwh * soc_max_frac
    if not (smin - 1e-9 <= soc0_kwh <= smax + 1e-9): raise ValueError("initial SOC outside allowed range")
    base = energy_cost(L, p, dt); zero = np.zeros(T)
    n = 4 * T + 1; ic, idd, isx, ig = 0, T, 2 * T, 3 * T + 1   # x = [c(T), d(T), s(T+1), g(T)]
    cost = np.zeros(n); cost[ic:ic+T] = deg_cost * dt; cost[idd:idd+T] = deg_cost * dt; cost[ig:] = p * dt
    Aeq = np.zeros((T + 1, n)); beq = np.zeros(T + 1)
    for t in range(T):
        Aeq[t, isx + t + 1] = 1; Aeq[t, isx + t] = -1; Aeq[t, ic + t] = -eff_c * dt; Aeq[t, idd + t] = dt / eff_d
    Aeq[T, isx] = 1; beq[T] = soc0_kwh
    Aub = np.zeros((T, n)); bub = -L
    for t in range(T):
        Aub[t, ic + t] = 1; Aub[t, idd + t] = -1; Aub[t, ig + t] = -1      # L + c - d <= g
    bnds = [(0, max_charge_kw)] * T + [(0, max_discharge_kw)] * T + [(smin, smax)] * (T + 1) + [(0, None)] * T
    bnds[isx + T] = (max(smin, soc0_kwh), smax)                              # terminal SOC >= initial
    res = linprog(cost, A_ub=Aub, b_ub=bub, A_eq=Aeq, b_eq=beq, bounds=bnds, method="highs")
    if not res.success:
        return {"status": "fallback_no_dispatch", "message": res.message, "charge_kw": zero, "discharge_kw": zero,
                "soc_kwh": np.full(T + 1, soc0_kwh), "baseline_cost": base, "optimized_cost": base, "savings": 0.0}
    c, d, s = res.x[ic:ic+T], res.x[idd:idd+T], res.x[isx:isx+T+1]
    imp = np.clip(L + c - d, 0, None); opt = energy_cost(imp, p, dt)
    return {"status": "optimal", "charge_kw": c, "discharge_kw": d, "soc_kwh": s, "grid_import_kw": imp,
            "baseline_cost": base, "optimized_cost": opt, "savings": base - opt,
            "baseline_peak_kw": float(np.clip(L, 0, None).max()), "optimized_peak_kw": float(imp.max()),
            "battery_losses_kwh": float(np.sum(c * dt) - np.sum(d * dt) - (s[-1] - s[0])),
            "simultaneous_intervals": int(np.sum((c > 1e-6) & (d > 1e-6))),
            "note": "SIMULATED estimate, not verified savings"}

def detect_anomalies(df, z_thresh=4.0):
    """Robust z-score vs median/MAD of the same (day-of-week, hour). Flags are candidates, not confirmed faults."""
    d = df.copy(); ts = pd.to_datetime(d["timestamp"])
    d["k"] = ts.dt.dayofweek * 24 + ts.dt.hour
    med = d.groupby("k")["demand_kw"].transform("median")
    mad = (d["demand_kw"] - med).abs().groupby(d["k"]).transform("median")
    z = (d["demand_kw"] - med) / np.maximum(mad / 0.6745, 1e-6)
    hit = z.abs() > z_thresh
    out = pd.DataFrame({"timestamp": d["timestamp"][hit], "metric": "demand_kw", "observed": d["demand_kw"][hit],
        "expected": med[hit], "deviation": (d["demand_kw"] - med)[hit], "robust_z": z[hit]})
    out["severity"] = np.where(out.robust_z.abs() > 2 * z_thresh, "high", "medium")
    out["explanation"] = "Demand differs strongly from the typical value for this weekday-hour."
    out["suggested_investigation"] = "Check schedules, equipment start-ups and metering for this interval."
    return out.reset_index(drop=True)

class Simulator:
    """Simulated live feed (NOT a grid connection). Each tick appends one simulated hour to the dataset
    used by all analytics, with a simple rule-based battery (charge <06h, discharge 18-22h)."""
    def __init__(self, df, seed=7, retention_rows=24 * 120, cap_kwh=800.0):
        self._init, self.seed, self.retention, self.cap = df.copy(), seed, retention_rows, cap_kwh
        self.reset()
    def reset(self):
        self.df = self._init.copy(); self.rng = np.random.default_rng(self.seed)
        self.running = False; self.soc = 0.5 * self.cap; self.events = []
    def tick(self):
        ts = self.df["timestamp"].iloc[-1] + pd.Timedelta(hours=1); h = ts.hour
        work = int(ts.dayofweek < 5 and 7 <= h < 19)
        temp = 26 + 5 * np.sin((h - 9) / 24 * 2 * np.pi) + self.rng.normal(0, 0.8)
        demand = max(300 + 250 * work + 4 * (temp - 26) + self.rng.normal(0, 12), 0.0)
        solar = max(250 * np.sin((h - 6) / 12 * np.pi) * self.rng.uniform(0.6, 1.0), 0.0) if 6 <= h < 18 else 0.0
        ch = dis = 0.0
        if h < 6: ch = max(min(100.0, (0.9 * self.cap - self.soc) / 0.95), 0.0)
        elif 18 <= h < 22: dis = max(min(100.0, (self.soc - 0.1 * self.cap) * 0.95), 0.0)
        self.soc += 0.95 * ch - dis / 0.95
        imp = max(demand - solar + ch - dis, 0.0)
        row = {"timestamp": ts, "demand_kw": demand, "demand_kwh": demand, "solar_kw": solar, "solar_kwh": solar,
               "tariff_inr_kwh": float(tariff_for([ts])[0]), "temp_c": temp, "is_working_hour": work,
               "injected_anomaly": 0, "source": "SIMULATED"}
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True).tail(self.retention).reset_index(drop=True)
        ev = {"timestamp": str(ts), "demand_kw": demand, "solar_kw": solar, "grid_import_kw": imp, "soc_kwh": self.soc,
              "charge_kw": ch, "discharge_kw": dis, "source": "SIMULATED"}
        self.events = (self.events + [ev])[-50:]; return ev
