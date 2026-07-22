# Ask AirView copilot

## Architecture

Ask AirView is a read-only dashboard copilot. The React popup sends a question with the selected city ID, pollutant, forecast horizon, snapshot ID, a random browser-session ID and at most four recent user/assistant messages. It never sends dashboard measurements.

`POST /api/copilot/chat` validates the request and resolves the snapshot from a bounded, process-local registry populated by the canonical dashboard snapshot builder. City, pollutant, horizon and snapshot ID must all match. Unknown, expired or mismatched snapshots receive HTTP 409 and Gemini is not called.

The backend uses a normal JSON response instead of SSE. This keeps cancellation, retry behaviour and structured-response validation reliable within the existing HTTP client architecture.

## Bounded context contract

Gemini receives only:

- city, state, pollutant, horizon, issue time, coverage and snapshot ID;
- up to five active stations and their active-pollutant reading metadata;
- current concentration, timestamp, value kind, provider, AQI category and freshness;
- a sampled forecast trajectory, canonical peak and priority;
- grid-cell count and up to five highest forecast cells;
- source-screening evidence, FIRMS availability/count and selected OSM feature counts;
- provider status/timestamps, recommended actions, citizen advisory and concise limitations.

Complete grids, full provider payloads, model internals, secrets, local paths and browser-supplied numerical values are excluded. Input context and model output are bounded by configuration.

## Gemini integration

The isolated service calls the Gemini `generateContent` REST endpoint with backend-only `GEMINI_API_KEY` and configurable `GEMINI_MODEL` (`gemini-2.5-flash` by default). It requests a response matching this contract:

```json
{
  "answer": "Concise grounded answer",
  "evidence": ["Supporting dashboard fact"],
  "data_status": "station-corrected | model-based | partial",
  "limitations": ["Relevant unavailable evidence"],
  "suggested_questions": ["Useful follow-up"]
}
```

Pydantic validates the response. Malformed or unsafe output is replaced with a safe grounded fallback. HTML and code-fence markers are removed, and the frontend renders strings as plain text rather than model-provided markup.

## Safety and security

- The Gemini key is accepted only through backend configuration and is never returned by either endpoint.
- The system instruction restricts answers to supplied AirView context and distinguishes observations, modelled-current values and forecasts.
- Source scores must not be described as emission shares or regulatory attribution.
- The copilot cannot diagnose, prescribe medication, execute actions or alter dashboard data.
- Key/path leakage and selected unsupported claims trigger a safe fallback.
- Logs contain provider/model, context size, history count and failure class/status only—never messages, prompts, keys or provider response bodies.
- Requests have strict field lengths, four-message history, a configurable timeout, one bounded retry and per-client/session sliding-window rate limiting.
- Active browser requests are aborted and stale responses ignored when city, pollutant, horizon or snapshot changes.

## Configuration and failure behaviour

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
AIRVIEW_COPILOT_ENABLED=true
AIRVIEW_COPILOT_TIMEOUT_SECONDS=20
AIRVIEW_COPILOT_MAX_OUTPUT_TOKENS=700
AIRVIEW_COPILOT_MAX_INPUT_CHARS=14000
AIRVIEW_COPILOT_RATE_LIMIT_PER_MINUTE=12
```

Set `AIRVIEW_COPILOT_ENABLED=false` or leave `GEMINI_API_KEY` blank to disable answers. `GET /api/copilot/status` then reports the deployment state without exposing secrets. Provider timeouts, rate limits and malformed responses produce concise UI states; dashboard panels continue independently.
