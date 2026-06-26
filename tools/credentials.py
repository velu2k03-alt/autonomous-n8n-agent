import os
import requests
from typing import List, Dict, Optional, Any
from tools.workflows import _base, _headers, _check


def list_credentials(limit: int = 50) -> List[Dict]:
    """
    List all stored credentials in the n8n instance.

    Returns a list of credential objects (names and types, NOT secrets).
    The n8n API never returns credential secret values — only metadata.
    """
    url = f"{_base()}/api/v1/credentials"
    params: Dict[str, Any] = {"limit": limit}
    return _check(requests.get(url, headers=_headers(), params=params), url).get("data", [])


def get_credential(credential_id: str) -> Dict:
    """
    Get credential metadata by ID.
    Note: n8n does not expose secret values via API — only type, name, and ID.
    """
    url = f"{_base()}/api/v1/credentials/{credential_id}"
    return _check(requests.get(url, headers=_headers()), url)


def delete_credential(credential_id: str) -> Dict:
    """
    Delete a stored credential by ID.
    Warning: workflows using this credential will stop working.
    """
    url = f"{_base()}/api/v1/credentials/{credential_id}"
    return _check(requests.delete(url, headers=_headers()), url)


def create_credential(name: str, credential_type: str, data: Dict) -> Dict:
    """
    Create a new stored credential.

    Args:
        name: Display name for the credential.
        credential_type: n8n credential type string (e.g. "slackApi", "githubApi").
        data: Dict of credential-specific fields (e.g. {"accessToken": "..."}).

    Note: This endpoint requires specific credential schemas per type.
    Refer to n8n docs for the correct data structure per credential_type.
    """
    url = f"{_base()}/api/v1/credentials"
    payload = {
        "name": name,
        "type": credential_type,
        "data": data,
    }
    return _check(requests.post(url, headers=_headers(), json=payload), url)
