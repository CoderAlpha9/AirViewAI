# AirView AI operational architecture

This document describes the production path only. Offline training and evaluation utilities remain under `ml/` and are not registered as application routes.

## Evidence and providers

The backend concurrently requests CPCB/Data.gov.in and OpenAQ station data, CAMS fields through Open-Meteo Air Quality, Open-Meteo weather, NASA FIRMS and OpenStreetMap context. Calls have bounded timeouts and TTL caches. Missing providers produce local unavailable or partial states; archived observations are never substituted into the live path.

## Canonical snapshot

Every live panel returns the resolved city, pollutant, horizon, issue time, coverage type and deterministic snapshot ID. The frontend cancels old requests and rejects responses whose context or snapshot differs from the active controls.

## Forecast evidence boundary

The six persisted pipelines were trained on station observations. Their exact target is `observed_station(t+h) - observed_station(t)`. Archived CAMS fields were not present. The legacy artifact keys `camps_current` and `camps_target` both contained the issue-time station observation during training.

At runtime, the selected persistence-trained correction is transferred onto a live CAMS trajectory. This is an operational transfer, not a historically validated CAMS-error model. Artifacts whose grouped validation selected persistence contribute zero learned correction. Live station residual interpolation remains separate and decays with lead time.

## Map lifecycle

The map contains one keyed GeoJSON grid layer for the active snapshot plus keyed station and FIRMS marker layers. A city or context change unmounts the previous keyed layers before mounting the new ones. `flyToBounds` fits the active grid and stations. The visible current-category fill is transparent; the selected-horizon forecast is retained separately in tooltips.

Leaflet renders grid polygons, station circles and FIRMS circles as SVG `<path>` elements. Therefore total SVG path count is not the grid-cell count. The audit counts `.airview-grid-cell`, `.airview-station-marker` and `.airview-firms-marker` separately and compares the grid class count with active metadata.

## Five-city comparison

The comparison is fixed to the next 24 hours and PM2.5. Each row uses the forecast peak value, AQI, category, colour and forecast priority from the same canonical city snapshot. It does not mix current-category wording into that future outlook.

## Product boundary

The production router exposes health, operational metadata, the fixed comparison and `/api/live/*` panels. Replay and research routes are not registered. Training reports remain evidence artifacts, not live fallbacks.
