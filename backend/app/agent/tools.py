from langchain_core.tools import tool
from sqlalchemy import text

from app.agent.aliases import resolve_sql_company, resolve_vector_source
from app.agent.vector_client import embed_query, get_index
from app.db import engine

FINANCIALS_COLUMNS = "company, ticker, sector, year, revenue, gross_profit, operating_income, net_income"


def _get_financials(companies: list[str] | None, years: list[int] | None) -> dict:
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

    found_names = {row["company"].lower() for row in rows} | {row["ticker"].lower() for row in rows}
    not_found = [c for c in (companies or []) if resolve_sql_company(c).lower() not in found_names]

    return {"rows": rows, "not_found": not_found}


def _vector_search(query: str, companies: list[str] | None, top_k: int) -> dict:
    source_filter = None
    unavailable: list[str] = []

    if companies:
        sources = []
        for company in companies:
            source = resolve_vector_source(company)
            if source:
                sources.append(source)
            else:
                unavailable.append(company)
        if sources:
            source_filter = {"source": {"$in": sources}}
        else:
            # None of the requested companies have any 10-K filing indexed at all.
            return {"matches": [], "unavailable_companies": unavailable}

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
    return {"matches": matches, "unavailable_companies": unavailable}


@tool
def get_financials(companies: list[str] | None = None, years: list[int] | None = None) -> dict:
    """Look up structured income-statement figures (revenue, gross_profit, operating_income,
    net_income) from the financial_data SQL table. `companies` accepts company names or
    tickers (e.g. "Apple", "AAPL", "Google", "Facebook" all resolve correctly). `years`
    filters to specific fiscal years (2022-2025). Omit either argument to fetch all rows
    for that dimension. Always call this before stating any dollar figure or growth
    percentage. If a requested company is not found, it is listed under "not_found" —
    report that explicitly rather than guessing numbers for it.
    """
    return _get_financials(companies, years)


@tool
def vector_search(query: str, companies: list[str] | None = None, top_k: int = 5) -> dict:
    """Search the 10-K filing text (qualitative/strategy content) for the most relevant
    chunks matching `query`. Only four companies have any 10-K text indexed at all: Apple,
    Amazon, Alphabet (aka Google), and Meta (aka Facebook). `companies` filters results to
    those company's filing(s) only; omit it to search across all indexed filings. If a
    requested company has no 10-K indexed, it is listed under "unavailable_companies" —
    you MUST report that no filing text is available for it rather than inventing an
    explanation.
    """
    return _vector_search(query, companies, top_k)
