# Architecture

## What does your memory system store, and why did you structure it that way?

The agent uses two JSON files on disk, each serving a distinct cognitive role
and a different retrieval pattern.

**Execution Memory** (`data/execution_memory.json`) is episodic: it records every
instruction given, the step sequence produced, which tools ran in which order,
how many API calls the run consumed, and whether it succeeded. The design choice
is storing complete step sequences with their outcomes rather than just the
instruction text. This lets the planner retrieve the proven optimal tool ordering
for similar future tasks, which is what produces the measurable reduction in API
calls over repeated runs. Retrieval uses keyword-overlap scoring on the instruction
text: simple, deterministic, zero extra dependencies. A vector database would
retrieve semantically similar text, but we need structured facts — step sequences
and API call counts — not document similarity. The approach is simpler and every
line is explainable.

**Capability Memory** (`data/capability_memory.json`) is semantic: it stores which
tools exist, their cumulative success and failure counts, constraints discovered at
runtime (e.g. "n8n does not support filtering workflows by name via API — must fetch
all and filter locally"), and the source code of tools synthesised at runtime so they
survive session restarts. The planner reads this before every decomposition: it knows
which tools exist, which have low reliability, what ordering constraints apply, and
what synthesised tools are available. Merging both layers would force the planner to
handle two different query patterns — "what have I done?" and "what can I do?" — in
a single data structure, complicating both.

## How does capability synthesis work in your implementation?

When the executor looks up a tool name in the tool registry and finds nothing, it
calls the SynthesisEngine. The engine sends Claude Sonnet 4.6 a structured prompt
specifying the exact function name needed, what it should do in one sentence, and
the expected parameters. Claude returns a Python function that calls the n8n REST
API. The engine compiles the code for syntax validity, execs it in an isolated
namespace, and verifies the function is callable. If these three checks pass, the
function is registered in the live tool registry for the current session and its
source code is written to capability memory for future sessions. The engine retries
up to three times, appending the failure reason to the prompt on each attempt. If
all attempts fail, the step is marked failed with a detailed error message.
Synthesised tools are never assumed to work without testing — only verified tools
are registered.

## What is your learning signal, and what does the agent do differently on run N vs run 1?

The primary signal is **API calls per task**, tracked in `data/learning_metrics.json`
and shown in the React UI chart and `python main.py learning-report`.

On run 1, the planner has no prior context. Claude decomposes the instruction from
first principles, sometimes including redundant steps (fetching node types before
listing workflows when the node type information is not needed) or suboptimal tool
orderings that cause retries. A typical compound task uses 4–6 API calls.

From run 3 onwards, the planner loads similar past executions from execution memory
and identifies the proven step sequence — the specific tool ordering from the most
efficient successful run. It provides this as explicit context in the planning prompt,
so Claude skips redundant steps and uses the ordering that is already known to work.
The constraint layer in capability memory further reduces errors: knowing that n8n
name-based workflow filtering is not supported means the planner routes through
get_workflow_by_name rather than attempting an unsupported parameter. The result is
2–3 API calls for the same task by run 5 — a 40–60% reduction visible as a
decreasing line in the learning chart.