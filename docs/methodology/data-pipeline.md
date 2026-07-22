# Data pipeline

The pipeline is run through `python -m airview_ml.data.pipeline`. It writes raw request responses
to `data/raw/<source>/http/`, processed tabular output to `data/processed/india/`, and report JSON
to `outputs/reports/`. Large raw and processed outputs are Git-ignored.

Profiles:

- `smoke`: three configured major cities, two days of weather, and conservative source probes.
- `hackathon`: national discovery plus configured major-city acquisition; it is resumable and does
  not expand to global archives.
- `full-india`: all discovered/configured eligible cities and configurable multi-year windows.

The CLI never creates observations when a source fails. It writes `credentials_required`, `failed`,
or `not_ready` status with an actionable message instead. Request cache keys are deterministic,
raw JSON is retained, and HTTP retries use bounded exponential backoff.

```powershell
.\.venv\Scripts\python.exe -m airview_ml.data.pipeline credentials
.\.venv\Scripts\python.exe -m airview_ml.data.pipeline fetch --profile smoke
.\.venv\Scripts\python.exe -m airview_ml.data.pipeline fetch --profile hackathon
.\.venv\Scripts\python.exe -m airview_ml.data.pipeline fetch --profile full-india
.\.venv\Scripts\python.exe -m airview_ml.data.pipeline build --profile hackathon
.\.venv\Scripts\python.exe -m airview_ml.data.pipeline report --profile hackathon
```

