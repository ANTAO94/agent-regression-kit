import asyncio
import unittest

from agent_regression import (
    AsyncCallableAgentAdapter,
    CallableAgentAdapter,
    FixtureTools,
    check_adapter_contract,
    check_async_adapter_contract,
)


class AdapterContractDiagnosticTests(unittest.TestCase):
    def test_sync_contract_report_contains_trace_and_actionable_checks(self):
        def runner(request, context):
            result = context.call_tool("get_order", {"order_id": request["order_id"]})
            context.final_answer("done", {"order_status": result["status"]})

        report = check_adapter_contract(
            CallableAgentAdapter({"name": "orders", "version": "1.0.0"}, runner),
            {"order_id": "123"},
            FixtureTools({"get_order": {"status": "paid"}}),
            expected_tool_path=["get_order"],
            expected_claims={"order_status": "paid"},
        )
        self.assertTrue(report["ok"])
        path_check = next(item for item in report["checks"] if item["name"] == "trace.tool_path")
        self.assertEqual(["get_order"], path_check["actual"])
        self.assertEqual("paid", report["trace"]["events"][-1]["claims"]["order_status"])

    def test_contract_report_explains_expected_path_regression(self):
        def runner(request, context):
            del request
            context.call_tool("lookup", {})
            context.final_answer("done", {"ok": True})

        report = check_adapter_contract(
            CallableAgentAdapter({"name": "orders", "version": "1.0.0"}, runner),
            {},
            FixtureTools({"lookup": {"ok": True}}),
            expected_tool_path=["get_order"],
        )
        self.assertFalse(report["ok"])
        path_check = next(item for item in report["checks"] if item["name"] == "trace.tool_path")
        self.assertEqual(["get_order"], path_check["expected"])
        self.assertEqual(["lookup"], path_check["actual"])

    def test_contract_report_rejects_missing_identity_version(self):
        report = check_adapter_contract(
            CallableAgentAdapter({"name": "orders"}, lambda request, context: None),
            {},
            FixtureTools({}),
        )
        self.assertFalse(report["ok"])
        self.assertEqual("identity.version", report["checks"][1]["name"])

    def test_async_contract_report_uses_same_contract_shape(self):
        async def runner(request, context):
            result = await context.call_tool("lookup", {"id": request["id"]}, parallel_group="read")
            context.final_answer("done", {"value": result["value"]})

        report = asyncio.run(
            check_async_adapter_contract(
                AsyncCallableAgentAdapter({"name": "async-orders", "version": "1.0.0"}, runner),
                {"id": "123"},
                FixtureTools({"lookup": {"value": "ok"}}),
                expected_tool_path=["lookup"],
                expected_claims={"value": "ok"},
            )
        )
        self.assertTrue(report["ok"])
        self.assertEqual("async", report["trace"]["events"][0]["metadata"]["execution"]["mode"])


if __name__ == "__main__":
    unittest.main()
