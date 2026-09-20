"""Minimal DeepSeek tool-Agent integration with no third-party dependency."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .framework import FrameworkTraceRecorder
from .model import AgentTrace
from .redaction import RedactionPolicy


JsonTransport = Callable[[str, str, Mapping[str, Any], float], Mapping[str, Any]]
ClaimsExtractor = Callable[[str], Mapping[str, Any]]


class DeepSeekAPIError(RuntimeError):
    """Raised when DeepSeek returns invalid data or the request fails."""


def _post_json(
    url: str,
    api_key: str,
    payload: Mapping[str, Any],
    timeout: float,
) -> Mapping[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise DeepSeekAPIError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DeepSeekAPIError(f"DeepSeek request failed: {type(exc).__name__}") from exc
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DeepSeekAPIError("DeepSeek returned invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise DeepSeekAPIError("DeepSeek response must be an object")
    return value


def _message(response: Mapping[str, Any]) -> Mapping[str, Any]:
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise DeepSeekAPIError("DeepSeek response must contain exactly one choice")
    choice = choices[0]
    if not isinstance(choice, Mapping) or not isinstance(choice.get("message"), Mapping):
        raise DeepSeekAPIError("DeepSeek response choice is missing a message")
    return choice["message"]


def _tool_catalog(tools: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    catalog: dict[str, Mapping[str, Any]] = {}
    for tool in tools:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        name = function.get("name") if isinstance(function, Mapping) else None
        if tool.get("type") != "function" or not isinstance(name, str) or not name:
            raise ValueError("DeepSeek tools must be named function definitions")
        if name in catalog:
            raise ValueError(f"duplicate DeepSeek tool name {name!r}")
        catalog[name] = tool
    if not catalog:
        raise ValueError("at least one DeepSeek tool is required")
    return catalog


def record_deepseek_tool_run(
    request: str,
    *,
    run_id: str,
    system_prompt: str,
    tools: Sequence[Mapping[str, Any]],
    tool_handlers: Mapping[str, Callable[..., Any]],
    claims_extractor: ClaimsExtractor,
    api_key: str | None = None,
    model: str = "deepseek-flash",
    base_url: str = "https://api.deepseek.com",
    force_first_tool: str | None = None,
    required_tool_sequence: Sequence[str] = (),
    max_tokens: int = 96,
    max_rounds: int = 4,
    timeout: float = 30.0,
    redaction_policy: RedactionPolicy | None = None,
    transport: JsonTransport | None = None,
) -> AgentTrace:
    """Run one credential-gated DeepSeek Agent loop and return validated evidence.

    The API key is read from ``DEEPSEEK_API_KEY`` when omitted and is never
    copied into the Trace. Thinking mode is disabled to keep tool forcing
    available and minimize paid output tokens. ``required_tool_sequence`` can
    force a deterministic multi-tool path while still leaving argument
    generation and cross-step data propagation to the model.
    """

    active_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not isinstance(active_key, str) or not active_key.strip():
        raise ValueError("DEEPSEEK_API_KEY is required")
    active_key = active_key.strip()
    if not isinstance(request, str) or not request:
        raise ValueError("DeepSeek request must be a non-empty string")
    if not isinstance(system_prompt, str) or not system_prompt:
        raise ValueError("DeepSeek system_prompt must be a non-empty string")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
        raise ValueError("DeepSeek max_tokens must be a positive integer")
    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1:
        raise ValueError("DeepSeek max_rounds must be a positive integer")
    catalog = _tool_catalog(tools)
    if set(catalog) != set(tool_handlers):
        raise ValueError("DeepSeek tool definitions and handlers must have the same names")
    if force_first_tool is not None and force_first_tool not in catalog:
        raise ValueError("force_first_tool must name a configured tool")
    sequence = tuple(required_tool_sequence)
    if force_first_tool is not None and sequence:
        raise ValueError("force_first_tool and required_tool_sequence are mutually exclusive")
    if any(not isinstance(name, str) or name not in catalog for name in sequence):
        raise ValueError("required_tool_sequence must contain configured tool names")
    if len(sequence) + 1 > max_rounds:
        raise ValueError("max_rounds must allow every required tool and a final answer")

    endpoint = base_url.rstrip("/") + "/chat/completions"
    send = transport or _post_json
    recorder = FrameworkTraceRecorder(
        {"name": "deepseek-tool-agent", "version": "1.0.0", "provider": "deepseek", "model": model},
        run_id=run_id,
        request=request,
        metadata={"provider": {"name": "deepseek", "model": model, "live": transport is None}},
        redaction_policy=redaction_policy,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request},
    ]
    executed_tool = False
    executed_tool_names: list[str] = []

    for round_number in range(1, max_rounds + 1):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": list(tools),
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
            "stream": False,
        }
        if len(executed_tool_names) < len(sequence):
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": sequence[len(executed_tool_names)]},
            }
        elif round_number == 1 and force_first_tool:
            payload["tool_choice"] = {
                "type": "function",
                "function": {"name": force_first_tool},
            }
        elif executed_tool:
            payload["tool_choice"] = "none"
            payload["response_format"] = {"type": "json_object"}

        response = send(endpoint, active_key, payload, timeout)
        message = _message(response)
        usage = response.get("usage") if isinstance(response.get("usage"), Mapping) else {}
        response_metadata = {
            "provider": "deepseek",
            "model": response.get("model", model),
            "response_id": response.get("id"),
            "usage": dict(usage),
            "round": round_number,
        }
        raw_calls = message.get("tool_calls") or []
        if raw_calls:
            if executed_tool and not sequence:
                raise DeepSeekAPIError("DeepSeek emitted another tool call after tool execution")
            if not isinstance(raw_calls, list):
                raise DeepSeekAPIError("DeepSeek tool_calls must be an array")
            if sequence and len(raw_calls) != 1:
                raise DeepSeekAPIError(
                    "DeepSeek must emit exactly one tool call for a required sequence step"
                )
            assistant_message = {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": raw_calls,
            }
            messages.append(assistant_message)
            for raw_call in raw_calls:
                function = raw_call.get("function") if isinstance(raw_call, Mapping) else None
                call_id = raw_call.get("id") if isinstance(raw_call, Mapping) else None
                name = function.get("name") if isinstance(function, Mapping) else None
                arguments_text = function.get("arguments") if isinstance(function, Mapping) else None
                if not isinstance(call_id, str) or not call_id:
                    raise DeepSeekAPIError("DeepSeek tool call is missing an ID")
                if name not in catalog:
                    raise DeepSeekAPIError(f"DeepSeek requested unknown tool {name!r}")
                if sequence:
                    sequence_index = len(executed_tool_names)
                    if sequence_index >= len(sequence) or name != sequence[sequence_index]:
                        expected = sequence[sequence_index] if sequence_index < len(sequence) else None
                        raise DeepSeekAPIError(
                            f"DeepSeek called {name!r}; expected required tool {expected!r}"
                        )
                try:
                    arguments = json.loads(arguments_text)
                except (TypeError, json.JSONDecodeError) as exc:
                    raise DeepSeekAPIError("DeepSeek tool arguments are not valid JSON") from exc
                if not isinstance(arguments, dict):
                    raise DeepSeekAPIError("DeepSeek tool arguments must be an object")
                recorder.tool_start(name, arguments, call_id=call_id, metadata=response_metadata)
                result = tool_handlers[name](**arguments)
                recorder.tool_end(call_id, result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(result, ensure_ascii=False, sort_keys=True),
                    }
                )
                executed_tool_names.append(name)
            executed_tool = True
            continue

        content = message.get("content")
        if force_first_tool and not executed_tool:
            raise DeepSeekAPIError(
                f"DeepSeek did not call required tool {force_first_tool!r}"
            )
        if sequence and len(executed_tool_names) != len(sequence):
            missing = sequence[len(executed_tool_names)]
            raise DeepSeekAPIError(f"DeepSeek did not call required tool {missing!r}")
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekAPIError("DeepSeek final answer is empty")
        claims = claims_extractor(content)
        if not isinstance(claims, Mapping):
            raise ValueError("claims_extractor must return an object")
        recorder.final_answer(content, claims, metadata=response_metadata)
        return recorder.finish()

    raise DeepSeekAPIError("DeepSeek Agent exceeded max_rounds without a final answer")
