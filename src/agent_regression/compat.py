"""Optional compatibility smoke checks for real MCP servers."""

from __future__ import annotations

from typing import Any, Dict


def _collect(client: Any, plural: str) -> list[Dict[str, Any]]:
    iterator = getattr(client, f"iter_{plural}", None)
    if iterator is not None:
        return list(iterator())
    return list(getattr(client, f"list_{plural}")())


def run_compatibility_smoke(client: Any) -> Dict[str, Any]:
    """Initialize an MCP client and probe primitives advertised by the server.

    This deliberately checks only discovery surfaces. It does not invoke tools,
    mutate resources, or send prompts to the server.
    """
    initialized = client.initialize()
    capabilities = initialized.get("capabilities", {})
    checks: Dict[str, Any] = {}

    if "tools" in capabilities:
        checks["tools"] = {"status": "passed", "count": len(_collect(client, "tools"))}
    else:
        checks["tools"] = {"status": "skipped", "reason": "capability not advertised"}

    if "resources" in capabilities:
        checks["resources"] = {
            "status": "passed",
            "count": len(_collect(client, "resources")),
        }
    else:
        checks["resources"] = {"status": "skipped", "reason": "capability not advertised"}

    if "prompts" in capabilities:
        checks["prompts"] = {
            "status": "passed",
            "count": len(_collect(client, "prompts")),
        }
    else:
        checks["prompts"] = {"status": "skipped", "reason": "capability not advertised"}

    if "tasks" in capabilities:
        checks["tasks"] = {"status": "passed", "count": len(_collect(client, "tasks"))}
    else:
        checks["tasks"] = {"status": "skipped", "reason": "capability not advertised"}

    return {
        "ok": True,
        "protocol_version": initialized.get("protocolVersion"),
        "server_info": initialized.get("serverInfo", {}),
        "capabilities": capabilities,
        "checks": checks,
    }
