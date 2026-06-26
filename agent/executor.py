import time
from typing import Any, Callable, Dict, List, Optional
from models.step import Step, StepStatus
from models.report import ExecutionReport
from tools import get_tool
from tools.workflows import N8NAPIError
from agent.specialists import get_specialist
from learning.tracker import LearningTracker


class Executor:
    """
    Runs a list of Steps sequentially, respecting dependency ordering.

    Key responsibilities:
    1. Check step dependencies before running each step (deps must be SUCCESS)
    2. Detect capability gaps (tool name not in registry)
    3. Trigger synthesis callback when gap detected, retry after
    4. Inject prior step results into dependent step params (result chaining)
    5. Retry failed steps with exponential back-off (transient + 5xx errors)
    6. Handle partial failures -- never silently skip or swallow errors
    7. Record accurate API call counts and timing per step
    8. Build and return the full ExecutionReport

    Design decision -- sequential vs parallel:
    Steps have dependency ordering. Parallel execution would require a DAG scheduler
    and creates race conditions on n8n state. Sequential is correct and explainable.
    """

    MAX_RETRIES: int = 2              # number of retry attempts after first failure
    RETRY_DELAY_SECONDS: float = 1.0  # initial delay; doubles each retry

    # HTTP status codes that are deterministic (retrying wastes calls)
    NO_RETRY_STATUS_CODES = {400, 401, 403, 404, 409, 422}

    def __init__(self):
        self.rollback_journal: List[Dict[str, Any]] = []

    def _deps_ok(self, step: Step, done: Dict[str, StepStatus]) -> bool:
        """Return True only if all declared dependencies completed with SUCCESS."""
        return all(done.get(dep) == StepStatus.SUCCESS for dep in step.depends_on)

    def _eval_path(self, expr: str, results: Dict[str, Any]) -> Any:
        """Evaluate a path-based placeholder expression (e.g. step_1.result.workflowId)."""
        expr = expr.replace("{", "").replace("}", "").strip()
        import re
        match = re.match(r"^(step_\d+)(.*)$", expr)
        if not match:
            return None
        step_id, path_str = match.groups()
        if step_id not in results:
            return None

        current = results[step_id]
        path_str = path_str.strip()
        if path_str in ("", ".result"):
            return current
        if path_str == ".id":
            return self._extract_id_or_value(current)

        if path_str.startswith("."):
            path_str = path_str[1:]
        path_str = path_str.replace("[", ".").replace("]", "")
        parts = [p for p in path_str.split(".") if p]

        for part in parts:
            if part == "result":
                continue
            if isinstance(current, list):
                try:
                    idx = int(part)
                    if 0 <= idx < len(current):
                        current = current[idx]
                        continue
                except ValueError:
                    pass
                if current:
                    first = current[0]
                    if isinstance(first, dict):
                        found = False
                        for k in (part, part.lower(), part.upper()):
                            for dict_key in first:
                                if dict_key.lower().replace("_", "") == k.lower().replace("_", ""):
                                    current = first[dict_key]
                                    found = True
                                    break
                            if found:
                                break
                        if found:
                            continue
                return None
            elif isinstance(current, dict):
                found = False
                for k in (part, part.lower(), part.upper()):
                    for dict_key in current:
                        if dict_key.lower().replace("_", "") == k.lower().replace("_", ""):
                            current = current[dict_key]
                            found = True
                            break
                    if found:
                        break
                if not found:
                    return None
            else:
                return None
        return current

    def _resolve_placeholders(self, val: Any, results: Dict[str, Any]) -> Any:
        """Recursively resolve step placeholders in any nested structure (dict, list, str, etc.)."""
        import re

        if isinstance(val, dict):
            return {k: self._resolve_placeholders(v, results) for k, v in val.items()}

        if isinstance(val, list):
            return [self._resolve_placeholders(item, results) for item in val]

        if isinstance(val, str):
            # Check if it contains any step reference
            matches = re.findall(r"step_\d+", val)
            if not matches:
                return val

            # Case 1: Exact placeholder matching (e.g. "{{step_1.result.workflowId}}" or "{{step_1}}")
            # If the entire string is just a single step expression, evaluate it directly to preserve type
            clean = val.replace("{", "").replace("}", "").strip()
            if re.match(r"^step_\d+[\w\d\.\[\]]*$", clean):
                injected = self._eval_path(clean, results)
                if injected is not None:
                    print(f"         [Chain-A-Exact] Resolved '{val}' -> {injected!r}")
                    return injected

            # Case 2: String interpolation (e.g. "Workflow ID is {{step_1.result.id}}")
            new_val = val
            # Find all potential bracketed/braced expressions
            exprs = re.findall(r"\{\{([^}]+)\}\}", val)
            if not exprs:
                # If no double braces, try step_\d+ directly
                exprs = matches
            for expr in exprs:
                injected = self._eval_path(expr, results)
                if injected is not None:
                    # Find how the expr matches in new_val
                    for pat in [f"{{{{{expr}}}}}", expr]:
                        if pat in new_val:
                            new_val = new_val.replace(pat, str(injected))
                            print(f"         [Chain-A-Sub] Replaced '{pat}' -> '{injected}' in parameter")
            return new_val

        return val

    def _inject_prior_results(self, step: Step, results: Dict[str, Any]) -> None:
        """
        Result chaining: map prior step outputs into this step's params.

        Two patterns supported:

        Pattern A -- step ID placeholder (planner sets param value = "step_1" or "{{step_1.result.id}}"):
          step_2.params = {"workflow_id": "{{step_1.result.id}}"}
          step_1.result = {"id": "abc123", "name": "My Workflow"}
          -> step_2.params becomes {"workflow_id": "abc123"}

        Pattern B -- None placeholder (planner leaves param as null):
          step_2.params = {"workflow_id": None}
          step_2.depends_on = ["step_1"]
          -> look at step_1 result and inject its id if it has one

        This makes compound instructions work without the planner knowing
        runtime IDs -- the executor fills them in from actual results.
        """
        if not results:
            return

        # 1. Recursively resolve any step placeholders (Pattern A and variants)
        step.params = self._resolve_placeholders(step.params, results)

        # 2. Pattern B: None placeholder -- try to fill from depends_on results
        for param_key, param_val in list(step.params.items()):
            if param_val is None and step.depends_on:
                for dep_id in step.depends_on:
                    if dep_id in results:
                        prior_result = results[dep_id]
                        injected = self._extract_id_or_value(prior_result)
                        if injected is not None and param_key in ("workflow_id", "execution_id", "credential_id", "id"):
                            step.params[param_key] = injected
                            print(f"         [Chain-B] {param_key} = {injected!r} (from {dep_id})")
                            break

    def _extract_id_or_value(self, result: Any) -> Any:
        """Extract the most useful value from a prior step's result."""
        if isinstance(result, dict):
            return result.get("id")  # Most n8n API responses have an id field
        if isinstance(result, (str, int, float, bool)):
            return result
        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, dict):
                return first.get("id")
        return None

    def _should_retry(self, error: Exception) -> bool:
        """
        Determine if an error is transient and worth retrying.

        N8NAPIError with 4xx status = deterministic, don't retry.
        N8NAPIError with 5xx status = server-side transient, retry.
        Generic Exception = transient (network, timeout), retry.
        """
        if isinstance(error, N8NAPIError):
            return error.status_code not in self.NO_RETRY_STATUS_CODES
        return True  # All other exceptions are assumed transient

    def _normalize_step_params(self, step: Step, fn: Callable) -> None:
        """
        Defensively align step.params keys with the target function's expected parameters.
        This handles minor planner deviations (e.g. passing workflow_name instead of name,
        or passing a single workflow dict instead of flat arguments).
        """
        import inspect
        import json
        try:
            sig = inspect.signature(fn)
            fn_params = sig.parameters
        except Exception:
            return  # if signature cannot be inspected, do nothing

        # 1. Flatten nested dictionary if the function expects flat keys but we got a single dictionary
        # Example: create_workflow expects name, nodes, connections but LLM passed {'workflow': {'name': ..., 'nodes': ...}}
        if len(step.params) == 1:
            single_key = list(step.params.keys())[0]
            single_val = step.params[single_key]
            if isinstance(single_val, dict) and single_key in ("workflow", "workflow_data", "data", "body", "params"):
                # If the function does NOT accept the single_key directly, but accepts the keys inside it, flat-map them!
                if single_key not in fn_params:
                    print(f"         [Normalize] Flattening nested dict parameter '{single_key}' into step.params")
                    nested_dict = step.params.pop(single_key)
                    for k, v in nested_dict.items():
                        step.params[k] = v

        # Also support stringified JSON dict/list in the parameter (sometimes Llama/Claude stringifies it)
        if len(step.params) == 1:
            single_key = list(step.params.keys())[0]
            single_val = step.params[single_key]
            if isinstance(single_val, str) and single_key in ("workflow", "workflow_data", "data", "body", "params"):
                try:
                    nested_dict = json.loads(single_val)
                    if isinstance(nested_dict, dict) and single_key not in fn_params:
                        print(f"         [Normalize] Deserializing and flattening '{single_key}' into step.params")
                        step.params.pop(single_key)
                        for k, v in nested_dict.items():
                            step.params[k] = v
                except Exception:
                    pass

        # 2. Map common parameter aliases
        alias_maps = {
            "name": ["workflow_name", "wf_name", "title"],
            "workflow_id": ["id", "wf_id", "workflowId"],
            "execution_id": ["id", "exec_id", "executionId"],
            "credential_id": ["id", "cred_id", "credentialId"],
        }

        for target, aliases in alias_maps.items():
            if target in fn_params and target not in step.params:
                for alias in aliases:
                    if alias in step.params:
                        val = step.params.pop(alias)
                        step.params[target] = val
                        print(f"         [Normalize] Mapped alias param: {alias} -> {target} ({val!r})")
                        break

        # 3. Clean up extra parameters that the function doesn't accept and doesn't have **kwargs
        has_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in fn_params.values())
        if not has_var_kwargs:
            extra_keys = [k for k in step.params.keys() if k not in fn_params]
            if extra_keys:
                print(f"         [Normalize] Removing unsupported parameter(s): {extra_keys}")
                for k in extra_keys:
                    step.params.pop(k)

    def _run_step_with_retry(self, step: Step, fn: Callable) -> None:
        """
        Execute a single step with exponential back-off retry on transient failures.

        Mutates step fields in-place:
          step.status, step.result, step.error, step.api_calls_made, step.duration_seconds
        """
        # Align step.params with fn's signature
        self._normalize_step_params(step, fn)

        last_error: Optional[str] = None
        delay = self.RETRY_DELAY_SECONDS
        total_calls = 0
        t_start = time.time()

        for attempt in range(1 + self.MAX_RETRIES):
            if attempt > 0:
                print(f"         [Retry {attempt}/{self.MAX_RETRIES}] waiting {delay:.1f}s ...")
                time.sleep(delay)
                delay *= 2

            try:
                total_calls += 1
                result = fn(**step.params)
                step.status = StepStatus.SUCCESS
                step.result = result
                step.error = None
                step.api_calls_made = total_calls
                step.duration_seconds = time.time() - t_start
                return

            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if not self._should_retry(e):
                    print(f"         [No retry] deterministic error: {e}")
                    step.status = StepStatus.FAILED
                    step.error = last_error
                    step.api_calls_made = total_calls
                    step.duration_seconds = time.time() - t_start
                    return
                else:
                    print(f"         [Attempt {attempt + 1} failed] {last_error}")

        # All retries exhausted
        step.status = StepStatus.FAILED
        step.error = f"Failed after {1 + self.MAX_RETRIES} attempts. Last error: {last_error}"
        step.api_calls_made = total_calls
        step.duration_seconds = time.time() - t_start

    def _trigger_rollback(self, report: ExecutionReport) -> None:
        """Undo all registered compensating actions in reverse order (LIFO)."""
        if not self.rollback_journal:
            print("         [Rollback] No rollback actions to execute.")
            return

        print("\n  " + "!" * 60)
        print("  [ROLLBACK ACTIVATED] Step execution failed. Reverting changes...")
        print("  " + "!" * 60)
        
        report.rollback_occurred = True
        
        while self.rollback_journal:
            entry = self.rollback_journal.pop()
            step_id = entry["step_id"]
            action = entry["action"]
            tool_name = action["tool"]
            params = action["params"]
            description = action["description"]
            
            print(f"  [Rollback] Compensating {step_id}: {description}")
            fn = get_tool(tool_name)
            if fn is None:
                err = f"Failed to find rollback tool '{tool_name}'"
                print(f"             {err}")
                report.rollback_log.append(f"FAILED: {description} ({err})")
                continue
                
            try:
                # Run the compensating tool
                result = fn(**params)
                msg = f"Undid step {step_id}: {description}"
                print(f"             [OK] {msg}")
                report.rollback_log.append(msg)
            except Exception as e:
                err = f"Rollback error: {e}"
                print(f"             [ERROR] {err}")
                report.rollback_log.append(f"FAILED: {description} ({err})")
                
        print("  " + "!" * 60 + "\n")

    def execute(self, steps: List[Step], instruction: str,
                on_capability_gap: Optional[Callable] = None) -> ExecutionReport:
        """
        Execute a plan (list of Steps) and return a complete ExecutionReport.
        """
        self.rollback_journal = []
        report = ExecutionReport(instruction=instruction, steps=steps)
        done: Dict[str, StepStatus] = {}   # {step_id: StepStatus}
        results: Dict[str, Any] = {}       # {step_id: result} for chaining
        t0 = time.time()

        # Load tool stats for confidence calculation
        try:
            tracker = LearningTracker()
            tool_stats = tracker.get_data().get("tool_stats", {})
        except Exception:
            tool_stats = {}

        for step in steps:
            # Route step to specialist agent
            specialist = get_specialist(step.tool)
            step.assigned_agent = specialist.name

            # 1. Dependency check
            if step.depends_on and not self._deps_ok(step, done):
                step.status = StepStatus.SKIPPED
                step.error = (
                    f"Dependency not met: required steps {step.depends_on} "
                    f"must all succeed first."
                )
                done[step.id] = StepStatus.SKIPPED
                step.confidence_score = 0.0
                step.confidence_reason = "Dependency skipped"
                print(f"  [SKIP] {step.id} [{specialist.name}]: {step.description}")
                print(f"         Reason: {step.error}")
                continue

            # 2. Result chaining -- inject prior step outputs into params
            self._inject_prior_results(step, results)

            # Calculate confidence score dynamically
            confidence, reason = specialist.calculate_confidence(step.tool, step.params, tool_stats)
            step.confidence_score = confidence
            step.confidence_reason = reason
            print(f"         [{specialist.name}] Assessed confidence: {confidence*100:.0f}% | Reason: {reason}")

            # Static pre-execution validation
            val_ok, val_err = specialist.validate_params(step.tool, step.params)
            if not val_ok:
                step.status = StepStatus.FAILED
                step.error = f"Static validation failed: {val_err}"
                done[step.id] = StepStatus.FAILED
                print(f"  [FAIL] {step.id} [{specialist.name}]: {step.error}")
                self._trigger_rollback(report)
                break

            # 3. Tool lookup
            fn = get_tool(step.tool)

            # 4. Capability gap handling
            if fn is None:
                print(f"  [GAP]  Unknown tool: '{step.tool}'")
                if on_capability_gap:
                    synthesised = on_capability_gap(step)
                    if synthesised:
                        fn = get_tool(step.tool)
                        report.synthesis_occurred = True
                        report.synthesised_tool_name = step.tool
                        print(f"  [SYNTH] '{step.tool}' successfully synthesised and registered")

                if fn is None:
                    step.status = StepStatus.FAILED
                    step.error = (
                        f"Capability gap: tool '{step.tool}' not found in registry "
                        f"and synthesis failed. Cannot execute this step."
                    )
                    done[step.id] = StepStatus.FAILED
                    print(f"  [FAIL] {step.id} [{specialist.name}]: {step.error}")
                    self._trigger_rollback(report)
                    break

            # Capture backup state for rollback
            pre_context = specialist.pre_execute_hook(step.tool, step.params)

            # 5. Execute with retry
            step.status = StepStatus.RUNNING
            print(f"  [RUN]  {step.id} [{specialist.name}]: {step.description}  [tool={step.tool}]")
            if step.params:
                # Show params (mask long values for readability)
                display_params = {
                    k: (str(v)[:60] + "..." if isinstance(v, (str, dict, list)) and len(str(v)) > 60 else v)
                    for k, v in step.params.items()
                }
                print(f"         Params: {display_params}")

            self._run_step_with_retry(step, fn)

            done[step.id] = step.status

            if step.status == StepStatus.SUCCESS:
                results[step.id] = step.result
                print(f"  [OK]   {step.id} [{specialist.name}]: {step.description}")

                # Register compensating action for rollback if successful
                rollback_act = specialist.get_rollback_action(step.tool, step.params, step.result, pre_context)
                if rollback_act:
                    self.rollback_journal.append({
                        "step_id": step.id,
                        "action": rollback_act
                    })
                    step.rollback_registered = True
                    report.rollback_actions.append(rollback_act)
                    print(f"         [Rollback] Registered compensating action: {rollback_act['description']}")

                # Print actual API result content — not just a count
                result = step.result
                if isinstance(result, list):
                    print(f"         → {len(result)} items returned:")
                    for item in result[:5]:
                        if isinstance(item, dict):
                            wf_id = str(item.get("id", ""))[:8]
                            name = item.get("name", item.get("workflowId", "unknown"))
                            active = item.get("active", "")
                            status = item.get("status", "")
                            if name and active != "":
                                print(f"             [{wf_id}] '{name}'  active={active}")
                            elif status:
                                print(f"             [{wf_id}] status={status}")
                            else:
                                print(f"             {item}")
                    if len(result) > 5:
                        print(f"             ... and {len(result) - 5} more")
                elif isinstance(result, dict):
                    wf_id = str(result.get("id", ""))[:8]
                    name = result.get("name", "")
                    active = result.get("active", "")
                    status = result.get("status", "")
                    if name:
                        print(f"         → [{wf_id}] '{name}'  active={active}")
                    elif status:
                        print(f"         → status: {status}")
                    elif wf_id:
                        print(f"         → id: {wf_id}")
            else:
                print(f"  [FAIL] {step.id} [{specialist.name}]: {step.error}")
                self._trigger_rollback(report)
                break

        # 6. Aggregate report
        report.total_api_calls = sum(s.api_calls_made for s in steps)
        report.total_duration_seconds = time.time() - t0

        non_skipped = [s for s in steps if s.status != StepStatus.SKIPPED]
        report.success = bool(non_skipped) and all(
            s.status == StepStatus.SUCCESS for s in non_skipped
        )

        failed_steps = [s for s in steps if s.status == StepStatus.FAILED]
        if failed_steps:
            msgs = "; ".join(f"'{s.id}': {s.error}" for s in failed_steps)
            report.failure_reason = msgs

        return report