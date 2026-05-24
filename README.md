<img width="1408" height="601" alt="IntelScan" src="https://github.com/user-attachments/assets/8ceb7a09-f93f-447c-944a-7b64a0485598" />

# IntelScan 

IntelScan is a lightweight workspace-summary tool for AI-assisted development workflows.
https://pypi.org/project/intelscan

It scans a repository, writes a structured manifest for tools, and generates a human-readable memory file so future agent passes can understand the project without rescanning everything from scratch.

## What it generates

- `workspace.json` - machine-readable workspace metadata
- `workspacememory.md` - human-readable workspace summary

These files are generated at the workspace root and are intended to be refreshed as the project changes.

## Why it helps

- Gives agents a fast starting point before broad repo scans
- Captures file inventory, package metadata, project structure, and Git status when available
- Keeps a stable handoff artifact for repeated AI-assisted workflows
- Supports both one-off scans and automated refresh flows

## Installation

Prerequisites:

- Python 3.8+
- Git on `PATH` if you want Git metadata included in the generated summary

Install from PyPI:

```bash
pip install intelscan
```

Install a specific release:

```bash
pip install intelscan==0.1.1
```

Install from source:

```bash
git clone https://github.com/Debanshu2005/IntelScan
cd IntelScan
python -m pip install .
```

## Quick Start

Run a one-time scan:

```bash
intelscan --root .
```

Run in watch mode:

```bash
intelscan --root . --watch
```

Create a project-local agent guide plus companion agent instruction files when they do not already exist:

```bash
intelscan --root . --init-agents
```

Run an agent command with automatic manifest refresh before and after the pass:

```bash
intelscan-agent --root . --agent-cmd "python your_agent_task.py"
```

For source-tree development without installing globally:

```bash
python workspace_scanner.py --root .
python workspace_scanner.py --root . --watch
python agent_coordinator.py --root . --agent-cmd "python your_agent_task.py"
```

## Agent Guide Bootstrap

`--init-agents` creates `AGENTS.md` as the canonical shared guide and also bootstraps companion files for common agent ecosystems when missing:

- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`

Existing files are preserved and are never overwritten.

## Main Commands

Scanner CLI:

```bash
intelscan --root .
intelscan --root . --watch
intelscan --root . --output-json workspace.json --output-md workspacememory.md
intelscan --root . --exclude-dir .cache
```

Coordinator CLI:

```bash
intelscan-agent --root . --agent-cmd "python your_agent_task.py"
intelscan-agent --root . --agent-cmd "python your_agent_task.py" --always-refresh
intelscan-agent --root . --agent-cmd "python your_agent_task.py" --skip-initial-scan
```

## Repository Layout

- `src/intelscan/workspace_scanner.py` - scanner implementation and CLI entry point
- `src/intelscan/agent_coordinator.py` - agent wrapper that refreshes workspace context around a command
- `workspace_scanner.py` - thin source-tree launcher for local development
- `agent_coordinator.py` - thin source-tree launcher for local development
- `WORKSPACE_SCANNER.md` - focused scanner behavior and usage notes
- `tests/test_workspace_scanner.py` - coverage for manifest and safety behavior

The project uses a `src/intelscan/` package layout. The root Python files are intentionally thin launchers so local development commands still work directly from the repository.

## Development

Run tests:

```bash
python -m unittest -q
```

Compile-check the main scripts:

```bash
python -m py_compile workspace_scanner.py agent_coordinator.py src/intelscan/workspace_scanner.py src/intelscan/agent_coordinator.py
```

Build a wheel locally when verifying packaging behavior:

```bash
python -m pip wheel --no-build-isolation --no-deps --wheel-dir .tmp_wheelhouse .
```

## Notes

- Output writes are constrained to the workspace root.
- Symlinked files and directories are not followed during scans.
- Git metadata is collected with safe non-interactive commands when Git is available.

## Publishing

Release guidance lives in [RELEASING.md](RELEASING.md). The repository also includes a GitHub Actions workflow for PyPI Trusted Publishing at `.github/workflows/publish.yml`.
