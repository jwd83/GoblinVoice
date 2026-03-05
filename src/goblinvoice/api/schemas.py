from __future__ import annotations

from pydantic import BaseModel, Field


class SynthesizeIn(BaseModel):
    guild_id: int = Field(alias="guildId")
    text: str
    voice: str | None = None
    style: str | None = None
    backend: str | None = None


class SynthesizeOut(BaseModel):
    guild_id: int = Field(alias="guildId")
    backend: str
    audio_path: str = Field(alias="audioPath")
    correlation_id: str = Field(alias="correlationId")


class CloneIn(BaseModel):
    guild_id: int = Field(alias="guildId")
    name: str
    sample_path: str = Field(alias="samplePath")
    consent_token: str = Field(alias="consentToken")
    target: str
    backend: str | None = None


class CloneOut(BaseModel):
    guild_id: int = Field(alias="guildId")
    voice_id: str = Field(alias="voiceId")
    name: str
    backend: str
    sample_path: str = Field(alias="samplePath")


class ConsentIn(BaseModel):
    guild_id: int = Field(alias="guildId")
    target: str
    issued_by: str = Field(alias="issuedBy")


class ConsentOut(BaseModel):
    guild_id: int = Field(alias="guildId")
    target: str
    token: str


class BackendDefaultIn(BaseModel):
    guild_id: int = Field(alias="guildId")
    provider: str


class ErrorEnvelope(BaseModel):
    error_code: str = Field(alias="errorCode")
    message: str
    retryable: bool
    provider: str | None = None
