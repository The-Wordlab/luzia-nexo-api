#!/usr/bin/env python3
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FILES = [ROOT / "README.md", *sorted(DOCS.glob("*.md"))]
FENCE_RE = re.compile(r"```mermaid\n([\s\S]*?)```", re.MULTILINE)


def extract_blocks(path: Path):
    text = path.read_text(encoding="utf-8")
    return [m.group(1).strip() for m in FENCE_RE.finditer(text) if m.group(1).strip()]


def validate_block(block: str, label: str) -> str | None:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        in_file = tmp / "diagram.mmd"
        out_file = tmp / "diagram.svg"
        in_file.write_text(block, encoding="utf-8")

        cmd = [
            "npx",
            "--yes",
            "@mermaid-js/mermaid-cli@10.9.1",
            "-p",
            str(ROOT / "scripts" / "puppeteer-config.json"),
            "-i",
            str(in_file),
            "-o",
            str(out_file),
        ]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            return f"{label}\\n{proc.stderr.strip() or proc.stdout.strip()}"
    return None


def main() -> int:
    failures: list[str] = []
    total = 0
    for file_path in FILES:
        blocks = extract_blocks(file_path)
        for idx, block in enumerate(blocks, start=1):
            total += 1
            err = validate_block(block, f"{file_path.relative_to(ROOT)} [block {idx}]")
            if err:
                failures.append(err)

    if failures:
        print("Mermaid validation failed:\n", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}\n", file=sys.stderr)
        return 1

    print(f"Mermaid validation passed ({total} blocks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
