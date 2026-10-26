# Limitations
- Simulated data only; no real grid/weather/meter integration; never controls physical equipment.
- Persistence is SQLite (not PostgreSQL); no migrations; no authentication; single simulated facility.
- Solar forecast is a persistence baseline. No prediction intervals, demand charges or export credits. Live simulation advances one simulated hour per tick, uses a fixed rule-based battery, and is in-memory (resets on restart).
- Optimizer savings are simulated estimates using illustrative tariffs.
- Recommendation benefits rest on stated assumptions (e.g. 10% movable peak load).
- "Verified savings" only reflects a user attestation of confounder control; it is not independent verification.
- Test coverage: core analytics and persistence logic. API routes, frontend and Docker images have not been run by the author's sandbox.
