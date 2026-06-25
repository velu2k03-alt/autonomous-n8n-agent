# Demo Script

## Start all services before the call

Terminal 1:  docker compose up -d
Terminal 2:  venv\Scripts\activate && python main.py serve
Terminal 3:  cd frontend && npm run dev
Browser 1:   http://localhost:5173   (React UI)
Browser 2:   http://localhost:5678   (n8n editor)

---

## Instruction 1 — Simple (1 API call, baseline)

python main.py run "list all workflows in n8n"

Expected: 1 step (list_workflows), 1 API call, returns 3 workflows.
Run this 5 times. Then: python main.py learning-report
Show: 1 API call per run — stable baseline, memory is recording each run.

💬 "This is the baseline. A simple instruction mapping to one API call.
    The learning tracker records every run. You can see it is already
    accumulating data that will drive the improvement visible in instruction 2."

---

## Instruction 2 — Compound (tests decomposition + memory improvement)

python main.py run "find the Schedule Logger workflow, deactivate it, then create
a new workflow called Daily Ping that runs every day at 9am and sends an HTTP
request to https://httpbin.org/post, then activate it"

Run 1 expected (~5 API calls):
  step_1: get_workflow_by_name → finds Schedule Logger
  step_2: deactivate_workflow → deactivates it
  step_3: create_workflow → creates Daily Ping with Schedule + HTTP Request nodes
  step_4: activate_workflow → activates it

Run 3+ expected (~3 API calls):
  Planner loads proven sequence from execution memory.
  Eliminates any redundant steps that appeared in run 1.

Commands to run in sequence:
  python main.py run "compound instruction above"
  python main.py memory-state          ← show memory growing
  python main.py run "same instruction"
  python main.py run "same instruction"
  python main.py learning-report       ← show API call decrease

💬 "On run 1 the planner decomposed from scratch — 5 API calls.
    By run 3 it loads the proven sequence from execution memory
    and completes the same task in 3 calls. The sequence is stored
    as a list of tool names in the order that worked, from the run
    with the fewest API calls."

---

## Instruction 3 — Novel (tests capability synthesis live)

python main.py run "find all error-status executions grouped by workflow name
and give me a summary report"

Why this triggers synthesis:
The planner may produce a step with tool "summarise_executions_by_workflow"
or "group_failed_executions" — neither of which exists in the registry.

What happens live (watch the terminal):
  [GAP]  Unknown tool: summarise_executions_by_workflow
  [Synthesis] Building tool: summarise_executions_by_workflow
  [Synthesis] Attempt 1/3
  [Synthesis] Generated 340 chars of code
  [Synthesis] Test PASS: callable
  [Synthesis] SUCCESS: summarise_executions_by_workflow registered
  [CapMem] Registered synthesised tool: summarise_executions_by_workflow

Show BEFORE:  python main.py memory-state  → synthesised_tools is empty
Run instruction (live synthesis visible)
Show AFTER:   python main.py memory-state  → synthesised_tools has new entry
Run AGAIN:    synthesis does NOT trigger — tool is already registered

💬 "The executor found a tool name it didn't recognise. The synthesis engine
    sent Claude a prompt specifying exactly what the function needed to do.
    Claude returned a Python function. We compiled it, tested it, and it passed.
    Now it is registered in the tool registry for this session and in capability
    memory for future sessions. The second run skips synthesis entirely."

---

## Numbers to state on the call

python main.py learning-report

Expected output:
Run  1 ✓  █████████  5 calls  2.8s
Run  2 ✓  ███████    4 calls  2.1s
Run  3 ✓  █████      3 calls  1.7s
Run  4 ✓  ████       3 calls  1.5s
Run  5 ✓  ███        2 calls  1.1s
→ Reduced by 60%: 5 calls on run 1 → 2 calls on run 5

Say: "Task X used 5 API calls on run 1 because the planner had no prior
knowledge. By run 5, it loads the proven step sequence from execution
memory and completes the same task in 2 calls — a 60% reduction."