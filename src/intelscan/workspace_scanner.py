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

SCHEMA_VERSION = 2
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

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".cs",
    ".go",
    ".rs",
}

GENERATED_DIR_HINTS = {"dist", "build", "coverage", "htmlcov", "graphify-out"}
DOC_DIR_HINTS = {"docs", "doc"}
TEST_DIR_HINTS = {"tests", "test", "spec", "specs"}
SOURCE_DIR_HINTS = {"src", "lib", "app", "server", "client", "pkg"}
CONFIG_DIR_HINTS = {".github", ".vscode", ".devcontainer"}


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


def read_project_scripts(root, package_metadata):
    if "pyproject.toml" not in package_metadata.get("files", []):
        return []

    pyproject_path = root / "pyproject.toml"
    try:
        content = pyproject_path.read_text(encoding="utf-8")
    except OSError:
        return []

    scripts = []
    in_scripts = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_scripts = line == "[project.scripts]"
            continue
        if not in_scripts or "=" not in line:
            continue
        name, value = line.split("=", 1)
        scripts.append({
            "name": name.strip(),
            "target": value.strip().strip('"').strip("'"),
        })
    return scripts


def resolve_module_source_path(module_name, file_paths):
    module_path = module_name.replace(".", "/") + ".py"
    candidate_paths = [
        module_path,
        "src/" + module_path,
    ]
    for candidate in candidate_paths:
        if candidate in file_paths:
            return candidate
    return ""


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


def is_test_path(path):
    normalized = path.replace("\\", "/")
    parts = normalized.split("/")
    filename = parts[-1].lower()
    stem = Path(filename).stem
    return (
        any(part.lower() in TEST_DIR_HINTS for part in parts[:-1])
        or filename.startswith("test_")
        or filename.endswith("_test.py")
        or stem.endswith("_test")
    )


def infer_component_role(path):
    normalized = path.replace("\\", "/")
    name = Path(normalized).name.lower()
    stem = Path(normalized).stem.lower()
    if is_test_path(normalized):
        return "automated tests"
    if name.endswith(".md") or name in {"readme", "license"}:
        return "documentation"
    if "scanner" in stem:
        return "workspace scanning and manifest generation"
    if "coordinator" in stem:
        return "agent command orchestration and refresh flow"
    if "config" in stem or "settings" in stem:
        return "configuration"
    if "cli" in stem or stem == "main":
        return "command-line entry point"
    if name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod"}:
        return "packaging and project metadata"
    return "source module"


def infer_area_kind(area_name, member_paths):
    lower_name = area_name.lower()
    if area_name == "[root]":
        return "workspace-root"
    if lower_name.endswith(".egg-info") or lower_name in GENERATED_DIR_HINTS:
        return "generated"
    if lower_name in DOC_DIR_HINTS:
        return "documentation"
    if lower_name in TEST_DIR_HINTS or any(is_test_path(path) for path in member_paths):
        return "tests"
    if lower_name in SOURCE_DIR_HINTS:
        return "source"
    if lower_name in CONFIG_DIR_HINTS:
        return "configuration"
    return "mixed"


def infer_area_purpose(area_name, kind):
    if kind == "workspace-root":
        return "Primary repository root containing the main source files, documentation, tests, and project metadata."
    if kind == "generated":
        return "Generated artifacts or package metadata rather than hand-maintained source."
    if kind == "documentation":
        return "Documentation and onboarding material."
    if kind == "tests":
        return "Automated tests and validation helpers."
    if kind == "source":
        return "Primary implementation code."
    if kind == "configuration":
        return "Tooling and editor configuration."
    return f"Top-level workspace area for `{area_name}`."


def detect_primary_stack(package_metadata, file_inventory):
    package_files = set(package_metadata.get("files", []))
    if {"pyproject.toml", "requirements.txt", "Pipfile"} & package_files:
        return "Python"
    if "package.json" in package_files:
        return "JavaScript/TypeScript"
    if "Cargo.toml" in package_files:
        return "Rust"
    if "go.mod" in package_files:
        return "Go"

    extensions = {item["extension"] for item in file_inventory}
    if ".py" in extensions:
        return "Python"
    if {".js", ".ts", ".tsx", ".jsx"} & extensions:
        return "JavaScript/TypeScript"
    if ".rs" in extensions:
        return "Rust"
    if ".go" in extensions:
        return "Go"
    return "Mixed-language"


def infer_architecture_style(area_counts, source_files):
    area_names = set(area_counts)
    if area_names & SOURCE_DIR_HINTS:
        return "package-oriented"
    if all("/" not in path for path in source_files) and source_files:
        return "flat-root-layout"
    if source_files:
        return "mixed-layout"
    return "undetermined"


def build_architecture_overview(primary_stack, architecture_style, package_metadata, areas):
    style_phrases = {
        "package-oriented": "a package-oriented layout",
        "flat-root-layout": "a flat root-level layout",
        "mixed-layout": "a mixed layout",
        "undetermined": "an undetermined layout",
    }
    generated_areas = [area for area in areas if area["kind"] == "generated"]
    overview = f"{primary_stack} project with {style_phrases.get(architecture_style, 'a mixed layout')}."
    if any(area["path"] == "[root]" for area in areas):
        overview += " Core source, docs, tests, and project metadata are organized from the repository root."
    if "pyproject.toml" in package_metadata.get("files", []):
        overview += " Packaging and CLI entry points are configured in `pyproject.toml`."
    if generated_areas:
        overview += " Generated artifacts are kept separate from the main source areas."
    return overview


def build_project_structure(root, file_inventory, package_metadata):
    file_paths = [item["path"] for item in file_inventory]
    area_members = {}
    for path in file_paths:
        area_name = path.split("/", 1)[0] if "/" in path else "[root]"
        area_members.setdefault(area_name, []).append(path)

    area_counts = {name: len(paths) for name, paths in area_members.items()}
    sorted_areas = sorted(area_members, key=lambda name: (name != "[root]", name.lower()))
    areas = []
    for area_name in sorted_areas[:20]:
        member_paths = sorted(area_members[area_name])
        kind = infer_area_kind(area_name, member_paths)
        areas.append({
            "path": area_name,
            "kind": kind,
            "fileCount": len(member_paths),
            "purpose": infer_area_purpose(area_name, kind),
            "examples": member_paths[:5],
        })

    docs = [path for path in file_paths if path.lower().endswith(".md")][:10]
    tests = [path for path in file_paths if is_test_path(path)][:10]
    source_files = [
        item["path"]
        for item in file_inventory
        if item["extension"] in SOURCE_EXTENSIONS and not is_test_path(item["path"])
    ]

    components = []
    for path in sorted(source_files)[:12]:
        components.append({
            "path": path,
            "kind": "source",
            "role": infer_component_role(path),
        })

    for path in sorted(
        item["path"] for item in file_inventory if item["path"] in {"pyproject.toml", "package.json", "Cargo.toml", "go.mod"}
    )[:4]:
        components.append({
            "path": path,
            "kind": "metadata",
            "role": infer_component_role(path),
        })

    entry_points = []
    for script in read_project_scripts(root, package_metadata):
        module_name = script["target"].split(":", 1)[0]
        entry_points.append({
            "name": script["name"],
            "target": script["target"],
            "path": resolve_module_source_path(module_name, file_paths),
            "kind": "cli",
        })

    primary_stack = detect_primary_stack(package_metadata, file_inventory)
    architecture_style = infer_architecture_style(area_counts, source_files)
    overview = build_architecture_overview(primary_stack, architecture_style, package_metadata, areas)

    return {
        "overview": overview,
        "architectureStyle": architecture_style,
        "primaryStack": primary_stack,
        "entryPoints": entry_points,
        "areas": areas,
        "components": components,
        "documentation": docs,
        "tests": tests,
    }


def build_manifest(root, scan, cfg: Config, refresh_reason="scan"):
    package_metadata = find_package_metadata(root)
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
        "package": package_metadata,
        "projectStructure": build_project_structure(root, scan["fileInventory"], package_metadata),
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
    structure = manifest.get("projectStructure", {})
    entry_points = structure.get("entryPoints", [])
    areas = structure.get("areas", [])
    components = structure.get("components", [])

    entry_point_lines = [
        f"- Entry point: {format_code_span(item['name'])} -> {format_code_span(item['target'])}"
        + (f" via {format_code_span(item['path'])}" if item.get("path") else "")
        for item in entry_points[:10]
    ] or ["- Entry points: none detected."]

    area_lines = [
        f"- Area: {format_code_span(area['path'])} ({area['fileCount']} files, {area['kind']}) - {area['purpose']}"
        for area in areas[:8]
    ] or ["- Major areas: none detected."]

    component_lines = [
        f"- Component: {format_code_span(component['path'])} - {component['role']}"
        for component in components[:8]
    ] or ["- Components: none detected."]

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
        f"- Refresh with {format_code_span('python workspace_scanner.py --root .')} or {format_code_span('intelscan --root .')} after significant edits or git branch changes.",
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
        "## Project Structure",
        f"- Architecture summary: {structure.get('overview', 'No structure summary detected.')}",
        f"- Architecture style: {format_code_span(structure.get('architectureStyle'))}",
        f"- Primary stack: {format_code_span(structure.get('primaryStack'))}",
        *entry_point_lines,
        *area_lines,
        *component_lines,
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
        "python workspace_scanner.py --root .",
        "intelscan --root .",
        "```",
        "",
        "Run in watch mode while editing:",
        "",
        "```bash",
        "python workspace_scanner.py --root . --watch",
        "intelscan --root . --watch",
        "```",
        "",
        "Run an agent command with automatic refresh:",
        "",
        "```bash",
        'python agent_coordinator.py --root . --agent-cmd "python your_agent_task.py"',
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
