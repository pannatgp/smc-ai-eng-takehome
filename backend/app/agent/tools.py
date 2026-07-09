"""Data-access functions for the graph nodes.

These are plain functions (not LLM-bound tools): the graph orchestrates them
deterministically. `query_financials` builds a parameterized SQL query itself — no
text-to-SQL — so there is no injection surface and no hallucinated columns.
"""

from sqlalchemy import text

from app.agent.aliases import resolve_sql_company
from app.agent.vector_client import embed_query, get_index
from app.db import engine
from app.registry import resolve_source

FINANCIALS_COLUMNS = "company, ticker, sector, year, revenue, gross_profit, operating_income, net_income"


def query_financials(companies: list[str] | None, years: list[int] | None) -> dict:
    """Look up income-statement figures from the financial_data table.

    Returns {"rows": [...], "not_found": [companies with no row]}.
    """
    resolved = [resolve_sql_company(c) for c in companies] if companies else None

    sql = f"SELECT {FINANCIALS_COLUMNS} FROM financial_data WHERE 1=1"
    params: dict = {}
    if resolved:
        sql += " AND (lower(company) = ANY(:names) OR lower(ticker) = ANY(:names))"
        params["names"] = [name.lower() for name in resolved]
    if years:
        sql += " AND year = ANY(:years)"
        params["years"] = years
    sql += " ORDER BY company, year"

    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    found = {row["company"].lower() for row in rows} | {row["ticker"].lower() for row in rows}
    not_found = [c for c in (companies or []) if resolve_sql_company(c).lower() not in found]

    return {"rows": rows, "not_found": not_found}


def search_filings(query: str, company: str | None = None, top_k: int = 3) -> dict:
    """Semantic search over 10-K text. If `company` is given, filter to its filing.

    Returns {"matches": [...], "available": bool}. `available` is False when a specific
    company was requested but has no filing in the vector store.
    """
    source_filter = None
    if company is not None:
        source = resolve_source(company)
        if source is None:
            return {"matches": [], "available": False}
        source_filter = {"source": {"$in": [source]}}

    index = get_index()
    vector = embed_query(query)
    result = index.query(
        namespace="__default__",
        vector=vector,
        top_k=top_k,
        include_metadata=True,
        filter=source_filter,
    )

    matches = [
        {
            "source": match["metadata"]["source"],
            "page": match["metadata"].get("page"),
            "page_label": match["metadata"].get("page_label"),
            "snippet": match["metadata"]["text"][:800],
            "score": match["score"],
        }
        for match in result["matches"]
    ]
    return {"matches": matches, "available": True}
