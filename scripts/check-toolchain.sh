#!/usr/bin/env bash
set -euo pipefail

required_node_major=22
required_python_major=3
required_python_minor=12

venv_python="${PWD}/.venv/bin/python"
if [[ -x "${venv_python}" ]]; then
  python_cmd="${venv_python}"
else
  python_cmd="python3"
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node is not installed"
  exit 1
fi
if ! command -v "${python_cmd}" >/dev/null 2>&1; then
  echo "python is not installed"
  exit 1
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
py_version="$(${python_cmd} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

if [[ "${node_major}" != "${required_node_major}" ]]; then
  echo "Node major version mismatch: expected ${required_node_major}.x, got $(node -v)"
  echo "Run: nvm use"
  exit 1
fi

if [[ "${py_version}" != "${required_python_major}.${required_python_minor}" ]]; then
  echo "Python version mismatch: expected ${required_python_major}.${required_python_minor}.x, got $(${python_cmd} --version)"
  exit 1
fi

echo "Toolchain OK: node $(node -v), python $(${python_cmd} --version | awk '{print $2}')"
