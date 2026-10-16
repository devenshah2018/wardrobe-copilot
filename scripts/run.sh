#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
    echo 'Create the Python environment first; see README.md.' >&2
    exit 1
fi
if [ ! -f frontend/dist/index.html ]; then
    echo 'Build the frontend first: cd frontend && npm ci && npm run build' >&2
    exit 1
fi
exec .venv/bin/python -m uvicorn wardrobe.app:app --app-dir backend --host 127.0.0.1 --port 8000
