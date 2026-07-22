from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ProjectInfoResponse(BaseModel):
    name: str
    problem_statement: str
    implementation_stage: str
    planned_modules: list[str]

