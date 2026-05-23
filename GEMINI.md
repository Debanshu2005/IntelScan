# Gemini AI Instructions

This repository uses `AGENTS.md` as the canonical shared guide for AI-assisted development workflows.
Start by reading `AGENTS.md` when it is available, then follow the generated workspace context below in Gemini CLI.

## Context Priority

1. Read `workspace.json` first when it exists.
2. Read `graphify-out/GRAPH_REPORT.md` next when it exists.
3. Read `graphify-out/WORKSPACE_MEMORY.md` and `workspacememory.md` after that when they exist.

## Working Notes

- Treat `workspace.json` and `workspacememory.md` as generated files.
- Do not manually maintain `graphify-out/` or `__pycache__/`.
- Keep output writes constrained to the workspace root.
- Do not follow symlinked files or directories during scans.

## Common Commands

```bash
python -m unittest -q
python workspace_scanner.py --root .
python agent_coordinator.py --root . --agent-cmd "python --version"
```
