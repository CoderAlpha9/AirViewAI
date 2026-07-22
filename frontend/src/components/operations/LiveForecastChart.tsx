import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { LiveContext, LiveForecast } from "../../api/live";

function shortTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", hour12: true }).format(new Date(value));
}

export function LiveForecastChart({ forecast, context }: { forecast: LiveForecast; context: LiveContext }) {
  const data = forecast.points.map((point) => ({ ...point, label: shortTime(point.timestamp_utc) }));
  const pollutant = context.pollutant === "pm2_5" ? "PM2.5" : "PM10";
  return (
    <div>
      <div className="h-[300px] min-h-[260px] w-full sm:h-[340px]" role="img" aria-label={`${pollutant} ${context.horizon}-hour live forecast chart`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 18, bottom: 18, left: 2 }}>
            <CartesianGrid stroke="#26383c" strokeDasharray="3 4" vertical={false} />
            <XAxis dataKey="label" minTickGap={42} tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={{ stroke: "#334155" }} />
            <YAxis width={48} tick={{ fill: "#94a3b8", fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{ background: "#101b1f", border: "1px solid #475569", borderRadius: 7 }}
              labelStyle={{ color: "#f1f5f9" }}
              formatter={(value, name) => [`${Number(value).toFixed(1)} µg/m³`, String(name)]}
            />
            <Legend wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
            <Line type="monotone" dataKey="cams" name="CAMS" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="prediction" name="AirView forecast" stroke="#2dd4bf" strokeWidth={2.25} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-xs text-slate-400">
        Issued {shortTime(context.issue_timestamp)} · {context.coverage_type === "station_corrected" ? "Station-corrected coverage" : "Model-based coverage"}
      </p>
    </div>
  );
}
