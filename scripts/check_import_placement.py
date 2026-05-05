#!/usr/bin/env python3
"""Diff-aware import placement guard for Python and JS/TS files.

This hook checks only newly added staged lines so repos with legacy local
imports can adopt the rule without a flag day cleanup.

Escape hatches:
- Python: `# noqa: PLC0415`
- Any language: `# import-placement: allow` or `// import-placement: allow`
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ALLOW_MARKERS = ("noqa: PLC0415", "import-placement: allow")
JS_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx"}
SKIP_PARTS = {
    ".git",
    ".next",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "playwright-report",
    "site",
    "test-results",
}

DIRECTIVE_RE = re.compile(r"""^["']use (?:client|server|strict)["'];?$""")
STATIC_IMPORT_RE = re.compile(r"^import(?:\s+type)?\b(?!\s*\()")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _get_added_lines(path: str) -> set[int]:
    diff = _git("diff", "--cached", "--unified=0", "--", path)
    if diff.returncode not in (0, 1):
        raise RuntimeError(diff.stderr.strip() or f"git diff failed for {path}")

    added: set[int] = set()
    for line in diff.stdout.splitlines():
        if not line.startswith("@@ "):
            continue
        match = re.search(r"\+(\d+)(?:,(\d+))?", line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        if count <= 0:
            continue
        added.update(range(start, start + count))
    return added


def _get_staged_source(path: str) -> str | None:
    show = _git("show", f":{path}")
    if show.returncode != 0:
        return None
    return show.stdout


def _has_allow_marker(line: str) -> bool:
    return any(marker in line for marker in ALLOW_MARKERS)


def _is_docstring_stmt(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_type_checking_test(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Name)
        and node.id == "TYPE_CHECKING"
        or isinstance(node, ast.Attribute)
        and node.attr == "TYPE_CHECKING"
    )


def _is_type_checking_if(node: ast.AST) -> bool:
    return isinstance(node, ast.If) and _is_type_checking_test(node.test)


def _python_violations(path: str, source: str, added_lines: set[int]) -> list[str]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        if exc.lineno is None or exc.lineno not in added_lines:
            return []
        return [f"{path}:{exc.lineno}: unable to parse staged Python source"]

    source_lines = source.splitlines()
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    allowed_preamble_nodes: set[ast.AST] = set()
    body = tree.body
    index = 1 if body and _is_docstring_stmt(body[0]) else 0
    while index < len(body):
        stmt = body[index]
        if isinstance(stmt, (ast.Import, ast.ImportFrom)) or _is_type_checking_if(stmt):
            allowed_preamble_nodes.add(stmt)
            index += 1
            continue
        break

    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if node.lineno not in added_lines:
            continue
        line = source_lines[node.lineno - 1] if node.lineno - 1 < len(source_lines) else ""
        if _has_allow_marker(line):
            continue

        parent = parents.get(node)
        if isinstance(parent, ast.Module):
            if node in allowed_preamble_nodes:
                continue
            violations.append(
                f"{path}:{node.lineno}: import should stay in the top-level import block "
                f"(move it to the top of the file or annotate with '# noqa: PLC0415')"
            )
            continue

        if (
            _is_type_checking_if(parent)
            and parents.get(parent) is tree
            and parent in allowed_preamble_nodes
        ):
            continue

        violations.append(
            f"{path}:{node.lineno}: nested import is discouraged "
            f"(move it to the top of the file or annotate with '# noqa: PLC0415')"
        )

    return violations


def _starts_block_comment(stripped: str) -> bool:
    return stripped.startswith("/*")


def _is_static_import_start(stripped: str) -> bool:
    return bool(STATIC_IMPORT_RE.match(stripped))


def _is_import_block_end(stripped: str) -> bool:
    return stripped.endswith(";") or bool(re.search(r"""["']\s*;?$""", stripped))


def _line_allows_js_import_preamble(lines: list[str], target_lineno: int) -> bool:
    in_block_comment = False
    in_import_block = False

    for raw_line in lines[: target_lineno - 1]:
        stripped = raw_line.strip()

        if in_block_comment:
            if "*/" not in stripped:
                continue
            stripped = stripped.split("*/", 1)[1].strip()
            in_block_comment = False
            if not stripped:
                continue

        if not stripped:
            continue

        if _starts_block_comment(stripped):
            if "*/" not in stripped:
                in_block_comment = True
                continue
            stripped = stripped.split("*/", 1)[1].strip()
            if not stripped:
                continue

        if stripped.startswith("//"):
            continue

        if in_import_block:
            if _is_import_block_end(stripped):
                in_import_block = False
            continue

        if DIRECTIVE_RE.match(stripped):
            continue

        if _is_static_import_start(stripped):
            if not _is_import_block_end(stripped):
                in_import_block = True
            continue

        return False

    return True


def _js_ts_violations(path: str, source: str, added_lines: set[int]) -> list[str]:
    source_lines = source.splitlines()
    violations: list[str] = []

    for lineno in sorted(added_lines):
        if lineno - 1 >= len(source_lines):
            continue
        line = source_lines[lineno - 1]
        stripped = line.strip()
        if not stripped or _has_allow_marker(line):
            continue

        if _is_static_import_start(stripped) and not _line_allows_js_import_preamble(
            source_lines, lineno
        ):
            violations.append(
                f"{path}:{lineno}: import should stay in the top-of-file import block "
                f"(move it upward or annotate with '// import-placement: allow')"
            )

    return violations


def _should_skip(path: str) -> bool:
    parts = Path(path).parts
    return any(part in SKIP_PARTS for part in parts)


def main(argv: list[str]) -> int:
    violations: list[str] = []
    for path in argv:
        if _should_skip(path):
            continue

        added_lines = _get_added_lines(path)
        if not added_lines:
            continue

        source = _get_staged_source(path)
        if source is None:
            continue

        suffix = Path(path).suffix.lower()
        if suffix == ".py":
            violations.extend(_python_violations(path, source, added_lines))
        elif suffix in JS_EXTENSIONS:
            violations.extend(_js_ts_violations(path, source, added_lines))

    if not violations:
        return 0

    print("\n".join(violations), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
