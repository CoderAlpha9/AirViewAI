import type { ReactNode } from "react";

export function Section({ title, eyebrow, action, children, className = "" }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`dashboard-panel p-5 sm:p-6 ${className}`}>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>{eyebrow && <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-300">{eyebrow}</p>}<h2 className="mt-1 text-lg font-semibold text-slate-100">{title}</h2></div>
        {action}
      </div>
      {children}
    </section>
  );
}
