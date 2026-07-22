import { useEffect, useState } from "react";

import { liveError, searchIndianCities, type ResolvedCity } from "../../api/live";
import type { ActiveCity } from "../../features/operations/useProgressiveDashboard";

export function CitySearch({ onSelect }: { onSelect: (city: ActiveCity) => void }) {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [results, setResults] = useState<ResolvedCity[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error" | "empty">("idle");
  const [requestId, setRequestId] = useState(0);

  useEffect(() => {
    if (!requestId || !submittedQuery) return;
    const controller = new AbortController();
    setStatus("loading");
    void searchIndianCities(submittedQuery, controller.signal)
      .then((cities) => {
        setResults(cities);
        setStatus(cities.length ? "idle" : "empty");
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setResults([]);
          setStatus(liveError(error) ? "error" : "idle");
        }
      });
    return () => controller.abort();
  }, [requestId, submittedQuery]);

  return (
    <div className="city-search">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim().length >= 2) {
            setSubmittedQuery(query.trim());
            setRequestId((value) => value + 1);
          }
        }}
      >
        <label htmlFor="city-search-input">Search another Indian city</label>
        <div className="flex gap-2">
          <input id="city-search-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. Mysuru" minLength={2} />
          <button type="submit" disabled={query.trim().length < 2 || status === "loading"}>{status === "loading" ? "Searching" : "Search"}</button>
        </div>
      </form>
      {results.length > 0 && (
        <ul aria-label="City search results">
          {results.slice(0, 5).map((city) => (
            <li key={city.city_id}>
              <button
                onClick={() => {
                  onSelect({ query: city.name, cityId: city.city_id, name: city.name, state: city.state });
                  setResults([]);
                  setQuery("");
                }}
              >
                <span className="truncate font-medium text-slate-100">{city.name}</span>
                <span className="truncate text-xs text-slate-400">{city.state ?? "India"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {status === "empty" && <p className="mt-2 text-xs text-slate-400">No matching Indian city found.</p>}
      {status === "error" && <p className="mt-2 text-xs text-amber-200">City search is temporarily unavailable.</p>}
    </div>
  );
}
