import requests
from typing import List, Dict
from tools.workflows import _base, _headers, _check

# Offline catalogue of the most important n8n node types (2025/2026).
# Used to seed capability memory so the agent knows what nodes exist
# even before making any API calls.
CORE_NODE_CATALOGUE = {
    "n8n-nodes-base.manualTrigger": {
        "displayName": "Manual Trigger", "category": "Trigger",
        "description": "Starts workflow manually via the UI",
        "defaultParams": {}
    },
    "n8n-nodes-base.scheduleTrigger": {
        "displayName": "Schedule Trigger", "category": "Trigger",
        "description": "Runs workflow on cron schedule or interval",
        "defaultParams": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}
    },
    "n8n-nodes-base.webhook": {
        "displayName": "Webhook", "category": "Trigger",
        "description": "Receives HTTP requests at a configurable path",
        "defaultParams": {"httpMethod": "POST", "path": "my-webhook", "responseMode": "onReceived"}
    },
    "n8n-nodes-base.httpRequest": {
        "displayName": "HTTP Request", "category": "Action",
        "description": "Makes HTTP calls to any REST API",
        "defaultParams": {"method": "GET", "url": "https://example.com"}
    },
    "n8n-nodes-base.code": {
        "displayName": "Code", "category": "Action",
        "description": "Runs JavaScript or Python code",
        "defaultParams": {"language": "javaScript", "jsCode": "return [{json: {}}]"}
    },
    "n8n-nodes-base.set": {
        "displayName": "Edit Fields", "category": "Transform",
        "description": "Add, modify, or remove data fields",
        "defaultParams": {}
    },
    "n8n-nodes-base.if": {
        "displayName": "If", "category": "Logic",
        "description": "Branch workflow based on true/false condition",
        "defaultParams": {}
    },
    "n8n-nodes-base.switch": {
        "displayName": "Switch", "category": "Logic",
        "description": "Route to multiple branches based on a value",
        "defaultParams": {}
    },
    "n8n-nodes-base.filter": {
        "displayName": "Filter", "category": "Transform",
        "description": "Remove items that don't match conditions",
        "defaultParams": {}
    },
    "n8n-nodes-base.merge": {
        "displayName": "Merge", "category": "Transform",
        "description": "Combine data from two branches",
        "defaultParams": {"mode": "combine"}
    },
    "n8n-nodes-base.splitInBatches": {
        "displayName": "Loop Over Items", "category": "Flow",
        "description": "Process list items one by one in a loop",
        "defaultParams": {"batchSize": 1}
    },
    "n8n-nodes-base.wait": {
        "displayName": "Wait", "category": "Flow",
        "description": "Pause execution for a set time",
        "defaultParams": {"resume": "timeInterval", "amount": 5, "unit": "seconds"}
    },
    "n8n-nodes-base.respondToWebhook": {
        "displayName": "Respond to Webhook", "category": "Action",
        "description": "Send custom HTTP response to webhook caller",
        "defaultParams": {"respondWith": "json"}
    },
    "n8n-nodes-base.slack": {
        "displayName": "Slack", "category": "Communication",
        "description": "Send messages and manage Slack workspace",
        "defaultParams": {"resource": "message", "operation": "post"}
    },
    "n8n-nodes-base.gmail": {
        "displayName": "Gmail", "category": "Communication",
        "description": "Send and read Gmail messages",
        "defaultParams": {"resource": "message", "operation": "send"}
    },
    "n8n-nodes-base.telegram": {
        "displayName": "Telegram", "category": "Communication",
        "description": "Send Telegram bot messages",
        "defaultParams": {"resource": "message", "operation": "sendMessage"}
    },
    "n8n-nodes-base.discord": {
        "displayName": "Discord", "category": "Communication",
        "description": "Post to Discord channels via webhook",
        "defaultParams": {}
    },
    "n8n-nodes-base.googleSheets": {
        "displayName": "Google Sheets", "category": "Data",
        "description": "Read and write Google Sheets",
        "defaultParams": {"resource": "sheet", "operation": "read"}
    },
    "n8n-nodes-base.notion": {
        "displayName": "Notion", "category": "Data",
        "description": "Create and update Notion pages",
        "defaultParams": {"resource": "page", "operation": "create"}
    },
    "n8n-nodes-base.github": {
        "displayName": "GitHub", "category": "DevOps",
        "description": "Manage GitHub issues, PRs, repos",
        "defaultParams": {"resource": "issue", "operation": "create"}
    },
    "n8n-nodes-base.postgres": {
        "displayName": "Postgres", "category": "Database",
        "description": "Query and modify PostgreSQL databases",
        "defaultParams": {"operation": "executeQuery"}
    },
    "n8n-nodes-base.airtable": {
        "displayName": "Airtable", "category": "Data",
        "description": "Read and write Airtable bases",
        "defaultParams": {"resource": "record", "operation": "list"}
    },
}


def get_installed_node_types() -> List[Dict]:
    """Query the live n8n instance for installed node types."""
    url = f"{_base()}/api/v1/node-types"
    try:
        return _check(requests.get(url, headers=_headers()), url)
    except Exception:
        return list(CORE_NODE_CATALOGUE.values())