import re
import unicodedata
from dataclasses import dataclass

POLLUTANT_ALIASES = {
    "pm2.5": "pm2_5",
    "pm 2.5": "pm2_5",
    "pm25": "pm2_5",
    "pm10": "pm10",
    "no2": "no2",
    "nitrogen dioxide": "no2",
    "so2": "so2",
    "sulphur dioxide": "so2",
    "sulfur dioxide": "so2",
    "co": "co",
    "carbon monoxide": "co",
    "o3": "o3",
    "ozone": "o3",
    "nh3": "nh3",
    "ammonia": "nh3",
    "bc": "bc",
    "black carbon": "bc",
}

CITY_ALIASES = {
    "bangalore": "bengaluru",
    "bombay": "mumbai",
    "calcutta": "kolkata",
    "madras": "chennai",
    "new delhi": "delhi ncr",
    "delhi": "delhi ncr",
    "gurgaon": "gurugram",
    "allahabad": "prayagraj",
    "baroda": "vadodara",
}


def normalise_text(value: str | None) -> str:
    if not value:
        return ""
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", normalised.lower())).strip()


def normalise_pollutant(value: str | None) -> str | None:
    cleaned = normalise_text(value).replace(" ", "")
    return POLLUTANT_ALIASES.get(cleaned) or POLLUTANT_ALIASES.get(normalise_text(value))


def normalise_city_name(value: str | None) -> str:
    cleaned = normalise_text(value)
    return CITY_ALIASES.get(cleaned, cleaned)


@dataclass(frozen=True)
class CityMatch:
    matched_slug: str | None
    confidence: str
    reason: str


def match_city(value: str | None, state: str | None, registry: list[dict[str, object]]) -> CityMatch:
    target = normalise_city_name(value)
    state_target = normalise_text(state)
    exact = [
        city
        for city in registry
        if normalise_city_name(str(city["name"])) == target
        and (not state_target or normalise_text(str(city["state"])) == state_target)
    ]
    if len(exact) == 1:
        return CityMatch(str(exact[0]["slug"]), "high", "state-aware exact or configured alias match")
    if not target:
        return CityMatch(None, "none", "missing city name")
    return CityMatch(None, "review", "no safe state-aware match; fuzzy matching is deliberately not automatic")
