from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.chat.service import ask
from app.db import get_db
from app.models import Message, User
from app.schemas import ChatRequest, ChatResponse, MessageOut

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    return ask(db, current_user.id, payload.message)


@router.get("/history", response_model=list[MessageOut])
def history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Message]:
    rows = (
        db.execute(
            select(Message).where(Message.user_id == current_user.id).order_by(Message.created_at.asc())
        )
        .scalars()
        .all()
    )
    return rows
