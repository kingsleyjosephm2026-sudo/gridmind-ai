import { useEffect, useState, FormEvent } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

const API = import.meta.env.VITE_API_URL ?? "/api";
async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) throw new Error(`${r.status}: ${(await r.json().catch(() => ({}))).detail ?? r.statusText}`);
  return r.json();
}
function useApi<T>(path: string, dep = 0) {
  const [data, setData] = useState<T | null>(null); const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  useEffect(() => { setLoading(true); call<T>(path).then(setData).then(() => setError("")).catch(e => setError(String(e.message))).finally(() => setLoading(false)); }, [path, dep]);
  return { data, error, loading };
}
const State = ({ loading, error }: { loading: boolean; error: string }) => loading ? <p>Loading…</p> : error ? <p className="err">Error: {error}</p> : null;

function Overview() {
  const { data, error, loading } = useApi<{ rows: number; total_kwh: number; peak_kw: number; solar_kwh: number }>("/summary");
  return <><State loading={loading} error={error} />{data && <div className="kpis">
    <div className="kpi">Hourly rows<b>{data.rows}</b></div><div className="kpi">Total energy<b>{data.total_kwh.toFixed(0)} kWh</b></div>
    <div className="kpi">Peak demand<b>{data.peak_kw.toFixed(0)} kW</b></div><div className="kpi">Solar<b>{data.solar_kwh.toFixed(0)} kWh</b></div></div>}</>;
}
function Forecast() {
  const { data, error, loading } = useApi<{ method: string; reason: string; timestamps: string[]; forecast_kw: number[]; metrics_test?: { baseline: { mae: number }; model: { mae: number } } }>("/forecast");
  return <><State loading={loading} error={error} />{data && <><p>Method: <b>{data.method}</b> — {data.reason}</p>
    {data.metrics_test && <p>Test MAE: baseline {data.metrics_test.baseline.mae.toFixed(1)} kW vs model {data.metrics_test.model.mae.toFixed(1)} kW (simulated data)</p>}
    <ResponsiveContainer width="100%" height={280}><LineChart data={data.forecast_kw.map((v, i) => ({ t: data.timestamps[i].slice(11, 16), kW: +v.toFixed(1) }))}>
      <XAxis dataKey="t" /><YAxis /><Tooltip /><Line dataKey="kW" stroke="#2563eb" dot={false} /></LineChart></ResponsiveContainer></>}</>;
}
type Opt = { status: string; message?: string; charge_kw: number[]; discharge_kw: number[]; soc_kwh: number[]; baseline_cost: number; optimized_cost: number; savings: number; baseline_peak_kw?: number; optimized_peak_kw?: number; battery_losses_kwh?: number };
function Battery() {
  const [cap, setCap] = useState(800); const [res, setRes] = useState<Opt | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const run = (e: FormEvent) => { e.preventDefault(); setBusy(true); call<Opt>("/optimize", { method: "POST", body: JSON.stringify({ capacity_kwh: cap, soc0_kwh: Math.min(100, cap * 0.5) }) })
    .then(r => { setRes(r); setError(""); }).catch(e => setError(e.message)).finally(() => setBusy(false)); };
  return <><form onSubmit={run}><label>Battery capacity (kWh) <input type="number" min={0} value={cap} onChange={e => setCap(+e.target.value)} /></label>
    <button className="act" disabled={busy}>{busy ? "Optimizing…" : "Run simulated optimization"}</button></form>
    {error && <p className="err">{error}</p>}
    {res && <><p>Status: {res.status} {res.message}</p><div className="kpis"><div className="kpi">Baseline cost<b>₹{res.baseline_cost.toFixed(0)}</b></div>
      <div className="kpi">Optimized cost<b>₹{res.optimized_cost.toFixed(0)}</b></div><div className="kpi">Simulated saving<b>₹{res.savings.toFixed(0)}</b></div></div>
      <ResponsiveContainer width="100%" height={280}><LineChart data={res.charge_kw.map((c, h) => ({ h, charge: c, discharge: res.discharge_kw[h], soc: res.soc_kwh[h + 1] }))}>
        <XAxis dataKey="h" /><YAxis /><Tooltip /><Legend /><Line dataKey="charge" stroke="#16a34a" dot={false} /><Line dataKey="discharge" stroke="#dc2626" dot={false} /><Line dataKey="soc" stroke="#2563eb" dot={false} /></LineChart></ResponsiveContainer>
      <p>Simulated estimate, not verified savings.</p></>}</>;
}
function Anomalies() {
  const { data, error, loading } = useApi<{ timestamp: string; observed: number; expected: number; severity: string; explanation: string }[]>("/anomalies");
  return <><State loading={loading} error={error} />{data && (data.length === 0 ? <p>No anomalies detected.</p> : <table><thead><tr><th>Time</th><th>Observed kW</th><th>Expected kW</th><th>Severity</th><th>Note</th></tr></thead>
    <tbody>{data.map(a => <tr key={a.timestamp}><td>{a.timestamp}</td><td>{a.observed.toFixed(0)}</td><td>{a.expected.toFixed(0)}</td><td>{a.severity}</td><td>{a.explanation}</td></tr>)}</tbody></table>)}</>;
}
type Rec = { id: number; title: string; evidence: string; severity: string; action: string; expected_benefit_inr: number | null; method: string; assumptions: string; confidence: string; status: string };
function Recs() {
  const [n, setN] = useState(0); const { data, error, loading } = useApi<Rec[]>("/recommendations", n); const [err, setErr] = useState("");
  const set = (id: number, status: string) => call(`/recommendations/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }).then(() => setN(n + 1)).catch(e => setErr(e.message));
  return <><State loading={loading} error={error || err} />{data?.map(r => <div className="card" key={r.id}><b>{r.title}</b> ({r.severity})
    <p>{r.evidence}</p><p>Action: {r.action}</p>{r.expected_benefit_inr != null && <p>Scenario estimate: ₹{r.expected_benefit_inr.toFixed(0)} — {r.method}</p>}
    <p><small>Assumptions: {r.assumptions} · Evidence strength: {r.confidence}</small></p>
    <select value={r.status} onChange={e => set(r.id, e.target.value)}>{["Open", "In progress", "Resolved", "Dismissed"].map(s => <option key={s}>{s}</option>)}</select></div>)}</>;
}
function Savings() {
  const [n, setN] = useState(0); const { data, error, loading } = useApi<{ id: number; name: string; calculated_savings: number; classification: string; method: string }[]>("/savings", n);
  const [f, setF] = useState({ name: "", baseline_kwh: 0, baseline_cost: 0, post_kwh: 0, post_cost: 0, baseline_hours: 0, post_hours: 0, confounders_controlled: false }); const [err, setErr] = useState("");
  const submit = (e: FormEvent) => { e.preventDefault(); const body = { ...f, baseline_hours: f.baseline_hours || null, post_hours: f.post_hours || null };
    call("/savings", { method: "POST", body: JSON.stringify(body) }).then(() => { setN(n + 1); setErr(""); }).catch(e => setErr(e.message)); };
  const num = (k: keyof typeof f, label: string) => <label>{label} <input type="number" step="any" value={f[k] as number} onChange={e => setF({ ...f, [k]: +e.target.value })} /></label>;
  return <><form onSubmit={submit} className="card"><label>Initiative <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} required /></label>
    {num("baseline_kwh", "Baseline kWh")}{num("baseline_cost", "Baseline ₹")}{num("post_kwh", "Post kWh")}{num("post_cost", "Post ₹")}{num("baseline_hours", "Baseline op. hours")}{num("post_hours", "Post op. hours")}
    <label><input type="checkbox" checked={f.confounders_controlled} onChange={e => setF({ ...f, confounders_controlled: e.target.checked })} /> I controlled weather/production/tariff changes</label>
    <button className="act">Record</button>{err && <p className="err">{err}</p>}</form>
    <State loading={loading} error={error} />{data && <table><thead><tr><th>Initiative</th><th>Savings ₹</th><th>Classification</th><th>Formula</th></tr></thead>
      <tbody>{data.map(s => <tr key={s.id}><td>{s.name}</td><td>{s.calculated_savings.toFixed(0)}</td><td>{s.classification}</td><td>{s.method}</td></tr>)}</tbody></table>}</>;
}
type Sim = { running: boolean; rows: number; source: string; latest: { timestamp: string; demand_kw: number; solar_kw: number; grid_import_kw: number; soc_kwh: number } | null; recent_events: { timestamp: string; demand_kw: number; grid_import_kw: number; soc_kwh: number }[] };
function Live() {
  const [s, setS] = useState<Sim | null>(null); const [err, setErr] = useState("");
  const act = (a?: string) => call<Sim>(a ? `/simulation/${a}` : "/simulation/status", a ? { method: "POST" } : undefined).then(r => { setS(r); setErr(""); }).catch(e => setErr(e.message));
  useEffect(() => { act(); const t = setInterval(() => act(), 5000); return () => clearInterval(t); }, []);
  return <>{err && <p className="err">{err}</p>}{s && <><p>{s.running ? "● LIVE DEMO (simulated)" : "Paused"} — {s.source}</p>
    <button className="act" onClick={() => act("start")}>Start</button><button className="act" onClick={() => act("pause")}>Pause</button><button className="act" onClick={() => act("reset")}>Reset</button>
    {s.latest ? <div className="kpis"><div className="kpi">Latest (sim. time)<b>{s.latest.timestamp.slice(0, 16)}</b></div><div className="kpi">Demand<b>{s.latest.demand_kw.toFixed(0)} kW</b></div>
      <div className="kpi">Solar<b>{s.latest.solar_kw.toFixed(0)} kW</b></div><div className="kpi">Grid import<b>{s.latest.grid_import_kw.toFixed(0)} kW</b></div><div className="kpi">Battery<b>{s.latest.soc_kwh.toFixed(0)} kWh</b></div></div> : <p>Press Start to generate simulated readings.</p>}
    <table><tbody>{s.recent_events.map(e => <tr key={e.timestamp}><td>{e.timestamp.slice(0, 16)}</td><td>{e.demand_kw.toFixed(0)} kW</td><td>{e.grid_import_kw.toFixed(0)} kW import</td><td>{e.soc_kwh.toFixed(0)} kWh</td></tr>)}</tbody></table>
    <p><a href={API + "/export.csv"}>Download CSV</a></p></>}</>;
}
const PAGES: Record<string, () => JSX.Element> = { Overview, "Live Simulation": Live, Forecast, Battery, Anomalies, Recommendations: Recs, "Savings Verification": Savings };
export default function App() {
  const [page, setPage] = useState("Overview"); const Page = PAGES[page];
  return <div className="layout"><nav><h1>GridMind AI</h1>{Object.keys(PAGES).map(p => <button key={p} className={p === page ? "on" : ""} onClick={() => setPage(p)}>{p}</button>)}</nav>
    <main><div className="banner">Demo with SIMULATED data. Not connected to a real grid; savings are simulated estimates.</div><h2>{page}</h2><Page /></main></div>;
}
