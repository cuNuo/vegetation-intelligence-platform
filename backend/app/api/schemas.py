"""HTTP接口数据模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class SourceReference(BaseModel):
    object_key: str | None = Field(default=None, alias="objectKey")
    local_path: str | None = Field(default=None, alias="localPath")

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_source(self) -> SourceReference:
        if not self.object_key and not self.local_path:
            raise ValueError("objectKey与localPath至少提供一个")
        return self


class ExecutionRequest(BaseModel):
    source: SourceReference
    indices: list[str] = Field(min_length=1, max_length=35)
    bands: dict[str, int]
    engine: Literal["auto", "numpy", "joblib", "torch"] = "auto"
    block_size: int = Field(default=1024, alias="blockSize", ge=128, le=2048)
    priority: int = Field(default=3, ge=1, le=5)
    statistics: bool = True
    preview: bool = True
    parameters: dict[str, dict[str, float]] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class RasterInspectRequest(BaseModel):
    path: str


class AgentLLMConfig(BaseModel):
    provider: Literal["openai-compatible", "anthropic"] = "openai-compatible"
    base_url: str | None = Field(default=None, alias="baseUrl", max_length=500)
    token: str | None = Field(default=None, max_length=4000)
    model: str = Field(default="gpt-4.1-mini", max_length=120)
    temperature: float = Field(default=0, ge=0, le=2)

    model_config = {"populate_by_name": True}


class AgentKnowledgeDocument(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)
    url: str | None = Field(default=None, max_length=500)


class AgentKnowledgeImportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=12000)
    source: str = Field(default="user-upload", max_length=500)
    session_id: str | None = Field(default=None, alias="sessionId", max_length=80)

    model_config = {"populate_by_name": True}


class AgentCustomIndexRequest(BaseModel):
    id: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=100)
    expression: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=500)
    expected_range: tuple[float, float] | None = Field(default=None, alias="expectedRange")
    categories: list[str] = Field(default_factory=lambda: ["custom"], max_length=8)
    recommendation_tags: list[str] = Field(
        default_factory=list,
        alias="recommendationTags",
        max_length=8,
    )
    limitations: list[str] = Field(default_factory=list, max_length=8)

    model_config = {"populate_by_name": True}


class AgentPlanRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)
    session_id: str | None = Field(default=None, alias="sessionId", max_length=80)
    available_bands: list[str] = Field(default_factory=list, alias="availableBands")
    raster_width: int | None = Field(default=None, alias="rasterWidth", ge=1)
    raster_height: int | None = Field(default=None, alias="rasterHeight", ge=1)
    llm: AgentLLMConfig | None = None
    enable_web_search: bool = Field(default=True, alias="enableWebSearch")
    external_documents: list[AgentKnowledgeDocument] = Field(
        default_factory=list,
        alias="externalDocuments",
    )
    custom_index: AgentCustomIndexRequest | None = Field(default=None, alias="customIndex")

    model_config = {"populate_by_name": True}


class ConfirmPlanRequest(BaseModel):
    source: SourceReference
    bands: dict[str, int]
    indices: list[str] | None = Field(default=None, min_length=1, max_length=35)
    engine: Literal["auto", "numpy", "joblib", "torch"] | None = None
    block_size: int = Field(default=1024, alias="blockSize", ge=128, le=2048)
    priority: int = Field(default=3, ge=1, le=5)

    model_config = {"populate_by_name": True}


class RecipeRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    indices: list[str] = Field(min_length=1, max_length=35)
    description: str = Field(default="", max_length=500)


class CustomFormulaRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=500)
    allowed_bands: list[str] = Field(alias="allowedBands", min_length=1)

    model_config = {"populate_by_name": True}


class ChangeDetectionRequest(BaseModel):
    before_path: str = Field(alias="beforePath")
    after_path: str = Field(alias="afterPath")
    output_path: str = Field(alias="outputPath")
    decrease_threshold: float = Field(default=-0.2, alias="decreaseThreshold")
    increase_threshold: float = Field(default=0.2, alias="increaseThreshold")

    model_config = {"populate_by_name": True}


class ZonalStatisticsRequest(BaseModel):
    raster_path: str = Field(alias="rasterPath")
    geojson: dict

    model_config = {"populate_by_name": True}


class AgentResultInterpretRequest(BaseModel):
    products: list[dict[str, Any]] = Field(default_factory=list)
    user_goal: str = Field(default="", alias="userGoal", max_length=1000)
    session_id: str | None = Field(default=None, alias="sessionId", max_length=80)
    llm: AgentLLMConfig | None = None

    model_config = {"populate_by_name": True}
