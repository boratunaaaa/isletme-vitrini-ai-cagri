"""Places provider'ları: Google Places (New) + içe aktarılmış lead kaynağı."""

from __future__ import annotations

import httpx

from app.config import get_settings
from app.providers.base import PlaceResult

_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.nationalPhoneNumber",
        "places.internationalPhoneNumber",
        "places.websiteUri",
        "places.formattedAddress",
        "places.primaryTypeDisplayName",
        "places.rating",
        "places.userRatingCount",
    ]
)


class PlacesDisabledError(RuntimeError):
    pass


class GooglePlacesProvider:
    name = "google_places"
    SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
    DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

    def _ensure_enabled(self) -> str:
        s = get_settings()
        if not s.ENABLE_GOOGLE_PLACES:
            raise PlacesDisabledError("Google Places entegrasyonu kapalı (ENABLE_GOOGLE_PLACES)")
        if not s.GOOGLE_PLACES_API_KEY:
            raise PlacesDisabledError("GOOGLE_PLACES_API_KEY tanımlı değil")
        return s.GOOGLE_PLACES_API_KEY

    @staticmethod
    def _to_result(place: dict) -> PlaceResult:
        return PlaceResult(
            external_place_id=place.get("id", ""),
            business_name=(place.get("displayName") or {}).get("text", ""),
            phone_raw=place.get("internationalPhoneNumber")
            or place.get("nationalPhoneNumber"),
            website=place.get("websiteUri"),
            address=place.get("formattedAddress"),
            category=(place.get("primaryTypeDisplayName") or {}).get("text"),
            rating=place.get("rating"),
            review_count=place.get("userRatingCount"),
        )

    async def search_text(self, query: str, *, max_results: int = 20) -> list[PlaceResult]:
        api_key = self._ensure_enabled()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                self.SEARCH_URL,
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": _FIELD_MASK,
                    "Content-Type": "application/json",
                },
                json={"textQuery": query, "maxResultCount": min(max_results, 20)},
            )
            response.raise_for_status()
            payload = response.json()
        return [self._to_result(p) for p in payload.get("places", [])]

    async def get_place_details(self, place_id: str) -> PlaceResult | None:
        api_key = self._ensure_enabled()
        field_mask = _FIELD_MASK.replace("places.", "")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                self.DETAILS_URL.format(place_id=place_id),
                headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            place = response.json()
        place.setdefault("id", place_id)
        return self._to_result(place)


class ImportedLeadProvider:
    """Dosyadan içe aktarılan lead'ler için sembolik provider — asıl iş
    app/services/importer.py'dedir; bu sınıf kaynak etiketini standardize eder."""

    name = "imported"

    async def search_text(self, query: str, *, max_results: int = 20) -> list[PlaceResult]:
        return []

    async def get_place_details(self, place_id: str) -> PlaceResult | None:
        return None
