# Autonomous n8n Platform Intelligence Agent

Watermelon Software recruitment assignment submission.
An agent that receives natural language instructions and manages
n8n workflows via the REST API — creating, updating, activating,
monitoring, and triggering them autonomously.

## Quick start

1. Install Docker Desktop with WSL2 enabled
2. Clone this repository
3. Copy `.env.example` to `.env` and fill in your keys
4. Start n8n: `docker compose up -d`
5. Activate Python env: `venv\Scripts\activate`
6. Install deps: `pip install -r requirements.txt`
7. Run the agent: `python main.py run "list all workflows"`

## All commands

python main.py run "instruction"    Execute a natural language instruction
python main.py serve                Start FastAPI server for the React UI
python main.py learning-report      Show API call improvement over runs
python main.py memory-state         Show both memory layers
python main.py reset                Clear all learned memory

## React UI

cd frontend && npm install && npm run dev
Open http://localhost:5173

## Architecture

See ARCHITECTURE.md for the three-question design document.
See DEMO.md for the three live demo instructions.