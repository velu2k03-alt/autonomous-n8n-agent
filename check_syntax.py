"""Syntax check script for all agent Python files."""
import ast
import sys

files = [
    'agent/core.py',
    'agent/planner.py',
    'agent/executor.py',
    'memory/execution_memory.py',
    'memory/capability_memory.py',
    'synthesis/engine.py',
    'learning/tracker.py',
    'api/server.py',
    'tools/__init__.py',
    'tools/workflows.py',
    'tools/executions.py',
    'tools/credentials.py',
    'tools/node_types.py',
    'models/step.py',
    'models/report.py',
    'main.py',
]

all_ok = True
for f in files:
    try:
        with open(f, encoding='utf-8') as fh:
            src = fh.read()
        ast.parse(src)
        print(f'  OK  {f}')
    except SyntaxError as e:
        print(f'  ERR {f}: {e}')
        all_ok = False
    except FileNotFoundError:
        print(f'  MISS {f}: file not found')
        all_ok = False

print()
if all_ok:
    print('All files: syntax OK')
else:
    print('SYNTAX ERRORS FOUND — fix before running')
    sys.exit(1)
