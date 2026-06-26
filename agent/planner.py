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
    Uses an LLM to decompose natural language instructions
    into an ordered list of Step objects.

    LLM backend: NVIDIA API (meta/llama-3.3-70b-instruct) via NVIDIA_API_KEY env var.
    Fallback: Any OpenAI-compatible endpoint.

    Why raw HTTP (not SDK): Keeps the dependency footprint minimal and makes
    every network call explicit and inspectable.

    Memory integration: Past successful executions are injected into the system
    prompt so the LLM can reuse proven step sequences, reducing API calls over time.
    """

    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "No LLM API key found. Set NVIDIA_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY in .env"
            )

        self.model = os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct")
        raw_endpoint = os.getenv(
            "LLM_API_ENDPOINT",
            "https://integrate.api.nvidia.com/v1/chat/completions"
        )
        self.endpoint = self._normalise_endpoint(raw_endpoint)

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
            raise ValueError(f"Invalid LLM API endpoint: {endpoint!r}")
        return endpoint
    def _get_tools_prompt_section(self) -> str:
        """Construct a formatted string of tools with their exact Python signatures and descriptions."""
        from tools import TOOL_REGISTRY
        import inspect
        lines = []
        for name, fn in TOOL_REGISTRY.items():
            try:
                sig = str(inspect.signature(fn))
            except Exception:
                sig = "(...)"
            doc = fn.__doc__ or ""
            # Take just the first line of the docstring
            first_line = doc.strip().split("\n")[0].strip()
            lines.append(f"  - {name}{sig}: {first_line}")
        return "\n".join(lines)

    def _build_system_prompt(self, past_executions: Optional[List[dict]] = None,
                               prior_results: Optional[Dict[str, Any]] = None,
                               global_constraints: Optional[List[str]] = None,
                               tool_constraints: Optional[List[str]] = None,
                               reusable_strategies: Optional[List[dict]] = None) -> str:
        """
        Build the system prompt.

        Includes:
        - Available tool list with signatures
        - n8n node type catalogue
        - Workflow JSON schema
        - Planning rules
        - Memory context from prior runs
        - Prior step results for result chaining
        - Dynamic global & tool constraints discovered at runtime
        - Reusable strategies from past successful runs
        """
        tools_def = self._get_tools_prompt_section()
        node_types = list(CORE_NODE_CATALOGUE.keys())[:20]

        memory_section = ""
        if past_executions:
            memory_section = "\n\nLEARNED FROM PAST RUNS (CRITICAL -- reuse these proven sequences):\n"
            for ex in past_executions[-5:]:
                if ex.get("success"):
                    seq = ex.get("execution_path") or [
                        s["tool"] for s in ex.get("steps", []) if s["status"] == "success"
                    ]
                    lessons = ex.get("lessons_learned", [])
                    memory_section += (
                        f"- Instruction: '{ex['instruction'][:80]}'\n"
                        f"  Proven tool sequence: {seq} ({ex['total_api_calls']} API calls)\n"
                        f"  REUSE this sequence if the new instruction is similar.\n"
                    )
                    if lessons:
                        memory_section += f"  Lessons: {lessons[0]}\n"

        prior_results_section = ""
        if prior_results:
            prior_results_section = "\n\nPRIOR STEP RESULTS (use these IDs in params where workflow_id or execution_id is needed):\n"
            for step_id, result in prior_results.items():
                if isinstance(result, dict) and "id" in result:
                    prior_results_section += f"  {step_id} returned id='{result['id']}' name='{result.get('name', '')}'\n"
                elif isinstance(result, list):
                    prior_results_section += f"  {step_id} returned list of {len(result)} items\n"

        # Dynamically inject platform constraints to prevent repeating past mistakes
        constraints_section = ""
        if global_constraints or tool_constraints:
            constraints_section = "\n\nDISCOVERED PLATFORM CONSTRAINTS (CRITICAL -- follow these to prevent runtime failures):\n"
            if global_constraints:
                for c in global_constraints:
                    constraints_section += f"- [GLOBAL] {c}\n"
            if tool_constraints:
                for c in tool_constraints:
                    constraints_section += f"- [TOOL-SPECIFIC] {c}\n"

        # Dynamically inject proven high-level strategies
        strategies_section = ""
        if reusable_strategies:
            strategies_section = "\n\nREUSABLE EXECUTION STRATEGIES:\n"
            for s in reusable_strategies[:5]:
                strategies_section += (
                    f"- Pattern: '{s.get('instruction_pattern', '')[:80]}...'\n"
                    f"  Proven sequence of tools: {s.get('tool_sequence', [])}\n"
                )

        return f"""You are the Planner for an Autonomous n8n Platform Intelligence Agent.

TASK: Decompose natural language instructions into ordered API calls that manage
an n8n workflow automation instance.

AVAILABLE TOOLS (Python functions that call n8n REST API with exact parameters):
{tools_def}

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
2. To update/activate/deactivate/delete a workflow, you need its ID first.
   Use get_workflow_by_name before those operations and set depends_on accordingly.
3. Every node in a create_workflow call needs a unique UUID as its "id" field.
4. Use depends_on to mark steps that need results from a prior step. ALWAYS set
   depends_on when a step needs the ID or output from a prior step.
5. If you see a proven sequence for a similar task in LEARNED FROM PAST RUNS, use it.
6. Never include redundant steps (e.g. getting node types when you already know them).
7. For create_workflow, include uuid.uuid4() calls as string literals in node IDs.
8. If the task requires custom logic, data manipulation, grouping, or reporting (such as grouping executions by workflow name and creating a summary report) that no built-in tool performs, you MUST invent a new, descriptive tool name (e.g., `summarise_executions_by_workflow` or `group_failed_executions`) and specify it. The agent will dynamically synthesise and run this new tool.
9. RESULT CHAINING: If a step needs to use the output or an ID from a prior step, use step placeholders in the parameters: e.g. "{{step_1}}" or "{{step_1.result}}" or "{{step_1.result.id}}" or "{{step_1.result.workflowId}}". For example, if step_1 returns a list of execution dictionaries, and step_2 needs to get the workflow name for the execution's workflowId, set step_2 params to {{ "workflow_id": "{{{{step_1.result.workflowId}}}}" }} and set depends_on to ["step_1"].
10. n8n execution records only contain workflowId (not workflowName or name) — to get workflow details like name, use get_workflow with the workflowId or list_workflows to fetch all workflows.
{memory_section}{prior_results_section}{constraints_section}{strategies_section}

OUTPUT FORMAT: Return ONLY a valid JSON array. No markdown. No prose. Start with [ end with ].
[
  {{
    "id": "step_1",
    "tool": "<tool_name>",
    "params": {{ ... }},
    "description": "<one sentence what this step does>",
    "depends_on": []
  }}
]"""

    def _rule_based_plan(self, instruction: str) -> Optional[List[Step]]:
        """
        Deterministic fast path for simple, well-known commands.

        This ensures demo baseline scenarios ALWAYS work deterministically
        even if the LLM is slow, rate-limited, or temporarily unavailable.
        It also guarantees the learning metric is accurate for these cases
        (always exactly 1 API call, provably consistent).
        """
        text = instruction.lower().strip()

        # -- Workflow listing variants ------------------------------------------
        if re.search(r"\b(list|show|get|display|fetch|give me|what are)\b.{0,30}\bworkflows?\b", text):
            return [
                Step(
                    id="step_1",
                    tool="list_workflows",
                    params={},
                    description="List all workflows in n8n",
                )
            ]

        # -- Execution listing variants -----------------------------------------
        if re.search(r"\b(list|show|get|fetch|display)\b.{0,30}\bexecutions?\b", text) and \
                not re.search(r"\b(fail|error|broken)\b", text):
            return [
                Step(
                    id="step_1",
                    tool="list_executions",
                    params={},
                    description="List recent executions in n8n",
                )
            ]

        # -- Failed execution variants ------------------------------------------
        if (re.search(r"\b(fail|error|broken|bad)\b.{0,30}\bexecutions?\b", text) or \
                re.search(r"\bexecutions?.{0,30}\b(fail|error|broken)\b", text)) and \
                not re.search(r"\b(group|summarise|summary|report)\b", text):
            return [
                Step(
                    id="step_1",
                    tool="get_failed_executions",
                    params={},
                    description="List all error-status executions in n8n",
                )
            ]

        # -- Credential listing ------------------------------------------------
        if re.search(r"\b(list|show|get)\b.{0,30}\bcredentials?\b", text):
            return [
                Step(
                    id="step_1",
                    tool="list_credentials",
                    params={},
                    description="List all stored credentials in n8n",
                )
            ]

        # No deterministic fast path matched -- fall through to LLM
        return None

    def _parse_model_output(self, raw: str) -> Any:
        """Parse JSON from raw LLM output, tolerating markdown wrappers."""
        # Strip markdown code fences
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to find a JSON array
            match = re.search(r'\[.*\]', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            # Try to find a JSON object
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Planner: LLM returned invalid JSON:\n{raw[:500]}")

    def _coerce_step_dict(self, item: Any, index: int) -> Dict[str, Any]:
        """Normalise a single step item from LLM output to a canonical dict."""
        if isinstance(item, str):
            return {
                "id": f"step_{index}",
                "tool": item,
                "params": {},
                "description": f"Call {item}",
                "depends_on": [],
            }

        if not isinstance(item, dict):
            raise ValueError(f"Planner: step {index} is not an object: {item!r}")

        # Handle nested function-call shape: {"function": {"name": "...", "arguments": {...}}}
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
                f"Planner: step {index} missing required fields. "
                f"Keys received: {sorted(item.keys())}"
            )

        return {
            "id": item.get("id") or f"step_{index}",
            "tool": tool,
            "params": params if isinstance(params, dict) else {},
            "description": description,
            "depends_on": item.get("depends_on", []),
        }

    def _normalise_plan_data(self, data: Any, raw: str) -> List[Dict[str, Any]]:
        """Normalise LLM output (any shape) into a list of canonical step dicts."""
        if isinstance(data, dict):
            if isinstance(data.get("steps"), list):
                data = data["steps"]
            elif isinstance(data.get("plan"), list):
                data = data["plan"]
            elif data.get("tool"):
                data = [data]
            elif isinstance(data.get("function"), (dict, str)):
                data = [data]

        if isinstance(data, str):
            data = [data]

        if not isinstance(data, list):
            raise ValueError(f"Planner: expected JSON array of steps, got: {type(data).__name__}")

        normalised = [self._coerce_step_dict(item, index) for index, item in enumerate(data, start=1)]
        if normalised:
            return normalised

        # Last resort: infer from tool names mentioned in raw text
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

        raise ValueError("Planner: LLM returned an empty plan")

    def plan(self, instruction: str,
             past_executions: Optional[List[dict]] = None,
             prior_results: Optional[Dict[str, Any]] = None,
             global_constraints: Optional[List[str]] = None,
             tool_constraints: Optional[List[str]] = None,
             reusable_strategies: Optional[List[dict]] = None) -> List[Step]:
        """
        Returns an ordered list of Steps for the executor to run.

        Args:
            instruction: Natural language instruction from the user.
            past_executions: Similar past runs from execution memory.
            prior_results: Map of step_id → result for context chaining in multi-step plans.
            global_constraints: General n8n platform constraints.
            tool_constraints: Specific tool constraints.
            reusable_strategies: Custom reusable workflow strategies.

        Raises:
            ValueError: If the LLM output cannot be parsed as a valid step list.
            RuntimeError: If the LLM API call fails.
        """
        # Deterministic fast path for known-simple commands
        rule_based = self._rule_based_plan(instruction)
        if rule_based is not None:
            return rule_based

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": self._build_system_prompt(
                        past_executions=past_executions,
                        prior_results=prior_results,
                        global_constraints=global_constraints,
                        tool_constraints=tool_constraints,
                        reusable_strategies=reusable_strategies
                    )
                },
                {
                    "role": "user",
                    "content": f"Decompose this instruction into steps:\n\n{instruction}"
                }
            ],
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        import time
        response = None
        for attempt in range(3):
            try:
                response = requests.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    verify=False,
                    timeout=60,
                )
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                print(f"[Planner] LLM Request attempt {attempt+1} failed: {e}. Retrying in 2s...")
                time.sleep(2)

        if response is None:
            raise RuntimeError("Planner: All LLM API requests timed out or failed.")

        if not response.ok:
            raise RuntimeError(
                f"Planner: LLM API error {response.status_code}: {response.text[:300]}"
            )

        try:
            raw = response.json()["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Planner: unexpected LLM response format: {e}\n{response.text[:300]}")

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
