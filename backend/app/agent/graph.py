import json

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState
from app.agent.tools import get_financials, vector_search
from app.config import settings

TOOLS = [get_financials, vector_search]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.openai_api_key).bind_tools(TOOLS)


def call_agent(state: AgentState) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
    response = _llm.invoke(messages)
    return {"messages": [response]}


def call_tools(state: AgentState) -> dict:
    last_message = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    new_citations: list[dict] = []

    for tool_call in last_message.tool_calls:
        tool_fn = TOOLS_BY_NAME[tool_call["name"]]
        result = tool_fn.invoke(tool_call["args"])
        tool_messages.append(
            ToolMessage(content=json.dumps(result, default=str), tool_call_id=tool_call["id"])
        )
        if tool_call["name"] == "get_financials":
            new_citations.append({"type": "sql", "data": result.get("rows", [])})
        elif tool_call["name"] == "vector_search":
            new_citations.append({"type": "vector", "data": result.get("matches", [])})

    return {"messages": tool_messages, "citations": new_citations}


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", call_agent)
    graph.add_node("tools", call_tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


compiled_graph = build_graph()
