# Data workspace

- `raw/`: immutable source extracts, excluded from Git by default
- `interim/`: validated and normalised intermediate data
- `processed/`: model-ready features and labels
- `reference/`: versioned public definitions, boundaries, and lookup tables
- `demo/`: explicitly labelled demonstration datasets safe to share

No live CPCB, CAAQMS, satellite, traffic, or city-system feed is connected in the foundation
stage. Any future simulated or semi-synthetic dataset must be identified in its filename,
metadata, documentation, and downstream presentation.

