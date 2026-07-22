import { lazy, Suspense, useEffect, useMemo, useState } from "react";

import { contextMatches, type Horizon, type LivePanel, type Pollutant } from "../api/live";
import { getNetworkOverview, type NetworkOverview } from "../api/operations";
import { CitySearch } from "../components/operations/CitySearch";
import { AskAirView } from "../components/operations/AskAirView";
import { LiveForecastChart } from "../components/operations/LiveForecastChart";
import { RefreshIcon } from "../components/operations/Icons";
import { EmptyPanel, PanelError, PanelSkeleton } from "../components/operations/PanelStatus";
import { Section } from "../components/operations/Section";
import {
  type ActiveCity,
  useProgressiveDashboard,
} from "../features/operations/useProgressiveDashboard";

const LiveOperationsMap = lazy(() =>
  import("../components/operations/LiveOperationsMap").then((module) => ({
    default: module.LiveOperationsMap,
  })),
);

const defaultCities: ActiveCity[] = [
  { query: "delhi-ncr", cityId: "delhi-ncr", name: "Delhi NCR", state: "Delhi" },
  { query: "agra", cityId: "agra", name: "Agra", state: "Uttar Pradesh" },
  { query: "amritsar", cityId: "amritsar", name: "Amritsar", state: "Punjab" },
  { query: "lucknow", cityId: "lucknow", name: "Lucknow", state: "Uttar Pradesh" },
  { query: "ludhiana", cityId: "ludhiana", name: "Ludhiana", state: "Punjab" },
];

function localDate(value?: string | null) {
  if (!value) return "Unavailable";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

function pollutantLabel(value: Pollutant) {
  return value === "pm2_5" ? "PM2.5" : "PM10";
}

function coverageLabel(value?: string) {
  return value === "station_corrected" ? "Station-corrected" : "Model-based";
}

function retryButton(panel: LivePanel, retry: (panel: LivePanel) => void) {
  return (
    <button className="text-xs font-semibold text-teal-300 hover:text-teal-200" onClick={() => retry(panel)}>
      Retry
    </button>
  );
}

export function OperationsDashboardPage() {
  const [activeCity, setActiveCity] = useState<ActiveCity>(defaultCities[0]);
  const [cityOptions, setCityOptions] = useState(defaultCities);
  const [pollutant, setPollutant] = useState<Pollutant>("pm2_5");
  const [horizon, setHorizon] = useState<Horizon>(24);
  const { states, retry, snapshotId } = useProgressiveDashboard(activeCity, pollutant, horizon);
  const [network, setNetwork] = useState<NetworkOverview>();
  const [networkStatus, setNetworkStatus] = useState<"loading" | "ready" | "error">("loading");
  const [networkRefresh, setNetworkRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setNetworkStatus("loading");
    void getNetworkOverview(controller.signal)
      .then((data) => {
        setNetwork(data);
        setNetworkStatus("ready");
      })
      .catch(() => {
        if (!controller.signal.aborted) setNetworkStatus("error");
      });
    return () => controller.abort();
  }, [networkRefresh]);

  const currentState = states.current;
  const stationState = states.stations;
  const forecastState = states.forecast;
  const mapState = states.map;
  const intelligenceState = states["source-intelligence"];
  const actionState = states.actions;
  const advisoryState = states.advisory;
  const current = currentState.data;
  const forecast = forecastState.data;
  const intelligence = intelligenceState.data;
  const stations = useMemo(() => stationState.data?.stations ?? [], [stationState.data]);
  const copilotContext = Object.values(states)
    .map((state) => state.context)
    .find(
      (context) =>
        context
        && contextMatches(context, {
          cityId: activeCity.cityId,
          cityName: activeCity.name,
          pollutant,
          horizon,
        }),
    );

  const mapStations = useMemo(
    () =>
      mapState.context && stationState.context?.snapshot_id === mapState.context.snapshot_id
        ? stations
        : [],
    [mapState.context, stationState.context, stations],
  );
  const mapCurrent =
    mapState.context && currentState.context?.snapshot_id === mapState.context.snapshot_id
      ? current
      : undefined;
  const forecastSnapshot = forecastState.context?.snapshot_id;
  const sourceMatchesForecast = Boolean(
    forecastSnapshot
      && intelligenceState.context?.snapshot_id === forecastSnapshot
      && (
        forecast?.peak
          ? intelligence?.forecast_category === forecast.peak.category
            && intelligence?.forecast_colour === forecast.peak.colour
            && intelligence?.forecast_aqi === forecast.peak.aqi
            && intelligence?.peak_value === forecast.peak.value
          : forecast?.status === "unavailable"
            && intelligence?.forecast_category == null
            && intelligence?.forecast_colour == null
            && intelligence?.forecast_aqi == null
            && intelligence?.peak_value == null
      ),
  );
  const actionsMatchForecast = Boolean(
    forecastSnapshot && actionState.context?.snapshot_id === forecastSnapshot,
  );
  const advisoryMatchesForecast = Boolean(
    forecastSnapshot
      && advisoryState.context?.snapshot_id === forecastSnapshot
      && (
        forecast?.peak
          ? advisoryState.data?.pollutant === pollutant
            && advisoryState.data?.horizon === horizon
            && advisoryState.data?.category === forecast.peak.category
            && advisoryState.data?.colour === forecast.peak.colour
            && advisoryState.data?.aqi === forecast.peak.aqi
            && advisoryState.data?.peak_value === forecast.peak.value
          : forecast?.status === "unavailable"
            && advisoryState.data?.status === "unavailable"
      ),
  );

  const chooseCity = (city: ActiveCity) => {
    setCityOptions((options) =>
      options.some((item) => item.cityId === city.cityId)
        ? options
        : [...options, city],
    );
    setActiveCity(city);
  };

  return (
    <div className="mx-auto w-full max-w-[1500px] px-4 pb-10 pt-5 sm:px-6 lg:px-8">
      <header className="mb-4 flex flex-col justify-between gap-3 border-b border-slate-800 pb-4 md:flex-row md:items-end">
        <div className="min-w-0">
          <p className="section-kicker">Urban air operations</p>
          <h1 className="mt-1 truncate text-2xl font-semibold text-white sm:text-3xl">{activeCity.name}</h1>
          <p className="mt-1 text-sm text-slate-400">
            {activeCity.state ?? "India"} · {pollutantLabel(pollutant)} · next {horizon} hours
          </p>
        </div>
        <div className="text-left text-xs text-slate-500 md:text-right">
          <p>{snapshotId ? `Snapshot ${snapshotId}` : "Establishing live snapshot"}</p>
          <p className="mt-1">Panels update independently</p>
        </div>
      </header>

      <div className="control-bar mb-3">
        <label>
          <span>Quick-select city</span>
          <select
            value={activeCity.cityId ?? activeCity.query}
            onChange={(event) => {
              const selected = cityOptions.find(
                (city) => (city.cityId ?? city.query) === event.target.value,
              );
              if (selected) setActiveCity(selected);
            }}
          >
            {cityOptions.map((city) => (
              <option key={city.cityId ?? city.query} value={city.cityId ?? city.query}>
                {city.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Pollutant</span>
          <select value={pollutant} onChange={(event) => setPollutant(event.target.value as Pollutant)}>
            <option value="pm2_5">PM2.5</option>
            <option value="pm10">PM10</option>
          </select>
        </label>
        <label>
          <span>Forecast window</span>
          <select value={horizon} onChange={(event) => setHorizon(Number(event.target.value) as Horizon)}>
            <option value={24}>24 hours</option>
            <option value={48}>48 hours</option>
            <option value={72}>72 hours</option>
          </select>
        </label>
        <button
          className="refresh-button"
          onClick={() => {
            (Object.keys(states) as LivePanel[]).forEach(retry);
            setNetworkRefresh((value) => value + 1);
          }}
        >
          <RefreshIcon /> Refresh all
        </button>
      </div>
      <CitySearch onSelect={chooseCity} />

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <article className="metric-card" data-testid="current-card">
          <p className="metric-label">Current concentration</p>
          {currentState.status === "loading" && !current ? <PanelSkeleton height="h-20" /> : current ? (
            <>
              <p className="metric-value" style={{ color: current.colour ?? undefined }}>{current.value.toFixed(1)} <span>µg/m³</span></p>
              <p className="metric-detail">{current.category ?? "Category unavailable"}{current.aqi != null ? ` · AQI ${current.aqi}` : ""}</p>
              <p className="metric-meta" title={current.station_name ?? current.provider}>{current.station_name ?? current.provider} · {current.freshness.label}</p>
            </>
          ) : <PanelError message={currentState.error ?? "Current conditions unavailable."} onRetry={() => retry("current")} />}
        </article>

        <article className="metric-card" data-category={forecast?.peak?.category ?? undefined} data-snapshot-id={forecastState.context?.snapshot_id} data-testid="forecast-card">
          <p className="metric-label">{horizon}h forecast peak</p>
          {forecastState.status === "loading" && !forecast ? <PanelSkeleton height="h-20" /> : forecast?.peak ? (
            <>
              <p className="metric-value" style={{ color: forecast.peak.colour ?? undefined }}>{forecast.peak.value.toFixed(1)} <span>µg/m³</span></p>
              <p className="metric-detail" style={{ color: forecast.peak.colour ?? undefined }}>{forecast.peak.category}{forecast.peak.aqi != null ? ` · forecast AQI ${forecast.peak.aqi}` : ""}</p>
              <p className="metric-meta">Peak near {localDate(forecast.peak.timestamp_utc)}</p>
            </>
          ) : <PanelError message={forecastState.error ?? "Forecast unavailable."} onRetry={() => retry("forecast")} />}
        </article>

        <article className="metric-card" data-testid="priority-card">
          <p className="metric-label">Forecast intervention priority</p>
          {(intelligenceState.status === "loading" || forecastState.status === "loading") && !sourceMatchesForecast ? <PanelSkeleton height="h-20" /> : intelligence && sourceMatchesForecast ? (
            <>
              <p className="metric-value">{intelligence.priority}</p>
              <p className="metric-detail">{Math.round(intelligence.confidence * 100)}% evidence confidence</p>
              <p className="metric-meta">{intelligence.forecast_category} forecast · {horizon}-hour window</p>
            </>
          ) : <PanelError message={intelligenceState.error ?? "Priority is not aligned with the selected forecast."} onRetry={() => retry("source-intelligence")} />}
        </article>

        <article className="metric-card" data-testid="coverage-card">
          <p className="metric-label">Monitoring coverage</p>
          {stationState.status === "loading" && !stationState.data ? <PanelSkeleton height="h-20" /> : stationState.status === "ready" ? (
            <>
              <p className="metric-value">{stationState.data.available_count} <span>available</span></p>
              <p className="metric-detail">{stationState.data.selected_count} selected · {coverageLabel(stationState.context.coverage_type)}</p>
              <p className="metric-meta">{current?.station_id ? "1 station used" : "No station correction"} · {stations[0]?.freshness.label ?? "No station feed"}</p>
            </>
          ) : <PanelError message={stationState.error ?? "Station coverage unavailable."} onRetry={() => retry("stations")} />}
        </article>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.55fr_0.85fr]">
        <Section title={`${pollutantLabel(pollutant)} forecast trajectory`} eyebrow="Forecast">
          {forecastState.status === "loading" && !forecast ? <PanelSkeleton height="h-[340px]" /> : forecast?.points.length && forecastState.context ? (
            <LiveForecastChart forecast={forecast} context={forecastState.context} />
          ) : <PanelError message={forecastState.error ?? "Forecast data is unavailable."} onRetry={() => retry("forecast")} />}
        </Section>
        <Section title="Likely contributing context" eyebrow="Source screening" action={intelligenceState.status === "error" ? retryButton("source-intelligence", retry) : undefined}>
          {(intelligenceState.status === "loading" || forecastState.status === "loading") && !sourceMatchesForecast ? <PanelSkeleton height="h-64" /> : intelligence && sourceMatchesForecast ? (
            <div className="space-y-3" data-snapshot-id={intelligenceState.context?.snapshot_id} data-testid="source-screening">
              {intelligence.sources.map((source) => (
                <article className="source-evidence" data-evidence-strength={source.evidence_strength} data-score={source.score ?? "unavailable"} key={source.source_id}>
                  <div className="source-evidence-heading">
                    <strong>{source.label}</strong>
                    <span>{source.evidence_strength}</span>
                  </div>
                  <p className="source-score">{source.score == null ? "Evidence score unavailable" : `Relative evidence score: ${source.score}/100`}</p>
                  {source.score != null && <div className="source-track" aria-label={`${source.label}: ${source.score} out of 100`}><span style={{ width: `${source.score}%` }} /></div>}
                  <p className="source-description">{source.description}</p>
                </article>
              ))}
              <details className="method-details"><summary>About these scores</summary><p>Relative operational evidence only; not pollution shares or confirmed source attribution.</p></details>
            </div>
          ) : <PanelError message={intelligenceState.error ?? "Source evidence is not aligned with the selected forecast."} onRetry={() => retry("source-intelligence")} />}
        </Section>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1.45fr_0.85fr]">
        <Section title="Current city air-quality map" eyebrow="1 km grid" action={mapState.context ? <span className="text-xs text-slate-400">{mapState.data?.metadata.cell_count ?? 0} cells</span> : undefined}>
          {mapState.status === "loading" && !mapState.data ? <PanelSkeleton height="h-[450px]" /> : mapState.data && mapState.context ? (
            <Suspense fallback={<PanelSkeleton height="h-[450px]" />}>
              <LiveOperationsMap data={mapState.data} stations={mapStations} current={mapCurrent} context={mapState.context} />
            </Suspense>
          ) : <PanelError message={mapState.error ?? "Map data is unavailable."} onRetry={() => retry("map")} />}
        </Section>
        <div className="grid content-start gap-4">
          <Section title="Monitoring stations" eyebrow="Live coverage">
            {stationState.status === "loading" && !stationState.data ? <PanelSkeleton height="h-52" /> : stationState.status === "ready" ? (
              stations.length ? (
                <ul className="space-y-2">
                  {stations.slice(0, 5).map((station) => {
                    const latest = station.latest[pollutant];
                    return (
                      <li className="station-row" key={station.station_id}>
                        <div className="min-w-0"><p className="truncate font-medium text-slate-100" title={station.name}>{station.name}{current?.station_id === station.station_id ? <span className="ml-2 text-[10px] font-semibold uppercase text-teal-300">Used</span> : null}</p><p className="truncate text-xs text-slate-400">{station.provider} · {station.freshness.label}</p></div>
                        <strong>{latest ? `${latest.value.toFixed(1)} µg/m³` : "Unavailable"}</strong>
                      </li>
                    );
                  })}
                </ul>
              ) : <EmptyPanel>No usable nearby PM stations. Forecast coverage remains model-based.</EmptyPanel>
            ) : <PanelError message={stationState.error ?? "Stations unavailable."} onRetry={() => retry("stations")} />}
          </Section>

          <Section title="Recommended action queue" eyebrow="Operational response">
            <div data-snapshot-id={actionState.context?.snapshot_id} data-testid="action-queue-panel">
              {(actionState.status === "loading" || forecastState.status === "loading") && !actionsMatchForecast ? <PanelSkeleton height="h-36" /> : actionState.data?.length && actionsMatchForecast ? (
                <div className="space-y-3" data-testid="recommended-actions">{actionState.data.map((action) => <article className="action-card" data-evidence-score={action.evidence_score} data-source-id={action.source_id} key={action.source_id}><div className="action-heading"><span>{action.priority} priority</span><strong>{action.title}</strong></div><p className="action-source">{action.source_label}</p><p>{action.action}</p><dl className="action-meta"><div><dt>Timeframe</dt><dd>{action.recommended_timeframe}</dd></div><div><dt>Effort</dt><dd>{action.operational_effort}</dd></div><div><dt>Evidence</dt><dd>{action.evidence_strength}</dd></div></dl></article>)}</div>
              ) : actionState.status === "error" ? <PanelError message={actionState.error} onRetry={() => retry("actions")} /> : !actionsMatchForecast ? <PanelError message="Actions are not aligned with the selected forecast." onRetry={() => retry("actions")} /> : <EmptyPanel>No source evidence currently warrants an operational action.</EmptyPanel>}
            </div>
          </Section>
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Section title="Citizen advisory" eyebrow="Public information">
          <div data-snapshot-id={advisoryState.context?.snapshot_id} data-status={advisoryState.data?.status} data-testid="citizen-advisory-panel">
            {(advisoryState.status === "loading" || forecastState.status === "loading") && !advisoryMatchesForecast ? <PanelSkeleton height="h-32" /> : advisoryState.data?.status === "available" && advisoryMatchesForecast ? (
              <div data-category={advisoryState.data.category} data-colour={advisoryState.data.colour ?? undefined} data-snapshot-id={advisoryState.context?.snapshot_id} data-testid="citizen-advisory"><p className="text-lg font-semibold" style={{ color: advisoryState.data.colour ?? undefined }}>{advisoryState.data.headline}</p><p className="mt-2 text-sm text-slate-300">{pollutantLabel(pollutant)} may peak near {advisoryState.data.peak_value?.toFixed(1)} µg/m³ around {localDate(advisoryState.data.peak_timestamp_utc)}.</p><ul className="advisory-list">{advisoryState.data.advice?.map((item) => <li key={item}>{item}</li>)}</ul><details className="method-details mt-3"><summary>Guidance note</summary><p>{advisoryState.data.qualification}</p></details></div>
            ) : advisoryState.status === "error" ? <PanelError message={advisoryState.error} onRetry={() => retry("advisory")} /> : !advisoryMatchesForecast && advisoryState.data?.status === "available" ? <PanelError message="Advisory is not aligned with the selected forecast." onRetry={() => retry("advisory")} /> : <EmptyPanel>Forecast advisory is unavailable for this context.</EmptyPanel>}
          </div>
        </Section>

        <Section title="Snapshot integrity" eyebrow="Data status">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div className="stat-cell"><dt>City</dt><dd className="truncate" title={activeCity.name}>{activeCity.name}</dd></div>
            <div className="stat-cell"><dt>Coverage</dt><dd>{coverageLabel(currentState.context?.coverage_type)}</dd></div>
            <div className="stat-cell"><dt>Issue time</dt><dd>{localDate(currentState.context?.issue_timestamp)}</dd></div>
            <div className="stat-cell"><dt>Snapshot</dt><dd className="font-mono text-xs">{snapshotId ?? "Loading"}</dd></div>
          </dl>
          <details className="method-details mt-4"><summary>Forecast methodology</summary><p>Live CAMS numerical forecast with a validation-selected persistence-residual transfer and freshness-weighted nearby-station correction where monitoring is available. The residual model was not trained on archived CAMS errors.</p></details>
        </Section>
      </div>

      <div className="mt-4">
        <Section title="Five-city next-24-hour watch" eyebrow="Fixed PM2.5 forecast comparison" action={networkStatus === "error" ? <button className="text-xs font-semibold text-teal-300" onClick={() => setNetworkRefresh((value) => value + 1)}>Retry</button> : undefined}>
          {networkStatus === "loading" && !network ? <PanelSkeleton height="h-52" /> : network ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead><tr><th>City</th><th>Next-24h peak</th><th>Peak AQI</th><th>Peak category</th><th>Forecast priority</th><th>Issued</th></tr></thead>
                <tbody>{network.cities.map((item) => <tr key={item.city_id}><td><button className="font-medium text-slate-100 hover:text-teal-300" onClick={() => { const city = defaultCities.find((entry) => entry.cityId === item.city_id); if (city) setActiveCity(city); }}>{item.city_name}</button><span>{item.state}</span></td><td style={{ color: item.colour ?? undefined }}>{item.value_24h == null ? "Unavailable" : `${item.value_24h.toFixed(1)} µg/m³`}</td><td>{item.aqi ?? "Unavailable"}</td><td style={{ color: item.colour ?? undefined }}>{item.category ?? "Unavailable"}</td><td>{item.priority}</td><td>{localDate(item.issue_timestamp)}</td></tr>)}</tbody>
              </table>
            </div>
          ) : <PanelError message="Five-city outlook is temporarily unavailable." onRetry={() => setNetworkRefresh((value) => value + 1)} />}
        </Section>
      </div>

      <footer className="mt-7 border-t border-slate-800 pt-4 text-xs text-slate-500">
        AirView AI · live operational decision support · OpenStreetMap attribution remains visible on the map
      </footer>
      <AskAirView
        cityName={activeCity.name}
        cityId={copilotContext?.city.city_id}
        pollutant={pollutant}
        horizon={horizon}
        snapshotId={copilotContext?.snapshot_id}
      />
    </div>
  );
}
