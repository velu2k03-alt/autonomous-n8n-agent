import json

with open("data/execution_memory.json") as f:
    data = json.load(f)

for i, ex in enumerate(data["executions"]):
    print(f"\nRun {i+1}: {ex['instruction']}")
    print(f"Success: {ex['success']} | API calls: {ex['total_api_calls']}")
    for s in ex.get("steps", []):
        print(f"  Step: {s.get('id')} | Tool: {s.get('tool')} | Status: {s.get('status')} | Error: {s.get('error')}")
