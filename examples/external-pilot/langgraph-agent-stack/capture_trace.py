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
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


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


def _load_candidate(project_dir: Path) -> tuple[Any, Any, Any, Any]:
    """Load the candidate's runtime using its already-installed environment."""
    project_text = str(project_dir.resolve())
    if project_text not in sys.path:
        sys.path.insert(0, project_text)

    # The environment is deliberately selected before importing candidate
    # settings. No provider key or network search is needed for this preview.
    os.environ.setdefault("LLM_PROVIDER", "mock")
    os.environ.setdefault("SEARCH_PROVIDER", "mock")

    from agents.researcher import ResearchAgent
    from core.config import get_settings
    from core.llm import get_llm
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver

    get_settings.cache_clear()
    settings = get_settings()
    return ResearchAgent, get_llm(settings.llm_config), HumanMessage, MemorySaver


async def _capture(
    project_dir: Path,
    request: str,
    run_id: str,
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
    research_agent_cls, llm, human_message_cls, memory_saver_cls = _load_candidate(
        project_dir
    )
    agent = research_agent_cls(
        thread_id=run_id,
        llm=llm,
        # The pilot is one isolated process; an in-memory saver avoids creating
        # a candidate-project database as a side effect of evidence capture.
        checkpointer=memory_saver_cls(),
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
    return events, context["research_result"]


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
        help="Intentionally change the extracted confidence to demonstrate a failing comparison.",
    )
    args = parser.parse_args()

    # Import the kit after the candidate path is prepared, but keep the
    # candidate's `core` package ahead of it in sys.path for this process.
    from agent_regression import trace_from_langgraph_events

    events, final_output = asyncio.run(
        _capture(args.project_dir, args.request, args.run_id)
    )
    output_for_trace = dict(final_output)
    if args.mutate_confidence is not None:
        output_for_trace["confidence"] = args.mutate_confidence
    trace = trace_from_langgraph_events(
        events,
        output_for_trace,
        args.request,
        run_id=args.run_id,
        identity={
            "name": "langgraph-agent-stack-research-agent",
            "version": "0.7.0",
            "framework": "langgraph",
            "source": "https://github.com/Brescou/langgraph-agent-stack",
        },
        claims_extractor=_claims,
    )
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
                "claims": trace.events[-1]["claims"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
