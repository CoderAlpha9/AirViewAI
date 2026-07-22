import { describe, expect, it } from "vitest";

import { contextMatches, snapshotsMatch, type LiveContext } from "./live";

function context(overrides: Partial<LiveContext> = {}): LiveContext {
  return {
    city: {
      city_id: "agra",
      name: "Agra",
      state: "Uttar Pradesh",
      latitude: 27.18,
      longitude: 78.01,
      bounds: [27, 77.8, 27.4, 78.2],
      bounds_source: "configured_radius",
      provider: "OpenStreetMap Nominatim",
    },
    pollutant: "pm2_5",
    horizon: 24,
    issue_timestamp: "2026-07-22T00:00:00Z",
    snapshot_id: "snapshot-a",
    schema_version: "2.0",
    generated_at_utc: "2026-07-22T00:00:01Z",
    data_freshness: { label: "recent", age_hours: 1 },
    coverage_type: "station_corrected",
    ...overrides,
  };
}

describe("live context validation", () => {
  it("accepts only the selected city, pollutant and horizon", () => {
    expect(contextMatches(context(), { cityId: "agra", cityName: "Agra", pollutant: "pm2_5", horizon: 24 })).toBe(true);
    expect(contextMatches(context(), { cityId: "lucknow", cityName: "Lucknow", pollutant: "pm2_5", horizon: 24 })).toBe(false);
    expect(contextMatches(context(), { cityId: "agra", cityName: "Agra", pollutant: "pm10", horizon: 24 })).toBe(false);
    expect(contextMatches(context(), { cityId: "agra", cityName: "Agra", pollutant: "pm2_5", horizon: 72 })).toBe(false);
  });

  it("rejects panels from different snapshots", () => {
    expect(snapshotsMatch(context(), context())).toBe(true);
    expect(snapshotsMatch(context(), context({ snapshot_id: "snapshot-b" }))).toBe(false);
  });

  it("matches searched cities by resolved name before their stable id is known", () => {
    const searched = context({ city: { ...context().city, city_id: "india-mysuru-1234", name: "Mysuru" } });
    expect(contextMatches(searched, { cityName: "mysuru", pollutant: "pm2_5", horizon: 24 })).toBe(true);
  });
});
