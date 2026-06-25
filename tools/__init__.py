"""
TOOL REGISTRY
Maps string names → callable Python functions.
The executor looks up tools here by name.
The synthesis engine registers new tools here at runtime.
This is what "capability synthesis at runtime" means concretely:
new functions get added to this dict while the agent is running.
"""
from tools.workflows import (
    list_workflows, get_workflow, get_workflow_by_name,
    create_workflow, update_workflow, activate_workflow,
    deactivate_workflow, delete_workflow,
)
from tools.executions import (
    list_executions, get_execution,
    get_recent_executions_for_workflow,
    get_failed_executions, delete_execution,
)
from tools.node_types import get_installed_node_types

TOOL_REGISTRY: dict = {
    "list_workflows": list_workflows,
    "get_workflow": get_workflow,
    "get_workflow_by_name": get_workflow_by_name,
    "create_workflow": create_workflow,
    "update_workflow": update_workflow,
    "activate_workflow": activate_workflow,
    "deactivate_workflow": deactivate_workflow,
    "delete_workflow": delete_workflow,
    "list_executions": list_executions,
    "get_execution": get_execution,
    "get_recent_executions_for_workflow": get_recent_executions_for_workflow,
    "get_failed_executions": get_failed_executions,
    "delete_execution": delete_execution,
    "get_installed_node_types": get_installed_node_types,
}


def get_tool(name: str):
    """Return tool function or None if not found. None = capability gap."""
    return TOOL_REGISTRY.get(name)


def register_tool(name: str, func) -> None:
    """Register a synthesised tool at runtime."""
    TOOL_REGISTRY[name] = func
    print(f"[Registry] Registered: {name}")


def list_tool_names() -> list:
    return list(TOOL_REGISTRY.keys())