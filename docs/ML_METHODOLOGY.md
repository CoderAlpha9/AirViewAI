# ML methodology

## Objective

AirView AI predicts PM2.5 or PM10 by starting with a live CAMS/Open-Meteo trajectory and optionally transferring a city-agnostic persistence-trained correction, then adding a live multi-station spatial residual.

## Persisted artifacts

Six `Pipeline(SimpleImputer, HistGradientBoostingRegressor)` artifacts are persisted under `models/forecasting/global_residual/{pollutant}/{horizon}`. The exact training target is `observed_station(t+h) - observed_station(t)`. Archived CAMS values were not present during training. The legacy feature keys `camps_current` and `camps_target` are retained for artifact compatibility, but both held `observed_station(t)` during training; they must not be interpreted as CAMS inputs. Missing features are handled by the persisted imputer.

The runtime loads the artifact for every pollutant/horizon, verifies its metadata and honours the stored validation champion. If persistence beat the learned residual, the learned correction is zero. If the learned residual won, its station-persistence correction is transferred onto live CAMS; this transfer was not directly validated against archived CAMS error.

## Validation

Validation is grouped leave-one-city-out across Agra, Amritsar, Delhi NCR, Lucknow and Ludhiana. This tests coordinate generalisation to a city excluded from training.

| Pollutant | Horizon | Selected residual | HGB residual RMSE | Persistence RMSE |
|---|---:|---|---:|---:|
| PM2.5 | 24 h | zero/persistence | 64.64 | 64.61 |
| PM2.5 | 48 h | HGB residual | 66.86 | 70.46 |
| PM2.5 | 72 h | HGB residual | 68.76 | 73.54 |
| PM10 | 24 h | zero/persistence | 122.91 | 117.89 |
| PM10 | 48 h | zero/persistence | 128.40 | 126.92 |
| PM10 | 72 h | HGB residual | 130.91 | 131.67 |

These metrics evaluate future station concentration against a causal station-persistence baseline. They do not evaluate CAMS residuals. Archived cell-level CAMS inputs were not retained, so the operational transfer onto CAMS has not been directly backtested. The limitation is preserved in every artifact's metadata.

## Operational inference

For active learned champions, live hourly inference is `max(0, CAMS(i) + (i/h) × model(x_live) + station_residual × exp(-i/18))`; for persistence champions the model term is zero. At the grid horizon it is `max(0, CAMS(h) + model(x_live_cell) + station_residual_cell × exp(-h/18) + bounded_wind_planning_adjustment_cell)`. Grid inference is batched and uses each cell centre. Up to five stations are ranked using freshness, pollutant availability, distance, completeness and provider preference.

Station residual weight decays with distance, observation age and forecast lead. Model-only cells receive lower confidence than station-corrected cells. Missing artifacts, providers or features produce zero correction or unavailable outputs rather than fabricated observations.

## Interpretation

The grid is an operational prioritisation surface. It is not a calibrated street-scale atmospheric simulation. AQI, category, colour, priority and advice are derived centrally by the backend. Unqualified status and map colours use current concentration; future values remain explicitly forecast-labelled within the same canonical context.
