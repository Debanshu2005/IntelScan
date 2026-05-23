# Agent Guide

This repository builds IntelScan, a lightweight workspace-summary tool for AI-assisted development workflows.

## Start Here

- Read `README.md` for the user-facing overview.
- Read `WORKSPACE_SCANNER.md` for scanner behavior and usage details.
- Use `workspace.json` and `workspacememory.md` as generated context files when present.

## Generated Files

Do not commit or manually maintain these files:

- `workspace.json`
- `workspacememory.md`
- `graphify-out/`
- `__pycache__/`

The scanner owns only the two root files:

- `workspace.json`
- `workspacememory.md`

`graphify-out/` is managed by Code Janitor or other external tooling, not by IntelScan.

## Common Commands

Run tests:

```bash
python -m unittest -q
```

Compile-check scripts:

```bash
python -m py_compile workspace_scanner.py agent_coordinator.py src/intelscan/workspace_scanner.py src/intelscan/agent_coordinator.py
```

Run a one-time scan:

```bash
python workspace_scanner.py --root .
```

Run the installed CLI:

```bash
intelscan --root .
```

Create a project-local agent guide for users of IntelScan:

```bash
intelscan --root . --init-agents
```

Run through the coordinator:

```bash
python agent_coordinator.py --root . --agent-cmd "python --version"
```

Run the installed coordinator CLI:

```bash
intelscan-agent --root . --agent-cmd "python --version"
```

## Packaging

The package metadata lives in `pyproject.toml`.

Before changing packaging behavior, verify:

```bash
python -m pip wheel --no-build-isolation --no-deps --wheel-dir .tmp_wheelhouse .
```

Clean up temporary build or install folders after verification.

## Development Notes

- Keep output writes constrained to the workspace root.
- Keep symlink handling conservative; do not follow symlinked files or directories during scans.
- Keep `src/intelscan/agent_coordinator.py` usable both from the source tree and from an installed package.
- The repository uses a `src/intelscan/` package layout; the root Python files are thin source-tree launchers.
- Preserve Python 3.8 compatibility unless `pyproject.toml` is intentionally updated.
- Prefer focused changes over broad refactors; this repo is intentionally small.

## Repository Context Priority

**For all AI agents**: Before broad repo scans or repo-level answers, use this order:

1. Read `workspace.json` first when it exists
2. Read `graphify-out/GRAPH_REPORT.md` next when it exists
3. Read `graphify-out/WORKSPACE_MEMORY.md` and `workspacememory.md` after that when they exist

Use `workspace.json` for structured repo metadata such as file inventory, package details, Git status, Graphify summary, recent changes, and suggested starting points.

## Graphify Knowledge Graph

**For all AI agents**: Before answering architecture questions or searching files, check if `graphify-out/GRAPH_REPORT.md` exists.

If the knowledge graph exists:
1. Read `workspace.json` first when it exists so you inherit machine-readable repo context
2. Read `graphify-out/GRAPH_REPORT.md`
3. Read `graphify-out/WORKSPACE_MEMORY.md` or `workspacememory.md` for handoff notes and recent activity
4. Identify god nodes (central files with high connectivity)
5. Understand community structure (how modules are organized)
6. Navigate via the dependency graph instead of grepping through every file

This approach:
- Improves accuracy by understanding architecture first
- Reduces unnecessary file reads
- Provides context for code changes

Supported platforms: Aider, OpenClaw, Factory Droid, Trae, Hermes, Codex, OpenCode
