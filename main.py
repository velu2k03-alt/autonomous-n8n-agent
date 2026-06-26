import os
import typer
from rich.console import Console
from dotenv import load_dotenv

load_dotenv()

# Force UTF-8 output on Windows to avoid cp1252 encoding errors with special chars
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(
    help="Autonomous n8n Platform Intelligence Agent",
    no_args_is_help=True,
)
console = Console(highlight=False)


@app.command()
def run(instruction: str = typer.Argument(..., help="Natural language instruction for the agent")):
    """Execute a natural language instruction on your n8n instance."""
    from agent.core import AgentCore
    AgentCore().run(instruction)


@app.command("learning-report")
def learning_report():
    """
    Show the measurable learning signal — API calls per run.
    This is what you show during the Watermelon walkthrough call.
    """
    from learning.tracker import LearningTracker
    tracker = LearningTracker()
    print("\n" + "="*60)
    print("WATERMELON ASSIGNMENT — LEARNING SIGNAL")
    print("="*60)
    print("Requirement: 'Task X took 4 API calls on first run and")
    print("2 on the fifth run because the agent learned Y'")
    print("-"*60)
    tracker.print_report()


@app.command("memory-state")
def memory_state():
    """Show current state of both memory layers (execution + capability)."""
    from memory.execution_memory import ExecutionMemory
    from memory.capability_memory import CapabilityMemory

    em = ExecutionMemory()
    cm = CapabilityMemory()

    console.print(f"\n[bold blue]Execution Memory[/bold blue] -- {em.count()} records")
    for ex in em.get_similar("workflow", limit=5):
        icon = "OK" if ex["success"] else "FAIL"
        console.print(f"  [{icon}]  {ex['instruction'][:60]}  ->  {ex['total_api_calls']} calls")

    console.print(f"\n[bold blue]Capability Memory[/bold blue] -- {len(cm.get_all_tools())} tools")
    for name, d in cm.get_all_tools().items():
        total = d["success_count"] + d["failure_count"]
        rate = round(d["success_count"] / total * 100) if total else 100
        synth = " [yellow][SYNTHESISED][/yellow]" if d.get("is_synthesised") else ""
        console.print(f"  [cyan]{name}[/cyan]{synth} -- {rate}% success rate")
        for c in d.get("discovered_constraints", []):
            console.print(f"    [yellow]!! {c}[/yellow]")

    console.print(f"\n[bold blue]Global Constraints[/bold blue]")
    for c in cm.get_global_constraints():
        console.print(f"  - [dim]{c}[/dim]")

    console.print(f"\n[bold blue]Synthesised Tools[/bold blue]")
    synth_tools = cm.get_synthesised_tools()
    if synth_tools:
        for t in synth_tools:
            console.print(f"  [yellow]* {t}[/yellow]")
    else:
        console.print("  [dim]None yet -- run a novel instruction to trigger synthesis[/dim]")

    console.print(f"\n[bold blue]Reusable Strategies[/bold blue]")
    strategies = cm.get_reusable_strategies()
    if strategies:
        for s in strategies[:3]:
            console.print(f"  {s['tool_sequence']} ({s['api_calls']} calls)")
    else:
        console.print("  [dim]None yet -- strategies are extracted from successful compound runs[/dim]")


@app.command()
def serve():
    """Start the FastAPI server (port 8000) for the React frontend."""
    import uvicorn
    console.print("[green]Starting FastAPI server on http://0.0.0.0:8000[/green]")
    console.print("[dim]Swagger UI: http://localhost:8000/docs[/dim]")
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)


@app.command()
def reset():
    """Clear all memory files. WARNING: agent loses all learned knowledge."""
    files = [
        "data/execution_memory.json",
        "data/capability_memory.json",
        "data/learning_metrics.json",
    ]
    deleted = []
    for f in files:
        if os.path.exists(f):
            os.remove(f)
            deleted.append(f)
            console.print(f"Deleted: {f}", style="red")
    if deleted:
        console.print("Memory cleared. Agent starts fresh on next run.", style="bold red")
    else:
        console.print("No memory files found to delete.", style="yellow")


if __name__ == "__main__":
    app()