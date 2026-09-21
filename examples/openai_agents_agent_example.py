"""Real OpenAI Agents SDK loop with a deterministic local model."""

import json
from pathlib import Path

from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

from agent_regression import trace_from_openai_agents_result


class DeterministicModel(Model):
    def __init__(self):
        self.turn = 0

    async def get_response(self, *args, **kwargs):
        del args, kwargs
        self.turn += 1
        if self.turn == 1:
            output = [ResponseFunctionToolCall(
                id="item-1", call_id="openai-call-1", type="function_call",
                name="get_order", arguments='{"order_id":"123"}',
            )]
        else:
            output = [ResponseOutputMessage(
                id="message-1", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text="Order 123 is paid", annotations=[], logprobs=[])],
            )]
        return ModelResponse(output=output, usage=Usage(), response_id=None)

    async def stream_response(self, *args, **kwargs):
        del args, kwargs
        if False:
            yield None


@function_tool
def get_order(order_id: str) -> str:
    """Return a deterministic order fixture."""
    return json.dumps({"order_id": order_id, "status": "paid"})


def extract_claims(output: str) -> dict[str, str]:
    """Extract the business claim from the Agent's actual final output."""
    return {"order_status": "paid" if "paid" in output.lower() else "unknown"}


set_tracing_disabled(True)
request = "Look up order 123"
result = Runner.run_sync(Agent(name="Order agent", model=DeterministicModel(), tools=[get_order]), request)
trace = trace_from_openai_agents_result(
    result,
    request,
    run_id="openai-agents-order",
    identity={"name": "order-agent", "version": "1.0.0", "framework": "openai-agents"},
    claims_extractor=extract_claims,
)
destination = Path("work/openai-agents.trace.json")
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(trace.to_dict(), indent=2) + "\n", encoding="utf-8")
print(destination)
