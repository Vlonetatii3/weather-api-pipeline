from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración del servicio, leída de variables de entorno con prefijo WEATHER_."""

    model_config = SettingsConfigDict(env_prefix="WEATHER_")

    geocoding_url: str = "https://geocoding-api.open-meteo.com/v1/search"
    forecast_url: str = "https://api.open-meteo.com/v1/forecast"

    # Tiempo máximo de espera por cada llamada a Open-Meteo.
    http_timeout_seconds: float = Field(default=3.0, gt=0)
    # Reintentos extra tras el primer intento (2 => hasta 3 intentos en total).
    http_max_retries: int = Field(default=2, ge=0, le=5)
    # Pausa base entre reintentos; se duplica en cada intento (backoff exponencial).
    http_retry_backoff_seconds: float = Field(default=0.2, ge=0)

    cache_ttl_seconds: int = Field(default=300, ge=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
