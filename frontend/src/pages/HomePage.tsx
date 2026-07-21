import { ApiStatus } from "../components/ApiStatus";

const foundationAreas = [
  ["Observe", "Validated city, sensor, weather, mobility, and remote-sensing inputs."],
  ["Understand", "Spatial-temporal forecasting, hotspot analysis, and source attribution."],
  ["Intervene", "Evidence-led enforcement, impact estimation, and public health guidance."],
] as const;

export function HomePage() {
  return (
    <>
      <section className="relative overflow-hidden">
        <div className="air-grid absolute inset-0 opacity-30" aria-hidden="true" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-6 py-20 sm:py-28 lg:grid-cols-[1.35fr_0.65fr] lg:items-end lg:px-10 lg:py-36">
          <div>
            <p className="mb-6 text-xs font-semibold uppercase tracking-[0.22em] text-air">
              Urban air-quality intelligence
            </p>
            <h1 className="max-w-4xl text-5xl font-semibold leading-[0.98] tracking-[-0.045em] sm:text-6xl lg:text-7xl">
              AirView AI
            </h1>
            <p className="mt-7 max-w-2xl text-xl leading-relaxed text-mist sm:text-2xl">
              From air-quality monitoring to intelligent city intervention.
            </p>
            <p className="mt-8 max-w-2xl border-l-2 border-air/60 pl-5 text-sm leading-7 text-mist">
              A decision-support foundation for turning environmental observations into
              transparent forecasts, source evidence, prioritised action, and citizen guidance.
            </p>
          </div>
          <ApiStatus />
        </div>
      </section>

      <section className="border-t border-line/70 bg-panel/30">
        <div className="mx-auto max-w-7xl px-6 py-16 lg:px-10 lg:py-20">
          <div className="mb-10 max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-air">
              Platform direction
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight">One operational view of urban air</h2>
          </div>
          <div className="grid gap-px overflow-hidden rounded-2xl border border-line bg-line md:grid-cols-3">
            {foundationAreas.map(([title, description], index) => (
              <article className="bg-ink p-7" key={title}>
                <span className="text-xs font-medium tabular-nums text-air">0{index + 1}</span>
                <h3 className="mt-8 text-xl font-medium">{title}</h3>
                <p className="mt-3 text-sm leading-6 text-mist">{description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

