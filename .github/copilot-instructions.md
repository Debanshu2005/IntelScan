# GitHub Copilot Instructions

This repository uses `AGENTS.md` as the canonical shared guide for AI-assisted development workflows.
Use it when available, and prefer the generated workspace context files below before broad file-by-file scanning.

## Context Priority

1. Read `workspace.json` first when it exists.
2. Read `graphify-out/GRAPH_REPORT.md` next when it exists.
3. Read `graphify-out/WORKSPACE_MEMORY.md` and `workspacememory.md` after that when they exist.

## Working Notes

- Treat `workspace.json` and `workspacememory.md` as generated files.
- Do not manually maintain `graphify-out/` or `__pycache__/`.
- Keep output writes constrained to the workspace root.
- Do not follow symlinked files or directories during scans.
- Keep `src/intelscan/agent_coordinator.py` usable both from the source tree and from an installed package.

## Common Commands

```bash
python -m unittest -q
python workspace_scanner.py --root .
python agent_coordinator.py --root . --agent-cmd "python --version"
```
