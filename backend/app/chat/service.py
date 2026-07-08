import uuid

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.graph import compiled_graph
from app.models import Message
from app.schemas import ChatResponse, Citations, SqlCitation, VectorCitation

HISTORY_LIMIT = 20


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


def _flatten_citations(raw_citations: list[dict]) -> Citations:
    sql_rows: list[SqlCitation] = []
    seen_sql: set[tuple] = set()
    vector_matches: list[VectorCitation] = []
    seen_vector: set[tuple] = set()

    for entry in raw_citations:
        if entry["type"] == "sql":
            for row in entry["data"]:
                key = (row["company"], row["year"])
                if key in seen_sql:
                    continue
                seen_sql.add(key)
                sql_rows.append(SqlCitation(**row))
        elif entry["type"] == "vector":
            for match in entry["data"]:
                key = (match["source"], match.get("page"))
                if key in seen_vector:
                    continue
                seen_vector.add(key)
                vector_matches.append(VectorCitation(**match))

    return Citations(sql=sql_rows, vector=vector_matches)


def ask(db: Session, user_id: uuid.UUID, question: str) -> ChatResponse:
    history = _load_history(db, user_id)
    result = compiled_graph.invoke({"messages": [*history, HumanMessage(content=question)], "citations": []})

    answer = result["messages"][-1].content
    citations = _flatten_citations(result["citations"])

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
