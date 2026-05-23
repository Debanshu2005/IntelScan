# IntelScan

IntelScan is a lightweight workspace-summary tool for AI-assisted development workflows.

It scans the repository, generates a structured manifest, and writes a human-readable memory file so agents can understand the repo without rescanning everything from scratch.

## What it generates

- `workspace.json` - machine-readable workspace metadata
- `workspacememory.md` - human-readable workspace summary

The generated outputs also include an inferred project structure section so agents can quickly see the repo layout, entry points, and major components.

These files are generated at the project root and are ignored by git.

## Installation

Prerequisites:

- Python 3.8+
- Git on `PATH` if they want Git metadata included in the generated summary

Install from PyPI:

```bash
pip install intelscan
```

Install a specific released version:

```bash
pip install intelscan==0.1.0
```

Install from the repository for local development:

```bash
git clone https://github.com/Debanshu2005/IntelScan
cd IntelScan
python -m pip install .
```

After installation, the CLI commands are available:

```bash
intelscan --root .
intelscan-agent --root . --agent-cmd "python your_agent_task.py"
```

Create agent guide files in a project:

```bash
intelscan --root . --init-agents
```

For local development without installing globally:

```bash
python workspace_scanner.py --root .
python agent_coordinator.py --root . --agent-cmd "python your_agent_task.py"
```

The repository now uses a `src/intelscan/` package layout. The two root-level Python files are thin development launchers so the source-tree commands above still work.

## Main files

- `src/intelscan/workspace_scanner.py` - scans the repo and generates the summary files
- `src/intelscan/agent_coordinator.py` - wraps an agent command and refreshes the workspace files before and after the run
- `workspace_scanner.py` - thin source-tree launcher for local development
- `agent_coordinator.py` - thin source-tree launcher for local development
- `WORKSPACE_SCANNER.md` - focused usage notes for the scanner
- `.vscode/tasks.json` - editor tasks for manual scan and watch flows

## Usage

Run a one-time scan:

```bash
intelscan --root .
```

Create `AGENTS.md` plus companion agent instruction files when they do not already exist:

```bash
intelscan --root . --init-agents
```

This creates `AGENTS.md` as the canonical shared guide and also bootstraps companion files for common agent ecosystems:

- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`

Existing files are preserved and never overwritten.

Run in watch mode:

```bash
intelscan --root . --watch
```

Run through the coordinator:

```bash
intelscan-agent --root . --agent-cmd "python your_agent_task.py"
```

## VS Code tasks

If you use VS Code, run these from `Terminal -> Run Task`:

- `Scan Workspace Once`
- `Watch Workspace`

## Notes

- The scanner ignores symlinks and keeps output writes inside the workspace root.
- Git metadata is included when available, with safe non-interactive Git calls.

## Publishing

Release notes for PyPI are in [RELEASING.md](RELEASING.md). The repo also includes a GitHub Actions workflow for PyPI Trusted Publishing at `.github/workflows/publish.yml`.
