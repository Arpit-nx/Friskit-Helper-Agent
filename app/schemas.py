# class ChatResponse(BaseModel):
#     answer: str
#     status: str

#     page_context: dict | None = None
#     guide_available: bool = False

#     sources: list[dict] = Field(default_factory=list)
#     retrieval: dict | None = None
#     trace: list[dict] = Field(default_factory=list)

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    current_page: str | None = None


class ChatResponse(BaseModel):
    answer: str
    steps: list[str] = Field(default_factory=list)
    id: str | None = None
