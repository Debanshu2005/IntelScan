#!/usr/bin/env python3
import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    from . import workspace_scanner
except ImportError:  # pragma: no cover - source-tree fallback
    import workspace_scanner

SOURCE_SCANNER_PATH = Path("src/intelscan/workspace_scanner.py")
WINDOWS_SHELL_CHARS = ("|", "&", "<", ">", "(", ")", "%")
WINDOWS_EXECUTABLE_SUFFIXES = (".exe", ".cmd", ".bat", ".ps1")


def collect_snapshot(root: Path):
    ignore_rules, ignore_sources = workspace_scanner.load_ignore_rules(root)
    cfg = workspace_scanner.Config(ignore_rules=ignore_rules, ignore_sources=ignore_sources)
    snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if rel_dir != Path(".") and workspace_scanner.should_ignore_path(rel_dir.as_posix(), cfg, is_dir=True):
            continue
        workspace_scanner.filter_walk_directories(root, dirpath, dirnames, cfg)
        for filename in filenames:
            rel_path = (rel_dir / filename).as_posix()
            if workspace_scanner.should_ignore_path(rel_path, cfg):
                continue
            try:
                stats = (root / rel_path).stat()
            except OSError:
                continue
            snapshot[rel_path] = (stats.st_mtime_ns, stats.st_size)
    return snapshot


def run_workspace_scanner(root: Path, scanner_path: Optional[Path], skip_initial_scan: bool):
    if skip_initial_scan:
        return
    if scanner_path is not None:
        if not scanner_path.exists():
            raise FileNotFoundError(f"Workspace scanner not found at: {scanner_path}")
        command = [sys.executable, str(scanner_path), "--root", str(root)]
    elif (root / SOURCE_SCANNER_PATH).exists():
        command = [sys.executable, str(root / SOURCE_SCANNER_PATH), "--root", str(root)]
    else:
        command = [sys.executable, "-m", "intelscan.workspace_scanner", "--root", str(root)]
    print(f"Running initial workspace scanner: {' '.join(command)}")
    result = subprocess.run(command, cwd=root)
    if result.returncode != 0:
        raise RuntimeError(f"Workspace scanner failed with exit code {result.returncode}")


def strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def candidate_executable_names(executable: str):
    normalized = Path(strip_wrapping_quotes(executable)).name
    if os.name != "nt" or Path(normalized).suffix:
        return [normalized]
    return [normalized, *(normalized + suffix for suffix in WINDOWS_EXECUTABLE_SUFFIXES)]


def find_executable_in_directories(executable: str, search_dirs):
    for search_dir in search_dirs:
        directory = Path(search_dir).expanduser()
        for candidate_name in candidate_executable_names(executable):
            candidate_path = directory / candidate_name
            try:
                if candidate_path.is_file():
                    return str(candidate_path)
            except OSError:
                continue
    return ""


def find_windows_extension_executable(executable: str):
    candidate_names = candidate_executable_names(executable)

    home_dir = Path.home()
    extension_roots = [
        home_dir / ".vscode" / "extensions",
        home_dir / ".vscode-insiders" / "extensions",
    ]
    candidates = []
    for extensions_dir in extension_roots:
        for candidate_name in candidate_names:
            try:
                matches = extensions_dir.glob(f"*/bin/**/{candidate_name}")
            except OSError:
                continue
            for match in matches:
                try:
                    stats = match.stat()
                except OSError:
                    continue
                candidates.append((stats.st_mtime_ns, match))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: (item[0], str(item[1]).lower()), reverse=True)
    return str(candidates[0][1])


def resolve_agent_command(agent_cmd: str, extra_search_dirs=None):
    if os.name != "nt":
        return shlex.split(agent_cmd), False

    if any(char in agent_cmd for char in WINDOWS_SHELL_CHARS):
        return agent_cmd, True

    argv = shlex.split(agent_cmd, posix=False)
    if not argv:
        raise RuntimeError("Agent command cannot be empty.")

    executable = strip_wrapping_quotes(argv[0])
    resolved = shutil.which(executable)
    if not resolved:
        resolved = find_executable_in_directories(executable, extra_search_dirs or [])
    if not resolved:
        resolved = find_windows_extension_executable(executable)
    if resolved:
        argv[0] = resolved
        return argv, False

    if Path(executable).exists():
        argv[0] = executable
        return argv, False

    return agent_cmd, True


def run_agent_command(root: Path, agent_cmd: str, extra_search_dirs=None):
    print(f"Running agent command: {agent_cmd}")
    cmd, use_shell = resolve_agent_command(agent_cmd, extra_search_dirs=extra_search_dirs)
    env = os.environ.copy()
    env["INTELSCAN_WORKSPACE_ROOT"] = str(root)
    env["INTELSCAN_WORKSPACE_JSON"] = str(root / workspace_scanner.OUTPUT_JSON)
    env["INTELSCAN_WORKSPACE_MD"] = str(root / workspace_scanner.OUTPUT_MD)
    result = subprocess.run(cmd, cwd=root, shell=use_shell, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Agent command failed with exit code {result.returncode}")


def main():
    parser = argparse.ArgumentParser(description="Coordinate agent passes with automatic workspace manifest refresh.")
    parser.add_argument("--root", default=".", help="Workspace root directory")
    parser.add_argument("--scanner", default="", help="Optional workspace scanner script path")
    parser.add_argument("--agent-cmd", required=True, help="Shell command that runs the agent pass")
    parser.add_argument("--agent-search-dir", action="append", default=[], help="Additional directory to search for the agent executable when it is not on PATH")
    parser.add_argument("--skip-initial-scan", action="store_true", help="Do not run the scanner before the agent command")
    parser.add_argument("--always-refresh", action="store_true", help="Always refresh the manifest after the agent command, even if no file changes are detected")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    scanner_path = Path(args.scanner) if args.scanner else None
    if scanner_path is not None and not scanner_path.is_absolute():
        scanner_path = root / scanner_path

    run_workspace_scanner(root, scanner_path, args.skip_initial_scan)
    before_snapshot = collect_snapshot(root)
    try:
        run_agent_command(root, args.agent_cmd, extra_search_dirs=args.agent_search_dir)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    after_snapshot = collect_snapshot(root)
    if args.always_refresh or before_snapshot != after_snapshot:
        print("Workspace changes detected, refreshing summary manifest...")
        run_workspace_scanner(root, scanner_path, skip_initial_scan=False)
        print("Workspace summary refreshed.")
    else:
        print("No workspace changes detected; manifest refresh skipped.")


if __name__ == "__main__":
    main()
