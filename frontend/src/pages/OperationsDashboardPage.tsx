import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getOperationalCities,
  getOperationsDashboard,
  getNetworkOverview,
  operationsError,
  type CityConfig,
  type DashboardMode,
  type Language,
  type NetworkOverview,
  type OperationsDashboard,
  type Pollutant,
} from "../api/operations";
import { ForecastChart } from "../components/operations/ForecastChart";
import { RefreshIcon } from "../components/operations/Icons";
import { MetricCard } from "../components/operations/MetricCard";
import { Section } from "../components/operations/Section";

const OperationsMap = lazy(() =>
  import("../components/operations/OperationsMap").then((module) => ({
    default: module.OperationsMap,
  })),
);

const aqiColor: Record<string, string> = {
  Good: "#54d189",
  Satisfactory: "#9acb59",
  Moderate: "#e1ba4e",
  Poor: "#ef8d45",
  "Very Poor": "#ef5a5a",
  Severe: "#b95073",
};

function localDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function titlePollutant(value: Pollutant) {
  return value === "pm2_5" ? "PM2.5" : "PM10";
}

function LoadingDashboard() {
  return (
    <div className="grid gap-4 lg:grid-cols-4" aria-live="polite">
      {Array.from({ length: 8 }, (_, index) => (
        <div
          key={index}
          className="h-36 animate-pulse rounded-xl border border-slate-800 bg-slate-900/80"
        />
      ))}
    </div>
  );
}

export function OperationsDashboardPage() {
  const [cities, setCities] = useState<CityConfig[]>([]);
  const [cityId, setCityId] = useState("delhi-ncr");
  const [pollutant, setPollutant] = useState<Pollutant>("pm2_5");
  const [horizon, setHorizon] = useState<24 | 48 | 72>(72);
  const [language, setLanguage] = useState<Language>("en");
  const [mode, setMode] = useState<DashboardMode>("live");
  const [dashboard, setDashboard] = useState<OperationsDashboard>();
  const [network, setNetwork] = useState<NetworkOverview>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    void getOperationalCities(controller.signal)
      .then(setCities)
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(operationsError(reason));
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void getNetworkOverview(mode, controller.signal)
      .then(setNetwork)
      .catch(() => undefined);
    return () => controller.abort();
  }, [mode, refreshKey]);

  const loadDashboard = useCallback(
    (signal: AbortSignal) => {
      setLoading(true);
      setError("");
      return getOperationsDashboard(
        { cityId, pollutant, horizon, language, mode },
        signal,
      )
        .then(setDashboard)
        .catch((reason: unknown) => {
          if (!signal.aborted) setError(operationsError(reason));
        })
        .finally(() => {
          if (!signal.aborted) setLoading(false);
        });
    },
    [cityId, horizon, language, mode, pollutant],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadDashboard(controller.signal);
    return () => controller.abort();
  }, [loadDashboard, refreshKey]);

  const selectedCity = cities.find((city) => city.city_id === cityId);
  const peak = dashboard?.forecast.peak;
  const topSources = useMemo(
    () =>
      dashboard?.intelligence.rankings
        .filter((item) => item.influence != null)
        .slice(0, 5) ?? [],
    [dashboard],
  );
  const liveFallback = mode === "live" && dashboard && !dashboard.live;

  return (
    <div className="mx-auto w-full max-w-[1560px] px-4 pb-12 pt-5 sm:px-6 lg:px-8">
      <header className="mb-5 flex flex-col justify-between gap-5 border-b border-slate-800 pb-5 xl:flex-row xl:items-end">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">
              Urban air operations
            </p>
            <span
              className={`status-chip ${dashboard?.live ? "status-live" : "status-replay"}`}
            >
              {dashboard?.live ? "Live forecast" : "Validated replay"}
            </span>
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white sm:text-4xl">
            Air-quality intervention command centre
          </h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            Forecast pollution 24–72 hours ahead, identify likely contributing
            context, and prioritise field action from one operational view.
          </p>
        </div>
        <p className="text-xs text-slate-500">
          Last assembled{" "}
          {dashboard ? localDate(dashboard.generated_at_utc) : "—"}
        </p>
      </header>

      <div className="control-bar mb-5">
        <label>
          <span>City</span>
          <select
            value={cityId}
            onChange={(event) => setCityId(event.target.value)}
          >
            {cities.map((city) => (
              <option key={city.city_id} value={city.city_id}>
                {city.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Pollutant</span>
          <select
            value={pollutant}
            onChange={(event) => setPollutant(event.target.value as Pollutant)}
          >
            <option value="pm2_5">PM2.5</option>
            <option value="pm10">PM10</option>
          </select>
        </label>
        <label>
          <span>Forecast window</span>
          <select
            value={horizon}
            onChange={(event) =>
              setHorizon(Number(event.target.value) as 24 | 48 | 72)
            }
          >
            <option value={24}>Next 24 hours</option>
            <option value={48}>Next 48 hours</option>
            <option value={72}>Next 72 hours</option>
          </select>
        </label>
        <label>
          <span>Advisory language</span>
          <select
            value={language}
            onChange={(event) => setLanguage(event.target.value as Language)}
          >
            <option value="en">English</option>
            <option value="hi">हिन्दी</option>
            <option value="pa">ਪੰਜਾਬੀ</option>
          </select>
        </label>
        <div className="mode-switch" role="group" aria-label="Data mode">
          <button
            className={mode === "live" ? "active" : ""}
            onClick={() => setMode("live")}
          >
            Live
          </button>
          <button
            className={mode === "demo" ? "active" : ""}
            onClick={() => setMode("demo")}
          >
            Replay
          </button>
        </div>
        <button
          className="refresh-button"
          onClick={() => setRefreshKey((value) => value + 1)}
          disabled={loading}
        >
          <RefreshIcon />
          Refresh
        </button>
      </div>

      {liveFallback && (
        <div className="mb-5 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <strong>Live providers are temporarily unavailable.</strong> AirView
          automatically switched to a validated historical replay so the
          operational workflow remains demonstrable.
        </div>
      )}
      {dashboard?.coverage_note && (
        <div className="mb-5 rounded-lg border border-sky-500/35 bg-sky-500/10 px-4 py-3 text-sm leading-6 text-sky-100">
          <strong>Regional replay note.</strong> {dashboard.coverage_note}
        </div>
      )}
      {error && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          <span>{error}</span>
          <button
            className="text-xs font-semibold uppercase tracking-wide"
            onClick={() => setRefreshKey((value) => value + 1)}
          >
            Retry
          </button>
        </div>
      )}

      {loading && !dashboard ? (
        <LoadingDashboard />
      ) : (
        dashboard && (
          <>
            <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Current concentration"
                value={
                  <>
                    {dashboard.current.value.toFixed(1)}{" "}
                    <span className="text-base font-medium text-slate-400">
                      µg/m³
                    </span>
                  </>
                }
                detail={`${dashboard.current.source} · ${localDate(dashboard.current.timestamp_utc)}`}
              />
              <MetricCard
                label={`${horizon}h forecast peak`}
                value={peak ? `${peak.value.toFixed(1)} µg/m³` : "Unavailable"}
                detail={
                  peak
                    ? `Expected around ${localDate(peak.timestamp_utc)}`
                    : "No peak could be resolved"
                }
                accent={aqiColor[peak?.category ?? ""]}
              />
              <MetricCard
                label="Forecast AQI category"
                value={peak?.category ?? "Unclassified"}
                detail={
                  peak?.aqi != null
                    ? `Exploratory 24-hour PM sub-index: ${peak.aqi}`
                    : "Insufficient rolling window for AQI sub-index"
                }
                accent={aqiColor[peak?.category ?? ""]}
              />
              <MetricCard
                label="Intervention priority"
                value={dashboard.intelligence.priority}
                detail={`${Math.round(dashboard.intelligence.confidence * 100)}% evidence confidence · ${dashboard.intelligence.firms_event_count} thermal anomalies`}
                accent={
                  dashboard.intelligence.priority === "Critical"
                    ? "#ef5a5a"
                    : "#f2c14e"
                }
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.55fr_0.9fr]">
              <Section
                title={`${titlePollutant(pollutant)} forecast trajectory`}
                eyebrow="Predictive intelligence"
                action={
                  <span className="text-xs text-slate-400">
                    Issued {localDate(dashboard.forecast.issue_timestamp)}
                  </span>
                }
              >
                <ForecastChart forecast={dashboard.forecast} />
              </Section>
              <Section
                title="Likely contributing context"
                eyebrow="Source screening"
              >
                <div className="space-y-4">
                  {topSources.map((source) => (
                    <div key={source.category_id}>
                      <div className="flex items-center justify-between gap-4 text-sm">
                        <span className="font-medium text-slate-200">
                          {source.label}
                        </span>
                        <span className="text-slate-400">
                          {Math.round((source.influence ?? 0) * 100)} indicator
                        </span>
                      </div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                        <div
                          className="h-full rounded-full bg-emerald-400"
                          style={{
                            width: `${Math.max(3, (source.influence ?? 0) * 100)}%`,
                          }}
                        />
                      </div>
                      <p className="mt-1.5 text-xs leading-5 text-slate-500">
                        {source.evidence[0] ?? "Evidence unavailable"}
                      </p>
                    </div>
                  ))}
                </div>
                <p className="mt-5 border-t border-slate-800 pt-4 text-xs leading-5 text-slate-500">
                  Influence indicators rank supporting context; they are not
                  emission shares or regulatory source apportionment.
                </p>
              </Section>
            </div>

            <div className="mt-5 grid gap-5 xl:grid-cols-[1.45fr_1fr]">
              <Section
                title="Hyperlocal intervention view"
                eyebrow="Geospatial intelligence"
              >
                <Suspense
                  fallback={
                    <div className="h-[430px] animate-pulse rounded-lg bg-slate-900" />
                  }
                >
                  <OperationsMap dashboard={dashboard} />
                </Suspense>
              </Section>
              <div className="grid gap-5">
                <Section
                  title="Recommended action queue"
                  eyebrow="Enforcement intelligence"
                >
                  <div className="space-y-3">
                    {dashboard.actions.length ? (
                      dashboard.actions.map((action) => (
                        <article
                          key={`${action.rank}-${action.source_category}`}
                          className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"
                        >
                          <div className="flex items-start gap-3">
                            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-emerald-400/15 text-xs font-semibold text-emerald-300">
                              {action.rank}
                            </span>
                            <div>
                              <h3 className="text-sm font-semibold text-slate-100">
                                {action.action}
                              </h3>
                              <p className="mt-1 text-xs text-slate-400">
                                {action.source_category} · {action.agency}
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <span className="data-tag">
                                  {action.response_time}
                                </span>
                                <span className="data-tag">
                                  {action.cost_tier} cost
                                </span>
                                {action.estimated_sensitivity_range_percent && (
                                  <span className="data-tag">
                                    {
                                      action
                                        .estimated_sensitivity_range_percent[0]
                                    }
                                    –
                                    {
                                      action
                                        .estimated_sensitivity_range_percent[1]
                                    }
                                    % sensitivity
                                  </span>
                                )}
                              </div>
                              <p className="mt-3 text-xs leading-5 text-slate-500">
                                {action.caveat}
                              </p>
                            </div>
                          </div>
                        </article>
                      ))
                    ) : (
                      <p className="text-sm text-slate-400">
                        No evidence-supported action is available for this
                        replay.
                      </p>
                    )}
                  </div>
                </Section>
                <Section
                  title="Weather and dispersion"
                  eyebrow="Atmospheric context"
                >
                  <dl className="grid grid-cols-2 gap-3 text-sm">
                    <div className="stat-cell">
                      <dt>Wind speed</dt>
                      <dd>
                        {dashboard.map.wind.speed != null
                          ? `${Number(dashboard.map.wind.speed).toFixed(1)} m/s`
                          : "Unavailable"}
                      </dd>
                    </div>
                    <div className="stat-cell">
                      <dt>Wind direction</dt>
                      <dd>
                        {dashboard.map.wind.direction != null
                          ? `${Number(dashboard.map.wind.direction).toFixed(0)}°`
                          : "Unavailable"}
                      </dd>
                    </div>
                    <div className="stat-cell">
                      <dt>Spatial evidence</dt>
                      <dd>
                        {dashboard.map.osm_available ? "Available" : "Partial"}
                      </dd>
                    </div>
                    <div className="stat-cell">
                      <dt>Forecast source</dt>
                      <dd>
                        {dashboard.live
                          ? "Live numerical feeds"
                          : "Validated replay"}
                      </dd>
                    </div>
                  </dl>
                </Section>
              </div>
            </div>

            <div className="mt-5 grid gap-5 xl:grid-cols-2">
              <Section
                title="Citizen health advisory"
                eyebrow="Public communication"
              >
                <h3 className="text-xl font-semibold leading-8 text-white">
                  {dashboard.advisory.headline}
                </h3>
                <p className="mt-3 text-sm leading-6 text-slate-300">
                  {dashboard.advisory.summary}
                </p>
                <ul className="mt-4 space-y-3">
                  {dashboard.advisory.actions.map((action) => (
                    <li
                      key={action}
                      className="flex gap-3 text-sm leading-6 text-slate-300"
                    >
                      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-400" />
                      {action}
                    </li>
                  ))}
                </ul>
                <p className="mt-5 border-t border-slate-800 pt-4 text-xs leading-5 text-slate-500">
                  {dashboard.advisory.disclaimer}
                </p>
              </Section>
              <Section
                title="Data pipeline status"
                eyebrow="Operational readiness"
              >
                <div className="grid gap-3 sm:grid-cols-2">
                  {Object.entries(dashboard.provider_status).map(
                    ([provider, status]) => (
                      <div
                        key={provider}
                        className="rounded-lg border border-slate-800 bg-slate-950/40 p-4"
                      >
                        <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                          {provider.replaceAll("_", " ")}
                        </p>
                        <p className="mt-2 text-sm font-medium text-slate-200">
                          {status}
                        </p>
                      </div>
                    ),
                  )}
                </div>
                <p className="mt-5 text-xs leading-5 text-slate-500">
                  {dashboard.disclaimer}
                </p>
              </Section>
            </div>
          </>
        )
      )}

      {network && (
        <div className="mt-5">
          <Section
            title="Five-city outlook"
            eyebrow="Comparative intelligence"
            action={
              <span className="text-xs text-slate-500">
                PM2.5 · next 24 hours
              </span>
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-[10px] uppercase tracking-[0.13em] text-slate-500">
                    <th className="px-3 py-3 font-semibold">City</th>
                    <th className="px-3 py-3 font-semibold">Current</th>
                    <th className="px-3 py-3 font-semibold">24h peak</th>
                    <th className="px-3 py-3 font-semibold">Category</th>
                    <th className="px-3 py-3 font-semibold">Priority</th>
                    <th className="px-3 py-3 font-semibold">Feed</th>
                  </tr>
                </thead>
                <tbody>
                  {network.cities.map((item) => (
                    <tr
                      key={item.city_id}
                      className={`border-b border-slate-800/70 ${item.city_id === cityId ? "bg-emerald-400/[0.05]" : ""}`}
                    >
                      <td className="px-3 py-3 font-medium text-slate-100">
                        <button
                          className="text-left hover:text-emerald-300"
                          onClick={() => setCityId(item.city_id)}
                        >
                          {item.city_name}
                        </button>
                        <span className="ml-2 text-xs font-normal text-slate-500">
                          {item.state}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-slate-300">
                        {item.current.toFixed(1)} µg/m³
                      </td>
                      <td className="px-3 py-3 text-slate-300">
                        {item.peak_24h.toFixed(1)} µg/m³
                      </td>
                      <td className="px-3 py-3">
                        <span
                          className="font-medium"
                          style={{ color: aqiColor[item.category ?? ""] }}
                        >
                          {item.category ?? "Unclassified"}
                        </span>
                      </td>
                      <td className="px-3 py-3 text-slate-300">
                        {item.priority}
                      </td>
                      <td className="px-3 py-3 text-xs text-slate-500">
                        {item.mode === "live_numerical_outlook"
                          ? "Live numerical"
                          : "Replay fallback"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-4 text-xs leading-5 text-slate-500">
              {network.methodology}. Select any city row to open its full
              operational workflow.
            </p>
          </Section>
        </div>
      )}

      <footer className="mt-8 flex flex-col gap-2 border-t border-slate-800 pt-5 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
        <span>
          {dashboard?.city.station_name ??
            selectedCity?.station_name ??
            "AirView monitoring network"}
        </span>
        <span>
          Five-city operational prototype · OpenAQ · Open-Meteo CAMS · NASA
          FIRMS · OpenStreetMap
        </span>
      </footer>
    </div>
  );
}
