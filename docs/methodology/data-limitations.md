# Data limitations

- No adapter is described as live without a successful request recorded in a pipeline report.
- OpenAQ v3, Data.gov.in, NASA FIRMS and Copernicus require credentials; absent credentials do not
  produce substitute data.
- Sentinel-5P columns are not ground-level pollutant concentrations and are kept separately.
- OSM road, land-use and facility features are traffic, industrial, construction, waste, and
  vulnerability-location proxies—not direct emissions or population counts.
- GHSL population is modelled and must not be represented as a census value.
- Schools and hospitals are vulnerability-location proxies; no age, illness, or demographic
  inference is made without a supporting dataset.
- Historical OpenAQ archive downloads require India location IDs discovered through the authenticated API.

