"""Deterministic retrieval graph.

Instead of letting the LLM freely decide tool calls, the graph orchestrates a fixed flow
with conditional edges. The LLM is used only at the edges — to extract search parameters
and to phrase the final answer — while routing, the "which companies have a filing" gate,
and the growth arithmetic are done in code. This makes the anti-hallucination behaviour a
property of the control flow, not of prompt adherence.

    extract ─▶ [needs_financials?] ─▶ sql ─▶ [needs_qualitative?] ─▶ vector ─▶ synthesize
              └▶ (qualitative only) ─▶ vector ─┘        └▶ synthesize ─┘
"""

from collections import defaultdict
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agent.prompts import EXTRACT_PROMPT, SYNTHESIZE_PROMPT
from app.agent.state import GraphState
from app.agent.tools import query_financials, search_filings
from app.config import settings

MODEL = "gpt-4o-mini"


class ExtractedQuery(BaseModel):
    companies: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    needs_financials: bool = True
    needs_qualitative: bool = False
    needs_growth: bool = False
    growth_metric: Literal["revenue", "net_income", "gross_profit", "operating_income"] = "revenue"
    search_query: str = ""


_extractor = ChatOpenAI(model=MODEL, temperature=0, api_key=settings.openai_api_key).with_structured_output(
    ExtractedQuery
)
_synthesizer = ChatOpenAI(model=MODEL, temperature=0, api_key=settings.openai_api_key)


# --- nodes ---------------------------------------------------------------------------


def extract_node(state: GraphState) -> dict:
    messages = [SystemMessage(content=EXTRACT_PROMPT), *state.get("history", []), HumanMessage(content=state["question"])]
    q: ExtractedQuery = _extractor.invoke(messages)
    return {
        "companies": q.companies,
        "years": q.years,
        "needs_financials": q.needs_financials,
        "needs_qualitative": q.needs_qualitative,
        "needs_growth": q.needs_growth,
        "growth_metric": q.growth_metric,
        "search_query": q.search_query or state["question"],
    }


def sql_node(state: GraphState) -> dict:
    result = query_financials(state.get("companies"), state.get("years"))
    out: dict = {"sql_rows": result["rows"], "not_found": result["not_found"]}
    if state.get("needs_growth"):
        growth = _compute_growth(result["rows"], state.get("growth_metric", "revenue"))
        out["growth"] = growth
        out["growth_leader"] = max(growth, key=lambda g: g["growth_pct"]) if growth else None
    return out


def vector_node(state: GraphState) -> dict:
    companies = state.get("companies") or []
    query = state.get("search_query") or state["question"]
    matches: list[dict] = []
    filers: list[str] = []
    unavailable: list[str] = []

    if companies:
        # Deterministic Big-N gate: each requested company is either a filer (search it) or
        # not (record it as unavailable). No LLM judgement involved.
        for company in companies:
            result = search_filings(query, company=company, top_k=3)
            if result["available"]:
                filers.append(company)
                matches.extend(result["matches"])
            else:
                unavailable.append(company)
    else:
        matches.extend(search_filings(query, company=None, top_k=5)["matches"])

    return {"vector_matches": matches, "filing_companies": filers, "unavailable_companies": unavailable}


def synthesize_node(state: GraphState) -> dict:
    context = _build_context(state)
    user = f"{state['question']}\n\n----- DATA CONTEXT -----\n{context}"
    messages = [SystemMessage(content=SYNTHESIZE_PROMPT), *state.get("history", []), HumanMessage(content=user)]
    response = _synthesizer.invoke(messages)
    return {"answer": response.content}


# --- routing -------------------------------------------------------------------------


def route_after_extract(state: GraphState) -> Literal["sql", "vector", "synthesize"]:
    if state.get("needs_financials", True):
        return "sql"
    if state.get("needs_qualitative"):
        return "vector"
    return "synthesize"


def route_after_sql(state: GraphState) -> Literal["vector", "synthesize"]:
    return "vector" if state.get("needs_qualitative") else "synthesize"


# --- helpers -------------------------------------------------------------------------


def _compute_growth(rows: list[dict], metric: str) -> list[dict]:
    """Growth over the full year span per company (earliest -> latest), computed in Python."""
    by_company: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_company[row["company"]].append(row)

    growth: list[dict] = []
    for company, company_rows in by_company.items():
        company_rows.sort(key=lambda r: r["year"])
        first, last = company_rows[0], company_rows[-1]
        start, end = first.get(metric), last.get(metric)
        if first["year"] == last["year"] or not start or not end:
            continue
        growth.append(
            {
                "company": company,
                "metric": metric,
                "from_year": first["year"],
                "to_year": last["year"],
                "from_value": start,
                "to_value": end,
                "growth_pct": round((end - start) / start * 100, 2),
            }
        )
    return growth


def _money(value: int | None) -> str:
    return f"${value:,}" if value is not None else "N/A"


def _build_context(state: GraphState) -> str:
    parts: list[str] = []

    rows = state.get("sql_rows") or []
    if rows:
        lines = ["=== FINANCIAL DATA (the only source for numbers) ==="]
        for r in rows:
            lines.append(
                f"{r['company']} ({r['ticker']}) {r['year']}: revenue={_money(r['revenue'])}, "
                f"gross_profit={_money(r['gross_profit'])}, operating_income={_money(r['operating_income'])}, "
                f"net_income={_money(r['net_income'])}"
            )
        parts.append("\n".join(lines))

    not_found = state.get("not_found") or []
    if not_found:
        parts.append("=== NOT FOUND IN FINANCIAL DATA ===\n" + ", ".join(not_found))

    growth = state.get("growth") or []
    if growth:
        lines = ["=== COMPUTED GROWTH (exact; use as-is, do not recompute) ==="]
        for g in growth:
            lines.append(
                f"{g['company']}: {g['metric']} {g['from_year']}->{g['to_year']}: "
                f"{_money(g['from_value'])} -> {_money(g['to_value'])} = {g['growth_pct']:+.2f}%"
            )
        leader = state.get("growth_leader")
        if leader:
            lines.append(f"Highest growth: {leader['company']} ({leader['growth_pct']:+.2f}%)")
        parts.append("\n".join(lines))

    matches = state.get("vector_matches") or []
    if matches:
        lines = ["=== 10-K EXCERPTS (the only source for qualitative 'why'/strategy) ==="]
        for m in matches:
            lines.append(f"[{m['source']}, page {m.get('page')}] {m['snippet']}")
        parts.append("\n".join(lines))

    unavailable = state.get("unavailable_companies") or []
    if unavailable:
        parts.append(
            "=== NO 10-K FILING AVAILABLE (state plainly; do NOT invent factors) ===\n"
            + ", ".join(unavailable)
        )

    return "\n\n".join(parts) if parts else "(No data was retrieved for this question.)"


# --- assembly ------------------------------------------------------------------------


def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("extract", extract_node)
    graph.add_node("sql", sql_node)
    graph.add_node("vector", vector_node)
    graph.add_node("synthesize", synthesize_node)

    graph.add_edge(START, "extract")
    graph.add_conditional_edges(
        "extract", route_after_extract, {"sql": "sql", "vector": "vector", "synthesize": "synthesize"}
    )
    graph.add_conditional_edges("sql", route_after_sql, {"vector": "vector", "synthesize": "synthesize"})
    graph.add_edge("vector", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


compiled_graph = build_graph()
