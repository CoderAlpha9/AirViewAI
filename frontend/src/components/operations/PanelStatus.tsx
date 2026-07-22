import type { ReactNode } from "react";

export function PanelSkeleton({ height = "h-48" }: { height?: string }) {
  return (
    <div className={`${height} animate-pulse rounded-lg bg-slate-800/55`} aria-label="Loading panel" aria-busy="true">
      <span className="sr-only">Loading current data</span>
    </div>
  );
}

export function PanelError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="grid min-h-32 place-items-center rounded-lg bg-slate-950/35 px-5 py-8 text-center" role="status">
      <div>
        <p className="text-sm text-slate-300">{message}</p>
        <button className="mt-3 rounded-md border border-slate-600 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:border-teal-500 hover:text-white" onClick={onRetry}>
          Retry panel
        </button>
      </div>
    </div>
  );
}

export function EmptyPanel({ children }: { children: ReactNode }) {
  return <div className="grid min-h-28 place-items-center rounded-lg bg-slate-950/30 px-5 py-7 text-center text-sm text-slate-400">{children}</div>;
}
