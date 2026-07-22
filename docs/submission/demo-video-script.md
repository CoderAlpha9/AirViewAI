# AirView AI demo script

## Opening

Open `/dashboard`. Explain that panels load independently and that the selected city, pollutant and horizon update immediately.

## City and provider workflow

Switch among the five defaults, then search for an Indian city such as Mysuru. Point out provider, freshness, station count and station-corrected versus model-based coverage. If a provider is unavailable, show the local panel state; there is no replay or archived-value fallback.

## Forecast evidence

Switch PM2.5/PM10 and 24/48/72 hours. Explain that the operational trajectory starts from live CAMS. The optional learned correction was trained on station change from persistence—not archived CAMS error—and is transferred onto CAMS only where grouped validation selected it. Nearby live stations add a separate lead-decayed spatial correction.

## Map and decisions

Show the relocated one-kilometre grid, current-category transparent colours, separate horizon forecast tooltip, station markers and FIRMS markers when available. Explain that source indicators guide field verification and are not emission shares.

## Fixed comparison

Close on the five-city next-24-hour PM2.5 comparison. Its peak value, AQI, category, colour and forecast priority come from one canonical snapshot per city.
