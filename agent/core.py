from dotenv import load_dotenv
from agent.planner import Planner
from agent.executor import Executor
from memory.execution_memory import ExecutionMemory
from memory.capability_memory import CapabilityMemory
from synthesis.engine import SynthesisEngine
from learning.tracker import LearningTracker
from models.report import ExecutionReport

load_dotenv()


class AgentCore:
    """
    Facade that wires together all components.
    External code (main.py, api/server.py) only calls agent.run(instruction).

    Design pattern: Facade
    Why: Callers don't need to know about internal components.
         Keeps the API clean and testable.
    """

    def __init__(self):
        self.planner = Planner()
        self.executor = Executor()
        self.execution_memory = ExecutionMemory()
        self.capability_memory = CapabilityMemory()
        self.synthesis_engine = SynthesisEngine()
        self.tracker = LearningTracker()
        print("[Agent] Ready.")
        print(f"[Agent] Known tools in capability memory: {len(self.capability_memory.get_all_tools())}")
        print(f"[Agent] Past executions in memory: {self.execution_memory.count()}")

    def run(self, instruction: str) -> ExecutionReport:
        """
        Full agent run:
        1. Load similar past executions from memory
        2. Planner decomposes instruction → Steps (using memory context)
        3. Executor runs each step (triggers synthesis if needed)
        4. Both memory layers updated with results
        5. Learning tracker updated
        6. ExecutionReport returned
        """
        print(f"\n{'='*60}")
        print(f"[Agent] {instruction}")
        print('='*60)

        # Step 1: Load memory context
        past = self.execution_memory.get_similar(instruction, limit=5)
        if past:
            print(f"[Memory] {len(past)} similar past runs loaded")

        # Step 2: Plan
        print("[Planner] Decomposing...")
        steps = self.planner.plan(instruction, past_executions=past)
        print(f"[Planner] {len(steps)} steps:")
        for s in steps:
            print(f"  {s.id}: {s.description} → tool: {s.tool}")

        # Step 3: Execute
        print("\n[Executor] Running steps...")

        def on_gap(step):
            """Called when executor finds an unknown tool. Triggers synthesis."""
            print(f"[Synthesis] Attempting to build: {step.tool}")
            return self.synthesis_engine.synthesise(
                step=step,
                capability_memory=self.capability_memory
            )

        report = self.executor.execute(steps, instruction, on_capability_gap=on_gap)

        # Step 4: Update memory
        self.execution_memory.save(report)
        self.capability_memory.update_from_report(report)

        # Step 5: Track learning signal
        self.tracker.record(report)

        # Step 6: Print and return
        print(f"\n{'='*60}")
        print(report.summary())
        print('='*60)
        return report