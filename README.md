# Autonomous n8n Platform Intelligence Agent

**Watermelon Software Recruitment Assignment — 2026**

An autonomous Python agent that receives natural language instructions and manages n8n workflows programmatically via the n8n REST API — creating, updating, activating, monitoring, and triggering them without any manual UI interaction.

---

## What this does

```
User: "find the Schedule Logger workflow, deactivate it, then create a new workflow
       called Daily Ping that runs every day at 9am and sends an HTTP request to
       https://httpbin.org/post, then activate it"

Agent:
  [Memory] 3 similar past runs loaded
  [Memory] Optimal proven sequence: ['get_workflow_by_name', 'deactivate_workflow', 'create_workflow', 'activate_workflow']
  [Planner] 4 steps produced
  [Executor] Running steps...
    [OK] step_1: Find Schedule Logger → id=abc123
    [OK] step_2: Deactivate it
    [OK] step_3: Create Daily Ping workflow → id=xyz789
    [OK] step_4: Activate Daily Ping
  Result: ✓ SUCCESS | 4 API calls | 2.1s
```

---

## Architecture

Three-layer system:

```
CLI / React UI / n8n Webhook
         ↓
    FastAPI (port 8000)
         ↓
    Agent Core
    ├── Planner (LLM → Step list, memory-informed)
    ├── Executor (runs steps, retries, result chaining)
    ├── Execution Memory (what I have done)
    ├── Capability Memory (what I can do)
    ├── Synthesis Engine (builds missing tools at runtime)
    └── Learning Tracker (measures API call reduction)
         ↓
    n8n REST API (port 5678, Docker + SQLite)
```

See **ARCHITECTURE.md** for the full design rationale.

---

## Quick start

### Prerequisites
- Windows 10/11 with Docker Desktop (WSL2 backend)
- Python 3.10+
- Node.js 18+
- NVIDIA API key (free: [build.nvidia.com](https://build.nvidia.com)) or Anthropic API key

### 1. Start n8n
```powershell
docker compose up -d
# Verify: docker ps → should show n8n running on port 5678
```

### 2. Set up Python environment
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment
```powershell
copy .env.example .env
# Open .env and fill in:
# - N8N_API_KEY (generate in n8n UI: Settings → API → Create API Key)
# - NVIDIA_API_KEY (from build.nvidia.com)
```

### 4. Run the agent
```powershell
python main.py run "list all workflows in n8n"
```

---

## All CLI commands

```powershell
python main.py run "instruction"    # Execute a natural language instruction
python main.py serve                # Start FastAPI server (port 8000)
python main.py learning-report      # Show API call improvement over runs
python main.py memory-state         # Show both memory layers
python main.py reset                # Clear all learned memory
```

---

## Three interfaces

### Interface 1 — CLI
```powershell
python main.py run "create a webhook workflow that responds with hello world"
```

### Interface 2 — React UI
```powershell
# Terminal 1
python main.py serve

# Terminal 2
cd frontend && npm install && npm run dev
# Open http://localhost:5173
```

### Interface 3 — n8n Webhook
```powershell
$body = '{"instruction": "list all workflows"}'
Invoke-RestMethod -Method POST `
  -Uri "http://localhost:5678/webhook/agent-trigger" `
  -ContentType "application/json" `
  -Body $body
```
*(Requires the "Agent Trigger Webhook" workflow to be active in n8n — see DEMO.md)*

---

## The learning signal

The agent demonstrably improves over repeated runs:

```
Run  1 ✓  █████████  5 calls  2.8s   ← no prior context, planner works from scratch
Run  2 ✓  ███████    4 calls  2.1s   ← memory starts recording
Run  3 ✓  █████      3 calls  1.7s   ← proven sequence loaded, redundant steps skipped
Run  4 ✓  ████       3 calls  1.5s
Run  5 ✓  ███        2 calls  1.1s   ← 60% reduction
```

Run `python main.py learning-report` to see this after running the demo instructions.

---

## Capability synthesis

When the planner requests a tool that doesn't exist, the synthesis engine:
1. Asks the LLM to generate a Python function for the n8n REST API
2. Tests it (compile → exec → callable → signature → return shape)
3. Registers it in the live tool registry (current session)
4. Stores the source code in capability memory (survives restarts)

```
[GAP]  Unknown tool: summarise_executions_by_workflow
[Synthesis] Building tool: summarise_executions_by_workflow
[Synthesis] Attempt 1/3
[Synthesis] Generated 340 chars of code
[Synthesis] Test PASS: valid and callable with correct signature
[Synthesis] SUCCESS: summarise_executions_by_workflow registered and persisted!
```

---

## File structure

```
n8n-agent/
├── docker-compose.yml         ← n8n container (SQLite, port 5678)
├── .env.example               ← copy to .env, fill in API keys
├── requirements.txt
├── main.py                    ← CLI entry point (typer)
├── agent/
│   ├── core.py                ← AgentCore facade
│   ├── planner.py             ← LLM-powered decomposition
│   └── executor.py            ← step execution with retry + result chaining
├── memory/
│   ├── execution_memory.py    ← episodic: what the agent has done
│   └── capability_memory.py   ← semantic: what the agent can do
├── tools/
│   ├── __init__.py            ← tool registry (runtime extensible)
│   ├── workflows.py           ← n8n workflow CRUD
│   ├── executions.py          ← n8n execution queries
│   ├── credentials.py         ← n8n credential management
│   └── node_types.py          ← n8n node type catalogue
├── synthesis/
│   └── engine.py              ← runtime capability synthesis
├── learning/
│   └── tracker.py             ← API call metrics + tool reliability
├── models/
│   ├── step.py                ← Step dataclass
│   └── report.py              ← ExecutionReport dataclass
├── api/
│   └── server.py              ← FastAPI (bridges UI ↔ agent)
└── frontend/
    └── src/                   ← React + Vite dashboard
```

---

## Design decisions

| Decision | Rationale |
|---|---|
| External Python agent (not n8n AI nodes) | Assignment requirement; enables independent testing of each component |
| NVIDIA Llama 3.3 70B via NVIDIA NIM | Free tier available; OpenAI-compatible API; configurable via env vars |
| JSON files for memory | Zero extra dependencies; every retrieval step is explainable; keyword scoring works for structured fact retrieval |
| Two memory layers | Different query patterns: "what did I do?" vs "what can I do?" |
| Sequential execution | Steps have dependency ordering; parallel execution would require a DAG scheduler and creates race conditions |
| exec() for synthesis | Acceptable with LLM-controlled input and pre-registration testing; noted as needing sandbox isolation in production |

---

See **ARCHITECTURE.md** and **DEMO.md** for more detail.