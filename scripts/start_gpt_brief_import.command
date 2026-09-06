#!/bin/zsh
set -eu
PROJECT_DIR="${0:A:h:h}"
cd "$PROJECT_DIR"
exec /usr/bin/python3 scripts/serve_gpt_brief_import.py
