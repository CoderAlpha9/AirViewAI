from dataclasses import dataclass


@dataclass(frozen=True)
class UnitConversion:
    value_canonical: float | None
    unit_canonical: str | None
    flags: list[str]


def normalise_unit(unit: str | None) -> str:
    return (unit or "").lower().replace("µ", "u").replace("³", "3").replace("/", " ").strip()


def convert_pollutant(value: float | None, unit: str | None, pollutant: str | None) -> UnitConversion:
    if value is None:
        return UnitConversion(None, None, ["missing_value"])
    canonical_pollutant = (pollutant or "").lower()
    cleaned_unit = normalise_unit(unit)
    if canonical_pollutant == "co":
        if cleaned_unit in {"mg m3", "mg m-3", "mg/m3"}:
            return UnitConversion(value, "mg/m3", [])
        if cleaned_unit in {"ug m3", "ug m-3", "ug/m3"}:
            return UnitConversion(value / 1000, "mg/m3", ["unit_converted_ug_m3_to_mg_m3"])
    elif canonical_pollutant in {"pm2_5", "pm10", "no2", "so2", "o3", "nh3", "bc"}:
        if cleaned_unit in {"ug m3", "ug m-3", "ug/m3", "micrograms per cubic meter"}:
            return UnitConversion(value, "ug/m3", [])
        if cleaned_unit in {"mg m3", "mg m-3", "mg/m3"}:
            return UnitConversion(value * 1000, "ug/m3", ["unit_converted_mg_m3_to_ug_m3"])
    return UnitConversion(None, None, ["unsupported_or_incompatible_unit"])
