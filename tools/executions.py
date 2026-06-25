import os
import requests
from typing import List, Dict, Optional, Any
from tools.workflows import _base, _headers, _check


def list_executions(workflow_id: Optional[str] = None,
                    status: Optional[str] = None,
                    limit: int = 20) -> List[Dict]:
    """
    List execution records.
    status options: 'success', 'error', 'waiting', 'running', 'canceled'
    """
    url = f"{_base()}/api/v1/executions"
    params: Dict[str, Any] = {"limit": limit, "includeData": False}
    if workflow_id:
        params["workflowId"] = workflow_id
    if status:
        params["status"] = status
    return _check(requests.get(url, headers=_headers(), params=params), url).get("data", [])


def get_execution(execution_id: str) -> Dict:
    """Get full execution details including node output data."""
    url = f"{_base()}/api/v1/executions/{execution_id}"
    return _check(requests.get(url, headers=_headers(),
                               params={"includeData": True}), url)


def get_recent_executions_for_workflow(workflow_id: str, limit: int = 5) -> List[Dict]:
    return list_executions(workflow_id=workflow_id, limit=limit)


def get_failed_executions(limit: int = 10) -> List[Dict]:
    return list_executions(status="error", limit=limit)


def delete_execution(execution_id: str) -> Dict:
    url = f"{_base()}/api/v1/executions/{execution_id}"
    return _check(requests.delete(url, headers=_headers()), url)