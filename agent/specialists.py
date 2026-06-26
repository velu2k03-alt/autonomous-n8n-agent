from typing import Dict, Any, Tuple, Optional, List
import re

class SpecialistAgent:
    """
    Base Specialist Agent class.
    Each specialist agent takes ownership of a subset of tools, performs pre-execution validation,
    calculates dynamic confidence scores, and defines rollback/compensating actions.
    """
    def __init__(self, name: str, handled_tools: List[str]):
        self.name = name
        self.handled_tools = handled_tools

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in self.handled_tools

    def validate_params(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Perform static pre-validation checks before calling the API."""
        return True, None

    def calculate_confidence(self, tool_name: str, params: Dict[str, Any], tool_stats: Dict[str, Any]) -> Tuple[float, str]:
        """Dynamically evaluate confidence (0.0 to 1.0) and output reasoning."""
        confidence = 1.0
        reasons = []

        # 1. Historical Tool Reliability
        if tool_name in tool_stats:
            stats = tool_stats[tool_name]
            succ = stats.get("success", 0)
            fail = stats.get("failure", 0)
            total = succ + fail
            if total > 0:
                reliability = succ / total
                if reliability < 0.95:
                    penalty = (1.0 - reliability) * 0.4
                    confidence -= penalty
                    reasons.append(f"Tool historical success rate is {reliability*100:.0f}%")

        # 2. Unresolved Dependencies / Dynamic Placeholders
        has_placeholders = False
        def scan_placeholders(v):
            nonlocal has_placeholders
            if isinstance(v, str) and ("step_" in v or "{{" in v):
                has_placeholders = True
            elif isinstance(v, dict):
                for val in v.values():
                    scan_placeholders(val)
            elif isinstance(v, list):
                for val in v:
                    scan_placeholders(val)
        scan_placeholders(params)

        if has_placeholders:
            confidence -= 0.15
            reasons.append("Parameters contain unresolved outputs from previous steps")

        confidence = max(0.1, min(1.0, confidence))
        reason_str = "; ".join(reasons) if reasons else "Tool has a stable history and parameters are resolved"
        return round(confidence, 2), reason_str

    def pre_execute_hook(self, tool_name: str, params: Dict[str, Any]) -> Optional[Any]:
        """Hook called before execution to capture context/backup state for rollback."""
        return None

    def get_rollback_action(self, tool_name: str, params: Dict[str, Any], result: Any, pre_execution_context: Any = None) -> Optional[Dict[str, Any]]:
        """Return compensating action (tool name, parameters, description) if state was modified."""
        return None


class WorkflowSpecialist(SpecialistAgent):
    """Specialist for n8n workflow management."""
    def __init__(self):
        super().__init__(
            name="Workflow Specialist",
            handled_tools=[
                "list_workflows",
                "get_workflow",
                "get_workflow_by_name",
                "create_workflow",
                "update_workflow",
                "activate_workflow",
                "deactivate_workflow",
                "delete_workflow",
            ]
        )

    def validate_params(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if tool_name in ["get_workflow", "update_workflow", "activate_workflow", "deactivate_workflow", "delete_workflow"]:
            wf_id = params.get("workflow_id") or params.get("id")
            # If no ID and no placeholder indicating it depends on a prior step
            if not wf_id and not any(isinstance(v, str) and "step_" in v for v in params.values()):
                return False, f"Missing workflow_id or id in parameters for {tool_name}."

        if tool_name == "create_workflow":
            if not params.get("name"):
                return False, "Missing workflow 'name' in parameters for create_workflow."
            # If nodes are passed, validate structural presence
            nodes = params.get("nodes")
            if nodes is not None:
                if not isinstance(nodes, list):
                    return False, "Parameter 'nodes' must be a list of node definitions."
                for idx, node in enumerate(nodes):
                    if not isinstance(node, dict) or not node.get("name") or not node.get("type"):
                        return False, f"Node at index {idx} is invalid: must have 'name' and 'type'."

        return True, None

    def calculate_confidence(self, tool_name: str, params: Dict[str, Any], tool_stats: Dict[str, Any]) -> Tuple[float, str]:
        conf, reason = super().calculate_confidence(tool_name, params, tool_stats)
        
        # Specific workflow validations that could lower confidence
        if tool_name == "create_workflow":
            nodes = params.get("nodes", [])
            connections = params.get("connections", {})
            if not nodes:
                conf -= 0.2
                reason += "; Creating an empty workflow is highly trivial and usually requires node configuration"
            elif not connections and len(nodes) > 1:
                conf -= 0.1
                reason += "; Multiple nodes present but connections map is empty"

        return round(max(0.1, conf), 2), reason

    def pre_execute_hook(self, tool_name: str, params: Dict[str, Any]) -> Optional[Any]:
        # For update and delete, fetch the current state first so we can restore it on rollback
        if tool_name in ["update_workflow", "delete_workflow"]:
            wf_id = params.get("workflow_id") or params.get("id")
            if wf_id and not ("step_" in str(wf_id) or "{{" in str(wf_id)):
                try:
                    from tools.workflows import get_workflow
                    return get_workflow(wf_id)
                except Exception as e:
                    print(f"         [Workflow Specialist] Backup pre-execution failed: {e}")
        return None

    def get_rollback_action(self, tool_name: str, params: Dict[str, Any], result: Any, pre_execution_context: Any = None) -> Optional[Dict[str, Any]]:
        # 1. create_workflow -> delete_workflow
        if tool_name == "create_workflow" and result:
            wf_id = result.get("id")
            if wf_id:
                return {
                    "tool": "delete_workflow",
                    "params": {"workflow_id": wf_id},
                    "description": f"Delete created workflow '{result.get('name')}' (ID: {wf_id})"
                }

        # 2. delete_workflow -> recreate workflow using the backup pre-execution context
        if tool_name == "delete_workflow" and pre_execution_context:
            return {
                "tool": "create_workflow",
                "params": {
                    "name": pre_execution_context.get("name"),
                    "nodes": pre_execution_context.get("nodes"),
                    "connections": pre_execution_context.get("connections"),
                    "active": pre_execution_context.get("active", False),
                    "settings": pre_execution_context.get("settings")
                },
                "description": f"Recreate deleted workflow '{pre_execution_context.get('name')}' (ID: {pre_execution_context.get('id')})"
            }

        # 3. update_workflow -> restore original configuration
        if tool_name == "update_workflow" and pre_execution_context:
            return {
                "tool": "update_workflow",
                "params": {
                    "workflow_id": pre_execution_context.get("id"),
                    "name": pre_execution_context.get("name"),
                    "nodes": pre_execution_context.get("nodes"),
                    "connections": pre_execution_context.get("connections")
                },
                "description": f"Restore workflow '{pre_execution_context.get('name')}' (ID: {pre_execution_context.get('id')}) to previous state"
            }

        # 4. activate_workflow -> deactivate_workflow
        if tool_name == "activate_workflow":
            wf_id = params.get("workflow_id") or params.get("id") or (result.get("id") if isinstance(result, dict) else None)
            if wf_id:
                return {
                    "tool": "deactivate_workflow",
                    "params": {"workflow_id": wf_id},
                    "description": f"Deactivate workflow (ID: {wf_id})"
                }

        # 5. deactivate_workflow -> activate_workflow
        if tool_name == "deactivate_workflow":
            wf_id = params.get("workflow_id") or params.get("id") or (result.get("id") if isinstance(result, dict) else None)
            if wf_id:
                return {
                    "tool": "activate_workflow",
                    "params": {"workflow_id": wf_id},
                    "description": f"Activate workflow (ID: {wf_id})"
                }

        return None


class ExecutionSpecialist(SpecialistAgent):
    """Specialist for querying and filtering n8n executions."""
    def __init__(self):
        super().__init__(
            name="Execution Specialist",
            handled_tools=[
                "list_executions",
                "get_execution",
                "get_recent_executions_for_workflow",
                "get_failed_executions",
                "delete_execution",
            ]
        )

    def validate_params(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if tool_name in ["get_execution", "delete_execution"]:
            exec_id = params.get("execution_id") or params.get("id")
            if not exec_id and not any(isinstance(v, str) and "step_" in v for v in params.values()):
                return False, f"Missing execution_id or id in parameters for {tool_name}."
        return True, None


class CredentialSpecialist(SpecialistAgent):
    """Specialist for n8n credentials."""
    def __init__(self):
        super().__init__(
            name="Credential Specialist",
            handled_tools=[
                "list_credentials",
                "get_credential",
                "create_credential",
                "delete_credential",
            ]
        )

    def validate_params(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        if tool_name == "create_credential":
            if not params.get("name") or not params.get("credential_type") or not params.get("data"):
                return False, "create_credential requires 'name', 'credential_type', and 'data' dictionary."
        if tool_name in ["get_credential", "delete_credential"]:
            cred_id = params.get("credential_id") or params.get("id")
            if not cred_id and not any(isinstance(v, str) and "step_" in v for v in params.values()):
                return False, f"Missing credential_id or id in parameters for {tool_name}."
        return True, None

    def get_rollback_action(self, tool_name: str, params: Dict[str, Any], result: Any, pre_execution_context: Any = None) -> Optional[Dict[str, Any]]:
        # create_credential -> delete_credential
        if tool_name == "create_credential" and result:
            cred_id = result.get("id")
            if cred_id:
                return {
                    "tool": "delete_credential",
                    "params": {"credential_id": cred_id},
                    "description": f"Delete created credential '{result.get('name')}' (ID: {cred_id})"
                }
        return None


class SynthesisSpecialist(SpecialistAgent):
    """Specialist that executes dynamically synthesised tools."""
    def __init__(self):
        super().__init__(
            name="Synthesis Specialist",
            handled_tools=[]  # Populated dynamically or matched via catch-all
        )

    def can_handle(self, tool_name: str) -> bool:
        # Synthesis Specialist handles any tool that doesn't belong to the predefined ones
        predefined = [
            "list_workflows", "get_workflow", "get_workflow_by_name", "create_workflow", "update_workflow",
            "activate_workflow", "deactivate_workflow", "delete_workflow", "list_executions", "get_execution",
            "get_recent_executions_for_workflow", "get_failed_executions", "delete_execution", "list_credentials",
            "get_credential", "create_credential", "delete_credential"
        ]
        return tool_name not in predefined

    def calculate_confidence(self, tool_name: str, params: Dict[str, Any], tool_stats: Dict[str, Any]) -> Tuple[float, str]:
        # Synthesised tools start with a slightly lower confidence baseline
        conf, reason = super().calculate_confidence(tool_name, params, tool_stats)
        conf = min(0.75, conf)
        reason += "; Dynamically synthesised runtime capability (assessed with initial review margin)"
        return round(conf, 2), reason


# Router list
SPECIALISTS: List[SpecialistAgent] = [
    WorkflowSpecialist(),
    ExecutionSpecialist(),
    CredentialSpecialist(),
    SynthesisSpecialist()
]

def get_specialist(tool_name: str) -> SpecialistAgent:
    """Find the specialist agent registered to handle the given tool."""
    for specialist in SPECIALISTS:
        if specialist.can_handle(tool_name):
            return specialist
    return SPECIALISTS[-1] # Fallback to Synthesis Specialist
