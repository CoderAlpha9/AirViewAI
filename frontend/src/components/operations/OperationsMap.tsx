import "leaflet/dist/leaflet.css";

import { CircleMarker, MapContainer, Popup, Rectangle, TileLayer, Tooltip } from "react-leaflet";
import { useEffect } from "react";
import { useMap } from "react-leaflet";

import type { OperationsDashboard } from "../../api/operations";

const categoryColor: Record<string, string> = {
  Good: "#38a169",
  Satisfactory: "#7fbf3f",
  Moderate: "#e0b43a",
  Poor: "#e47d32",
  "Very Poor": "#d64545",
  Severe: "#8b2e4f",
};

function RecenterMap({ center, bounds }: { center: [number, number]; bounds: [[number, number], [number, number]][] }) {
  const map = useMap();
  useEffect(() => {
    if (bounds.length) map.fitBounds(bounds.flat(), { padding: [24, 24], maxZoom: 12 });
    else map.setView(center, 12);
  }, [map, center, bounds]);
  return null;
}

export function OperationsMap({ dashboard }: { dashboard: OperationsDashboard }) {
  const { map } = dashboard;
  const center: [number, number] = [map.station.latitude, map.station.longitude];
  return (
    <div>
      <div className="h-[430px] overflow-hidden rounded-lg border border-slate-700/80" aria-label="Air-quality intervention map">
        <MapContainer center={center} zoom={12} scrollWheelZoom className="h-full w-full">
          <RecenterMap center={center} bounds={map.grid.map((cell) => cell.bounds)} />
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {map.grid.map((cell) => (
            <Rectangle
              key={cell.cell_id}
              bounds={cell.bounds}
              pathOptions={{ color: categoryColor[cell.category ?? ""] ?? "#78909c", fillColor: categoryColor[cell.category ?? ""] ?? "#78909c", fillOpacity: 0.32, weight: 0.7 }}
            >
              <Tooltip sticky>{cell.forecast_peak.toFixed(1)} µg/m³ · {cell.category ?? "Unclassified"}</Tooltip>
            </Rectangle>
          ))}
          <CircleMarker center={center} radius={8} pathOptions={{ color: "#ffffff", fillColor: "#18b998", fillOpacity: 1, weight: 2 }}>
            <Popup><strong>{map.station.name}</strong><br />Primary monitoring location</Popup>
          </CircleMarker>
          {map.firms.map((event, index) => (
            <CircleMarker
              key={`${event.timestamp_utc}-${index}`}
              center={[event.latitude, event.longitude]}
              radius={Math.max(3, Math.min(8, 3 + (event.fire_radiative_power ?? 0) / 20))}
              pathOptions={{ color: "#f59e0b", fillColor: "#f97316", fillOpacity: 0.7, weight: 1 }}
            >
              <Popup>
                <strong>Satellite-detected thermal anomaly</strong><br />
                {new Date(event.timestamp_utc).toLocaleString("en-IN")}<br />
                {event.distance_km != null ? `${event.distance_km.toFixed(0)} km from station` : "Distance unavailable"}
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-400">
        <span><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-emerald-400" />Monitoring station</span>
        <span><span className="mr-2 inline-block h-2.5 w-2.5 rounded-full bg-orange-500" />Thermal anomaly</span>
        <span>1 km intervention-planning cells</span>
        <span>{map.firms.length} near-real-time FIRMS markers shown</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-slate-500">
        {map.grid_methodology ?? "Grid values are downscaled planning indicators, not independently resolved 1 km atmospheric simulations."}
      </p>
    </div>
  );
}
