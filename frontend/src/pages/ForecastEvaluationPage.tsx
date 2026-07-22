import { useEffect, useState } from "react";
import { getDataReport } from "../api/data";

export function ForecastEvaluationPage() {
  const [status, setStatus] = useState<unknown>();
  const [metrics, setMetrics] = useState<unknown>();
  useEffect(() => { void Promise.all([getDataReport("/forecast/status"), getDataReport("/forecast/metrics")]).then(([a,b]) => { setStatus(a); setMetrics(b); }); }, []);
  return <section className="mx-auto max-w-7xl px-6 py-16 lg:px-10"><p className="text-xs font-semibold uppercase tracking-[.18em] text-air">Internal evaluation</p><h1 className="mt-3 text-4xl font-semibold">Forecast evaluation</h1><p className="mt-4 max-w-3xl text-sm leading-7 text-mist">Historical replay only. Forecasts are evaluated against held-out observations and are never presented as live while source data is stale.</p><div className="mt-10 grid gap-4 md:grid-cols-2"><article className="rounded-xl border border-line bg-panel/50 p-5"><h2 className="font-medium">Mode and freshness</h2><pre className="mt-4 overflow-auto text-xs text-mist">{JSON.stringify(status, null, 2)}</pre></article><article className="rounded-xl border border-line bg-panel/50 p-5"><h2 className="font-medium">Untouched test metrics</h2><pre className="mt-4 overflow-auto text-xs text-mist">{JSON.stringify(metrics, null, 2)}</pre></article></div></section>;
}
