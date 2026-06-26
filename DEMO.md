# Demo Script

This document details the three instructions you will run live on the walkthrough call, and what the agent is expected to do for each.

---

## Service Startup Checklist
Before the call, ensure your environment is running:

```powershell
# Terminal 1 — Start n8n
docker compose up -d

# Terminal 2 — Start Backend Server
venv\Scripts\activate
python main.py serve

# Terminal 3 — Start React UI
cd frontend
npm run dev
```

Open the following browser tabs:
* **Dashboard**: `http://localhost:5173/`
* **n8n Editor**: `http://localhost:5678/`

---

## Instruction 1: Compound Task with Routing & Confidence
This demonstration shows multi-agent decomposition, domain routing, and confidence scoring.

### Query to Run
```text
Find the Schedule Logger workflow, deactivate it, then create a new workflow called Daily Ping that runs every day at 9am, then activate it
```

### What the Agent Does
1. **Multi-Agent Routing**: The planner decomposes the instruction into steps. Steps are routed to the **Workflow Specialist**.
2. **Confidence Assessment**: The specialist evaluates the parameters (checking if dependencies are resolved) and historical success rates, printing a dynamic confidence score (e.g. `100%`) and rationale.
3. **Execution**: The agent runs the steps sequentially.

---

## Instruction 2: Rollback & Reverting State Modification
This demonstration shows how the agent protects n8n configuration states using its LIFO rollback journal.

### Method A: Automated Failure Rollback
Run the dedicated rollback test script:
```bash
venv\Scripts\python.exe scratch/test_rollback.py
```
* **Expected behavior**: The Workflow Specialist creates a workflow and registers a compensating `delete_workflow` step in the LIFO journal. The next step fails (due to a non-existent ID). The rollback engine intercepts the failure, executes the compensating action in reverse order, and deletes the workflow, leaving n8n clean.

### Method B: Manual User Rollback
In the React UI query bar, type:
```text
rollback
```
* **Expected behavior**: The agent recovers the modified workflow state from the previous run and undoes it (e.g., reactivating the deactivated workflow or deleting created workflows), printing `[ROLLBACK] Reverting modifications from previous run`.

---

## Instruction 3: Synthesis & Episodic Memory Compaction
This demonstration shows dynamic tool synthesis for novel tasks and memory compaction.

### Query to Run (triggers Synthesis)
```text
Summarise all workflow executions by status
```
* **Expected behavior**: The agent detects a capability gap for a workflow status summary tool. The `SynthesisEngine` generates, tests, and registers `summarise_executions_by_workflow`. The tool is persisted under `data/capability_memory.json` for future runs.

### Triggering Memory Compaction
Run the compaction script to show how logs are consolidated:
```bash
venv\Scripts\python.exe scratch/test_compaction.py
```
* **Expected behavior**: Adding 5 similar execution logs triggers the **Episodic Memory Compactor**. It clusters queries using Jaccard similarity, merges duplicates into a single golden execution record, and reduces database records (e.g., from 14 down to 5), ensuring the context window remains lightweight.