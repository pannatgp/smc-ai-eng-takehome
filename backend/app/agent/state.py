from typing import TypedDict

from langchain_core.messages import BaseMessage


class GraphState(TypedDict, total=False):
    # input
    question: str
    history: list[BaseMessage]

    # set by extract_node
    companies: list[str]
    years: list[int]
    needs_financials: bool
    needs_qualitative: bool
    needs_growth: bool
    growth_metric: str
    search_query: str

    # set by sql_node
    sql_rows: list[dict]
    not_found: list[str]
    growth: list[dict]
    growth_leader: dict | None

    # set by vector_node
    vector_matches: list[dict]
    filing_companies: list[str]
    unavailable_companies: list[str]

    # set by synthesize_node
    answer: str
