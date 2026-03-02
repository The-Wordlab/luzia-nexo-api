#!/usr/bin/env bash
set -euo pipefail

required_node_major=22
required_python_major=3
required_python_minor=12

if ! command -v node >/dev/null 2>&1; then
  echo "node is not installed"
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed"
  exit 1
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
py_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

if [[ "${node_major}" != "${required_node_major}" ]]; then
  echo "Node major version mismatch: expected ${required_node_major}.x, got $(node -v)"
  echo "Run: nvm use"
  exit 1
fi

if [[ "${py_version}" != "${required_python_major}.${required_python_minor}" ]]; then
  echo "Python version mismatch: expected ${required_python_major}.${required_python_minor}.x, got $(python3 --version)"
  exit 1
fi

echo "Toolchain OK: node $(node -v), python $(python3 --version | awk '{print $2}')"
