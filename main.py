"""FastAPI layer (NOT executed in the build sandbox: fastapi was not installable offline). Data is SIMULATED."""
import asyncio, io, os
from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import pandas as pd
from gridmind import core

app = FastAPI(title="GridMind AI (simulated data)", version="0.1.0")
SIM = core.Simulator(core.generate_data(90, 42))
TICK_SECONDS = float(os.environ.get("GRIDMIND_TICK_SECONDS", "5"))

class BatteryReq(BaseModel):
    capacity_kwh: float = Field(800, ge=0); soc0_kwh: float = Field(100, ge=0)
    max_charge_kw: float = Field(200, ge=0); max_discharge_kw: float = Field(200, ge=0)
    eff_c: float = Field(0.95, gt=0, le=1); eff_d: float = Field(0.95, gt=0, le=1)
    reserve_frac: float = Field(0, ge=0, le=1); deg_cost: float = Field(0.05, ge=0)

@app.get("/health")
def health(): return {"status": "ok", "data_source": "SIMULATED"}

@app.get("/summary")
def summary():
    return {"rows": len(SIM.df), "total_kwh": float(SIM.df.demand_kwh.sum()), "peak_kw": float(SIM.df.demand_kw.max()),
            "solar_kwh": float(SIM.df.solar_kwh.sum()), "source": "SIMULATED"}

@app.get("/forecast")
def forecast():
    f = core.forecast_demand(SIM.df)
    return {"method": f["method"], "reason": f["reason"], "metrics_test": f.get("metrics_test"),
            "timestamps": [str(t) for t in f["timestamps"]], "forecast_kw": [float(v) for v in f["forecast"]]}

@app.post("/optimize")
def optimize(b: BatteryReq):
    f = core.forecast_demand(SIM.df); solar = SIM.df.solar_kw.to_numpy()[-24:]   # persistence solar baseline
    tariff = core.tariff_for(f["timestamps"])
    try:
        r = core.optimize_battery(f["forecast"] - solar, tariff, b.capacity_kwh, b.soc0_kwh, b.max_charge_kw,
                                  b.max_discharge_kw, reserve_frac=b.reserve_frac, eff_c=b.eff_c, eff_d=b.eff_d, deg_cost=b.deg_cost)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in r.items()}

@app.get("/anomalies")
def anomalies():
    return core.detect_anomalies(SIM.df).assign(timestamp=lambda d: d.timestamp.astype(str)).to_dict("records")

@app.post("/validate-csv")
async def validate_csv(file: UploadFile):
    try: df = pd.read_csv(io.BytesIO(await file.read()))
    except Exception: raise HTTPException(400, "Could not parse CSV")
    r = core.validate_readings(df)
    return {"errors": r["errors"], "valid_rows": len(r["valid"]),
            "rejected": r["rejected"].astype(str).to_dict("records")}

# ---- persistence endpoints (SQLite via gridmind.store) ----
from gridmind import store
DB = store.connect()
class StatusReq(BaseModel): status: str
class SavingsReq(BaseModel):
    name: str; baseline_kwh: float; baseline_cost: float; post_kwh: float; post_cost: float
    baseline_hours: float | None = None; post_hours: float | None = None
    expected_savings: float | None = None; confounders_controlled: bool = False; notes: str = ""

@app.get("/recommendations")
def recommendations():
    store.upsert_recommendations(DB, store.generate_recommendations(SIM.df, core.detect_anomalies(SIM.df)))
    return store.list_recommendations(DB)

@app.patch("/recommendations/{rec_id}")
def update_rec(rec_id: int, b: StatusReq):
    try: store.set_status(DB, rec_id, b.status)
    except ValueError as e: raise HTTPException(422, str(e))
    except KeyError: raise HTTPException(404, "recommendation not found")
    return {"id": rec_id, "status": b.status}

@app.get("/savings")
def savings(): return store.list_savings(DB)

@app.post("/savings", status_code=201)
def create_savings(b: SavingsReq):
    try: return {"id": store.add_savings(DB, **b.model_dump())}
    except ValueError as e: raise HTTPException(422, str(e))

# ---- simulation + export ----
async def _loop():
    while True:
        await asyncio.sleep(TICK_SECONDS)
        if SIM.running:
            try: SIM.tick()
            except Exception as e: print("simulation tick failed:", e)

@app.on_event("startup")
async def _start(): asyncio.create_task(_loop())

def _sim_status():
    return {"running": SIM.running, "source": "SIMULATED (not a real grid connection)", "rows": len(SIM.df),
            "latest": SIM.events[-1] if SIM.events else None, "recent_events": SIM.events[-10:][::-1], "tick_seconds": TICK_SECONDS}

@app.get("/simulation/status")
def sim_status(): return _sim_status()

@app.post("/simulation/{action}")
def sim_action(action: str):
    if action == "start": SIM.running = True
    elif action == "pause": SIM.running = False
    elif action == "reset": SIM.reset()
    elif action == "tick": SIM.tick()
    else: raise HTTPException(404, "unknown action")
    return _sim_status()

@app.get("/export.csv")
def export_csv(): return Response(SIM.df.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=gridmind_simulated.csv"})

if os.path.isdir("static"):  # built frontend (single-container deploy); mounted last so API routes win
    app.mount("/", StaticFiles(directory="static", html=True), name="ui")
