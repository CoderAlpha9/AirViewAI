"""Safe, compact persistence and export helpers for historical replay packages."""
# ruff: noqa: E701, E702
import html
import json
from pathlib import Path
from typing import Any


def root() -> Path: return Path(__file__).resolve().parents[3]
def runs_dir() -> Path:
    path = root() / "data" / "processed" / "india" / "orchestration_runs"; path.mkdir(parents=True, exist_ok=True); return path
def clean(value: Any) -> Any:
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items() if "path" not in str(k).lower()}
    if isinstance(value, list): return [clean(v) for v in value]
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))): return None
    return value
def normalise(value: dict[str, Any]) -> dict[str, Any]:
    request = value.get("request", {})
    value = clean(value)
    value.setdefault("schema_version", "1.1")
    for key in ("city_id", "station_id", "pollutant", "horizon", "issue_timestamp", "mode", "safety_result", "limitations", "agents", "duration_ms"): value.setdefault(key, request.get(key) if key in request else None)
    value.setdefault("advisory", {"language": request.get("language", "en"), "audience": request.get("audience", "general_public"), "format": request.get("format", "standard")})
    value.setdefault("overall_status", "partial" if any(agent.get("status") != "completed" for agent in value.get("agents", [])) else "completed")
    return value
def persist(run: dict[str, Any]) -> None: (runs_dir() / f"{run['run_id']}.json").write_text(json.dumps(clean(run), indent=2, ensure_ascii=False), encoding="utf-8")
def read(run_id: str) -> dict[str, Any] | None:
    path = runs_dir() / f"{run_id}.json"
    return normalise(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else None
def list_runs() -> list[dict[str, Any]]:
    data=[]
    for path in runs_dir().glob("*.json"):
        try: data.append(normalise(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError): continue
    return sorted(data, key=lambda item: item.get("created_at_utc", ""), reverse=True)
def compact(run: dict[str, Any]) -> dict[str, Any]: return {key: run.get(key) for key in ("run_id", "created_at_utc", "city_id", "station_id", "pollutant", "horizon", "issue_timestamp", "mode", "overall_status", "safety_result", "duration_ms")}
def export_html(run: dict[str, Any]) -> str:
    title = f"AirView AI historical replay — {run.get('city_id', 'unknown')}"
    agents = "".join(f"<li><b>{html.escape(str(a.get('agent_name')))}</b>: {html.escape(str(a.get('status')))} ({a.get('duration_ms', 'unavailable')} ms)</li>" for a in run.get("agents", []))
    limits = "".join(f"<li>{html.escape(str(item))}</li>" for item in run.get("limitations", []))
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>body{{font:15px Arial;color:#18251f;margin:40px;max-width:850px}}h1{{color:#126b4b}}.warning{{border:2px solid #a66b00;background:#fff5d8;padding:14px}}dt{{font-weight:bold}}dd{{margin:0 0 10px}}</style></head><body><h1>{html.escape(title)}</h1><p class='warning'><b>Historical replay only.</b> This report is not a live forecast, regulatory source apportionment, causal intervention estimate, or medical advice.</p><h2>Replay context</h2><dl><dt>Run</dt><dd>{html.escape(str(run.get('run_id')))}</dd><dt>City / station</dt><dd>{html.escape(str(run.get('city_id')))} / {html.escape(str(run.get('station_id')))}</dd><dt>Pollutant / horizon</dt><dd>{html.escape(str(run.get('pollutant')))} / {html.escape(str(run.get('horizon')))} h</dd><dt>Issue timestamp</dt><dd>{html.escape(str(run.get('issue_timestamp')))}</dd><dt>Safety result</dt><dd>{html.escape(str(run.get('safety_result')))}</dd></dl><h2>Agent execution</h2><ul>{agents}</ul><h2>Limitations</h2><ul>{limits}</ul><h2>Methodology references</h2><p>{html.escape(', '.join(str(x) for x in run.get('evidence_references', [])))}</p></body></html>"
