import unittest

from agent_regression import (
    trace_from_langgraph_events,
    trace_from_langgraph_result,
    trace_from_openai_agents_result,
    trace_from_pydantic_ai_result,
)


class ToolCallPart:
    def __init__(self, name, args, call_id):
        self.tool_name = name
        self.args = args
        self.tool_call_id = call_id


class ToolReturnPart:
    def __init__(self, content, call_id):
        self.content = content
        self.tool_call_id = call_id


class ModelMessage:
    def __init__(self, parts):
        self.parts = parts


class PydanticResult:
    output = {"order_status": "paid"}

    def all_messages(self):
        return [
            ModelMessage([ToolCallPart("get_order", {"order_id": "123"}, "pyd-1")]),
            ModelMessage([ToolReturnPart({"status": "paid"}, "pyd-1")]),
        ]


class ToolCallItem:
    def __init__(self):
        self.raw_item = {
            "name": "get_order",
            "arguments": '{"order_id":"123"}',
            "call_id": "oa-1",
        }


class ToolCallOutputItem:
    def __init__(self):
        self.raw_item = {"call_id": "oa-1"}
        self.output = '{"status":"paid"}'


class OpenAIResult:
    new_items = [ToolCallItem(), ToolCallOutputItem()]
    final_output = "Order 123 is paid"


class AIMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class ToolMessage:
    def __init__(self, content, call_id):
        self.content = content
        self.tool_call_id = call_id


class FrameworkIntegrationTests(unittest.TestCase):
    def test_pydantic_ai_result_becomes_a_valid_trace(self):
        trace = trace_from_pydantic_ai_result(
            PydanticResult(), {"order_id": "123"}, run_id="pydantic"
        )
        self.assertEqual("get_order", trace.events[0]["tool"])
        self.assertEqual("paid", trace.events[-1]["claims"]["order_status"])

    def test_openai_agents_result_becomes_a_valid_trace(self):
        trace = trace_from_openai_agents_result(
            OpenAIResult(),
            "lookup order 123",
            run_id="openai",
            claims_extractor=lambda output: {"order_status": "paid"},
        )
        self.assertEqual({"order_id": "123"}, trace.events[0]["arguments"])
        self.assertEqual({"status": "paid"}, trace.events[1]["result"])

    def test_langgraph_message_state_becomes_a_valid_trace(self):
        result = {
            "messages": [
                AIMessage(
                    tool_calls=[
                        {"name": "get_order", "args": {"order_id": "123"}, "id": "lg-1"}
                    ]
                ),
                ToolMessage('{"status":"paid"}', "lg-1"),
                AIMessage("Order 123 is paid"),
            ]
        }
        trace = trace_from_langgraph_result(
            result,
            "lookup order 123",
            run_id="langgraph",
            claims_extractor=lambda output: {"order_status": "paid"},
        )
        self.assertEqual(
            ["tool_call", "tool_result", "final_answer"],
            [e["type"] for e in trace.events],
        )
        self.assertEqual("Order 123 is paid", trace.events[-1]["text"])

    def test_langgraph_event_stream_records_tools_hidden_from_message_state(self):
        events = [
            {
                "event": "on_tool_start",
                "name": "web_search",
                "run_id": "tool-run-1",
                "data": {"input": {}},
                "metadata": {"langgraph_node": "research"},
            },
            {
                "event": "on_tool_end",
                "name": "web_search",
                "run_id": "tool-run-1",
                "data": {"input": None, "output": "result"},
            },
        ]
        trace = trace_from_langgraph_events(
            events,
            {"summary": "done"},
            "research LangGraph",
            run_id="langgraph-events",
            claims_extractor=lambda output: {"summary": output["summary"]},
        )
        self.assertEqual(
            ["tool_call", "tool_result", "final_answer"],
            [e["type"] for e in trace.events],
        )
        self.assertEqual("web_search", trace.events[0]["tool"])
        self.assertEqual({}, trace.events[0]["arguments"])
        self.assertEqual("result", trace.events[1]["result"])
        self.assertEqual({"summary": "done"}, trace.events[-1]["claims"])

    def test_langgraph_event_stream_records_tool_errors(self):
        trace = trace_from_langgraph_events(
            [
                {
                    "event": "on_tool_start",
                    "name": "web_search",
                    "run_id": "tool-run-2",
                    "data": {"input": "query"},
                },
                {
                    "event": "on_tool_error",
                    "name": "web_search",
                    "run_id": "tool-run-2",
                    "data": {"error": "upstream unavailable"},
                },
            ],
            "fallback",
            "research LangGraph",
            run_id="langgraph-error-events",
        )
        self.assertTrue(trace.events[1]["is_error"])
        self.assertEqual("upstream unavailable", trace.events[1]["error"])


if __name__ == "__main__":
    unittest.main()
