import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, Path, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.weather import (
    CityNotFoundError,
    UpstreamBadResponseError,
    UpstreamUnavailableError,
    WeatherClient,
    WeatherReport,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Antes del yield: arranque. Después del yield: apagado (cierra las conexiones).
    async with httpx.AsyncClient() as http:
        app.state.weather_client = WeatherClient(http, get_settings())
        yield


app = FastAPI(title="Weather API", lifespan=lifespan)


@app.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/weather/{city}")
async def get_weather(
    city: Annotated[str, Path(min_length=1, max_length=100)], request: Request
) -> WeatherReport:
    client: WeatherClient = request.app.state.weather_client
    return await client.get_weather(city)


@app.exception_handler(CityNotFoundError)
async def city_not_found_handler(
    request: Request, exc: CityNotFoundError
) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "error": "city_not_found",
            "detail": f"No se encontró la ciudad '{exc}'.",
        },
    )


@app.exception_handler(UpstreamUnavailableError)
async def upstream_unavailable_handler(
    request: Request, exc: UpstreamUnavailableError
) -> JSONResponse:
    logger.error("Open-Meteo no disponible: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "error": "upstream_unavailable",
            "detail": "El servicio de clima no está disponible. Intentá de nuevo en unos minutos.",
        },
    )


@app.exception_handler(UpstreamBadResponseError)
async def upstream_bad_response_handler(
    request: Request, exc: UpstreamBadResponseError
) -> JSONResponse:
    logger.error("Respuesta inválida de Open-Meteo: %s", exc)
    return JSONResponse(
        status_code=502,
        content={
            "error": "upstream_bad_response",
            "detail": "El servicio de clima devolvió una respuesta inválida.",
        },
    )
