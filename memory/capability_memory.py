import json
import os
from typing import Dict, List, Optional
from models.report import ExecutionReport
from tools.node_types import CORE_NODE_CATALOGUE

MEMORY_FILE = "data/capability_memory.json"


class CapabilityMemory:
    """
    Semantic memory: stores what the agent knows how to do.

    Contains:
    - Built-in tool descriptions, success/failure counts, discovered constraints
    - Source code of synthesised tools (persists across session restarts)
    - n8n node type catalogue
    - Global platform constraints discovered at runtime

    Interview answer for "why two separate layers?":
    Execution memory answers 'what have I done?' (episodic, lookup by instruction).
    Capability memory answers 'what can I do?' (semantic, lookup by tool name).
    They serve different query patterns and mixing them would complicate both.

    Interview answer for "how do synthesised tools survive restarts?":
    When the synthesis engine generates a new function, its source code is stored
    in synthesised_code here. On startup, _reload_synthesised_tools() execs that
    code and re-registers the function in the live tool registry, exactly as if
    synthesis had just run. The agent never needs to re-synthesise a tool it
    already knows.
    """

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE) as f:
                self._data = json.load(f)
        else:
            self._data = self._bootstrap()
            self._write()

        # Reload any previously synthesised tools into the live registry
        self._reload_synthesised_tools()

    def _bootstrap(self) -> dict:
        """Pre-seed with all built-in tools so the agent is useful from run 1."""
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
            "list_credentials": "List all stored credentials",
            "get_credential": "Get credential details by ID",
            "delete_credential": "Delete a stored credential",
        }
        tools = {}
        for name, desc in built_in.items():
            tools[name] = {
                "description": desc,
                "success_count": 0,
                "failure_count": 0,
                "is_synthesised": False,
                "synthesised_code": None,
                "discovered_constraints": [],
                "reusable_strategies": [],
            }
        return {
            "tools": tools,
            "node_catalogue": {k: v["displayName"] for k, v in CORE_NODE_CATALOGUE.items()},
            "global_constraints": [
                "n8n API does not support filtering workflows by name — use get_workflow_by_name which fetches all and filters locally",
                "n8n workflow JSON requires node IDs to be UUID strings — use str(uuid.uuid4())",
                "Workflow must be deactivated before deleting if it has active webhook triggers",
                "n8n execution list is paginated — use limit param (must be <= 250, API rejects limits > 250), check nextCursor for more pages",
                "n8n execution records only contain workflowId (not workflowName or name) — to get workflow details like name, use get_workflow with the workflowId or list_workflows to fetch all workflows.",
                "Activating a webhook workflow makes its URL live at /webhook/{path}",
                "update_workflow requires the full current workflow JSON — it fetches and merges automatically",
                "When creating a workflow, the activate flag can be set True to activate immediately after creation",
            ],
            "synthesised_tools": [],
        }

    def _reload_synthesised_tools(self) -> None:
        """
        On startup: re-register all previously synthesised tools into the live registry.

        This is what makes synthesised capabilities survive session restarts.
        Without this, every restart would require re-synthesising all custom tools,
        wasting API calls and time.
        """
        # Import here to avoid circular import at module load time
        try:
            from tools import register_tool
        except ImportError:
            return

        reloaded = 0
        for name, tool_data in self._data.get("tools", {}).items():
            if tool_data.get("is_synthesised") and tool_data.get("synthesised_code"):
                try:
                    code = tool_data["synthesised_code"]
                    ns = {
                        "requests": __import__("requests"),
                        "os": __import__("os"),
                        "json": __import__("json"),
                    }
                    exec(code, ns)
                    if name in ns and callable(ns[name]):
                        register_tool(name, ns[name])
                        reloaded += 1
                        print(f"[CapMem] Reloaded synthesised tool: {name}")
                    else:
                        print(f"[CapMem] WARNING: Could not reload '{name}' — function not found in stored code")
                except Exception as e:
                    print(f"[CapMem] WARNING: Failed to reload synthesised tool '{name}': {e}")

        if reloaded:
            print(f"[CapMem] Reloaded {reloaded} synthesised tool(s) from capability memory")

    def update_from_report(self, report: ExecutionReport) -> None:
        updated_tools = []
        new_constraints = []

        for step in report.steps:
            name = step.tool
            if name not in self._data["tools"]:
                self._data["tools"][name] = {
                    "description": f"Synthesised: {name}",
                    "success_count": 0,
                    "failure_count": 0,
                    "is_synthesised": True,
                    "discovered_constraints": [],
                }

            t = self._data["tools"][name]

            if step.status.value == "success":
                t["success_count"] += 1
                updated_tools.append(f"{name}(✓)")
            elif step.status.value == "failed" and step.error:
                t["failure_count"] += 1
                updated_tools.append(f"{name}(✗)")
                constraint = self._extract_constraint(name, step.error)
                if constraint and constraint not in t["discovered_constraints"]:
                    t["discovered_constraints"].append(constraint)
                    new_constraints.append(constraint)

        if updated_tools:
            print(f"[CapMem] Updated tool stats: {', '.join(updated_tools)}")
        if new_constraints:
            for c in new_constraints:
                print(f"[CapMem] NEW CONSTRAINT DISCOVERED: {c}")
                print(f"         This will be used to avoid failures in future runs")

        # Extract reusable strategies from successful compound runs
        if report.success and len(report.steps) >= 2:
            seq = [s.tool for s in report.steps if s.status.value == "success"]
            strategy = {
                "instruction_pattern": report.instruction[:100],
                "tool_sequence": seq,
                "api_calls": report.total_api_calls,
                "duration": report.total_duration_seconds,
            }
            if "reusable_execution_strategies" not in self._data:
                self._data["reusable_execution_strategies"] = []

            # Only store if it's a new/better strategy
            existing = [s for s in self._data["reusable_execution_strategies"]
                       if s.get("tool_sequence") == seq]
            if not existing:
                self._data["reusable_execution_strategies"].append(strategy)
                print(f"[CapMem] New reusable strategy stored: {seq}")

        self._write()

    def _extract_constraint(self, tool: str, error: str) -> Optional[str]:
        """Extract a reusable constraint lesson from a failure error message."""
        e = error.lower()
        if "not found" in e:
            return f"Verify resource exists before calling {tool} — 404 was returned"
        if "401" in e:
            return "API key invalid or expired — check N8N_API_KEY in .env"
        if "uuid" in e or ("invalid" in e and "id" in e):
            return "Node IDs in workflow JSON must be valid UUID strings (use str(uuid.uuid4()))"
        if "active" in e and ("delete" in e or "workflow" in e):
            return "Deactivate workflow before deleting — active workflows cannot be deleted"
        if "422" in e:
            return f"Validation error on {tool} — check required parameters and data types"
        if "timeout" in e or "connection" in e.lower():
            return "n8n connection issue — verify docker container is running"
        return None

    def get_all_tools(self) -> Dict:
        return self._data["tools"]

    def get_tool_info(self, name: str) -> Optional[dict]:
        return self._data["tools"].get(name)

    def get_global_constraints(self) -> List[str]:
        return self._data.get("global_constraints", [])

    def get_synthesised_tools(self) -> List[str]:
        return self._data.get("synthesised_tools", [])

    def get_reusable_strategies(self) -> List[dict]:
        return self._data.get("reusable_execution_strategies", [])

    def get_tool_success_rate(self, tool_name: str) -> float:
        """Return success rate (0.0–1.0) for a tool. Returns 1.0 if never used."""
        t = self._data["tools"].get(tool_name)
        if not t:
            return 1.0
        total = t["success_count"] + t["failure_count"]
        return t["success_count"] / total if total else 1.0

    def register_synthesised_tool(self, name: str, description: str, code: str) -> None:
        """
        Register a newly synthesised tool in capability memory.
        The source code is stored so the tool can be reloaded on next startup.
        """
        self._data["tools"][name] = {
            "description": description,
            "success_count": 0,
            "failure_count": 0,
            "is_synthesised": True,
            "synthesised_code": code,
            "discovered_constraints": [],
            "reusable_strategies": [],
        }
        if name not in self._data["synthesised_tools"]:
            self._data["synthesised_tools"].append(name)
        self._write()
        print(f"[CapMem] Registered synthesised tool: {name}")

    def _write(self) -> None:
        with open(MEMORY_FILE, "w") as f:
            json.dump(self._data, f, indent=2)