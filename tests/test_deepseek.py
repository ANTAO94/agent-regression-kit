import json
import os
import unittest
from unittest.mock import patch

from agent_regression import DeepSeekAPIError, record_deepseek_tool_run


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
            },
        },
    }
]


class FakeTransport:
    def __init__(self):
        self.requests = []

    def __call__(self, url, api_key, payload, timeout):
        self.requests.append((url, api_key, payload, timeout))
        if len(self.requests) == 1:
            return {
                "id": "response-tool",
                "model": "deepseek-flash",
                "usage": {"prompt_tokens": 30, "completion_tokens": 8, "total_tokens": 38},
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "deepseek-call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "get_order",
                                        "arguments": '{"order_id":"123"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        return {
            "id": "response-final",
            "model": "deepseek-flash",
            "usage": {"prompt_tokens": 60, "completion_tokens": 12, "total_tokens": 72},
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"order_id":"123","order_status":"not_shipped"}',
                    }
                }
            ],
        }


def record(transport, *, api_key="test-secret"):
    return record_deepseek_tool_run(
        "查询订单 123",
        run_id="deepseek-test",
        system_prompt="Call the tool, then return JSON.",
        tools=TOOLS,
        tool_handlers={
            "get_order": lambda order_id: {"order_id": order_id, "status": "not_shipped"}
        },
        claims_extractor=lambda content: {
            "order_id": json.loads(content)["order_id"],
            "order_status": json.loads(content)["order_status"],
        },
        api_key=api_key,
        force_first_tool="get_order",
        transport=transport,
    )


class DeepSeekIntegrationTests(unittest.TestCase):
    def test_live_shape_records_tool_loop_without_recording_secret(self):
        transport = FakeTransport()
        trace = record(transport)

        self.assertEqual(
            ["tool_call", "tool_result", "final_answer"],
            [event["type"] for event in trace.events],
        )
        self.assertEqual({"order_id": "123"}, trace.events[0]["arguments"])
        self.assertEqual("not_shipped", trace.events[-1]["claims"]["order_status"])
        self.assertNotIn("test-secret", json.dumps(trace.to_dict()))
        self.assertEqual("https://api.deepseek.com/chat/completions", transport.requests[0][0])
        self.assertEqual({"type": "disabled"}, transport.requests[0][2]["thinking"])
        self.assertEqual("none", transport.requests[1][2]["tool_choice"])
        self.assertEqual({"type": "json_object"}, transport.requests[1][2]["response_format"])

    def test_key_can_be_loaded_from_environment(self):
        transport = FakeTransport()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "environment-secret"}):
            trace = record_deepseek_tool_run(
                "查询订单 123",
                run_id="environment-key",
                system_prompt="Call the tool, then return JSON.",
                tools=TOOLS,
                tool_handlers={"get_order": lambda order_id: {"order_id": order_id}},
                claims_extractor=lambda content: json.loads(content),
                force_first_tool="get_order",
                transport=transport,
            )
        self.assertEqual("environment-secret", transport.requests[0][1])
        self.assertNotIn("environment-secret", json.dumps(trace.to_dict()))

    def test_missing_key_fails_before_network(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "DEEPSEEK_API_KEY"):
                record(FakeTransport(), api_key=None)

    def test_unknown_tool_is_rejected(self):
        transport = FakeTransport()
        response = transport(None, None, None, None)
        response["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "refund"

        def send(*args):
            return response

        with self.assertRaisesRegex(DeepSeekAPIError, "unknown tool"):
            record(send)

    def test_required_tool_cannot_be_skipped(self):
        def send(*args):
            return {
                "model": "deepseek-flash",
                "choices": [
                    {"message": {"role": "assistant", "content": '{"answer":"guess"}'}}
                ],
            }

        with self.assertRaisesRegex(DeepSeekAPIError, "did not call required tool"):
            record(send)


if __name__ == "__main__":
    unittest.main()
