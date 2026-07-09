import uuid

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph import compiled_graph
from app.models import Message
from app.schemas import ChatResponse, Citations, SqlCitation, VectorCitation

HISTORY_LIMIT = 20

_SQL_FIELDS = ("company", "ticker", "year", "revenue", "gross_profit", "operating_income", "net_income")
_VECTOR_FIELDS = ("source", "page", "page_label", "snippet")


def _load_history(db: Session, user_id: uuid.UUID) -> list:
    rows = (
        db.execute(
            select(Message)
            .where(Message.user_id == user_id)
            .order_by(Message.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
        .scalars()
        .all()
    )
    rows.reverse()

    messages = []
    for row in rows:
        if row.role == "user":
            messages.append(HumanMessage(content=row.content))
        else:
            messages.append(AIMessage(content=row.content))
    return messages


def _build_citations(sql_rows: list[dict], vector_matches: list[dict]) -> Citations:
    sql_citations: list[SqlCitation] = []
    seen_sql: set[tuple] = set()
    for row in sql_rows:
        key = (row["company"], row["year"])
        if key in seen_sql:
            continue
        seen_sql.add(key)
        sql_citations.append(SqlCitation(**{k: row.get(k) for k in _SQL_FIELDS}))

    vector_citations: list[VectorCitation] = []
    seen_vector: set[tuple] = set()
    for match in vector_matches:
        key = (match["source"], match.get("page"))
        if key in seen_vector:
            continue
        seen_vector.add(key)
        vector_citations.append(VectorCitation(**{k: match.get(k) for k in _VECTOR_FIELDS}))

    return Citations(sql=sql_citations, vector=vector_citations)


def ask(db: Session, user_id: uuid.UUID, question: str) -> ChatResponse:
    history = _load_history(db, user_id)
    result = compiled_graph.invoke({"question": question, "history": history})

    answer = result["answer"]
    citations = _build_citations(result.get("sql_rows", []), result.get("vector_matches", []))

    db.add(Message(user_id=user_id, role="user", content=question))
    db.add(
        Message(
            user_id=user_id,
            role="assistant",
            content=answer,
            citations=citations.model_dump(),
        )
    )
    db.commit()

    return ChatResponse(answer=answer, citations=citations)
