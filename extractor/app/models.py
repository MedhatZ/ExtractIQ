from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    url: str = Field(..., min_length=1, max_length=2048)


class Entities(BaseModel):
    people: list[str] = Field(default_factory=list)
    organizations: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)


class Extraction(BaseModel):
    title: str
    summary: str
    topics: list[str]
    entities: Entities
    keyFacts: list[str]


class Source(BaseModel):
    url: str
    fetchedAt: str
    contentType: str
    truncated: bool


class Meta(BaseModel):
    model: str
    mock: bool


class ExtractResponse(BaseModel):
    source: Source
    extraction: Extraction
    meta: Meta


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
