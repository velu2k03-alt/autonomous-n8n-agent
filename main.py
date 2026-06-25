import typer
from rich.console import Console
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(help="Autonomous n8n Platform Intelligence Agent")
console = Console()


@app.command()
def run(instruction: str = typer.Argument(..., help="Natural language instruction")):
    """Execute a natural language instruction on your n8n instance."""
    from agent.core import AgentCore
    AgentCore().run(instruction)


@app.command("learning-report")
def learning_report():
    """Show the learning signal — API call counts per run."""
    from learning.tracker import LearningTracker
    LearningTracker().print_report()


@app.command("memory-state")
def memory_state():
    """Show current state of both memory layers."""
    from memory.execution_memory import ExecutionMemory
    from memory.capability_memory import CapabilityMemory

    em = ExecutionMemory()
    cm = CapabilityMemory()

    console.print(f"\n[bold blue]Execution Memory[/bold blue] — {em.count()} records")
    for ex in em.get_similar("workflow", limit=4):
        icon = "✓" if ex["success"] else "✗"
        console.print(f"  {icon}  {ex['instruction'][:60]}  →  {ex['total_api_calls']} calls")

    console.print(f"\n[bold blue]Capability Memory[/bold blue] — {len(cm.get_all_tools())} tools")
    for name, d in cm.get_all_tools().items():
        total = d["success_count"] + d["failure_count"]
        rate = round(d["success_count"] / total * 100) if total else 100
        synth = " [yellow][SYNTHESISED][/yellow]" if d.get("is_synthesised") else ""
        console.print(f"  [cyan]{name}[/cyan]{synth} — {rate}% success rate")
        for c in d.get("discovered_constraints", []):
            console.print(f"    [yellow]⚠  {c}[/yellow]")

    console.print(f"\n[bold blue]Global Constraints[/bold blue]")
    for c in cm.get_global_constraints():
        console.print(f"  • [dim]{c}[/dim]")


@app.command()
def serve():
    """Start the FastAPI server for the React frontend."""
    import uvicorn
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)


@app.command()
def reset():
    """Clear all memory. WARNING: agent loses all learned knowledge."""
    import os
    for f in ["data/execution_memory.json", "data/capability_memory.json", "data/learning_metrics.json"]:
        if os.path.exists(f):
            os.remove(f)
            console.print(f"Deleted: {f}", style="red")
    console.print("Memory cleared. Agent starts fresh.", style="bold red")


if __name__ == "__main__":
    app()