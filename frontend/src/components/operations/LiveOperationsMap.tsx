import "leaflet/dist/leaflet.css";

import L, { type GeoJSON as LeafletGeoJSON, type Layer } from "leaflet";
import { useEffect, useMemo } from "react";
import { CircleMarker, GeoJSON, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";

import type { CurrentConditions, LiveContext, LiveMap, LiveStation } from "../../api/live";

function MapViewport({ data, stations, context }: { data: LiveMap; stations: LiveStation[]; context: LiveContext }) {
  const map = useMap();
  useEffect(() => {
    const container = map.getContainer();
    delete container.dataset.mapCityId;
    const recordViewport = () => {
      const centre = map.getCenter();
      container.dataset.mapCityId = context.city.city_id;
      container.dataset.mapCenter = `${centre.lat.toFixed(5)},${centre.lng.toFixed(5)}`;
    };
    map.once("moveend", recordViewport);
    const bounds = L.geoJSON(data as GeoJSON.FeatureCollection).getBounds();
    stations.forEach((station) => bounds.extend([station.latitude, station.longitude]));
    if (bounds.isValid()) map.flyToBounds(bounds, { padding: [24, 24], maxZoom: 12, duration: 0.55 });
    else map.setView([context.city.latitude, context.city.longitude], 11);
    recordViewport();
    return () => {
      map.off("moveend", recordViewport);
      delete container.dataset.mapCityId;
      delete container.dataset.mapCenter;
    };
  }, [context.city.city_id, context.city.latitude, context.city.longitude, data, map, stations]);
  return null;
}

export function LiveOperationsMap({
  data,
  stations,
  current,
  context,
}: {
  data: LiveMap;
  stations: LiveStation[];
  current: CurrentConditions | null | undefined;
  context: LiveContext;
}) {
  const style = useMemo(
    () => (feature?: GeoJSON.Feature) => ({
      color: "#64748b",
      weight: 0.55,
      className: "airview-grid-cell",
      fillColor: String(feature?.properties?.colour ?? "#64748b"),
      fillOpacity: feature?.properties?.current == null ? 0.12 : 0.44,
    }),
    [],
  );
  const issueLabel = new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(context.issue_timestamp));
  const onEachFeature = (feature: GeoJSON.Feature, layer: Layer) => {
    const properties = feature.properties;
    const currentValue = properties?.current == null ? "Unavailable" : `${Number(properties.current).toFixed(1)} µg/m³`;
    const forecastValue = properties?.forecast == null ? "Unavailable" : `${Number(properties.forecast).toFixed(1)} µg/m³`;
    const category = properties?.category ?? "Unclassified";
    const confidence = properties?.confidence == null ? "" : `<br>Confidence: ${Math.round(Number(properties.confidence) * 100)}%`;
    (layer as LeafletGeoJSON).bindTooltip(`Current: ${currentValue} · ${category}<br>${context.horizon}h forecast: ${forecastValue}${confidence}<br>Issued: ${issueLabel}`, { sticky: true });
  };
  return (
    <div>
      <div className="h-[390px] overflow-hidden rounded-lg border border-slate-700 sm:h-[450px]" aria-label={`Air-quality grid for ${context.city.name}`} data-city-id={context.city.city_id} data-city-name={context.city.name} data-grid-cell-count={data.metadata.cell_count} data-snapshot-id={context.snapshot_id}>
        <MapContainer center={[context.city.latitude, context.city.longitude]} zoom={11} scrollWheelZoom className="h-full w-full">
          <MapViewport data={data} stations={stations} context={context} />
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <GeoJSON key={`${context.city.city_id}-${context.snapshot_id}-${data.metadata.cell_count}`} data={data as GeoJSON.FeatureCollection} style={style} onEachFeature={onEachFeature} />
          {stations.slice(0, 5).map((station) => {
            const latest = station.latest[context.pollutant];
            const selected = current?.station_id === station.station_id;
            return (
              <CircleMarker key={`${context.snapshot_id}-${station.station_id}`} center={[station.latitude, station.longitude]} radius={selected ? 8 : 6} pathOptions={{ className: "airview-station-marker", color: selected ? "#f8fafc" : "#0f766e", fillColor: "#14b8a6", fillOpacity: 0.95, weight: selected ? 2 : 1 }}>
                <Popup>
                  <strong>{station.name}</strong><br />
                  {station.provider}<br />
                  {latest ? `${latest.value.toFixed(1)} µg/m³ · ${station.freshness.label}` : "Current value unavailable"}
                </Popup>
              </CircleMarker>
            );
          })}
          {data.firms.slice(0, 120).map((event, index) => (
            <CircleMarker key={`${context.snapshot_id}-${event.timestamp_utc}-${index}`} center={[event.latitude, event.longitude]} radius={4} pathOptions={{ className: "airview-firms-marker", color: "#c2410c", fillColor: "#f97316", fillOpacity: 0.72, weight: 1 }}>
              <Popup><strong>Thermal anomaly</strong><br />{new Date(event.timestamp_utc).toLocaleString("en-IN")}<br />{event.fire_radiative_power != null ? `FRP ${event.fire_radiative_power.toFixed(1)}` : "FRP unavailable"}</Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-400">
        <span><span className="legend-dot bg-teal-500" />Monitoring stations ({stations.length})</span>
        <span><span className="legend-dot bg-orange-500" />FIRMS ({data.firms.length})</span>
        <span>{data.metadata.cell_count} × 1 km planning cells</span>
        <span>{context.coverage_type === "station_corrected" ? "Station-corrected" : "Model-based"}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-400" aria-label="Current air-quality category colour legend">
        <span className="font-semibold text-slate-300">Current grid category</span>
        {data.metadata.category_legend.map((item) => (
          <span key={item.category} className="inline-flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-sm border border-white/30" style={{ backgroundColor: item.colour, opacity: 0.7 }} aria-hidden="true" />
            {item.category}
          </span>
        ))}
      </div>
      {data.metadata.truncated && <p className="mt-2 text-xs text-slate-400">The grid is capped to the cells nearest the city centre for responsive rendering.</p>}
    </div>
  );
}
