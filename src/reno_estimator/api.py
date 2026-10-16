"""HTTP API and demo page."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from .context import catastro_context
from .env import load_dotenv
from .estimator import EstimationError, estimate
from .images import ImageError, prepare
from .providers import DEFAULT_MODELS, ProviderError, get_provider
from .schema import Estimate, EstimateRequest, Quality

load_dotenv()
STATIC = Path(__file__).parent / "static"
DEFAULT_SPEC = os.environ.get("RENO_MODEL", f"anthropic:{DEFAULT_MODELS['anthropic']}")


def create_app(http_client: httpx.AsyncClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
        yield
        if http_client is None:
            await app.state.http.aclose()

    app = FastAPI(title="AI Renovation Estimator", version="0.1.0", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/models")
    async def models() -> dict:
        return {"default": DEFAULT_SPEC, "providers": DEFAULT_MODELS}

    @app.post("/api/estimate", response_model=Estimate)
    async def create_estimate(
        description: Annotated[str, Form()],
        province: Annotated[str | None, Form()] = None,
        area_m2: Annotated[float | None, Form()] = None,
        quality: Annotated[Quality, Form()] = "media",
        cadastral_reference: Annotated[str | None, Form()] = None,
        model: Annotated[str | None, Form()] = None,
        photos: Annotated[list[UploadFile] | None, File()] = None,
    ) -> Estimate:
        try:
            context = await catastro_context(cadastral_reference) if cadastral_reference else None
            request = EstimateRequest(
                description=description,
                province=province or None,
                area_m2=area_m2,
                quality=quality,
                property_context=context,
            )
            images = prepare([await p.read() for p in photos or [] if p.filename])
            provider = get_provider(model or DEFAULT_SPEC, app.state.http)
        except (ValidationError, ImageError, ProviderError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        try:
            return await estimate(request, provider, images)
        except EstimationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return app


app = create_app()
