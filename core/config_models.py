from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class PersonalInfo(BaseModel):
    full_name: str = Field(..., min_length=1)
    email: str = Field(..., pattern=r".+@.+\..+")
    phone: str = Field(default="")
    location: str = Field(default="")
    linkedin: str = Field(default="")
    github: str = Field(default="")
    portfolio: str = Field(default="")
    work_authorization: str = Field(default="")
    current_ctc: str = Field(default="")
    expected_ctc: str = Field(default="")
    notice_period: str = Field(default="")


class Education(BaseModel):
    degree: str = Field(default="")
    field: str = Field(default="")
    institution: str = Field(default="")
    year: str = Field(default="")
    gpa: str = Field(default="")


class Experience(BaseModel):
    company: str = Field(default="")
    title: str = Field(default="")
    period: str = Field(default="")
    highlights: List[str] = Field(default_factory=list)


class ProfileConfig(BaseModel):
    personal: PersonalInfo
    education: List[Education] = Field(default_factory=list)
    experience: List[Experience] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    target_roles: List[str] = Field(default_factory=list)
    target_locations: List[str] = Field(default_factory=list)
    resume_path: str = Field(default="")

    @field_validator("resume_path")
    @classmethod
    def resume_must_exist(cls, v):
        if v and not Path(v).exists():
            raise ValueError(f"Resume file not found: {v}")
        return v

    @field_validator("skills")
    @classmethod
    def skills_not_empty(cls, v):
        if not v:
            raise ValueError("At least one skill is required")
        return v

    @field_validator("target_roles")
    @classmethod
    def roles_not_empty(cls, v):
        if not v:
            raise ValueError("At least one target role is required")
        return v


class LLMSettings(BaseModel):
    provider: str = Field(default="openai")
    model: str = Field(default="gpt-4")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=100)


class ScoringSettings(BaseModel):
    min_score_to_apply: int = Field(default=65, ge=0, le=100)
    min_score_auto_submit: int = Field(default=65, ge=0, le=100)


class RateLimits(BaseModel):
    linkedin: int = Field(default=50, ge=0)
    naukri: int = Field(default=50, ge=0)
    instahyre: int = Field(default=100, ge=0)
    indeed: int = Field(default=50, ge=0)
    company_ats: int = Field(default=100, ge=0)


class GlobalSettings(BaseModel):
    dry_run: bool = False
    max_jobs_per_run: int = Field(default=200, ge=1)
    headless: bool = True
    data_dir: str = Field(default="./data")
    max_captcha_per_run: int = Field(default=3, ge=1)
    log_file: str = Field(default="")


class NotifySettings(BaseModel):
    enabled: bool = False
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_pass: str = Field(default="")
    from_addr: str = Field(default="")
    to_addr: str = Field(default="")


class SettingsConfig(BaseModel):
    llm: LLMSettings = Field(default_factory=LLMSettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    rate_limits: RateLimits = Field(default_factory=RateLimits)
    global_: GlobalSettings = Field(default_factory=GlobalSettings, alias="global")
    notify: NotifySettings = Field(default_factory=NotifySettings)
