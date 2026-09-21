"""Capture a real LangGraph event stream from langgraph-agent-stack.

This script is intentionally kept outside the candidate project. It proves
that an independently checked-out LangGraph application can feed its own
runtime events into Agent Regression Kit without changing its business graph.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

EXPECTED_CANDIDATE_COMMIT = "a8a2dac566d46c48619ba94c69dfffb1b370520d"
FACTS_MARKER = "FACTS_JSON="


class _InstrumentedTool:
    """Capture the value crossing the real tool boundary before delegation."""

    def __init__(
        self,
        target: Any,
        calls: list[Any],
        results: list[Any],
        replacement: str | None,
        result_resolver: Callable[[Any, Any], Any] | None,
    ):
        self._target = target
        self._calls = calls
        self._results = results
        self._replacement = replacement
        self._result_resolver = result_resolver
        self.name = target.name

    def invoke(self, tool_input: Any, config: Any = None, **kwargs: Any) -> Any:
        forwarded = tool_input
        if self._replacement is not None:
            forwarded = self._replacement
        self._calls.append(forwarded)
        if config is None:
            delegated = self._target.invoke(forwarded, **kwargs)
        else:
            delegated = self._target.invoke(forwarded, config=config, **kwargs)
        consumed = (
            self._result_resolver(forwarded, delegated)
            if self._result_resolver is not None
            else delegated
        )
        self._results.append(consumed)
        return consumed


def _candidate_revision(project_dir: Path) -> str:
    status = subprocess.run(
        ["git", "-C", str(project_dir), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise RuntimeError(
            "candidate checkout must be clean; uncommitted files would make "
            "the captured revision ambiguous:\n" + status.stdout.strip()
        )
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


def _load_fixture(path: Path) -> dict[str, Any]:
    try:
        fixture = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"research fixture not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"research fixture is not valid JSON: {path}") from exc
    if not isinstance(fixture, dict):
        raise RuntimeError("research fixture must contain an object")
    queries = fixture.get("queries")
    documents = fixture.get("documents")
    facts = fixture.get("facts")
    if (
        not isinstance(queries, list)
        or len(queries) != 3
        or not all(isinstance(query, str) and query.strip() for query in queries)
    ):
        raise RuntimeError("research fixture must contain exactly three queries")
    if (
        not isinstance(documents, list)
        or len(documents) != len(queries)
        or not all(isinstance(document, dict) for document in documents)
    ):
        raise RuntimeError("research fixture must contain one document per query")
    if not isinstance(facts, dict) or not facts:
        raise RuntimeError("research fixture must contain non-empty facts")
    for required in ("fixture_id", "request", "source"):
        if not fixture.get(required):
            raise RuntimeError(f"research fixture is missing {required!r}")
    return fixture


def _fixture_result(fixture: Mapping[str, Any], query: Any, _delegated: Any) -> str:
    """Return the reviewed document snapshot at the real tool boundary."""
    normalized = str(query).strip().casefold()
    queries = fixture["queries"]
    documents = fixture["documents"]
    try:
        index = [str(item).strip().casefold() for item in queries].index(normalized)
    except ValueError:
        return (
            f"[FIXTURE MISS] No reviewed document matched query {query!r}. "
            "The candidate must not infer a supported fact from this result."
        )
    document = documents[index]
    source = fixture["source"]
    return (
        f"Document-ID: {document['id']}\n"
        f"Section: {document.get('section', 'unknown')}\n"
        f"Excerpt: {document['content']}\n"
        f"Source: {source['url']}"
    )


def _facts_from_evidence(prompt: str) -> dict[str, Any]:
    """Extract facts from evidence text, without consulting expected fixture facts."""
    normalized = re.sub(r"\s+", " ", prompt).casefold()
    facts: dict[str, Any] = {}
    if "checkpointer saves graph-state snapshots for one thread" in normalized:
        facts["checkpointer_scope"] = "single_thread"
    if "store keeps application-defined data that can be shared across threads" in normalized:
        facts["store_scope"] = "cross_thread"
    if (
        "invokes it with configurable.thread_id" in normalized
        and "thread identifier groups checkpoints for the same thread" in normalized
    ):
        facts["thread_id_required"] = True
    if (
        "in-memory checkpointer keeps checkpoints in ram" in normalized
        and "loses them when the process restarts" in normalized
    ):
        facts["in_memory_survives_restart"] = False
    return facts


def _events_with_consumed_results(
    events: list[Mapping[str, Any]], consumed_results: list[Any]
) -> list[Mapping[str, Any]]:
    """Make tool-end evidence match the value returned to the Agent."""
    reconciled: list[Mapping[str, Any]] = []
    result_ordinal = 0
    for event in events:
        copied = dict(event)
        if event.get("event") == "on_tool_end":
            if result_ordinal >= len(consumed_results):
                raise RuntimeError("event stream emitted more tool results than the Agent consumed")
            raw_data = event.get("data")
            data = dict(raw_data) if isinstance(raw_data, Mapping) else {}
            data["output"] = consumed_results[result_ordinal]
            copied["data"] = data
            result_ordinal += 1
        reconciled.append(copied)
    if result_ordinal != len(consumed_results):
        raise RuntimeError(
            "Agent consumed more tool results than the event stream emitted: "
            f"events={result_ordinal} consumed={len(consumed_results)}"
        )
    return reconciled


def _claims(output: Any) -> dict[str, Any]:
    """Derive claims from the facts emitted in the candidate's actual summary."""
    if not isinstance(output, Mapping):
        raise ValueError("candidate final output must be an object")
    findings = output.get("findings", [])
    sources = output.get("sources", [])
    summary = str(output.get("summary", ""))
    marker_index = summary.find(FACTS_MARKER)
    if marker_index < 0:
        raise ValueError("candidate summary did not contain the FACTS_JSON marker")
    facts_text = summary[marker_index + len(FACTS_MARKER) :].splitlines()[0].strip()
    try:
        facts = json.loads(facts_text)
    except json.JSONDecodeError as exc:
        raise ValueError("candidate FACTS_JSON marker was not valid JSON") from exc
    if not isinstance(facts, dict):
        raise ValueError("candidate FACTS_JSON must be an object")
    return {
        "summary_present": bool(summary),
        "findings_count": len(findings) if isinstance(findings, list) else 0,
        "source_count": len(sources) if isinstance(sources, list) else 0,
        "confidence": output.get("confidence"),
        "facts": facts,
    }


def _load_candidate(project_dir: Path) -> tuple[Any, Any, Any, Any, str]:
    """Load the candidate's runtime using its already-installed environment."""
    revision = _candidate_revision(project_dir)
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
        revision,
    )


def _instrument_agent(
    agent: Any,
    observed_inputs: list[Any],
    consumed_results: list[Any],
    *,
    skip_search: bool,
    replacement_query: str | None,
    result_resolver: Callable[[Any, Any], Any] | None,
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
                _InstrumentedTool(
                    tool,
                    observed_inputs,
                    consumed_results,
                    replacement_query,
                    result_resolver,
                )
            )
    if not search_found:
        raise RuntimeError("candidate ResearchAgent has no web_search tool")
    agent.tools = rewritten_tools


def _install_fixture_model(
    agent: Any,
    fixture: Mapping[str, Any],
    *,
    misread_fact: str | None,
    vary_evidence_order: bool,
    summary_confidence: float | None,
) -> dict[str, bool]:
    """Make the upstream mock provider answer from the reviewed fixture.

    The upstream graph and event stream remain real. Only its deterministic
    provider responses are replaced so the pilot can assert business facts
    without network access or a paid model. Claims are parsed back from the
    summary produced by this provider, not copied into the Trace by the
    harness.
    """
    original = agent._invoke_llm_with_retry
    state = {"summary_applied": False, "expansion_applied": False}

    def response_payload(response: Any, payload: Mapping[str, Any] | list[str]) -> Any:
        response.content = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return response

    def wrapped(messages: Any, *args: Any, **kwargs: Any) -> Any:
        response = original(messages, *args, **kwargs)
        prompt = "\n".join(str(getattr(message, "content", "")) for message in messages)
        if "Provide 3 focused sub-queries" in prompt and not state["expansion_applied"]:
            state["expansion_applied"] = True
            return response_payload(response, list(fixture["queries"]))
        if "Are these findings sufficient" in prompt:
            sufficient = any(
                f"Document-ID: {document['id']}" in prompt
                for document in fixture["documents"]
            )
            return response_payload(
                response,
                {"sufficient": sufficient, "reason": "Reviewed fixture coverage."},
            )
        if "Provide a JSON object with keys" in prompt and not state["summary_applied"]:
            state["summary_applied"] = True
            evidence_ids = [
                document["id"]
                for document in fixture["documents"]
                if f"Document-ID: {document['id']}" in prompt
            ]
            facts = _facts_from_evidence(prompt)
            facts["evidence_ids"] = evidence_ids
            if misread_fact is not None and misread_fact in facts:
                wrong_values = {
                    "checkpointer_scope": "cross_thread",
                    "store_scope": "single_thread",
                    "thread_id_required": False,
                    "in_memory_survives_restart": True,
                }
                facts[misread_fact] = wrong_values[misread_fact]
            if vary_evidence_order:
                facts["evidence_ids"] = list(reversed(evidence_ids))
            summary = (
                "The answer was generated from the reviewed document excerpts.\n"
                + FACTS_MARKER
                + json.dumps(facts, ensure_ascii=False, sort_keys=True)
            )
            confidence = 0.92 if summary_confidence is None else summary_confidence
            return response_payload(
                response,
                {"summary": summary, "confidence": confidence},
            )
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
    fixture: Mapping[str, Any],
    misread_fact: str | None = None,
    vary_evidence_order: bool = False,
    summary_confidence: float | None = None,
    corrupt_evidence: bool = False,
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
    consumed_results: list[Any] = []
    _instrument_agent(
        agent,
        observed_inputs,
        consumed_results,
        skip_search=skip_search,
        replacement_query=replacement_query,
        result_resolver=lambda query, delegated: (
            re.sub(
                r"Excerpt: .*\nSource:",
                "Excerpt: [CORRUPTED EVIDENCE]\nSource:",
                _fixture_result(fixture, query, delegated),
                flags=re.DOTALL,
            )
            if corrupt_evidence
            else _fixture_result(fixture, query, delegated)
        ),
    )
    injection_state = _install_fixture_model(
        agent,
        fixture,
        misread_fact=misread_fact,
        vary_evidence_order=vary_evidence_order,
        summary_confidence=summary_confidence,
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
    if not injection_state["summary_applied"]:
        raise RuntimeError("fixture summary response was not applied")
    tool_starts = [event for event in events if event.get("event") == "on_tool_start"]
    if any(event.get("name") != "web_search" for event in tool_starts):
        raise RuntimeError("pilot expects every observed tool start to be web_search")
    if len(tool_starts) != len(observed_inputs):
        raise RuntimeError(
            "tool boundary capture count does not match event stream: "
            f"events={len(tool_starts)} captured={len(observed_inputs)}"
        )
    events = _events_with_consumed_results(events, consumed_results)
    return events, context["research_result"], observed_inputs, revision


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a langgraph-agent-stack ResearchAgent into AgentTrace."
    )
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).with_name("research-fixture.json"),
        help="Reviewed fixed-document fixture used by the deterministic pilot.",
    )
    parser.add_argument("--request")
    parser.add_argument("--run-id", default="langgraph-agent-stack-pilot")
    parser.add_argument(
        "--mutate-confidence",
        type=float,
        help="Change confidence after the Agent run; comparator-only demonstration.",
    )
    parser.add_argument(
        "--mutate-summary-confidence",
        type=float,
        help="Legacy confidence-only mutation; use --misread-fact for business evidence.",
    )
    parser.add_argument(
        "--misread-fact",
        choices=(
            "checkpointer_scope",
            "store_scope",
            "thread_id_required",
            "in_memory_survives_restart",
        ),
        help="Change one fact in the summariser response during Agent execution.",
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
    parser.add_argument(
        "--vary-evidence-order",
        action="store_true",
        help="Return the same evidence IDs in another order; the config normalizes this.",
    )
    parser.add_argument(
        "--corrupt-evidence",
        action="store_true",
        help="Replace evidence bodies while preserving IDs; business facts must fail closed.",
    )
    args = parser.parse_args()
    if sum(
        value is not None
        for value in (args.mutate_confidence, args.mutate_summary_confidence, args.misread_fact)
    ) > 1:
        parser.error(
            "choose at most one of --mutate-confidence, --mutate-summary-confidence, "
            "or --misread-fact"
        )
    fixture = _load_fixture(args.fixture)
    request = args.request or str(fixture["request"])
    fixture_sha256 = hashlib.sha256(args.fixture.read_bytes()).hexdigest()

    # Import the kit after the candidate path is prepared, but keep the
    # candidate's `core` package ahead of it in sys.path for this process.
    from agent_regression import trace_from_langgraph_events

    events, final_output, observed_inputs, revision = asyncio.run(
        _capture(
            args.project_dir,
            request,
            args.run_id,
            fixture=fixture,
            skip_search=args.skip_search,
            replacement_query=args.mutate_search_query,
            misread_fact=args.misread_fact,
            vary_evidence_order=args.vary_evidence_order,
            summary_confidence=args.mutate_summary_confidence,
            corrupt_evidence=args.corrupt_evidence,
        )
    )
    output_for_trace = dict(final_output)
    if args.mutate_confidence is not None:
        output_for_trace["confidence"] = args.mutate_confidence
    trace = trace_from_langgraph_events(
        events,
        output_for_trace,
        request,
        run_id=args.run_id,
        tool_input_resolver=(
            lambda _event, ordinal: observed_inputs[ordinal - 1]
            if ordinal <= len(observed_inputs)
            else (_ for _ in ()).throw(
                RuntimeError(
                    "tool input resolver received more starts than the instrumented "
                    "tool boundary captured"
                )
            )
        ),
        identity={
            "name": "langgraph-agent-stack-research-agent",
            "version": f"0.7.0+git.{revision[:12]}",
            "framework": "langgraph",
            "source": "https://github.com/Brescou/langgraph-agent-stack",
            "source_revision": revision,
            "fixture_id": fixture["fixture_id"],
            "fixture_sha256": fixture_sha256,
            "source_snapshot": fixture["source"],
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
