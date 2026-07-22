# Final delivery report

## Delivered operational path

- One production React dashboard with independent panel loading, cancellation, retry and snapshot validation.
- Five quick-select cities plus Nominatim-backed Indian city search.
- PM2.5/PM10 and 24/48/72-hour forecasts.
- Station-aware current conditions, one-kilometre GeoJSON grids, FIRMS/OSM context, interventions and citizen guidance.
- Six persisted station-persistence-residual artifacts with leave-one-city-out metadata and validation-selected transfer onto live CAMS.
- Separate backend/frontend launchers, combined launcher, owned-process stop script and semantic end-to-end verifier.
- Production router excludes archived replay/evaluation APIs. Offline training and evaluation code remains separate under `ml/` and documentation folders.

## Data integrity

Every independent panel carries a canonical city, pollutant, horizon, issue timestamp and snapshot ID. The frontend rejects stale or mismatched responses. AQI, category, colour and priority are backend-owned. Provider failure never substitutes archived values or fabricates station observations.

Unqualified dashboard category labels, advisory, current intervention priority and visible grid colours use current concentration. The five-city table is a separate fixed next-24-hour PM2.5 peak comparison; each row's value, AQI, category, colour and forecast priority comes from one snapshot. The map receives its six-colour category legend from the backend, renders the current layer with transparent fills and keeps the selected-horizon forecast as a separate tooltip value.

## Validation summary

- Ruff lint: passed.
- Ruff format check: 75 files formatted, passed.
- Backend and ML: 69 tests passed.
- Frontend ESLint: passed with zero warnings.
- TypeScript: passed.
- Frontend: 3 tests passed.
- Production build: passed (738 modules transformed).
- End-to-end verifier: 28 passed, 0 failed.
- Headless Chrome audit: passed at 1440Ã—1000 and 390Ã—844; progressive loading was observed; Delhi NCR â†’ Ludhiana â†’ Mysuru â†’ Jaipur â†’ Delhi NCR and a five-city rapid-switch sequence ended on the correct snapshot and viewport; Mysuru, Jaipur and Pune search succeeded; PM2.5/PM10 and 24/48/72-hour controls were exercised; all active grid-path counts matched their 102/400-cell metadata; all six legend labels rendered; there were no console errors, failed application requests or mobile horizontal overflow.
- Persisted artifacts were loaded and regenerated with scikit-learn 1.9.0; the declared PyArrow minimum is 23.0 so the committed archived feature table remains readable by the training utility.

The captured browser run returned 102 one-kilometre cells for Mysuru and 400 for the other audited cities. No fresh station or FIRMS markers were returned by external providers in that run, so none are claimed; model-based coverage remained operational. Multi-station selection and spatial correction are covered by deterministic backend tests.

See `docs/ML_METHODOLOGY.md` for exact per-horizon model metrics and their limitations.

## External limitations

Live station, FIRMS, Overpass, Nominatim and tile availability is controlled by external providers and credentials. Model-based coverage is expected where no usable station is returned. The planning grid is decision support, not regulatory dispersion modelling.
