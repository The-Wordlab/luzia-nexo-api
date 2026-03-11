#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install pytest

# Install all Python example dependencies so make test-* works on a fresh clone.
while IFS= read -r req; do
  python -m pip install -r "${req}"
done < <(find "${REPO_ROOT}/examples" -name requirements.txt | sort)

python -m pip install -r "${REPO_ROOT}/docs/requirements-docs.txt"

echo "Development environment ready."
echo "Run: source .venv/bin/activate"
