import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from memory.execution_memory import ExecutionMemory
from models.report import ExecutionReport
from models.step import Step, StepStatus
import time

def test_compaction():
    # Setup fresh memory (or append to existing)
    em = ExecutionMemory()
    original_count = em.count()
    print(f"Current executions count in memory: {original_count}")
    
    # We will simulate and save 5 runs with very similar instructions
    similar_instructions = [
        "Fetch all active n8n workflows and list them",
        "Fetch and list all active n8n workflows",
        "Show me all active workflows on n8n",
        "Get all active n8n workflows",
        "List all active workflows in n8n"
    ]
    
    for i, instr in enumerate(similar_instructions):
        print(f"\nSaving run #{i+1} with instruction: '{instr}'")
        
        # Build a dummy successful report
        step = Step(
            id=f"step_{i}",
            tool="list_workflows",
            description="List active workflows",
            status=StepStatus.SUCCESS,
            api_calls_made=5 - i, # simulating improving efficiency: 5, 4, 3, 2, 1 calls!
            params={}
        )
        
        report = ExecutionReport(instruction=instr, steps=[step])
        report.success = True
        
        # Save to memory (this should trigger compaction when count >= 5)
        em.save(report)
        
    print(f"\nFinal executions count in memory: {em.count()}")
    print("Compaction testing completed.")

if __name__ == "__main__":
    test_compaction()
