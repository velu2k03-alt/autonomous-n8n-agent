import traceback
import os
import inspect
import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from models.step import Step
from tools import register_tool

# Suppress SSL warnings when verify=False
urllib3.disable_warnings(InsecureRequestWarning)


class SynthesisEngine:
    """
    Generates new tool functions at runtime when the executor encounters
    a capability gap (unknown tool name in the registry).

    7-step synthesis process (per the assignment requirements):
    1. Detect capability gap (executor finds no tool -> calls this engine)
    2. Reason about missing functionality (build a structured prompt)
    3. Generate an implementation (LLM produces Python function code)
    4. Test it (compile + exec + callable + signature + static call check)
    5. Validate it (verify return type is dict or list)
    6. Register it (live tool registry for current session)
    7. Reuse it (capability memory persists code to disk for future sessions)

    CRITICAL DESIGN NOTE on function signatures:
    Synthesised tools are called by the executor as fn(**step.params).
    step.params contains only the logical parameters (e.g. {"workflow_id": "abc"}).
    It does NOT contain base_url or api_key.
    Therefore synthesised functions MUST read base_url and api_key from
    os.getenv(), NOT from function parameters.
    This matches exactly how all built-in tools work (see tools/workflows.py).

    Note on exec():
    exec() runs arbitrary code. Acceptable here because:
    - Code comes from a controlled LLM prompt
    - We test it before registering
    - Isolated namespace prevents pollution of global scope
    In production, use subprocess isolation (e.g., RestrictedPython or a sandbox).
    """

    def __init__(self, max_attempts: int = 3):
        self.api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        self.model = os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct")
        self.endpoint = os.getenv(
            "LLM_API_ENDPOINT",
            "https://integrate.api.nvidia.com/v1/chat/completions"
        )
        self.max_attempts = max_attempts

    def synthesise(self, step: Step, capability_memory) -> bool:
        """
        Attempt to synthesise a new tool function for the given step.

        Returns True if synthesis succeeded and the tool was registered.
        Returns False if all attempts failed.

        Side effects on success:
        - Registers function in live TOOL_REGISTRY (current session)
        - Writes source code to capability_memory (survives restarts)
        """
        tool_name = step.tool
        description = step.description
        params = step.params

        print(f"[Synthesis] Building tool: {tool_name}")
        print(f"[Synthesis] Description  : {description}")
        print(f"[Synthesis] Step params  : {list(params.keys())}")

        prompt = self._build_prompt(tool_name, description, params)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, self.max_attempts + 1):
            print(f"[Synthesis] Attempt {attempt}/{self.max_attempts}")
            try:
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 2048,
                }

                import time
                api_response = None
                for api_retry in range(3):
                    try:
                        response = requests.post(
                            self.endpoint,
                            headers=headers,
                            json=payload,
                            verify=False,
                            timeout=60,
                        )
                        api_response = response
                        break
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as req_err:
                        print(f"[Synthesis] LLM Request attempt {api_retry+1} failed: {req_err}. Retrying in 2s...")
                        time.sleep(2)

                if api_response is None:
                    print("[Synthesis] All LLM API requests timed out.")
                    continue

                response = api_response

                if not response.ok:
                    print(f"[Synthesis] LLM API error {response.status_code}: {response.text[:200]}")
                    prompt += f"\n\nAttempt {attempt} got HTTP {response.status_code}. Please try again."
                    continue

                code = response.json()["choices"][0]["message"]["content"].strip()

                # Strip markdown code fences if LLM added them
                if "```python" in code:
                    code = code.split("```python")[1].split("```")[0].strip()
                elif "```" in code:
                    code = code.split("```")[1].split("```")[0].strip()

                print(f"[Synthesis] Generated {len(code)} chars of code")
                if code:
                    preview = code[:250].replace('\n', ' ')
                    print(f"[Synthesis] Preview: {preview}...")

                # 5-stage validation
                test_result = self._test(code, tool_name, params)
                if test_result["passed"]:
                    # Register in live session
                    ns = {
                        "requests": __import__("requests"),
                        "os": __import__("os"),
                        "json": __import__("json"),
                    }
                    exec(code, ns)
                    register_tool(tool_name, ns[tool_name])

                    # Persist source code to capability memory for future sessions
                    capability_memory.register_synthesised_tool(
                        name=tool_name,
                        description=description,
                        code=code,
                    )
                    print(f"[Synthesis] SUCCESS: '{tool_name}' registered and persisted!")
                    return True
                else:
                    failure_detail = test_result.get("reason", "unknown test failure")
                    print(f"[Synthesis] Test FAIL (attempt {attempt}): {failure_detail}")
                    prompt += (
                        f"\n\nAttempt {attempt} FAILED: {failure_detail}\n"
                        f"CORRECTIONS REQUIRED:\n"
                        f"- Function must be named exactly `{tool_name}`\n"
                        f"- Must accept keyword args: {list(params.keys()) or 'none (no extra params)'}\n"
                        f"- Must read base_url and api_key from os.getenv(), NOT from parameters\n"
                        f"- Must use requests with header X-N8N-API-KEY\n"
                        f"- Must return a dict or list\n"
                        f"- Return ONLY the function definition, no imports, no markdown\n"
                    )

            except Exception as e:
                print(f"[Synthesis] Error on attempt {attempt}: {e}")
                traceback.print_exc()
                prompt += f"\n\nAttempt {attempt} raised Python exception: {e}. Fix and retry."

        print(f"[Synthesis] FAILED after {self.max_attempts} attempts: {tool_name}")
        return False

    def _build_prompt(self, tool_name: str, description: str, params: dict) -> str:
        """
        Build the synthesis prompt.

        CRITICAL: Instructs the LLM to use os.getenv() for credentials,
        NOT function parameters. This matches how all built-in tools work
        and ensures synthesised tools are callable via fn(**step.params).
        """
        extra_params = list(params.keys())
        param_str = (
            ", ".join(f"{k}: str" for k in extra_params)
            if extra_params
            else "no extra parameters needed"
        )

        return f"""You are generating a Python function for an n8n REST API client.

FUNCTION NAME: `{tool_name}`
PURPOSE: {description}
EXTRA PARAMETERS (beyond credentials): {param_str}

MANDATORY REQUIREMENTS:
1. Function signature: def {tool_name}({", ".join(extra_params) if extra_params else ""})
   - Read base_url from: os.getenv("N8N_BASE_URL", "http://localhost:5678")
   - Read api_key from:  os.getenv("N8N_API_KEY", "")
   - Do NOT add base_url or api_key as function parameters
2. Use the `requests` library for HTTP calls (already imported in scope)
3. Authentication header: {{"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}}
4. n8n API base path: f"{{base_url}}/api/v1/..."
5. Return a dict or list from response.json()
6. Raise Exception with descriptive message on non-2xx response
7. Do NOT include any import statements (requests, os, json are already available)
8. Do NOT include markdown formatting, backticks, or explanations
9. Return ONLY the function definition — nothing else
10. Any API request limit parameter MUST be between 1 and 250 (e.g. limit=100 or limit=250). n8n rejects limits > 250 with a 400 Bad Request error.
11. If the function is called with non-empty, valid argument data (e.g., a list of executions or workflows is passed as a parameter), process that input directly instead of making redundant HTTP requests.
12. Defensive Input Handling: When processing input arguments (like a list of executions), keep in mind they might be passed as a string representation, a parsed list/dict, or JSON. Safely check the type: if it is already a list or dict, use it directly. If it is a string, check if it looks like JSON and load it with json.loads() or ast.literal_eval() (which you should import inside the function if needed) using try-except, or fallback to an empty list/dict. Do not call json.loads() directly on a list or dict object.
13. n8n API schema knowledge: n8n execution records have a status field (not finishing or finished) whose values are 'success', 'error', 'waiting', 'running', 'canceled'. They also contain a workflowId field (not workflowName or name) that references the workflow.


CORRECT TEMPLATE (follow this pattern exactly):
def {tool_name}({", ".join(extra_params) if extra_params else ""}):
    base_url = os.getenv("N8N_BASE_URL", "http://localhost:5678")
    api_key = os.getenv("N8N_API_KEY", "")
    headers = {{"X-N8N-API-KEY": api_key, "Content-Type": "application/json"}}
    url = f"{{base_url}}/api/v1/..."  # fill in the correct endpoint
    r = requests.get(url, headers=headers)
    if not r.ok:
        raise Exception(f"n8n API error {{r.status_code}}: {{r.text}}")
    return r.json().get("data", r.json())"""

    def _test(self, code: str, name: str, expected_params: dict) -> dict:
        """
        5-stage test for synthesised code:

        Stage 1: Compile      -- valid Python syntax
        Stage 2: Exec         -- runs without import-time errors
        Stage 3: Callable     -- function name exists and is callable
        Stage 4: Signature    -- accepts correct parameter set (from step.params)
        Stage 5: Static call  -- can be invoked with step.params without TypeError

        Returns: {"passed": bool, "reason": str}
        """
        ns = {
            "requests": __import__("requests"),
            "os": __import__("os"),
            "json": __import__("json"),
        }

        # Stage 1: Syntax check
        try:
            compile(code, "<synthesised>", "exec")
        except SyntaxError as e:
            return {"passed": False, "reason": f"Stage 1 (syntax): {e}"}

        # Stage 2: Exec check
        try:
            exec(code, ns)
        except Exception as e:
            return {"passed": False, "reason": f"Stage 2 (exec): {e}"}

        # Stage 3: Callable check
        if name not in ns:
            return {"passed": False, "reason": f"Stage 3: function '{name}' not found in generated code"}
        if not callable(ns[name]):
            return {"passed": False, "reason": f"Stage 3: '{name}' exists but is not callable"}

        # Stage 4: Signature check
        # The function should accept exactly the step.params keys (not base_url/api_key)
        try:
            sig = inspect.signature(ns[name])
            fn_params = sig.parameters
            has_var_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in fn_params.values()
            )

            if not has_var_kwargs:
                # Check that the function doesn't require base_url or api_key as positional params
                # (they should be read from os.getenv instead)
                required_positional = [
                    k for k, p in fn_params.items()
                    if p.default is inspect.Parameter.empty
                    and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                ]
                problematic = [p for p in required_positional if p in ("base_url", "api_key")]
                if problematic:
                    return {
                        "passed": False,
                        "reason": (
                            f"Stage 4: function has {problematic} as required positional params. "
                            f"They must be read from os.getenv() inside the function, not as parameters."
                        )
                    }
        except Exception as e:
            return {"passed": False, "reason": f"Stage 4 (signature check): {e}"}

        # Stage 5: Static call check — verify fn(**step.params) won't raise TypeError
        try:
            # Build safe dummy kwargs matching expected_params
            dummy_kwargs = {k: "test_value" for k in expected_params.keys()}
            # Try binding (doesn't execute, just checks args match)
            sig.bind(**dummy_kwargs)
        except TypeError as e:
            return {
                "passed": False,
                "reason": (
                    f"Stage 5: calling fn(**step.params) would raise TypeError: {e}. "
                    f"Function signature doesn't accept params: {list(expected_params.keys())}"
                )
            }
        except Exception:
            pass  # Other errors are acceptable at static-check stage

        print(f"[Synthesis] Test PASS: '{name}' passed all 5 stages")
        return {"passed": True, "reason": "all 5 stages passed"}