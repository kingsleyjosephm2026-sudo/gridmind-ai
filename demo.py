"""Run: python demo.py  -> writes data/sample_90d_simulated.csv and prints a simulated scenario comparison."""
import numpy as np
from gridmind import core
df = core.generate_data(90, 42); df.to_csv("data/sample_90d_simulated.csv", index=False)
f = core.forecast_demand(df); print("Forecast method:", f["method"], "|", f["reason"]); print("Test metrics:", f.get("metrics_test"))
r = core.optimize_battery(f["forecast"] - df.solar_kw.to_numpy()[-24:], core.tariff_for(f["timestamps"]), 800, 100, 200, 200)
print({k: round(r[k], 2) for k in ["baseline_cost", "optimized_cost", "savings", "baseline_peak_kw", "optimized_peak_kw", "battery_losses_kwh"]}, r["status"])
print("Anomalies flagged:", len(core.detect_anomalies(df)), "| injected:", int(df.injected_anomaly.sum()))
