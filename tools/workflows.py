import os
import requests
from typing import List, Dict, Any, Optional


class N8NAPIError(Exception):
    def __init__(self, status_code: int, message: str, endpoint: str):
        self.status_code = status_code
        self.endpoint = endpoint
        super().__init__(f"n8n API {status_code} at {endpoint}: {message}")


def _base() -> str:
    return os.getenv("N8N_BASE_URL", "http://localhost:5678")


def _headers() -> Dict[str, str]:
    """
    Every n8n REST API request needs X-N8N-API-KEY.
    NOT Bearer. NOT Basic. Just this header.
    """
    return {
        "X-N8N-API-KEY": os.getenv("N8N_API_KEY", ""),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _check(response: requests.Response, endpoint: str) -> Any:
    if response.status_code == 401:
        raise N8NAPIError(401, "Invalid API key. Check N8N_API_KEY in .env", endpoint)
    if response.status_code == 404:
        raise N8NAPIError(404, "Resource not found", endpoint)
    if response.status_code == 422:
        msg = response.json().get("message", response.text)
        raise N8NAPIError(422, f"Validation: {msg}", endpoint)
    if not response.ok:
        try:
            msg = response.json().get("message", response.text)
        except Exception:
            msg = response.text
        raise N8NAPIError(response.status_code, msg, endpoint)
    if response.status_code == 204:
        return {}
    return response.json()


# ── Workflow CRUD ────────────────────────────────────────────────────────────

def list_workflows(active: Optional[bool] = None, limit: int = 100) -> List[Dict]:
    """
    List all workflows. Optionally filter by active status.

    n8n API uses cursor pagination. limit=100 covers any demo instance.
    Filtering by name is NOT supported server-side — see get_workflow_by_name.
    This is a runtime constraint stored in capability memory.
    """
    url = f"{_base()}/api/v1/workflows"
    params: Dict[str, Any] = {"limit": limit}
    if active is not None:
        params["active"] = str(active).lower()
    r = requests.get(url, headers=_headers(), params=params)
    return _check(r, url).get("data", [])


def get_workflow(workflow_id: str) -> Dict:
    """Get a single workflow's full JSON by its ID."""
    url = f"{_base()}/api/v1/workflows/{workflow_id}"
    return _check(requests.get(url, headers=_headers()), url)


def get_workflow_by_name(name: str) -> Optional[Dict]:
    """
    Find a workflow by display name.
    n8n has no name filter on the API — we fetch all and filter locally.
    This constraint is pre-loaded into capability memory at startup.
    """
    for wf in list_workflows():
        if wf.get("name", "").lower() == name.lower():
            return wf
    return None


def create_workflow(name: str, nodes: List[Dict], connections: Dict,
                    active: bool = False,
                    settings: Optional[Dict] = None) -> Dict:
    """
    Create a new workflow in n8n.

    nodes: List of node dicts. Each node must have:
      - id: UUID string (use str(uuid.uuid4()))
      - name: display name string
      - type: e.g. "n8n-nodes-base.webhook"
      - typeVersion: integer (usually 1 or 2)
      - position: [x, y] array
      - parameters: dict of node-specific config

    connections: Dict mapping source node name to its output connections.
    Example:
      {"Webhook": {"main": [[{"node": "Set", "type": "main", "index": 0}]]}}

    This is the core capability — generating valid workflow JSON from
    natural language is what makes this assignment non-trivial.
    """
    url = f"{_base()}/api/v1/workflows"
    payload = {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": settings or {"executionOrder": "v1"},
    }
    result = _check(requests.post(url, headers=_headers(), json=payload), url)
    if active and result.get("id"):
        activate_workflow(result["id"])
    return result


def update_workflow(workflow_id: str, name: Optional[str] = None,
                    nodes: Optional[List[Dict]] = None,
                    connections: Optional[Dict] = None) -> Dict:
    """
    Update an existing workflow. Fetches current state first, then merges.
    n8n PUT replaces the entire workflow — we merge to avoid data loss.
    """
    current = get_workflow(workflow_id)
    payload = {
        "name": name or current["name"],
        "nodes": nodes or current["nodes"],
        "connections": connections or current["connections"],
        "settings": current.get("settings", {"executionOrder": "v1"}),
    }
    url = f"{_base()}/api/v1/workflows/{workflow_id}"
    return _check(requests.put(url, headers=_headers(), json=payload), url)


def activate_workflow(workflow_id: str) -> Dict:
    url = f"{_base()}/api/v1/workflows/{workflow_id}/activate"
    return _check(requests.post(url, headers=_headers()), url)


def deactivate_workflow(workflow_id: str) -> Dict:
    url = f"{_base()}/api/v1/workflows/{workflow_id}/deactivate"
    return _check(requests.post(url, headers=_headers()), url)


def delete_workflow(workflow_id: str) -> Dict:
    url = f"{_base()}/api/v1/workflows/{workflow_id}"
    return _check(requests.delete(url, headers=_headers()), url)