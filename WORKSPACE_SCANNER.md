# Workspace Scanner

A standalone workspace scanner for generating repository metadata that agents can use instead of rescanning the entire repo.

## What it does

- Scans the workspace root and builds a structured JSON manifest.
- Writes a human-readable markdown summary alongside the JSON file.
- Captures workspace statistics, package manifest detection, file inventory, recent changes, and Git status when available.

## Why this helps

- Agents can read `workspace.json` and `workspacememory.md` first before scanning every file.
- After edits, the workspace scanner can be rerun to refresh repo context for subsequent agent passes.
- Keeps a stable high-level summary available for both humans and automation.

## Usage

Run from the repository root:

```bash
python workspace_scanner.py --root .
```

Run in watch mode to keep the summary files updated automatically when repository files change:

```bash
python workspace_scanner.py --root . --watch
```

Optional customize outputs:

```bash
python workspace_scanner.py --root . --output-json workspace.json --output-md workspacememory.md
```

## Output files

- `workspace.json` - machine-readable workspace manifest.
- `workspacememory.md` - human-readable workspace summary.

## Agent integration pattern

1. Before broad repo scanning, agents should read `workspace.json` and `workspacememory.md`.
2. Use the manifest fields for file inventory, package data, and Git status.
3. Run the coordinator wrapper instead of a manual scan so agent passes update the manifest automatically.

## Automated coordinator usage

Run an agent pass with automatic manifest refresh:

```bash
python agent_coordinator.py --root . --agent-cmd "python your_agent_task.py"
```

The wrapper does this:

- generates `workspace.json` and `workspacememory.md` first
- runs the requested agent command
- detects whether workspace files changed
- reruns `workspace_scanner.py` automatically after agent completion

## VS Code tasks

The repo also includes VS Code tasks for manual editor-driven refreshes:

- `Scan Workspace Once` runs a single root-level refresh.
- `Watch Workspace` keeps `workspace.json` and `workspacememory.md` updated while the task is running.

## Extending the scanner

- Add additional package detectors for other ecosystems.
- Add a watch mode to refresh manifests automatically on file changes.
- Add project planner references to the manifest.
