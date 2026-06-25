from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="n8n Platform Intelligence Agent API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5678"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent = None

def get_agent():
    global _agent
    if _agent is None:
        from agent.core import AgentCore
        _agent = AgentCore()
    return _agent


class RunRequest(BaseModel):
    instruction: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run_instruction(req: RunRequest):
    """Execute a natural language instruction. Returns the ExecutionReport."""
    try:
        return get_agent().run(req.instruction).to_dict()
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.get("/memory")
def get_memory():
    """Current state of both memory layers. Used by the React MemoryViewer."""
    from memory.execution_memory import ExecutionMemory
    from memory.capability_memory import CapabilityMemory
    exec_mem = ExecutionMemory()
    cap_mem = CapabilityMemory()
    return {
        "execution_memory": {
            "count": exec_mem.count(),
            "recent": exec_mem.get_similar("workflow", limit=5),
        },
        "capability_memory": {
            "tools": cap_mem.get_all_tools(),
            "constraints": cap_mem.get_global_constraints(),
        },
    }


@app.get("/learning")
def get_learning():
    """Learning metrics for the React chart."""
    from learning.tracker import LearningTracker
    return LearningTracker().get_data()


@app.post("/webhook-relay")
def webhook_relay(body: dict):
    """
    Receives calls forwarded from the n8n Webhook node.
    n8n sends: {"instruction": "..."}
    We route it to the agent and return the report.
    """
    instruction = body.get("instruction")
    if not instruction:
        raise HTTPException(400, detail="Missing 'instruction' field")
    try:
        return get_agent().run(instruction).to_dict()
    except Exception as e:
        raise HTTPException(500, detail=str(e))