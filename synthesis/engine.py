import traceback
import os
import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from models.step import Step
from tools import register_tool

# Suppress SSL warnings when verify=False
urllib3.disable_warnings(InsecureRequestWarning)

class SynthesisEngine:
    """
    Generates new tool functions at runtime using NVIDIA's API when the executor
    encounters a capability gap.
    """

    def __init__(self, max_attempts: int = 3):
        self.api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        self.model = "meta/llama-3.3-70b-instruct"
        self.endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"
        self.max_attempts = max_attempts

    def synthesise(self, step: Step, capability_memory) -> bool:
        tool_name = step.tool
        description = step.description
        params = step.params

        print(f"[Synthesis] Building tool: {tool_name}")
        print(f"[Synthesis] Description: {description}")

        prompt = self._build_prompt(tool_name, description, params)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        for attempt in range(1, self.max_attempts + 1):
            print(f"[Synthesis] Attempt {attempt}/{self.max_attempts}")
            try:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 2048
                }
                
                response = requests.post(self.endpoint, headers=headers, json=payload, verify=False)
                if not response.ok:
                    print(f"[Synthesis] NVIDIA API error: {response.text}")
                    continue

                code = response.json()["choices"][0]["message"]["content"].strip()

                # Strip markdown code fences
                if "```python" in code:
                    code = code.split("```python")[1].split("```")[0].strip()
                elif "```" in code:
                    code = code.split("```")[1].split("```")[0].strip()

                print(f"[Synthesis] Generated {len(code)} characters of code.")

                if self._test(code, tool_name):
                    # Register in live session
                    ns = {"requests": __import__("requests"), "os": __import__("os")}
                    exec(code, ns)
                    register_tool(tool_name, ns[tool_name])

                    # Write to persistent Capability Memory
                    capability_memory.register_synthesised_tool(
                        name=tool_name,
                        description=description,
                        code=code,
                    )
                    print(f"[Synthesis] SUCCESS: {tool_name} successfully registered!")
                    return True

                # Retry feedback loop
                prompt += (
                    f"\n\nAttempt {attempt} failed structural tests. "
                    f"Ensure the function is named exactly `{tool_name}`, "
                    f"accepts keyword arguments matching {list(params.keys())}, "
                    f"uses requests library with X-N8N-API-KEY header, "
                    f"and returns a valid dictionary or list."
                )

            except Exception as e:
                print(f"[Synthesis] Error on attempt {attempt}: {e}")
                traceback.print_exc()

        print(f"[Synthesis] FAILED after {self.max_attempts} attempts: {tool_name}")
        return False

    def _build_prompt(self, tool_name: str, description: str, params: dict) -> str:
        return f"""You are generating a Python function for an n8n REST API client.

FUNCTION NAME: `{tool_name}`
PURPOSE: {description}
EXTRA PARAMETERS (beyond base_url and api_key): {list(params.keys())}

REQUIREMENTS:
1. Signature: def {tool_name}(base_url: str, api_key: str, **kwargs)
   OR: def {tool_name}({", ".join(["base_url: str", "api_key: str"] + list(params.keys()))})
2. Use the `requests` library (already imported in scope)
3. Authentication header: {{"X-N8N-API-KEY": api_key}}
4. n8n API base path: f"{{base_url}}/api/v1/..."
5. Return dict or list from response.json()
6. Raise Exception with descriptive message on non-2xx response

Return ONLY the executable Python function definition block. Do not provide markdown code blocks (```python). Do not explain or write comments outside of the code."""

    def _test(self, code: str, name: str) -> bool:
        try:
            compile(code, "<synthesised>", "exec")
            ns = {"requests": __import__("requests"), "os": __import__("os")}
            exec(code, ns)
            if name not in ns:
                return False
            if not callable(ns[name]):
                return False
            return True
        except Exception as e:
            print(f"[Synthesis Test Error] {e}")
            return False