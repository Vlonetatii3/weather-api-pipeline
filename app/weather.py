import asyncio
import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings

logger = logging.getLogger(__name__)

CURRENT_FIELDS = "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code"


class WeatherError(Exception):
    """Base de los errores del cliente de clima."""


class CityNotFoundError(WeatherError):
    """Open-Meteo no encontró la ciudad pedida."""


class UpstreamUnavailableError(WeatherError):
    """Open-Meteo no respondió: timeout o error de conexión."""


class UpstreamBadResponseError(WeatherError):
    """Open-Meteo respondió, pero con un error o con datos inesperados."""


class WeatherReport(BaseModel):
    city: str
    country: str | None
    latitude: float
    longitude: float
    temperature_c: float
    humidity_percent: float
    wind_speed_kmh: float
    weather_code: int
    observed_at: str
    cached: bool = False


class TTLCache:
    """Caché en memoria donde cada entrada vence a los `ttl_seconds`."""

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, WeatherReport]] = {}

    def get(self, key: str) -> WeatherReport | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        # monotonic() no salta si cambia la hora del sistema (NTP, cambio de horario).
        if time.monotonic() >= expires_at:
            del self._entries[key]
            return None
        return value

    def set(self, key: str, value: WeatherReport) -> None:
        self._entries[key] = (time.monotonic() + self._ttl, value)


class WeatherClient:
    """Cliente de Open-Meteo con timeout, reintentos y caché."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings
        self._cache = TTLCache(settings.cache_ttl_seconds)

    async def get_weather(self, city: str) -> WeatherReport:
        key = city.strip().lower()
        cached = self._cache.get(key)
        if cached is not None:
            return cached.model_copy(update={"cached": True})

        place = await self._geocode(city)
        report = await self._fetch_current(place)
        self._cache.set(key, report)
        return report

    async def _geocode(self, city: str) -> dict[str, Any]:
        params = {"name": city, "count": 1, "language": "es", "format": "json"}
        data = await self._get_json(self._settings.geocoding_url, params)
        results = data.get("results")
        if not results:
            raise CityNotFoundError(city)
        return results[0]

    async def _fetch_current(self, place: dict[str, Any]) -> WeatherReport:
        try:
            params = {
                "latitude": place["latitude"],
                "longitude": place["longitude"],
                "current": CURRENT_FIELDS,
                "timezone": "auto",
            }
            data = await self._get_json(self._settings.forecast_url, params)
            current = data["current"]
            return WeatherReport(
                city=place["name"],
                country=place.get("country"),
                latitude=place["latitude"],
                longitude=place["longitude"],
                temperature_c=current["temperature_2m"],
                humidity_percent=current["relative_humidity_2m"],
                wind_speed_kmh=current["wind_speed_10m"],
                weather_code=current["weather_code"],
                observed_at=current["time"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamBadResponseError(
                f"datos inesperados de Open-Meteo: {exc!r}"
            ) from exc

    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """GET con timeout y reintentos con backoff exponencial ante fallas transitorias."""
        attempts = self._settings.http_max_retries + 1
        last_error: WeatherError

        for attempt in range(1, attempts + 1):
            try:
                response = await self._http.get(
                    url, params=params, timeout=self._settings.http_timeout_seconds
                )
            except httpx.TransportError as exc:
                # Timeout, conexión rechazada, DNS: no hubo respuesta. Reintentable.
                last_error = UpstreamUnavailableError(
                    f"{type(exc).__name__} llamando a {url}"
                )
            else:
                if response.status_code < 500:
                    return self._parse_json(response, url)
                # 5xx: falla del lado de Open-Meteo, puede ser transitoria. Reintentable.
                last_error = UpstreamBadResponseError(
                    f"{url} respondió {response.status_code}"
                )

            if attempt < attempts:
                delay = self._settings.http_retry_backoff_seconds * 2 ** (attempt - 1)
                logger.warning(
                    "intento %d/%d falló (%s); reintento en %.2fs",
                    attempt,
                    attempts,
                    last_error,
                    delay,
                )
                await asyncio.sleep(delay)

        raise last_error

    @staticmethod
    def _parse_json(response: httpx.Response, url: str) -> dict[str, Any]:
        # 4xx: el request que armamos está mal; repetirlo daría lo mismo. No se reintenta.
        if response.is_error:
            raise UpstreamBadResponseError(f"{url} respondió {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamBadResponseError(f"{url} devolvió un JSON inválido") from exc
        if not isinstance(data, dict):
            raise UpstreamBadResponseError(
                f"{url} devolvió un JSON que no es un objeto"
            )
        return data
