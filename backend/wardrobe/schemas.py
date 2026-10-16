from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Category = Literal[
    "tops",
    "bottoms",
    "one-piece",
    "outerwear",
    "footwear",
    "accessories",
    "unrecognized",
]
WardrobeId = Literal["personal", "deepfashion2"]


class Attributes(BaseModel):
    category: Category = "unrecognized"
    subtype: str = Field(default="", max_length=80)
    color: str = Field(default="", max_length=80)
    pattern: str = Field(default="", max_length=80)
    style: str = Field(default="", max_length=80)


class GarmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: Category | None = None
    subtype: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=80)
    pattern: str | None = Field(default=None, max_length=80)
    style: str | None = Field(default=None, max_length=80)
    available: bool | None = None

    @field_validator("*", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError(
                "Use an empty string to clear a tag; null is not supported."
            )
        return value


class MessageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=2000)


class Constraints(BaseModel):
    query: str = ""
    count: int = Field(default=3, ge=1, le=3)
    include_ids: list[str] = Field(default_factory=list)
    exclude_ids: list[str] = Field(default_factory=list)
    exclude_categories: list[Category] = Field(default_factory=list)
    exclude_colors: list[str] = Field(default_factory=list)
    exclude_subtypes: list[str] = Field(default_factory=list)
    exclude_descriptions: list[str] = Field(default_factory=list)
    clarification: str = ""


class OutfitProposal(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    explanation: str = Field(max_length=700)
    item_ids: list[str] = Field(min_length=1, max_length=8)


class Proposal(BaseModel):
    message: str = Field(default="", max_length=1200)
    outfits: list[OutfitProposal] = Field(default_factory=list, max_length=3)


class Intent(Constraints):
    release_references: list[str] = Field(default_factory=list)
    allow_references: list[str] = Field(default_factory=list)
    include_references: list[str] = Field(default_factory=list)
    exclude_references: list[str] = Field(default_factory=list)
    replace_categories: list[Category] = Field(default_factory=list)
    reference_outfit: int | None = Field(default=None, ge=1, le=3)
    reset: bool = False

    release_ids: list[str] = Field(default_factory=list)
    allow_ids: list[str] = Field(default_factory=list)
    allow_categories: list[Category] = Field(default_factory=list)
    allow_colors: list[str] = Field(default_factory=list)
    allow_subtypes: list[str] = Field(default_factory=list)


class Garment(Attributes):
    id: str
    name: str
    available: bool
    image_url: str
    thumbnail_url: str
    analysis_status: Literal["pending", "ready", "review", "failed"]
    analysis_error: str | None
    alternatives: list[str]
    created_at: str
    suggestions: dict = Field(default_factory=dict)
    edited_fields: list[str] = Field(default_factory=list)


class RemovedGarment(BaseModel):
    id: str
    name: str
    available: Literal[False] = False
    deleted: Literal[True] = True
    image_url: None = None
    thumbnail_url: None = None


class Outfit(OutfitProposal):
    items: list[Garment | RemovedGarment]
    missing_components: list[str]


class Message(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    outfits: list[Outfit]
    created_at: str


class Conversation(BaseModel):
    id: str
    wardrobe: WardrobeId = "personal"
    messages: list[Message]
    constraints: dict


class ItemPage(BaseModel):
    items: list[Garment]
    total: int


class DatasetStatus(BaseModel):
    photo_count: int
    indexed_count: int
    ready: bool


class BenchmarkCase(BaseModel):
    id: str
    label: str
    prompt: str
    follow_up_to: str | None
    seconds: float
    outfit_count: int
    partial_count: int
    distinct_count: int
    message: str
    outfits: list[Outfit]
    error: str | None


class BenchmarkRun(BaseModel):
    id: str
    created_at: str
    status: Literal["running", "complete", "failed"]
    photo_count: int
    indexed_count: int
    cases: list[BenchmarkCase]
    error: str | None = None


class ModelStatus(BaseModel):
    vision_ready: bool
    ollama_ready: bool
    ollama_model: str
    setup_hint: str


class ParsedRequest(BaseModel):
    released_pieces: list[str] = Field(
        default_factory=list,
        description="Previously required pieces no longer mandatory; otherwise []",
    )
    query: str = Field(
        description="Desired style or occasion, without item restrictions"
    )
    count: int = Field(ge=1, le=3)
    required_pieces: list[str] = Field(
        description="Exact garment descriptions explicitly requested; otherwise []"
    )
    avoided_pieces: list[str] = Field(
        description="Exact garment descriptions explicitly banned; otherwise []"
    )
    allowed_pieces: list[str] = Field(
        description="Earlier bans explicitly lifted; otherwise []"
    )
    replacement_category: str = Field(
        description="Garment category to replace; empty string unless replacing a role in an outfit"
    )
    outfit_number: int = Field(
        ge=0,
        le=3,
        description="Referenced option number; 0 unless an option is referenced",
    )
    start_over: bool = Field(
        description="True only if user explicitly asks to start fresh"
    )
