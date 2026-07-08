import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChatRequest(BaseModel):
    message: str


class SqlCitation(BaseModel):
    company: str
    ticker: str
    year: int
    revenue: int | None = None
    gross_profit: int | None = None
    operating_income: int | None = None
    net_income: int | None = None


class VectorCitation(BaseModel):
    source: str
    page: int | None = None
    page_label: str | None = None
    snippet: str


class Citations(BaseModel):
    sql: list[SqlCitation] = []
    vector: list[VectorCitation] = []


class ChatResponse(BaseModel):
    answer: str
    citations: Citations


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    citations: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
