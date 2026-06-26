import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 output on Windows to avoid cp1252 encoding errors
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from agent.core import AgentCore
from models.step import Step
from models.report import ExecutionReport

def test_rollback():
    agent = AgentCore()
    
    # We will build a plan manually to execute:
    # 1. Create a workflow named "Temp Rollback Test Workflow"
    # 2. Update that workflow's nodes (invalid step parameters to trigger static validation failure, or a step that fails at runtime)
    # Let's make Step 2 fail at runtime by requesting a non-existent workflow to trigger a failure.
    
    steps = [
        Step(
            id="step_1",
            tool="create_workflow",
            description="Create a temporary workflow for rollback testing",
            params={
                "name": "Temp Rollback Test Workflow",
                "nodes": [
                    {
                        "parameters": {},
                        "type": "n8n-nodes-base.manualTrigger",
                        "typeVersion": 1,
                        "position": [250, 300],
                        "id": "manual-trigger-id",
                        "name": "When clicking ‘Test workflow’"
                    }
                ],
                "connections": {}
            }
        ),
        Step(
            id="step_2",
            tool="get_workflow",
            description="Intentionally fail by fetching a non-existent workflow",
            params={"workflow_id": "99999999-9999-9999-9999-999999999999"}, # non-existent UUID
            depends_on=["step_1"]
        )
    ]
    
    print("\nExecuting manually-defined plan designed to fail at Step 2...")
    report = agent.executor.execute(steps, "Manually planned failure test")
    
    print("\n--- TEST EXECUTION REPORT ---")
    print(f"Success: {report.success}")
    print(f"Rollback Occurred: {report.rollback_occurred}")
    print(f"Rollback Log: {report.rollback_log}")
    print(f"Failure Reason: {report.failure_reason}")

if __name__ == "__main__":
    test_rollback()
