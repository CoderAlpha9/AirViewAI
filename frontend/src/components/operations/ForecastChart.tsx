import { Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ForecastResult } from "../../api/operations";

function shortTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    hour12: true,
  }).format(new Date(value));
}

export function ForecastChart({ forecast }: { forecast: ForecastResult }) {
  const data = forecast.points.map((point) => ({
    ...point,
    label: shortTime(point.timestamp_utc),
    interval: [point.lower, point.upper],
  }));

  return (
    <div>
      <div className="h-[330px] w-full" role="img" aria-label={`${forecast.pollutant_label} ${forecast.horizon_hours}-hour forecast chart`}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 12, right: 10, bottom: 16, left: 4 }}>
            <CartesianGrid stroke="#20393a" strokeDasharray="3 4" vertical={false} />
            <XAxis dataKey="label" minTickGap={38} tick={{ fill: "#8fa5a6", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#294647" }} />
            <YAxis width={52} unit="" tick={{ fill: "#8fa5a6", fontSize: 11 }} tickLine={false} axisLine={false} label={{ value: forecast.unit, angle: -90, position: "insideLeft", fill: "#8fa5a6", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#0d1c1d", border: "1px solid #2c4c4e", borderRadius: 8 }}
              labelStyle={{ color: "#f3f7f7" }}
              formatter={(value, name) => {
                if (Array.isArray(value)) return [`${Number(value[0]).toFixed(1)} – ${Number(value[1]).toFixed(1)} ${forecast.unit}`, "90% interval"];
                if (value == null) return ["Unavailable", String(name)];
                return [`${Number(value).toFixed(1)} ${forecast.unit}`, String(name)];
              }}
            />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
            <Area dataKey="interval" name="90% interval" stroke="none" fill="#3b7074" fillOpacity={0.28} isAnimationActive={false} />
            <Line type="linear" dataKey="provider_baseline" name="CAMS baseline" stroke="#809496" strokeWidth={1.5} strokeDasharray="5 5" dot={false} connectNulls={false} isAnimationActive={false} />
            {data.some((point) => point.actual != null) && <Line type="linear" dataKey="actual" name="Observed" stroke="#f2c14e" strokeWidth={2} dot={false} connectNulls={false} isAnimationActive={false} />}
            <Line type="linear" dataKey="prediction" name="AirView forecast" stroke="#3dd9b3" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-400">
        Forecast issued {shortTime(forecast.issue_timestamp)}. Peak {forecast.peak.value.toFixed(1)} {forecast.unit}; uncertainty is shown as the calibrated 90% interval.
      </p>
    </div>
  );
}
