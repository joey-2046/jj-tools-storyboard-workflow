#!/usr/bin/env python3
"""Safe structural checks for a JJ Tools storyboard project.

This script never reads .env files, imports the application, or calls a model.
It can optionally run unit tests and probe local read-only HTTP endpoints.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple


REQUIRED_FILES = (
    "server.py",
    "main.py",
    "web/index.html",
    "requirements.txt",
    "电影感光效提示词知识库规则文档.md",
    "ai视频影视视听语言知识库规则文档.md",
)

REQUIRED_SERVER_FUNCTIONS = {
    "split_into_episodes",
    "resolve_episode_text",
    "process_episode_attempt",
    "process_job",
    "process_worker",
    "call_deepseek",
    "validate_stage2_segments",
    "build_seedance_zip_bytes",
    "content_disposition",
}

REQUIRED_ROUTES = {
    "/",
    "/api/health",
    "/api/models",
    "/api/upload",
    "/api/process",
    "/api/result/{episode_id}",
    "/api/download",
    "/api/results",
    "/api/history",
    "/api/download-all",
    "/api/clear",
}

REQUIRED_FRONTEND_MARKERS = (
    "const API_BASE",
    "currentSessionId",
    "currentJobId",
    "function loadModels",
    "function uploadFile",
    "function runPipeline",
    "function handleSSEEvent",
    "function fetchResult",
    "function downloadAll",
)

REQUIRED_REQUIREMENTS = {
    "python-docx",
    "openai",
    "python-dotenv",
    "fastapi",
    "uvicorn",
    "python-multipart",
    "httpx",
}


class Reporter:
    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def ok(self, message: str) -> None:
        print("[OK] " + message)

    def warn(self, message: str) -> None:
        self.warnings += 1
        print("[WARN] " + message)

    def error(self, message: str) -> None:
        self.errors += 1
        print("[ERROR] " + message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def collect_function_names(tree: ast.AST) -> Set[str]:
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def collect_fastapi_routes(tree: ast.AST) -> Set[str]:
    routes: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
            ):
                continue
            route_arg = decorator.args[0]
            if isinstance(route_arg, ast.Constant) and isinstance(route_arg.value, str):
                routes.add(route_arg.value)
    return routes


def normalized_requirements(lines: Iterable[str]) -> Set[str]:
    names = set()
    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        name = line
        for delimiter in ("==", ">=", "<=", "~=", "!=", ">", "<", "["):
            name = name.split(delimiter, 1)[0]
        names.add(name.strip().lower())
    return names


def check_structure(root: Path, report: Reporter) -> None:
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        report.error("Missing required files: " + ", ".join(missing))
        return
    report.ok("Required project files are present")

    trees = {}
    for relative in ("server.py", "main.py"):
        path = root / relative
        try:
            source = read_text(path)
            compile(source, str(path), "exec")
            trees[relative] = ast.parse(source, filename=str(path))
            report.ok(relative + " parses and compiles")
        except (OSError, SyntaxError, UnicodeError) as exc:
            report.error(relative + " failed syntax check: " + str(exc))

    server_tree = trees.get("server.py")
    if server_tree is not None:
        functions = collect_function_names(server_tree)
        missing_functions = sorted(REQUIRED_SERVER_FUNCTIONS - functions)
        if missing_functions:
            report.error("Missing server workflow functions: " + ", ".join(missing_functions))
        else:
            report.ok("Core server workflow functions are present")

        routes = collect_fastapi_routes(server_tree)
        missing_routes = sorted(REQUIRED_ROUTES - routes)
        if missing_routes:
            report.error("Missing required API routes: " + ", ".join(missing_routes))
        else:
            report.ok("Core API routes are present")
        if "/api/feishu/events" not in routes:
            report.warn("Optional Feishu webhook route is absent")

    try:
        frontend = read_text(root / "web/index.html")
        missing_markers = [m for m in REQUIRED_FRONTEND_MARKERS if m not in frontend]
        if missing_markers:
            report.error("Missing frontend workflow markers: " + ", ".join(missing_markers))
        else:
            report.ok("Core frontend workflow markers are present")
    except (OSError, UnicodeError) as exc:
        report.error("Could not read web/index.html: " + str(exc))

    try:
        requirements = normalized_requirements(read_text(root / "requirements.txt").splitlines())
        missing_requirements = sorted(REQUIRED_REQUIREMENTS - requirements)
        if missing_requirements:
            report.error("Missing runtime requirements: " + ", ".join(missing_requirements))
        else:
            report.ok("Expected runtime requirements are declared")
    except (OSError, UnicodeError) as exc:
        report.error("Could not read requirements.txt: " + str(exc))

    if not (root / "tests").is_dir():
        report.warn("No tests directory found")
    if not (root / "AGENTS.md").is_file():
        report.warn("No project-local AGENTS.md found")


def run_tests(root: Path, report: Reporter) -> None:
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        report.error("Cannot run tests: tests directory is missing")
        return
    command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    completed = subprocess.run(command, cwd=str(root), check=False)
    if completed.returncode == 0:
        report.ok("Unit tests passed")
    else:
        report.error("Unit tests failed with exit code " + str(completed.returncode))


def fetch_json(url: str) -> Tuple[int, object]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body)


def check_health(base_url: str, report: Reporter) -> None:
    base = base_url.rstrip("/")
    for path in ("/api/health", "/api/models"):
        url = base + path
        try:
            status, payload = fetch_json(url)
        except (urllib.error.URLError, json.JSONDecodeError, UnicodeError) as exc:
            report.error("Read-only endpoint failed " + url + ": " + str(exc))
            continue
        if status != 200:
            report.error(url + " returned HTTP " + str(status))
            continue
        if not isinstance(payload, dict):
            report.error(url + " did not return a JSON object")
            continue
        report.ok(url + " returned HTTP 200")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="JJ Tools project root (default: current directory)")
    parser.add_argument("--with-tests", action="store_true", help="Run unittest discovery after structural checks")
    parser.add_argument(
        "--health-url",
        help="Probe read-only /api/health and /api/models on an already running local service",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] = ()) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(args.root).expanduser().resolve()
    report = Reporter()

    print("JJ Tools project check: " + str(root))
    check_structure(root, report)
    if args.with_tests:
        run_tests(root, report)
    if args.health_url:
        check_health(args.health_url, report)

    print(
        "Summary: errors={0}, warnings={1}".format(
            report.errors,
            report.warnings,
        )
    )
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
