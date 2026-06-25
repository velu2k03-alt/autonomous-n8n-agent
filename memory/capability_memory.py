import json, os
from typing import Dict, List, Optional
from models.report import ExecutionReport
from tools.node_types import CORE_NODE_CATALOGUE

MEMORY_FILE = "data/capability_memory.json"


class CapabilityMemory:
    """
    Semantic memory: stores what the agent knows how to do.
    Pre-seeded with all built-in tools and n8n node types.
    Updated after every run: success/failure counts, discovered constraints.

    Interview answer for "why two separate layers?":
    Execution memory answers 'what have I done?' (episodic lookup by instruction).
    Capability memory answers 'what can I do?' (direct lookup by tool name).
    They serve different query patterns and mixing them would complicate both.
    """

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE) as f:
                self._data = json.load(f)
        else:
            self._data = self._bootstrap()
            self._write()

    def _bootstrap(self) -> dict:
        """Pre-seed with all built-in tools so agent is useful from run 1."""
        built_in = {
            "list_workflows": "List all workflows in the n8n instance",
            "get_workflow": "Get a workflow's full JSON by ID",
            "get_workflow_by_name": "Find workflow by display name (fetches all, filters locally)",
            "create_workflow": "Create a new workflow with nodes and connections JSON",
            "update_workflow": "Modify an existing workflow — fetches current state first",
            "activate_workflow": "Activate a workflow so it responds to triggers",
            "deactivate_workflow": "Deactivate a workflow",
            "delete_workflow": "Permanently delete a workflow",
            "list_executions": "List execution records, filterable by workflow and status",
            "get_execution": "Get full execution details including node output data",
            "get_recent_executions_for_workflow": "Get recent executions for one workflow",
            "get_failed_executions": "Get all error-status executions",
            "delete_execution": "Delete one execution record",
            "get_installed_node_types": "Query n8n for all installed node types",
        }
        tools = {}
        for name, desc in built_in.items():
            tools[name] = {
                "description": desc,
                "success_count": 0,
                "failure_count": 0,
                "is_synthesised": False,
                "discovered_constraints": [],
            }
        return {
            "tools": tools,
            "node_catalogue": {k: v["displayName"] for k, v in CORE_NODE_CATALOGUE.items()},
            "global_constraints": [
                "n8n API does not support filtering workflows by name — use get_workflow_by_name which fetches all and filters locally",
                "n8n workflow JSON requires node IDs to be UUID strings — use str(uuid.uuid4())",
                "Workflow must be deactivated before deleting if it has active webhook triggers",
                "n8n execution list is paginated — use limit param, check nextCursor for more pages",
                "Activating a webhook workflow makes its URL live at /webhook/{path}",
            ],
            "synthesised_tools": [],
        }

    def update_from_report(self, report: ExecutionReport) -> None:
        """Update success/failure counts and extract new constraints after a run."""
        for step in report.steps:
            name = step.tool
            if name not in self._data["tools"]:
                self._data["tools"][name] = {
                    "description": f"Synthesised tool: {name}",
                    "success_count": 0, "failure_count": 0,
                    "is_synthesised": True, "discovered_constraints": [],
                }
            t = self._data["tools"][name]
            if step.status.value == "success":
                t["success_count"] += 1
            elif step.status.value == "failed" and step.error:
                t["failure_count"] += 1
                c = self._extract_constraint(step.tool, step.error)
                if c and c not in t["discovered_constraints"]:
                    t["discovered_constraints"].append(c)
                    print(f"[CapMem] New constraint discovered: {c}")
        self._write()

    def _extract_constraint(self, tool: str, error: str) -> Optional[str]:
        e = error.lower()
        if "not found" in e:
            return f"Verify resource exists before calling {tool}"
        if "401" in e:
            return "API key invalid or expired — check N8N_API_KEY"
        if "uuid" in e or ("invalid" in e and "id" in e):
            return "Node IDs in workflow JSON must be valid UUID strings"
        if "active" in e and ("delete" in e or "workflow" in e):
            return "Deactivate workflow before deleting"
        return None

    def get_all_tools(self) -> Dict:
        return self._data["tools"]

    def get_global_constraints(self) -> List[str]:
        return self._data.get("global_constraints", [])

    def register_synthesised_tool(self, name: str, description: str, code: str) -> None:
        self._data["tools"][name] = {
            "description": description,
            "success_count": 0, "failure_count": 0,
            "is_synthesised": True,
            "synthesised_code": code,
            "discovered_constraints": [],
        }
        if name not in self._data["synthesised_tools"]:
            self._data["synthesised_tools"].append(name)
        self._write()
        print(f"[CapMem] Registered synthesised tool: {name}")

    def _write(self):
        with open(MEMORY_FILE, "w") as f:
            json.dump(self._data, f, indent=2)