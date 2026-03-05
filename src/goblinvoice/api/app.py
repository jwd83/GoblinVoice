from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from goblinvoice.api.schemas import (
    BackendDefaultIn,
    CloneIn,
    CloneOut,
    ConsentIn,
    ConsentOut,
    SynthesizeIn,
    SynthesizeOut,
)
from goblinvoice.config import Settings, load_settings
from goblinvoice.errors import GoblinVoiceError
from goblinvoice.orchestrator.service import GoblinVoiceService
from goblinvoice.types import CloneRequest, SynthesizeRequest


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
        }
        correlation = getattr(record, "correlation_id", None)
        if isinstance(correlation, str):
            payload["correlationId"] = correlation
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(settings: Settings) -> None:
    settings.logs_path.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(settings.logs_path / "api.log", encoding="utf-8")
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()
    configure_logging(resolved)

    service = GoblinVoiceService.from_settings(resolved)
    app = FastAPI(title="GoblinVoice API")
    app.state.service = service

    @app.on_event("startup")
    async def startup() -> None:
        await service.start()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        await service.stop()

    @app.exception_handler(GoblinVoiceError)
    async def handle_goblinvoice_error(_: Request, exc: GoblinVoiceError) -> JSONResponse:
        status = 503 if exc.retryable else 400
        return JSONResponse(status_code=status, content=exc.to_envelope())

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return await service.health()

    @app.post("/synthesize", response_model=SynthesizeOut)
    async def synthesize(payload: SynthesizeIn) -> SynthesizeOut:
        result = await service.synthesize(
            SynthesizeRequest(
                guild_id=payload.guild_id,
                text=payload.text,
                voice=payload.voice,
                style=payload.style,
                backend=payload.backend,
            )
        )
        return SynthesizeOut(
            guildId=result.guild_id,
            backend=result.backend,
            audioPath=str(result.audio_path),
            correlationId=result.correlation_id,
        )

    @app.post("/clone", response_model=CloneOut)
    async def clone(payload: CloneIn) -> CloneOut:
        profile = await service.clone(
            CloneRequest(
                guild_id=payload.guild_id,
                name=payload.name,
                sample_path=Path(payload.sample_path),
                consent_token=payload.consent_token,
                target=payload.target,
                backend=payload.backend,
            )
        )
        return CloneOut(
            guildId=profile.guild_id,
            voiceId=profile.voice_id,
            name=profile.name,
            backend=profile.backend,
            samplePath=profile.sample_path,
        )

    @app.post("/consent", response_model=ConsentOut)
    async def consent(payload: ConsentIn) -> ConsentOut:
        token = service.create_consent(
            payload.guild_id,
            target=payload.target,
            issued_by=payload.issued_by,
        )
        return ConsentOut(guildId=payload.guild_id, target=payload.target, token=token)

    @app.get("/voices/{guild_id}")
    async def voices(guild_id: int) -> dict[str, Any]:
        return await service.list_voice_catalog(guild_id)

    @app.post("/backend/default")
    async def set_backend_default(payload: BackendDefaultIn) -> dict[str, str | int]:
        service.set_guild_default_backend(payload.guild_id, payload.provider)
        return {"guildId": payload.guild_id, "provider": payload.provider}

    return app


def main() -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Run GoblinVoice FastAPI service")
    parser.add_argument("--host", default=settings.api_host)
    parser.add_argument("--port", default=settings.api_port, type=int)
    args = parser.parse_args()

    uvicorn.run(
        "goblinvoice.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
