export function ReplayModeBadge() { return <span className="rounded-full border border-air/50 bg-air/10 px-2 py-1 text-xs font-medium text-air">Historical replay</span>; }
export function FreshnessBadge() { return <span className="rounded-full border border-amber-300/40 bg-amber-300/10 px-2 py-1 text-xs text-amber-100">Observations are stale</span>; }
export function ReadinessBadge({ ready, label }: { ready: boolean; label: string }) { return <span className={`rounded-full px-2 py-1 text-xs ${ready ? "bg-air/10 text-air" : "bg-white/10 text-mist"}`}>{label}</span>; }
export function ConfidenceIndicator({ value }: { value?: number | null }) { return <span className="text-sm text-air">{value === undefined || value === null ? "Confidence unavailable" : `${Math.round(value * 100)}% confidence`}</span>; }
export function LimitationNotice({ items }: { items: string[] }) { return <aside className="mt-4 rounded border border-amber-300/30 bg-amber-300/5 p-3 text-xs leading-5 text-amber-100"><strong>Limitations:</strong> {items.join(" ")}</aside>; }
export function LoadingState({ label = "Loading replay evidence…" }: { label?: string }) { return <p className="rounded border border-line bg-panel/50 p-5 text-sm text-mist" role="status">{label}</p>; }
export function ErrorState({ message }: { message: string }) { return <p className="rounded border border-red-300/30 bg-red-300/5 p-4 text-sm text-red-200" role="alert">{message}</p>; }
export function EmptyState({ message }: { message: string }) { return <p className="rounded border border-line bg-panel/50 p-4 text-sm text-mist">{message}</p>; }
export function PartialDataNotice({ message }: { message: string }) { return <p className="mt-3 text-xs leading-5 text-mist">Partial evidence: {message}</p>; }
