import type { ReactNode } from "react";

export function MetricCard({ label, value, detail, accent }: { label: string; value: ReactNode; detail: string; accent?: string }) {
  return (
    <article className="dashboard-panel min-h-32 p-5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">{label}</p>
      <div className="mt-3 text-3xl font-semibold tracking-tight" style={{ color: accent }}>{value}</div>
      <p className="mt-2 text-xs leading-5 text-slate-400">{detail}</p>
    </article>
  );
}
