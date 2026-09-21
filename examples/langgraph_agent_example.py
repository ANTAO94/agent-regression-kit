"""Real LangGraph tool loop with a deterministic model node."""

import json
import os
from pathlib import Path

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent_regression import trace_from_langgraph_result


@tool
def get_order(order_id: str) -> dict:
    """Return a deterministic order fixture."""
    return {"order_id": order_id, "status": "paid"}


def extract_claims(output: str) -> dict[str, str]:
    """Extract the business claim from the Agent's actual final output."""
    return {"order_status": "paid" if "paid" in output.lower() else "unknown"}


def model_node(state: MessagesState):
    if not any(getattr(message, "type", "") == "tool" for message in state["messages"]):
        return {"messages": [AIMessage(content="", tool_calls=[{
            "name": "get_order",
            "args": {"order_id": os.environ.get("AGENT_TOOL_ORDER_ID", "123")},
            "id": "langgraph-call-1",
            "type": "tool_call",
        }])]}
    return {"messages": [AIMessage(content="Order 123 is paid")]}


builder = StateGraph(MessagesState)
builder.add_node("agent", model_node)
builder.add_node("tools", ToolNode([get_order]))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
graph = builder.compile()
request = "Look up order 123"
result = graph.invoke({"messages": [("user", request)]})
trace = trace_from_langgraph_result(
    result,
    request,
    run_id="langgraph-order",
    identity={"name": "order-agent", "version": "1.0.0", "framework": "langgraph"},
    claims_extractor=extract_claims,
)
destination = Path(os.environ.get("AGENT_TRACE_OUT", "work/langgraph.trace.json"))
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
print(destination)
