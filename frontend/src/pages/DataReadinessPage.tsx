import { useEffect, useState } from "react";

import { getDataReport, type DataReport } from "../api/data";

type ReportState = Record<string, DataReport>;

const reports = [
  ["Sources", "/data/sources"],
  ["Coverage", "/data/coverage"],
  ["Quality", "/data/quality"],
  ["Cities", "/data/cities"],
  ["Stations", "/data/stations"],
  ["Readiness", "/data/readiness"],
  ["Archive availability", "/data/archive/availability"],
  ["Download plan", "/data/archive/plan"],
  ["Model readiness", "/data/model-readiness"],
  ["CPCB recovery", "/data/sources/cpcb"],
  ["Sentinel-5P", "/data/sources/sentinel"],
  ["NASA FIRMS", "/data/sources/firms"],
  ["GHSL population", "/data/sources/ghsl"],
  ["OSM coverage", "/data/sources/osm"],
  ["Source failures", "/data/sources/failures"],
  ["Latest pipeline run", "/data/pipeline/latest-run"],
] as const;

export function DataReadinessPage() {
  const [state, setState] = useState<ReportState>({});

  useEffect(() => {
    const controller = new AbortController();
    void Promise.all(reports.map(async ([label, path]) => [label, await getDataReport(path)] as const))
      .then((items) => {
        if (!controller.signal.aborted) setState(Object.fromEntries(items));
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ Connection: { status: "not_ready", message: "The data-status API is unavailable." } });
      });
    return () => controller.abort();
  }, []);

  return (
    <section className="mx-auto min-h-[70vh] max-w-7xl px-6 py-16 lg:px-10 lg:py-20">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-air">Internal view</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-tight">Data readiness</h1>
      <p className="mt-4 max-w-2xl text-sm leading-7 text-mist">
        This view reflects generated pipeline reports only. It does not infer source coverage or invent national metrics.
      </p>
      <div className="mt-10 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {reports.map(([label]) => {
          const report = state[label];
          const ready = report?.status === "ready";
          return (
            <article className="rounded-xl border border-line bg-panel/50 p-5" key={label}>
              <div className="flex items-center justify-between gap-4">
                <h2 className="font-medium">{label}</h2>
                <span className={`h-2.5 w-2.5 rounded-full ${ready ? "bg-air" : "bg-mist/50"}`} />
              </div>
              <p className="mt-4 text-sm text-mist">
                {report ? (ready ? "Generated report available" : report.message ?? "Not ready") : "Loading report status…"}
              </p>
            </article>
          );
        })}
      </div>
    </section>
  );
}
