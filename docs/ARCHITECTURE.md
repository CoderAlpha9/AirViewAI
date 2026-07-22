# AirView AI architecture

## Operational request flow

1. The React dashboard changes city, pollutant or horizon immediately.
2. `useProgressiveDashboard` aborts old requests and starts independent current, station, forecast, map, intelligence, action and advisory queries. The fixed five-city outlook has its own request.
3. FastAPI resolves configured cities locally or searched Indian cities through Nominatim.
4. The snapshot service concurrently requests CAMS/Open-Meteo, weather, stations and—where needed—FIRMS and OSM context under bounded timeouts.
5. A canonical context is created from the resolved city, pollutant, horizon, issue time and coverage. Its snapshot ID is deterministic for that context and excludes volatile request-age metadata.
6. The persisted artifact is loaded for the pollutant/horizon. It was trained on station-observation change from persistence, without archived CAMS fields. Its correction is transferred onto the live CAMS endpoint only when metadata selects the learned residual as champion.
7. Up to five selected stations contribute a distance- and freshness-weighted residual. The residual is recomputed for every grid-cell centre.
8. The API returns backend-owned AQI, category, colour, priority, advisory and intervention values. Current status drives unqualified dashboard categories, advisory, current priority and map colour. The separately labelled five-city comparison uses one fixed next-24-hour PM2.5 peak context for its value, AQI, category, colour and forecast priority.
9. The frontend renders a panel only when its context matches the current controls and its snapshot matches already accepted panels.

## Runtime boundaries

- `backend/app/api/routes/dynamic.py`: production live-city panels.
- `backend/app/services/dynamic_operational.py`: provider orchestration, model inference and grid assembly.
- `backend/app/services/city_support.py`: Indian city resolution, station selection and grid geometry.
- `backend/app/services/decision.py`: canonical context and backend-owned decision values.
- `frontend/src/features/operations/useProgressiveDashboard.ts`: cancellation, stale-response rejection and independent panel state.
- `frontend/src/components/operations/LiveOperationsMap.tsx`: viewport fitting and bounded map rendering.
- `ml/airview_ml/forecasting/global_residual.py`: offline training/evaluation utility. It is not executed by the operational server.

Legacy evaluation modules and archived example outputs are not registered as production API routes. The production router exposes system health, operational metadata/five-city outlook and `/api/live/*` endpoints.

## Failure isolation

Provider calls have timeouts, limited retries and TTL caching. A failed optional provider is represented in `provider_status`; it does not cause archived data substitution. A failed panel shows a local retry state while other successful panels remain mounted. Generation counters and request cancellation prevent a late response from replacing a newer context.

## Security and configuration

Credentials are loaded from ignored `.env` files or process environment variables. Responses never include keys, stack traces or provider response bodies. CORS origins are configurable and the combined launcher derives them from its selected frontend port.
