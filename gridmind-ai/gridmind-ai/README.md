# GridMind AI

Energy forecasting, anomaly detection, battery-cost optimization, recommendations and savings tracking — a **prototype under development**.
All data is **SIMULATED**. No real grid connection, no deployed customers, no verified savings.

## Features
React + TypeScript dashboard (Overview, Forecast, Battery, Anomalies, Recommendations, Savings Verification) over a FastAPI backend.
- Forecast: baseline vs gradient boosting, chronological split, baseline fallback
- Optimizer: SciPy linear program with SOC/power/efficiency/reserve constraints
- Anomalies: robust z-score by weekday-hour (candidates, not confirmed faults)
- Recommendations + savings tracking persisted in SQLite; "Verified" is never automatic
- Simulated live feed (start/pause/reset) that appends readings used by all analytics; CSV export
- CSV validation endpoint with rejected-row reasons

## Run with Docker (simplest)
```
cp .env.example .env
docker compose up --build
```
App + API on one port: http://localhost:8000  ·  API docs: http://localhost:8000/docs

## Deploy (Render, free tier)
Render dashboard → New → Blueprint → select this repo (uses `render.yaml`). Free instances sleep when idle and lose SQLite data on restart.

## Run without Docker
```
pip install -r requirements.txt && uvicorn api.main:app --reload
cd frontend && npm install && npm run dev      # http://localhost:5173
python -m unittest discover -s tests -v
```

## Status
See LIMITATIONS.md. Not yet built: PostgreSQL/Alembic, solar ML model, demand charges, auth.
