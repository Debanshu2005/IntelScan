#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import stat
import subprocess
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
OUTPUT_JSON = "workspace.json"
OUTPUT_MD = "workspacememory.md"
AGENTS_MD = "AGENTS.md"
GIT_COMMAND_TIMEOUT_SECONDS = 5

PACKAGE_FILES = [
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "Cargo.toml",
    "go.mod",
    "project.clj",
]

EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", "target", "build", ".venv", "venv"}


@dataclass
class Config:
    output_json: str = OUTPUT_JSON
    output_md: str = OUTPUT_MD
    exclude_dirs: set = field(default_factory=lambda: set(EXCLUDE_DIRS))
TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".cs",
    ".go",
    ".rs",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".html",
    ".css",
    ".scss",
    ".ini",
    ".cfg",
    ".dockerfile",
}


def to_iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def collapse_whitespace(value):
    return " ".join(str(value).split())


def format_code_span(value, fallback="none"):
    text = collapse_whitespace(value)
    if not text:
        text = fallback
    return "`" + text.replace("`", "'") + "`"


def is_relative_to(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_workspace_root(root_arg):
    root = Path(root_arg).resolve()
    if not root.exists():
        raise ValueError(f"Workspace root does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"Workspace root is not a directory: {root}")
    return root


def normalize_output_path(root, output_value, label):
    output_path = Path(output_value)
    if output_path.is_absolute():
        raise ValueError(f"{label} must be a relative path inside the workspace root.")

    resolved_root = root.resolve()
    resolved_output = (resolved_root / output_path).resolve(strict=False)
    if not is_relative_to(resolved_output, resolved_root):
        raise ValueError(f"{label} must stay inside the workspace root.")

    relative_output = resolved_output.relative_to(resolved_root).as_posix()
    if not relative_output or relative_output == ".":
        raise ValueError(f"{label} must point to a file inside the workspace root.")
    return relative_output


def validate_config(root, cfg: Config, watch_interval):
    cfg.output_json = normalize_output_path(root, cfg.output_json, "--output-json")
    cfg.output_md = normalize_output_path(root, cfg.output_md, "--output-md")

    output_paths = {cfg.output_json, cfg.output_md}
    if len(output_paths) != 2:
        raise ValueError("Output files must be distinct paths inside the workspace root.")
    if watch_interval <= 0:
        raise ValueError("--watch-interval must be greater than zero.")


def resolve_output_target(root, relative_output, label):
    normalized_output = normalize_output_path(root, relative_output, label)
    return root / normalized_output


def safe_stat(path):
    try:
        stats = path.stat(follow_symlinks=False)
    except OSError:
        return None
    if stat.S_ISLNK(stats.st_mode):
        return None
    return stats


def filter_walk_directories(dirpath, dirnames, cfg: Config):
    filtered = []
    for directory in dirnames:
        if directory in cfg.exclude_dirs:
            continue
        dir_path = Path(dirpath) / directory
        stats = safe_stat(dir_path)
        if stats is None or not stat.S_ISDIR(stats.st_mode):
            continue
        filtered.append(directory)
    dirnames[:] = filtered


def run_git_command(git_exe, root, *args):
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        [
            git_exe,
            "--no-pager",
            "-c",
            "color.ui=false",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "pager.show=false",
            "-c",
            "pager.status=false",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        stdin=subprocess.DEVNULL,
        timeout=GIT_COMMAND_TIMEOUT_SECONDS,
        env=env,
    )


def find_package_metadata(root):
    metadata = {"available": False, "files": [], "error": "Not detected."}
    for file_name in PACKAGE_FILES:
        path = root / file_name
        stats = safe_stat(path)
        if stats is not None and stat.S_ISREG(stats.st_mode):
            metadata["available"] = True
            metadata["files"].append(str(path.relative_to(root)).replace("\\", "/"))
    if not metadata["available"]:
        metadata["error"] = "No recognized package manifest files found."
    else:
        metadata.pop("error", None)
    return metadata


def collect_files(root, cfg: Config):
    file_inventory = []
    extension_counts = Counter()
    top_level = Counter()
    file_type_counts = Counter()
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if any(part in cfg.exclude_dirs for part in rel_dir.parts):
            continue
        filter_walk_directories(dirpath, dirnames, cfg)
        for name in filenames:
            path = Path(dirpath) / name
            rel_path = path.relative_to(root).as_posix()
            if is_excluded_path(rel_path, cfg):
                continue
            stats = safe_stat(path)
            if stats is None or not stat.S_ISREG(stats.st_mode):
                continue
            ext = path.suffix.lower()
            total_size += stats.st_size
            extension_counts[ext or "<none>"] += 1
            top_level_part = rel_path.split("/")[0]
            top_level[top_level_part] += 1
            file_type = "text" if ext in TEXT_EXTENSIONS else "binary"
            file_type_counts[file_type] += 1
            file_inventory.append({
                "path": rel_path,
                "extension": ext or "<none>",
                "size": stats.st_size,
                "modifiedAt": to_iso(datetime.fromtimestamp(stats.st_mtime, timezone.utc)),
                "type": file_type,
            })
    file_inventory.sort(key=lambda item: (item["path"]))
    return {
        "totalFiles": len(file_inventory),
        "totalSize": total_size,
        "topLevelAreas": [name for name, _ in top_level.most_common(20)],
        "primaryFileTypes": [name for name, _ in file_type_counts.most_common(5)],
        "fileInventory": file_inventory,
        "extensionCounts": dict(extension_counts.most_common(50)),
    }


def get_git_info(root):
    git_info = {
        "available": False,
        "branch": "",
        "headSummary": "",
        "statusSummary": "",
        "changedFileCount": 0,
        "statusLines": [],
        "error": "git not available or not a repository.",
    }
    git_exe = shutil.which("git")
    if not git_exe:
        git_info["error"] = "git executable not found on PATH."
        return git_info
    try:
        if run_git_command(git_exe, root, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true":
            git_info["available"] = True
            branch = run_git_command(git_exe, root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            head_summary = run_git_command(git_exe, root, "show", "-s", "--format=%h %ad %s", "--date=short").stdout.strip()
            status = run_git_command(git_exe, root, "status", "--short").stdout.strip().splitlines()
            git_info.update({
                "branch": branch,
                "headSummary": head_summary,
                "statusSummary": f"{len(status)} changed files",
                "changedFileCount": len(status),
                "statusLines": status,
                "error": "",
            })
    except subprocess.TimeoutExpired:
        git_info["error"] = f"git command timed out after {GIT_COMMAND_TIMEOUT_SECONDS} seconds."
    except (OSError, subprocess.SubprocessError) as exc:
        git_info["error"] = str(exc)
    return git_info


def summarize_recent_changes(root, file_inventory):
    changes = []
    for item in file_inventory:
        path = root / item["path"]
        stats = safe_stat(path)
        if stats is None or not stat.S_ISREG(stats.st_mode):
            continue
        mtime = datetime.fromtimestamp(stats.st_mtime, timezone.utc)
        age_days = (datetime.now(timezone.utc) - mtime).days
        if age_days <= 30:
            changes.append({
                "path": item["path"],
                "modifiedAt": item["modifiedAt"],
                "ageDays": age_days,
            })
    changes.sort(key=lambda x: x["modifiedAt"], reverse=True)
    return changes[:50]


def build_manifest(root, scan, cfg: Config, refresh_reason="scan"):
    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": to_iso(datetime.now(timezone.utc)),
        "generatedAtEpochMs": int(datetime.now(timezone.utc).timestamp() * 1000),
        "generator": {
            "name": "Workspace Scanner",
            "feature": "workspace-memory",
        },
        "workspace": {
            "name": root.name,
            "root": str(root),
            "activeFile": None,
            "refreshReason": refresh_reason,
            "outputFiles": {
                "markdown": cfg.output_md,
                "structuredManifest": cfg.output_json,
            },
            "suggestedStartingPoints": [],
            "stats": {
                "totalFiles": scan["totalFiles"],
                "topLevelAreas": scan["topLevelAreas"],
                "primaryFileTypes": scan["primaryFileTypes"],
                "keyFiles": [],
                "fileInventory": scan["fileInventory"],
            },
        },
        "package": find_package_metadata(root),
        "currentStack": {
            "lastActivityAt": "",
            "trackedChangeCount": 0,
            "trackedFileSnapshotCount": 0,
            "changeTypeCounts": {
                "save": 0,
                "create": 0,
                "delete": 0,
                "rename": 0,
            },
        },
        "trackedSnapshots": [],
        "recentChanges": summarize_recent_changes(root, scan["fileInventory"]),
        "hotFiles": [],
        "git": get_git_info(root),
        "github": {
            "available": False,
            "summary": "GitHub context unavailable in standalone workspace scanner.",
        },
        "graphify": {
            "reportAvailable": False,
            "graphAvailable": False,
            "reportPath": "",
            "graphPath": "",
            "highlights": "",
        },
        "projectPlanner": None,
        "agentNotes": [
            "Read the generated markdown and JSON manifest before scanning the repository file-by-file.",
            "Refresh the workspace manifest after significant edits or branch changes.",
            "Use the summary files as high-level repo context for agents and automation.",
        ],
    }
    return manifest


def is_excluded_path(rel_path, cfg: Config):
    normalized = rel_path.replace("\\", "/")
    excluded = {
        cfg.output_json.replace("\\", "/"),
        cfg.output_md.replace("\\", "/"),
    }
    return normalized in excluded or normalized.startswith("graphify-out/")


def collect_file_snapshot(root, cfg: Config):
    snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        if any(part in cfg.exclude_dirs for part in rel_dir.parts):
            continue
        filter_walk_directories(dirpath, dirnames, cfg)
        for name in filenames:
            path = Path(dirpath) / name
            rel_path = path.relative_to(root).as_posix()
            if is_excluded_path(rel_path, cfg):
                continue
            stats = safe_stat(path)
            if stats is None or not stat.S_ISREG(stats.st_mode):
                continue
            snapshot[rel_path] = (stats.st_mtime_ns, stats.st_size)
    return snapshot


def watch_workspace(root, interval, cfg: Config):
    previous_snapshot = collect_file_snapshot(root, cfg)
    print(f"Watching workspace for changes every {interval} seconds...")
    while True:
        try:
            time.sleep(interval)
            current_snapshot = collect_file_snapshot(root, cfg)
            if current_snapshot != previous_snapshot:
                print("Change detected, regenerating workspace manifest...")
                scan = collect_files(root, cfg)
                manifest = build_manifest(root, scan, cfg, refresh_reason="watch")
                write_output(root, manifest, cfg)
                print(f"Updated manifest: {root / cfg.output_json}")
                print(f"Updated markdown: {root / cfg.output_md}")
                previous_snapshot = current_snapshot
        except KeyboardInterrupt:
            print("Watch mode stopped.")
            break


def build_markdown(manifest, cfg: Config):
    workspace = manifest["workspace"]
    git = manifest["git"]
    package = manifest["package"]
    changes = manifest["recentChanges"]

    recent_lines = [
        f"- {format_code_span(c['path'])} (modified {format_code_span(c['modifiedAt'])}, {c['ageDays']} days ago)"
        for c in changes[:10]
    ] or ["- No file modifications detected in the last 30 days."]

    git_lines = (
        [
            f"- Branch: {format_code_span(git['branch'])}",
            f"- Head summary: {format_code_span(git['headSummary'])}",
            f"- Changed files: {git['changedFileCount']}",
        ]
        if git["available"] else [f"- Git context unavailable: {format_code_span(git.get('error'), fallback='unknown error')}"]
    )

    lines = [
        "# Workspace Memory",
        "This file is maintained automatically by Workspace Scanner for AI agents to reuse repo context without rescanning everything from scratch.",
        f"Generated: {format_code_span(manifest['generatedAt'])}",
        f"Workspace: {format_code_span(workspace['name'])}",
        f"Workspace root: {format_code_span(workspace['root'])}",
        f"Refresh reason: {format_code_span(workspace['refreshReason'])}",
        f"Output path: {format_code_span(cfg.output_md)}",
        "",
        "## Handoff Guidance",
        "- Read the generated JSON manifest before scanning broad parts of the repository.",
        "- Use this markdown file and the root JSON manifest for machine-readable repo context.",
        f"- Refresh with {format_code_span('python workspace_scanner.py --root .')} after significant edits or git branch changes.",
        "",
        "## Repository Blueprint",
        "- Audience: any AI agent working in this repository.",
        "- Workspace scanner: standalone feature that emits root-level workspace metadata for agents.",
        f"- Last activity: {format_code_span(manifest['generatedAt'])}",
        "",
        "## Workspace Focus",
        f"- Active file: {format_code_span(workspace['activeFile'])}",
        f"- Suggested starting points: {', '.join(format_code_span(point) for point in workspace['suggestedStartingPoints']) or 'none detected.'}",
        "",
        "## Current Workspace",
        f"- Total files: {workspace['stats']['totalFiles']}",
        f"- Primary file types: {', '.join(format_code_span(file_type) for file_type in workspace['stats']['primaryFileTypes']) or 'none detected.'}",
        f"- Top-level areas: {', '.join(format_code_span(area) for area in workspace['stats']['topLevelAreas']) or 'none detected.'}",
        "",
        "## Package Snapshot",
        (
            f"- Package metadata available from: {', '.join(format_code_span(path) for path in package['files'])}"
            if package["available"]
            else f"- Package metadata unavailable: {format_code_span(package.get('error'), fallback='not detected')}"
        ),
        "",
        "## Recent Changes",
        *recent_lines,
        "",
        "## Git Snapshot",
        *git_lines,
        "",
        "## Agent Notes",
        "- Recent changes: start with `Recent Changes` and `Git Snapshot` before broad repo scans.",
        "- Repository context: use the JSON manifest for machine-readable inventory.",
        "- Refresh the manifest after edits so future agent passes rely on up-to-date summaries.",
        "",
    ]
    return "\n".join(lines)


def write_output(root, manifest, cfg: Config):
    json_path = resolve_output_target(root, cfg.output_json, "--output-json")
    md_path = resolve_output_target(root, cfg.output_md, "--output-md")
    for parent in {json_path.parent, md_path.parent}:
        os.makedirs(parent, exist_ok=True)
    md_content = build_markdown(manifest, cfg)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    with md_path.open("w", encoding="utf-8") as handle:
        handle.write(md_content)


def build_agents_markdown(cfg: Config):
    return "\n".join([
        "# Agent Guide",
        "",
        "This project uses IntelScan workspace memory files to help agents get oriented quickly.",
        "",
        "## Start Here",
        "",
        f"- Read `{cfg.output_md}` first when it exists.",
        f"- Use `{cfg.output_json}` for machine-readable workspace metadata.",
        "- Refresh the workspace memory after significant edits, branch changes, or generated-file updates.",
        "",
        "## Refresh Commands",
        "",
        "Run a one-time refresh:",
        "",
        "```bash",
        "intelscan --root .",
        "```",
        "",
        "Run in watch mode while editing:",
        "",
        "```bash",
        "intelscan --root . --watch",
        "```",
        "",
        "Run an agent command with automatic refresh:",
        "",
        "```bash",
        'intelscan-agent --root . --agent-cmd "python your_agent_task.py"',
        "```",
        "",
        "## Generated Files",
        "",
        "Do not manually maintain these generated files:",
        "",
        f"- `{cfg.output_json}`",
        f"- `{cfg.output_md}`",
        "",
        "`graphify-out/` may be managed by other tooling and should be treated as external generated context.",
        "",
        "## Agent Notes",
        "",
        "- Prefer the generated workspace memory before broad file-by-file scanning.",
        "- Keep generated files out of commits unless the project explicitly chooses otherwise.",
        "- Preserve project-specific instructions in this file when editing it.",
    ])


def write_agents_guide(root, cfg: Config, agents_md=AGENTS_MD):
    agents_path = resolve_output_target(root, agents_md, "--agents-md")
    if agents_path.exists() or agents_path.is_symlink():
        return False
    os.makedirs(agents_path.parent, exist_ok=True)
    with agents_path.open("w", encoding="utf-8") as handle:
        handle.write(build_agents_markdown(cfg))
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="Generate workspace metadata manifest and markdown summary.")
    parser.add_argument("--root", default=".", help="Workspace root directory to scan")
    parser.add_argument("--output-json", default=OUTPUT_JSON, help="Structured manifest filename")
    parser.add_argument("--output-md", default=OUTPUT_MD, help="Markdown summary filename")
    parser.add_argument("--agents-md", default=AGENTS_MD, help="Agent guide filename used with --init-agents")
    parser.add_argument("--init-agents", action="store_true", help="Create AGENTS.md if it does not already exist")
    parser.add_argument("--exclude-dir", action="append", default=[], help="Additional directory names to exclude from scanning")
    parser.add_argument("--watch", action="store_true", help="Run continuously and regenerate manifest on workspace changes")
    parser.add_argument("--watch-interval", type=float, default=3.0, help="Seconds between polling cycles in watch mode")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        root = resolve_workspace_root(args.root)
        cfg = Config(
            output_json=args.output_json,
            output_md=args.output_md,
            exclude_dirs=EXCLUDE_DIRS | set(args.exclude_dir),
        )
        validate_config(root, cfg, args.watch_interval)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if args.init_agents:
        try:
            created_agents = write_agents_guide(root, cfg, args.agents_md)
        except ValueError as exc:
            raise SystemExit(str(exc))
        if created_agents:
            print(f"Generated agent guide: {root / args.agents_md}")
        else:
            print(f"Agent guide already exists: {root / args.agents_md}")

    print(f"Scanning workspace: {root}")
    scan = collect_files(root, cfg)
    manifest = build_manifest(root, scan, cfg, refresh_reason="watch" if args.watch else "scan")
    write_output(root, manifest, cfg)
    print(f"Generated manifest: {root / cfg.output_json}")
    print(f"Generated markdown: {root / cfg.output_md}")

    if args.watch:
        try:
            watch_workspace(root, args.watch_interval, cfg)
        except KeyboardInterrupt:
            print("Stopping watch mode.")


if __name__ == "__main__":
    main()
