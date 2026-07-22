from datetime import datetime, timezone

from airview_ml.data.contracts import SourceResult


class GhslAdapter:
    source = "ghsl"
    official_url = "https://human-settlement.emergency.copernicus.eu/"

    @staticmethod
    def subset_request(
        city_slug: str, bbox: tuple[float, float, float, float], product: str = "GHS_POP"
    ) -> dict[str, object]:
        return {
            "city_slug": city_slug,
            "product": product,
            "bbox_wgs84": bbox,
            "output_crs": "EPSG:4326",
            "purpose": "download only a verified India-intersecting tile or official subset; never fabricate population",
        }

    def status(self) -> SourceResult:
        return SourceResult(
            source=self.source,
            status="not_ready",
            retrieved_at_utc=datetime.now(timezone.utc),
            official_url=self.official_url,
            value_kind="modelled",
            warnings=[
                "Automatic GHSL subset endpoints vary by product and may require an approved stable direct download URL. No population values are produced until a verified product response is retrieved."
            ],
            processing_steps=["request construction ready", "source availability recorded"],
        )
