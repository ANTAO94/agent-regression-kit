"""Human-oriented next-step suggestions for regression reports."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


_ACTIONS = {
    "tool_arguments": "Inspect the candidate tool arguments and the input-to-tool mapping before changing the baseline.",
    "tool_name": "Check the Agent tool selection and the Contract allowlist; an unexpected tool is not a wording-only change.",
    "required_tool": "Confirm the Agent still reaches the required tool, then add a fixture for the missing branch if the behavior is intentional.",
    "forbidden_tool": "Remove the forbidden tool call or review the security Contract explicitly; do not allow it by accident.",
    "unauthorized_tool_call": "Review the tool allowlist and add a narrow rule only when the new capability is approved.",
    "tool_count": "Inspect retries and loops; adjust the tool limit only with a negative test for runaway calls.",
    "step_limit": "Inspect the Agent loop for an extra step before increasing max_steps.",
    "behavior_path": "Compare the observed tool path with the declared alternatives and keep unsafe paths closed.",
    "extra_tool_call": "Review the extra call and configure it as an explicit observational call only if it is safe.",
    "retry_limit_exceeded": "Check retry policy and failure handling; a repeated failed attempt must not silently pass.",
    "required_success_missing": "The expected operation only failed; fix the Agent or provide an explicit benchmark-specific success policy.",
    "result_interpretation": "Inspect the structured claims derived from the live tool result; do not fix a result misread by changing prose only.",
    "required_claim": "Emit the required business claim from the Agent's actual result and add a case covering the missing branch.",
    "contract_assertion": "Compare the failed assertion with the candidate evidence and decide whether the Agent or the Contract is wrong.",
    "contract_relation": "Trace the cross-step values used by the relation; missing evidence should be fixed at the adapter boundary.",
    "tool_result": "Inspect the live tool result and fixture version; decide whether the result change is expected or a service regression.",
    "tool_error_state": "Check error handling and retry behavior; a success/error flip is a behavioral change.",
    "state_change": "Review the state snapshot and isolate external side effects before accepting the change.",
    "state_equivalence": "Review the declared state-equivalence paths and verify that the alternative outcome is safe.",
    "state_evidence_missing": "Record initial and final state through a SnapshotBackend or remove the state rule that cannot be evidenced.",
    "side_effect": "Inspect the business side effect in an isolated test account before updating the baseline.",
    "execution_concurrency": "Check parallel groups and result correlation; keep concurrency changes covered by a deterministic fixture.",
    "final_answer": "If only wording changed, consider claims-only; keep structured business claims strict.",
}


def next_actions_for_differences(
    differences: Iterable[Dict[str, Any]], *, limit: int = 4
) -> List[str]:
    """Return deduplicated actions for blocking differences first."""
    blocking = [item for item in differences if not item.get("allowed", False)]
    if not blocking:
        return [
            "Review the report and commit the candidate as the new baseline only after a deliberate behavior review."
        ]
    actions: List[str] = []
    for difference in blocking:
        category = str(difference.get("category", ""))
        action = _ACTIONS.get(
            category,
            "Inspect the first blocking difference, reproduce it with the same fixture, and update the Contract only with an explicit safety decision.",
        )
        if action not in actions:
            actions.append(action)
        if len(actions) >= limit:
            break
    return actions
