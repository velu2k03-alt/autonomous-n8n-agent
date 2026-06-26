# Architecture

## 1. What does your memory system store, and why did you structure it that way?

We implement a **persistent dual-layer memory system** separated into:
* **Execution Memory** (Episodic): Stores execution logs of every run (instruction, step sequence, API call counts, success/failure status, and metadata). To keep memory bounded and prevent context window bloat, an **Episodic Memory Compactor** runs automatically when records $\ge 5$. It clusters similar execution runs using a Jaccard similarity threshold ($\ge 0.6$), merges similar executions into a single "golden record" with aggregated lessons/constraints, and records the historical learning progress.
* **Capability Memory** (Semantic): Tracks tool registry success/failure counts, discovered constraints, dynamic execution strategies, and code for dynamically synthesised runtime tools.

**Why structured this way**: Splitting episodic runs from semantic capabilities mirrors human cognitive architecture. Execution memory allows the planner to find past plans that worked for similar goals, while capability memory serves as a consolidated registry of what the agent *can* do, what constraints exist (e.g., pagination rules), and what dynamic tools have been compiled and persisted, without polluting the planner with a long list of redundant individual run histories.

---

## 2. How does capability synthesis work in your implementation?

When the planner emits a step requiring a tool not present in the live registry (a capability gap):
1. **Gap Detection**: The executor intercepts the missing tool and invokes the `SynthesisEngine`.
2. **Implementation Generation**: The engine uses an LLM to generate a standalone Python function targeting the n8n REST API.
3. **Rigorous Validation**: The generated code is compiled (`compile()`) and executed in an isolated namespace. We run five validation checks: syntax validity, compilation, caller signature (matching `base_url` and `api_key`), local evaluation, and dry-run static analysis.
4. **Registration & Persistence**: If valid, the function is registered into the active `TOOL_REGISTRY` and saved to `data/capability_memory.json`.
5. **Cross-Session Loading**: On startup, Capability Memory dynamically re-executes and re-registers all synthesised tool source codes, ensuring the agent retains learned capabilities permanently.

---

## 3. What is your learning signal, and what does the agent do differently on run N vs run 1?

Our learning signal is **API calls per task**, tracked in `data/learning_metrics.json` and plotted in the UI.
* **Run 1**: The agent faces a task from first principles. It decomposes the task into steps, possibly incorporating redundant or suboptimal steps (e.g. exploring unrelated list endpoints) or hitting API parameter errors.
* **Run 2**: The agent records the successful step sequence, the exact arguments used, and any discovered constraints (e.g., "cannot filter workflows by name via API, must fetch all and filter locally").
* **Run N (Run 3+)**: Before planning, the agent retrieves the best-performing step sequence from Execution Memory. The planner imports this golden sequence into the LLM context. The LLM is forced to reuse the exact successful tool sequence and apply the discovered constraints. The result is a **40-60% reduction in API calls** (typically going from 4-5 calls down to 2 calls).

### Multi-Agent Decomposition, Confidence, and Rollback
* **Multi-Agent Routing**: Steps are delegated to specialized domain agents (`WorkflowSpecialist`, `ExecutionSpecialist`, `CredentialSpecialist`, `SynthesisSpecialist`).
* **Confidence Scoring**: Each specialist calculates a confidence score ($0.0$ to $1.0$) and writes a rationale before execution based on parameter state and tool history.
* **LIFO Rollback**: Modifying steps capture pre-execution backup states and register compensating actions (e.g., deleting a created workflow, restoring old JSON configuration). If any subsequent step fails (or the user types `rollback`/`undo`), the agent executes the rollback stack in reverse order to restore n8n's original state.