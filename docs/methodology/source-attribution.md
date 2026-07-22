# Source-attribution indicators

AirView AI produces transparent, receptor-centred **source attribution indicators**. They are evidence-supported source likelihood rankings, not confirmed emissions sources, regulatory source apportionment, emissions percentages, or causal findings. The configurable weights live in `ml/airview_ml/intelligence/weights.json` and combine pollutant pattern, time pattern, mapped-proxy proximity, wind/accumulation, regional-event, and forecast-severity indicators. Missing evidence lowers confidence and can produce `insufficient evidence`.

One station per city supports station-centred screening only. OSM is a static proxy; Sentinel-5P has zero validated pixels, GHSL is absent, and the present processed workspace lacks time-aligned FIRMS events.
