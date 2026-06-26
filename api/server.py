from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional
import os

load_dotenv()

app = FastAPI(
    title="n8n Platform Intelligence Agent API",
    version="2.0.0",
    description=(
        "Autonomous agent that receives natural language instructions "
        "and manages n8n workflows via the REST API. "
        "Supports three interfaces: CLI, React UI (via this API), and n8n Webhook."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5678", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent = None


def get_agent():
    """Lazy-init singleton pattern — agent is expensive to initialise."""
    global _agent
    if _agent is None:
        from agent.core import AgentCore
        _agent = AgentCore()
    return _agent


# -- Request / Response models --------------------------------------------------

class RunRequest(BaseModel):
    instruction: str


class WebhookRelayBody(BaseModel):
    instruction: Optional[str] = None

    class Config:
        extra = "allow"   # accept extra fields from n8n without failing


# -- Endpoints -----------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    """Health check. Returns ok when the server is ready."""
    return {
        "status": "ok",
        "agent_ready": _agent is not None,
        "n8n_url": os.getenv("N8N_BASE_URL", "http://localhost:5678"),
    }


@app.post("/run", tags=["Agent"])
def run_instruction(req: RunRequest):
    """
    Execute a natural language instruction on the n8n instance.

    The agent will:
    1. Load similar past executions from memory
    2. Decompose the instruction into steps using the LLM planner
    3. Execute each step against the n8n REST API
    4. Synthesise new tools if a capability gap is encountered
    5. Return the full ExecutionReport

    Returns: ExecutionReport dict with steps, timing, and success flag.
    """
    try:
        return get_agent().run(req.instruction).to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memory", tags=["Memory"])
def get_memory():
    """
    Current state of both memory layers.

    Used by the React MemoryViewer component to show:
    - How many past executions have been recorded
    - Recent execution summaries
    - Known tools and their success rates
    - Global platform constraints discovered at runtime
    """
    from memory.execution_memory import ExecutionMemory
    from memory.capability_memory import CapabilityMemory
    exec_mem = ExecutionMemory()
    cap_mem = CapabilityMemory()
    return {
        "execution_memory": {
            "count": exec_mem.count(),
            "recent": exec_mem.get_similar("workflow", limit=5),
            "all_lessons": exec_mem.get_all_lessons()[:10],
        },
        "capability_memory": {
            "tools": cap_mem.get_all_tools(),
            "constraints": cap_mem.get_global_constraints(),
            "synthesised_tools": cap_mem.get_synthesised_tools(),
            "reusable_strategies": cap_mem.get_reusable_strategies()[:5],
        },
    }


@app.get("/learning", tags=["Learning"])
def get_learning():
    """
    Learning metrics for the React LearningChart component.

    Shows API call counts per run. A decreasing trend proves the agent
    is learning: it uses fewer API calls on repeated similar instructions
    because it loads the optimal step sequence from execution memory.
    """
    from learning.tracker import LearningTracker
    return LearningTracker().get_data()


@app.post("/webhook-relay", tags=["Webhook"])
def webhook_relay(body: dict):
    """
    Receives instructions forwarded from the n8n 'Agent Trigger Webhook' workflow.

    The n8n workflow sends: {"instruction": "..."}
    This endpoint routes it to the agent and returns the full ExecutionReport.

    This is the third input interface:
    CLI -> python main.py run "..."
    UI  -> POST /run
    n8n -> POST /webhook/agent-trigger -> n8n HTTP Request -> POST /webhook-relay
    """
    instruction = body.get("instruction")
    if not instruction:
        raise HTTPException(
            status_code=400,
            detail="Missing 'instruction' field in request body. Expected: {\"instruction\": \"...\"}",
        )
    try:
        return get_agent().run(instruction).to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tools", tags=["System"])
def list_tools():
    """List all tools currently registered in the tool registry."""
    from tools import list_tool_names, describe_tools
    return {
        "tools": list_tool_names(),
        "descriptions": describe_tools(),
        "count": len(list_tool_names()),
    }


@app.delete("/memory", tags=["Memory"])
def clear_memory():
    """
    Clear all memory layers and learning metrics.
    WARNING: The agent loses all learned knowledge and will start from scratch.
    """
    import os as _os
    deleted = []
    for f in ["data/execution_memory.json", "data/capability_memory.json", "data/learning_metrics.json"]:
        if _os.path.exists(f):
            _os.remove(f)
            deleted.append(f)

    # Reset singleton so it re-initialises with fresh memory
    global _agent
    _agent = None

    return {"deleted": deleted, "message": "Memory cleared. Agent will re-initialise on next call."}