import json
import re
import os
import requests
import urllib3
from typing import Any, Dict, List, Optional
from urllib3.exceptions import InsecureRequestWarning
from urllib.parse import urlparse

# Suppress SSL warnings when verify=False
urllib3.disable_warnings(InsecureRequestWarning)

from models.step import Step
from tools import list_tool_names
from tools.node_types import CORE_NODE_CATALOGUE

class Planner:
    """
    Uses NVIDIA API (Llama 3.3 70B Instruct) to decompose natural language instructions
    into an ordered list of Step objects.
    """

    def __init__(self):
        # Read API key from environment
        self.api_key = os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            # Fallback to general env variable
            self.api_key = os.getenv("ANTHROPIC_API_KEY") # Check if you saved your key here
        
        # Free-tier high performing instruction model
        self.model = "meta/llama-3.3-70b-instruct"
        endpoint = os.getenv("NVIDIA_API_ENDPOINT", "https://integrate.api.nvidia.com/v1/chat/completions")
        self.endpoint = self._normalise_endpoint(endpoint)

    def _normalise_endpoint(self, endpoint: str) -> str:
        """
        Accept a plain URL and defensively recover from copied Markdown links such as
        [https://...](https://...).
        """
        endpoint = endpoint.strip()
        markdown_match = re.fullmatch(r"\[(https?://[^\]]+)\]\((https?://[^)]+)\)", endpoint)
        if markdown_match:
            endpoint = markdown_match.group(2)

        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid NVIDIA API endpoint: {endpoint}")
        return endpoint

    def _build_system_prompt(self, past_executions: Optional[List[dict]] = None) -> str:
        tools = list_tool_names()
        node_types = list(CORE_NODE_CATALOGUE.keys())[:20]

        memory_section = ""
        if past_executions:
            memory_section = "\n\nLEARNED FROM PAST RUNS (use this to avoid redundant steps):\n"
            for ex in past_executions[-5:]:
                if ex.get("success"):
                    seq = [s["tool"] for s in ex.get("steps", []) if s["status"] == "success"]
                    memory_section += f"- '{ex['instruction']}' → {seq} ({ex['total_api_calls']} calls)\n"

        return f"""You are the Planner for an Autonomous n8n Platform Intelligence Agent.

TASK: Decompose natural language instructions into ordered API calls that manage
an n8n workflow automation instance.

AVAILABLE TOOLS (Python functions that call n8n REST API):
{json.dumps(tools, indent=2)}

AVAILABLE n8n NODE TYPES (use these when building create_workflow steps):
{json.dumps(node_types, indent=2)}

n8n WORKFLOW JSON SCHEMA (required structure for create_workflow):
{{
  "name": "My Workflow",
  "nodes": [
    {{
      "id": "use-str-uuid4-here",
      "name": "NodeDisplayName",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [250, 300],
      "parameters": {{}}
    }}
  ],
  "connections": {{
    "NodeDisplayName": {{
      "main": [[{{"node": "NextNode", "type": "main", "index": 0}}]]
    }}
  }},
  "settings": {{"executionOrder": "v1"}}
}}

PLANNING RULES:
1. To find a workflow by name, use get_workflow_by_name (NOT a name param on list_workflows).
   n8n does not support name-based filtering — this is a known constraint.
2. To update a workflow, you need its ID first. Use get_workflow_by_name before update_workflow.
3. Every node in a create_workflow call needs a unique UUID as its "id" field.
4. Use depends_on to mark steps that need results from a prior step.
5. Load past runs — if you see a proven sequence for a similar task, prefer it.
6. Never include redundant steps (e.g. getting node types when you already know them).
{memory_section}

OUTPUT FORMAT: Return ONLY a valid JSON array. Do not include markdown formatting or code blocks like ```json. Do not include explanations. Just start with [ and end with ]."""

    def _rule_based_plan(self, instruction: str) -> Optional[List[Step]]:
        """
        Deterministic fast path for simple demo commands. This keeps the baseline
        scenarios in the assignment stable even if the LLM returns inconsistent JSON.
        """
        text = instruction.lower().strip()
        if re.search(r"\blist\b.*\bworkflows?\b", text):
            return [
                Step(
                    id="step_1",
                    tool="list_workflows",
                    params={},
                    description="List all workflows in n8n",
                )
            ]
        if re.search(r"\b(show|list|get)\b.*\bfailed\b.*\bexecutions?\b", text):
            return [
                Step(
                    id="step_1",
                    tool="get_failed_executions",
                    params={},
                    description="List failed executions in n8n",
                )
            ]
        return None

    def _parse_model_output(self, raw: str) -> Any:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Planner: NVIDIA model returned invalid JSON output:\n{raw}")

    def _coerce_step_dict(self, item: Any, index: int) -> Dict[str, Any]:
        if isinstance(item, str):
            return {
                "id": f"step_{index}",
                "tool": item,
                "params": {},
                "description": f"Call {item}",
            }

        if not isinstance(item, dict):
            raise ValueError(f"Planner: step {index} is not an object: {item!r}")

        # Common function-call shape: {"function": {"name": "...", "arguments": {...}}}
        nested_fn = item.get("function")
        if isinstance(nested_fn, dict):
            merged = dict(item)
            merged.setdefault("tool", nested_fn.get("name") or nested_fn.get("tool"))
            if "params" not in merged and "arguments" not in merged:
                merged["params"] = nested_fn.get("arguments") or nested_fn.get("params") or {}
            item = merged

        tool = item.get("tool") or item.get("function") or item.get("name") or item.get("action")
        params = item.get("params")
        if params is None:
            params = item.get("arguments")
        if params is None:
            params = item.get("args", {})

        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {"input": params}

        description = (
            item.get("description")
            or item.get("reason")
            or item.get("summary")
            or (f"Call {tool}" if tool else None)
        )
        if not tool or not description:
            raise ValueError(
                f"Planner: step {index} is missing required fields. "
                f"Received keys: {sorted(item.keys())}"
            )

        return {
            "id": item.get("id") or f"step_{index}",
            "tool": tool,
            "params": params if isinstance(params, dict) else {},
            "description": description,
            "depends_on": item.get("depends_on", []),
        }

    def _normalise_plan_data(self, data: Any, raw: str) -> List[Dict[str, Any]]:
        if isinstance(data, dict):
            if isinstance(data.get("steps"), list):
                data = data["steps"]
            elif isinstance(data.get("plan"), list):
                data = data["plan"]
            elif data.get("tool"):
                data = [data]
            elif isinstance(data.get("function"), dict) or isinstance(data.get("function"), str):
                data = [data]

        if isinstance(data, str):
            data = [data]

        if not isinstance(data, list):
            raise ValueError(f"Planner: expected a JSON array of steps, got: {type(data).__name__}")

        normalised = [self._coerce_step_dict(item, index) for index, item in enumerate(data, start=1)]
        if normalised:
            return normalised

        known_tools = list_tool_names()
        inferred = []
        for index, tool_name in enumerate(known_tools, start=1):
            if tool_name in raw:
                inferred.append({
                    "id": f"step_{index}",
                    "tool": tool_name,
                    "params": {},
                    "description": f"Call {tool_name}",
                    "depends_on": [],
                })
        if inferred:
            return inferred

        raise ValueError("Planner: model returned an empty plan")

    def plan(self, instruction: str, past_executions: Optional[List[dict]] = None) -> List[Step]:
        rule_based = self._rule_based_plan(instruction)
        if rule_based is not None:
            return rule_based

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._build_system_prompt(past_executions)},
                {"role": "user", "content": f"Decompose this instruction into steps:\n\n{instruction}"}
            ],
            "temperature": 0.1,
            "max_tokens": 2048
        }

        response = requests.post(self.endpoint, headers=headers, json=payload, verify=False)
        if not response.ok:
            raise Exception(f"NVIDIA API Error: {response.status_code} - {response.text}")
            
        raw = response.json()["choices"][0]["message"]["content"].strip()

        # Clean markdown wrappers if Llama mistakenly includes them
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        data = self._parse_model_output(raw)
        normalised_steps = self._normalise_plan_data(data, raw)

        return [
            Step(
                id=step_data["id"],
                tool=step_data["tool"],
                params=step_data["params"],
                description=step_data["description"],
                depends_on=step_data["depends_on"],
            )
            for step_data in normalised_steps
        ]
