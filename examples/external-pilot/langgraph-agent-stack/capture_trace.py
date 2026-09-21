"""Capture a real LangGraph event stream from langgraph-agent-stack.

This script is intentionally kept outside the candidate project. It proves
that an independently checked-out LangGraph application can feed its own
runtime events into Agent Regression Kit without changing its business graph.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

EXPECTED_CANDIDATE_COMMIT = "a8a2dac566d46c48619ba94c69dfffb1b370520d"


class _InstrumentedTool:
    """Capture the value crossing the real tool boundary before delegation."""

    def __init__(self, target: Any, calls: list[Any], replacement: str | None):
        self._target = target
        self._calls = calls
        self._replacement = replacement
        self.name = target.name

    def invoke(self, tool_input: Any, config: Any = None, **kwargs: Any) -> Any:
        forwarded = tool_input
        if self._replacement is not None:
            forwarded = self._replacement
        self._calls.append(forwarded)
        if config is None:
            return self._target.invoke(forwarded, **kwargs)
        return self._target.invoke(forwarded, config=config, **kwargs)


def _candidate_revision(project_dir: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if revision != EXPECTED_CANDIDATE_COMMIT:
        raise RuntimeError(
            "candidate checkout is not the reviewed commit "
            f"{EXPECTED_CANDIDATE_COMMIT}; got {revision}"
        )
    return revision


def _claims(output: Any) -> dict[str, Any]:
    """Derive regression claims from the candidate's actual research result."""
    if not isinstance(output, Mapping):
        raise ValueError("candidate final output must be an object")
    findings = output.get("findings", [])
    sources = output.get("sources", [])
    return {
        "summary_present": bool(output.get("summary")),
        "findings_count": len(findings) if isinstance(findings, list) else 0,
        "source_count": len(sources) if isinstance(sources, list) else 0,
        "confidence": output.get("confidence"),
    }


def _load_candidate(project_dir: Path) -> tuple[Any, Any, Any, Any, str]:
    """Load the candidate's runtime using its already-installed environment."""
    project_text = str(project_dir.resolve())
    if project_text not in sys.path:
        sys.path.insert(0, project_text)

    # This pilot is intentionally deterministic and offline. Force the
    # candidate's provider selection instead of inheriting a developer's
    # environment and accidentally making an API call.
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["SEARCH_PROVIDER"] = "mock"

    from agents.researcher import ResearchAgent
    from core.config import get_settings
    from core.llm import get_llm
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver

    get_settings.cache_clear()
    settings = get_settings()
    return (
        ResearchAgent,
        get_llm(settings.llm_config),
        HumanMessage,
        MemorySaver,
        _candidate_revision(project_dir),
    )


def _instrument_agent(
    agent: Any,
    observed_inputs: list[Any],
    *,
    skip_search: bool,
    replacement_query: str | None,
) -> None:
    original_tools = list(agent.tools)
    rewritten_tools: list[Any] = []
    search_found = False
    for tool in original_tools:
        if getattr(tool, "name", None) != "web_search":
            rewritten_tools.append(tool)
            continue
        search_found = True
        if not skip_search:
            rewritten_tools.append(
                _InstrumentedTool(tool, observed_inputs, replacement_query)
            )
    if not search_found:
        raise RuntimeError("candidate ResearchAgent has no web_search tool")
    agent.tools = rewritten_tools


def _inject_summary_confidence(agent: Any, confidence: float) -> dict[str, bool]:
    """Change the summariser response before the Agent interprets it."""
    original = agent._invoke_llm_with_retry
    state = {"applied": False}

    def wrapped(messages: Any, *args: Any, **kwargs: Any) -> Any:
        response = original(messages, *args, **kwargs)
        prompt = "\n".join(str(getattr(message, "content", "")) for message in messages)
        if not state["applied"] and "summaris" in prompt.lower():
            payload = json.loads(str(response.content))
            if not isinstance(payload, dict):
                raise RuntimeError("summary response was not a JSON object")
            payload["confidence"] = confidence
            response.content = json.dumps(payload)
            state["applied"] = True
        return response

    agent._invoke_llm_with_retry = wrapped
    return state


async def _capture(
    project_dir: Path,
    request: str,
    run_id: str,
    *,
    skip_search: bool = False,
    replacement_query: str | None = None,
    summary_confidence: float | None = None,
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any], list[Any], str]:
    (
        research_agent_cls,
        llm,
        human_message_cls,
        memory_saver_cls,
        revision,
    ) = _load_candidate(project_dir)
    agent = research_agent_cls(
        thread_id=run_id,
        llm=llm,
        # The pilot is one isolated process; an in-memory saver avoids creating
        # a candidate-project database as a side effect of evidence capture.
        checkpointer=memory_saver_cls(),
    )
    observed_inputs: list[Any] = []
    _instrument_agent(
        agent,
        observed_inputs,
        skip_search=skip_search,
        replacement_query=replacement_query,
    )
    injection_state = (
        _inject_summary_confidence(agent, summary_confidence)
        if summary_confidence is not None
        else None
    )
    initial_state = {
        "messages": [human_message_cls(content=request)],
        "context": {},
        "metadata": {},
        "step_count": 0,
        "status": "running",
    }
    config = {"configurable": {"thread_id": run_id}}
    events: list[Mapping[str, Any]] = []
    final_state: Mapping[str, Any] | None = None
    async for event in agent._graph.astream_events(
        initial_state,
        config=config,
        version="v2",
    ):
        events.append(event)
        if event.get("event") == "on_chain_end" and event.get("name") == "LangGraph":
            output = event.get("data", {}).get("output")
            if isinstance(output, Mapping):
                final_state = output
    if final_state is None:
        raise RuntimeError("candidate LangGraph stream did not emit a final state")
    context = final_state.get("context")
    if not isinstance(context, Mapping) or not isinstance(
        context.get("research_result"), Mapping
    ):
        raise RuntimeError("candidate final state has no context.research_result")
    if injection_state is not None and not injection_state["applied"]:
        raise RuntimeError("summary confidence injection was not applied")
    return events, context["research_result"], observed_inputs, revision


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a langgraph-agent-stack ResearchAgent into AgentTrace."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--request", default="What is LangGraph?")
    parser.add_argument("--run-id", default="langgraph-agent-stack-pilot")
    parser.add_argument(
        "--mutate-confidence",
        type=float,
        help="Change confidence after the Agent run; comparator-only demonstration.",
    )
    parser.add_argument(
        "--mutate-summary-confidence",
        type=float,
        help="Change the summariser response during Agent execution.",
    )
    parser.add_argument(
        "--mutate-search-query",
        metavar="QUERY",
        help="Replace every query at the real web_search boundary during execution.",
    )
    parser.add_argument(
        "--skip-search",
        action="store_true",
        help="Remove web_search from the Agent tool set during execution.",
    )
    parser.add_argument(
        "--vary-presentation",
        action="store_true",
        help="Change only final wording after claims are derived; claims-only should pass.",
    )
    args = parser.parse_args()
    if args.mutate_confidence is not None and args.mutate_summary_confidence is not None:
        parser.error("choose --mutate-confidence or --mutate-summary-confidence")

    # Import the kit after the candidate path is prepared, but keep the
    # candidate's `core` package ahead of it in sys.path for this process.
    from agent_regression import trace_from_langgraph_events

    events, final_output, observed_inputs, revision = asyncio.run(
        _capture(
            args.project_dir,
            args.request,
            args.run_id,
            skip_search=args.skip_search,
            replacement_query=args.mutate_search_query,
            summary_confidence=args.mutate_summary_confidence,
        )
    )
    output_for_trace = dict(final_output)
    if args.mutate_confidence is not None:
        output_for_trace["confidence"] = args.mutate_confidence
    trace = trace_from_langgraph_events(
        events,
        output_for_trace,
        args.request,
        run_id=args.run_id,
        tool_input_resolver=(
            lambda _event, ordinal: observed_inputs[ordinal - 1]
            if ordinal <= len(observed_inputs)
            else None
        ),
        identity={
            "name": "langgraph-agent-stack-research-agent",
            "version": f"0.7.0+git.{revision[:12]}",
            "framework": "langgraph",
            "source": "https://github.com/Brescou/langgraph-agent-stack",
            "source_revision": revision,
        },
        claims_extractor=_claims,
    )
    if args.vary_presentation:
        trace.events[-1]["text"] = "Reviewed wording: " + trace.events[-1]["text"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "event_count": len(events),
                "tool_call_count": sum(
                    1 for event in trace.events if event["type"] == "tool_call"
                ),
                "tool_inputs": observed_inputs,
                "claims": trace.events[-1]["claims"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
