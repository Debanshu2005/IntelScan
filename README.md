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

Install from the repository:

```bash
git clone https://github.com/Debanshu2005/IntelScan
cd IntelScan
python -m pip install .
```

After the first PyPI release, users will also be able to install it directly with:

```bash
pip install intelscan
```

After installation, the CLI commands are available:

```bash
intelscan --root .
intelscan-agent --root . --agent-cmd "python your_agent_task.py"
```

Create an agent guide in a project:

```bash
intelscan --root . --init-agents
```

For local development without installing globally:

```bash
python workspace_scanner.py --root .
python agent_coordinator.py --root . --agent-cmd "python your_agent_task.py"
```

## Main files

- `workspace_scanner.py` - scans the repo and generates the summary files
- `agent_coordinator.py` - wraps an agent command and refreshes the workspace files before and after the run
- `WORKSPACE_SCANNER.md` - focused usage notes for the scanner
- `.vscode/tasks.json` - editor tasks for manual scan and watch flows

## Usage

Run a one-time scan:

```bash
intelscan --root .
```

Create `AGENTS.md` if the project does not already have one:

```bash
intelscan --root . --init-agents
```

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
