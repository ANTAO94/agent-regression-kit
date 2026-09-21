"""Real PydanticAI runtime with a deterministic local model."""

import json
from pathlib import Path

from pydantic_ai import Agent, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from agent_regression import trace_from_pydantic_ai_result


def get_order(order_id: str) -> dict:
    """Return a deterministic order fixture."""
    return {"order_id": order_id, "status": "paid"}


def extract_claims(output: str) -> dict[str, str]:
    """Extract the business claim from the Agent's actual final output."""
    return {"order_status": "paid" if "paid" in output.lower() else "unknown"}


def model(messages, info):
    del info
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("get_order", {"order_id": "123"})])
    return ModelResponse(parts=[TextPart("Order 123 is paid")])


agent = Agent(FunctionModel(model), tools=[get_order])
result = agent.run_sync("Look up order 123")
trace = trace_from_pydantic_ai_result(
    result,
    "Look up order 123",
    run_id="pydantic-ai-order",
    identity={"name": "order-agent", "version": "1.0.0", "framework": "pydantic-ai"},
    claims_extractor=extract_claims,
)
destination = Path("work/pydantic-ai.trace.json")
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
print(destination)
