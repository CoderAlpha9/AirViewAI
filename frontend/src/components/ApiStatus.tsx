import { useApiHealth } from "../features/system/useApiHealth";

export function ApiStatus() {
  const health = useApiHealth();
  const connected = health.state === "connected";

  return (
    <section
      className="rounded-2xl border border-line bg-panel/70 p-5 shadow-2xl shadow-black/10"
      aria-live="polite"
      aria-label="Platform connection status"
    >
      <div className="flex items-start justify-between gap-5">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mist">
            Platform status
          </p>
          <p className="mt-3 text-lg font-medium">
            {health.state === "checking" && "Checking API connection"}
            {connected && "API connected"}
            {health.state === "unavailable" && "API unavailable"}
          </p>
          <p className="mt-1 text-sm text-mist">
            {connected
              ? `${health.data.service} · v${health.data.version}`
              : health.state === "checking"
                ? "Contacting the local backend service…"
                : "Start the backend service, then refresh this page."}
          </p>
        </div>
        <span
          className={`mt-1 h-3 w-3 shrink-0 rounded-full ${
            connected
              ? "bg-air shadow-[0_0_14px_rgba(83,214,162,0.75)]"
              : health.state === "checking"
                ? "animate-pulse bg-amber-300"
                : "bg-rose-400"
          }`}
        />
      </div>
    </section>
  );
}

