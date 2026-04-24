from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


ScanType = Literal["pain_points", "content_ideas"]
JobStatus = Literal["queued", "running", "completed", "failed"]


class StartScanRequest(BaseModel):
    profile: str | None = Field(default=None, description="Built-in profile name, e.g. tr or global.")
    config_yaml: str | None = Field(default=None, description="Full TopicConfig YAML.")
    scan_type: ScanType | None = None
    language: str | None = Field(default=None, pattern="^(tr|en)$")
    topic_name: str | None = None

    @model_validator(mode="after")
    def require_profile_or_yaml(self) -> "StartScanRequest":
        if not self.profile and not self.config_yaml:
            raise ValueError("Provide either profile or config_yaml.")
        if self.profile and self.config_yaml:
            raise ValueError("Use profile or config_yaml, not both.")
        return self


class StartScanResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobSnapshot(BaseModel):
    job_id: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    profile: str | None = None
    topic_name: str | None = None
    scan_id: str | None = None
    error: str | None = None

