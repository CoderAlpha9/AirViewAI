from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CopilotHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=800)

    @field_validator("content")
    @classmethod
    def clean_content(cls, value: str) -> str:
        return value.strip()


class CopilotChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=800)
    city_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9-]+$")
    pollutant: Literal["pm2_5", "pm10"]
    horizon: Literal[24, 48, 72]
    snapshot_id: str = Field(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    session_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    language: str | None = Field(default=None, min_length=2, max_length=40)
    history: list[CopilotHistoryMessage] = Field(default_factory=list, max_length=4)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        return value.strip()


class CopilotReply(BaseModel):
    answer: str = Field(min_length=1, max_length=2400)
    evidence: list[str] = Field(default_factory=list, max_length=5)
    data_status: Literal["station-corrected", "model-based", "partial"]
    limitations: list[str] = Field(default_factory=list, max_length=4)
    suggested_questions: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("answer")
    @classmethod
    def clean_answer(cls, value: str) -> str:
        return value.strip()

    @field_validator("evidence", "limitations", "suggested_questions")
    @classmethod
    def clean_items(cls, value: list[str]) -> list[str]:
        return [item.strip()[:300] for item in value if item.strip()]
