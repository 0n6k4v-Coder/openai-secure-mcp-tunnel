from __future__ import annotations

import json

_FORMATTER_HELPER = r"""
import json
import os
import pathlib
import subprocess

_FORMATTER_ROOT = os.path.realpath("/workspace/project")
_PRETTIER_EXTENSIONS = {
    ".astro", ".cjs", ".css", ".graphql", ".gql", ".html", ".json",
    ".json5", ".jsonc", ".js", ".jsx", ".less", ".md", ".mdx",
    ".mjs", ".mts", ".scss", ".ts", ".tsx", ".vue", ".yaml",
    ".yml", ".xml", ".svg",
}


def _format_text(relative_path, content):
    suffix = pathlib.PurePosixPath(relative_path).suffix.lower()
    if suffix == ".py":
        argv = ["ruff", "format", "--stdin-filename", relative_path, "-"]
        formatter = "Ruff"
    elif suffix in _PRETTIER_EXTENSIONS:
        argv = ["prettier", "--stdin-filepath", relative_path]
        formatter = "Prettier"
    else:
        return content, None

    try:
        result = subprocess.run(
            argv,
            cwd=_FORMATTER_ROOT,
            input=content,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError:
        return content, f"skipped: {formatter} is not installed in the target sandbox"
    except subprocess.TimeoutExpired:
        return content, f"skipped: {formatter} timed out"
    except OSError as exc:
        return content, f"skipped: {formatter} could not be started ({type(exc).__name__})"

    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        reason = detail[0][:180] if detail else f"exit code {result.returncode}"
        return content, f"skipped: {formatter} could not format the content ({reason})"

    formatted = result.stdout
    if len(formatted.encode("utf-8")) > 1_000_000:
        return content, f"skipped: {formatter} output exceeded the 1,000,000-byte limit"
    return formatted, f"formatted with {formatter}"
"""

_FORMAT_RUNNER = (
    _FORMATTER_HELPER
    + "\nimport sys\n"
    + "relative_path = sys.argv[1]\n"
    + "content = sys.stdin.read()\n"
    + "formatted, status = _format_text(relative_path, content)\n"
    + 'sys.stdout.write(json.dumps({"content": formatted, "status": status}))\n'
)


def execute_sandbox_argv(*args, **kwargs):
    """Import the sandbox client lazily so file tools stay lightweight to import."""
    from ..infrastructure.openshell.sandbox import execute_sandbox_argv as execute

    return execute(*args, **kwargs)


def format_text_in_sandbox(
    sandbox_name: str,
    relative_path: str,
    content: str,
) -> tuple[str, str | None]:
    """Format supported text in the selected sandbox, preserving content on failure."""
    if (
        not isinstance(relative_path, str)
        or not relative_path.strip()
        or "\x00" in relative_path
        or relative_path.startswith("/")
        or any(part == ".." for part in relative_path.split("/"))
    ):
        raise ValueError("Formatting requires a relative workspace path.")
    result = execute_sandbox_argv(
        sandbox_name,
        ["python", "-c", _FORMAT_RUNNER, relative_path],
        stdin=content,
        timeout_seconds=25,
    )
    if int(result.get("return_code", 1)) != 0:
        stderr = str(result.get("stderr", "")).strip().splitlines()
        detail = stderr[0][:180] if stderr else "formatter runner failed"
        return content, f"skipped: formatting runner failed ({detail})"
    try:
        payload = json.loads(str(result.get("stdout", "")))
    except json.JSONDecodeError:
        return content, "skipped: formatting runner returned invalid output"
    if not isinstance(payload, dict) or not isinstance(payload.get("content"), str):
        return content, "skipped: formatting runner returned an invalid result"
    status = payload.get("status")
    if status is not None and not isinstance(status, str):
        return content, "skipped: formatting runner returned an invalid status"
    return payload["content"], status


__all__ = ["_FORMATTER_HELPER", "format_text_in_sandbox"]
