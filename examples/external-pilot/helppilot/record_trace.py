"""Run the pinned HelpPilot graph and export an Agent Regression Trace.

This adapter deliberately does not copy HelpPilot's implementation. It imports a
caller-provided checkout, replaces only the model and retrieval boundaries with
deterministic test doubles, then records the external project's own SQLite audit
log as a framework trace. The graph, nodes, approval interrupt and business tools
still execute from the external checkout.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from agent_regression import FrameworkTraceRecorder


ORDER_ID = "ORD-5001"
CUSTOMER_ID = "CUST-1001"
QUERY = (
    "My package never arrived and it has been two weeks. "
    "Order ORD-5001. Refund please."
)
TRACKED_ACTIONS = {
    "get_order",
    "get_tracking",
    "check_refund_policy",
    "create_refund_draft",
    "issue_refund",
}


def _source_commit(project_dir: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(project_dir), "rev-parse", "HEAD"],
        text=True,
    ).strip()


class DeterministicModel:
    """Small ChatModel-shaped substitute for triage, solver and reviewer calls."""

    def __init__(self, model_name: str, mutation: str) -> None:
        self.model_name = model_name
        self.mutation = mutation
        self._tool_call_index = 0

    def bind_tools(self, _tools: list[Any]) -> "DeterministicModel":
        return self

    def invoke(self, messages: list[Any]) -> Any:
        from langchain_core.messages import AIMessage, SystemMessage

        system = "\n".join(
            str(getattr(message, "content", ""))
            for message in messages
            if isinstance(message, SystemMessage)
        )
        if "support triage classifier" in system:
            return AIMessage(
                content=json.dumps({"route": "use_tools", "reason": "refund request"})
            )
        if "reviewer gating a support reply" in system:
            return AIMessage(
                content=json.dumps(
                    {
                        "grounded": True,
                        "citations_ok": True,
                        "pii_found": False,
                        "approved": True,
                        "reason": "the fixed policy passage supports the reply",
                    }
                )
            )

        tool_names = [
            call.get("name")
            for message in messages
            if isinstance(message, AIMessage)
            for call in (getattr(message, "tool_calls", None) or [])
        ]
        lookup_order = "ORD-5002" if self.mutation == "wrong-resource" else ORDER_ID
        if "get_order" not in tool_names:
            name, arguments = "get_order", {"order_id": lookup_order}
        elif self.mutation != "skip-tool" and "get_tracking" not in tool_names:
            name, arguments = "get_tracking", {"order_id": lookup_order}
        elif "check_refund_policy" not in tool_names:
            name, arguments = "check_refund_policy", {"query": "lost package refund"}
        elif "create_refund_draft" not in tool_names:
            amount = 89.00 if self.mutation == "wrong-resource" else 129.99
            name, arguments = "create_refund_draft", {
                "order_id": lookup_order,
                "amount": amount,
            }
        else:
            status = "delivered" if self.mutation == "misread-result" else "lost"
            return AIMessage(
                content=f"Order {lookup_order} is {status} and qualifies for a full refund [refund-policy]."
            )

        self._tool_call_index += 1
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": arguments,
                    "id": f"helppilot-fake-call-{self._tool_call_index}",
                }
            ],
        )


def _load_external_project(project_dir: Path) -> tuple[Any, Any, Any, Any, Any]:
    sys.path.insert(0, str(project_dir))
    from helppilot import config, db, graph, rag, seed

    return config, db, graph, rag, seed


def _action_rows(db: Any, thread_id: str) -> list[dict[str, Any]]:
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT action, payload, result FROM actions_log "
            "WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
    return [
        {
            "action": row["action"],
            "payload": json.loads(row["payload"]) if row["payload"] else {},
            "result": json.loads(row["result"]) if row["result"] else {},
        }
        for row in rows
    ]


def _trace_from_run(
    *,
    db: Any,
    first: dict[str, Any],
    final: dict[str, Any],
    thread_id: str,
    source_commit: str,
    mutation: str,
) -> Any:
    rows = [row for row in _action_rows(db, thread_id) if row["action"] in TRACKED_ACTIONS]
    recorder = FrameworkTraceRecorder(
        {
            "name": "helppilot",
            "version": "0.1.0",
            "framework": "langgraph",
            "source_commit": source_commit,
        },
        run_id=f"helppilot-{mutation}",
        request={"query": QUERY, "customer_id": CUSTOMER_ID, "order_id": ORDER_ID},
        metadata={
            "source_repository": "poysa213/HelpPilot",
            "source_commit": source_commit,
            "scenario": "lost-order-refund-with-human-approval",
            "mutation": mutation,
            "approval_before_resume": first["status"] == "interrupted",
            "approved_by": "human",
        },
    )
    for index, row in enumerate(rows, start=1):
        call_id = recorder.tool_start(row["action"], row["payload"], call_id=f"call-{index}")
        result = dict(row["result"])
        # HelpPilot's SQLite seed adds a creation timestamp to order rows. It is
        # operational metadata, not part of the refund decision, so remove only
        # this explicitly identified field before the trace is compared.
        if row["action"] == "get_order":
            result.pop("created_at", None)
        recorder.tool_end(call_id, result, is_error="error" in result)

    state = final["state"]
    issue = next((row for row in rows if row["action"] == "issue_refund"), None)
    claims = {
        "route": state.get("route"),
        "order_id": ORDER_ID,
        "order_status": "delivered" if mutation == "misread-result" else "lost",
        "approval_required": True,
        "approval_decision": state.get("approval_decision"),
        "refund_issued": issue is not None,
        "refund_order_id": issue["result"].get("order_id") if issue else None,
        "refund_amount": issue["result"].get("amount") if issue else None,
        "grounded": bool(state.get("review", {}).get("grounded")),
        "citations": list(state.get("citations", [])),
    }
    recorder.final_answer(state.get("final_reply", ""), claims)
    return recorder.finish()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--mutation",
        choices=["none", "wrong-resource", "skip-tool", "misread-result"],
        default="none",
    )
    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    source_commit = _source_commit(project_dir)
    config, db, graph, rag, seed = _load_external_project(project_dir)

    with tempfile.TemporaryDirectory(prefix="helppilot-agent-regression-") as tmp:
        data_dir = Path(tmp) / "data"
        data_dir.mkdir()
        config.DATA_DIR = data_dir
        config.DB_PATH = data_dir / "helppilot.db"
        config.CHROMA_DIR = data_dir / "chroma"
        config.CHECKPOINT_DB_PATH = data_dir / "checkpoints.sqlite"
        db.init_db()
        seed.seed_sqlite()
        rag.retrieve = lambda _query, k=3: [
            {
                "doc_id": "refund-policy",
                "title": "Refund policy",
                "text": "Lost packages qualify for a full refund.",
                "score": 1.0,
            }
        ][:k]
        graph._llm = lambda model, temperature=0.0: DeterministicModel(model, args.mutation)

        thread_id = f"helppilot-{args.mutation}"
        app = graph.get_app()
        first = graph.run_turn(QUERY, CUSTOMER_ID, thread_id, app=app)
        if first["status"] != "interrupted":
            raise RuntimeError(f"expected an approval interrupt, got {first['status']!r}")
        before_resume = _action_rows(db, thread_id)
        if any(row["action"] == "issue_refund" for row in before_resume):
            raise RuntimeError("issue_refund occurred before human approval")
        final = graph.resume_turn(thread_id, approved=True, decided_by="human", app=app)
        if final["status"] != "done":
            raise RuntimeError(f"expected a completed resumed run, got {final['status']!r}")
        trace = _trace_from_run(
            db=db,
            first=first,
            final=final,
            thread_id=thread_id,
            source_commit=source_commit,
            mutation=args.mutation,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out), "source_commit": source_commit, "mutation": args.mutation}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
